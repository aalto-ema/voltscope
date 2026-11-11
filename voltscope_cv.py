"""CV background and peak-current analysis, without a time/scan-rate requirement.

Missing samples are explicitly recorded, acquisition order is retained, and
minor E jitter/duplicate potentials do not invalidate a sweep. Detection-only
filtering never replaces the stored measured or baseline-corrected current.
"""
import copy
import math
import numpy as np
from scipy.signal import find_peaks, peak_widths
from scipy.ndimage import gaussian_filter1d

MODELS = ['Robust linear background', 'Robust quadratic background',
          'Constant background', 'No subtraction']


def _number(value, label, default=None):
    if value is None or (isinstance(value,str) and not value.strip()):
        if default is not None:
            return default
        raise ValueError(f'Enter {label}.')
    from voltscope_analysis import finite
    return finite(value,label)


def finite_pair(x,y):
    return (isinstance(x,(int,float,np.number)) and not isinstance(x,(bool,np.bool_)) and
            isinstance(y,(int,float,np.number)) and not isinstance(y,(bool,np.bool_)) and
            math.isfinite(float(x)) and math.isfinite(float(y)))


def sweep_ranges(x, tolerance=None):
    """Directional-change segmentation with hysteresis, in acquisition order.

    A reversal is confirmed only after a move away from the running extremum
    by tolerance. Vertex points are shared by adjoining sweeps. No sorting or
    equal-length assumption is made.
    """
    x=np.asarray(x,dtype=float)
    if len(x)<2 or not np.all(np.isfinite(x)):
        return [],0.
    span=float(np.ptp(x))
    if not span:
        return [(0,len(x)-1,0)],0.
    steps=np.abs(np.diff(x)); steps=steps[steps>span*1e-10]
    step=float(np.median(steps)) if len(steps) else 0.
    auto=min(span*.15,max(span*.01,step*3))
    tol=_number(tolerance,'reversal tolerance',auto)
    if tol<0:
        raise ValueError('Reversal tolerance cannot be negative.')
    tol=max(tol,span*1e-12)
    result=[];start=0;direction=0;extreme=0
    for i in range(1,len(x)):
        if direction==0:
            if abs(x[i]-x[start])>=tol:
                direction=1 if x[i]>x[start] else -1
                extreme=i
        elif direction>0:
            if x[i]>=x[extreme]:extreme=i
            elif x[extreme]-x[i]>=tol:
                result.append((start,extreme,1));start=extreme;direction=-1;extreme=i
        else:
            if x[i]<=x[extreme]:extreme=i
            elif x[i]-x[extreme]>=tol:
                result.append((start,extreme,-1));start=extreme;direction=1;extreme=i
    result.append((start,len(x)-1,direction))
    return result,tol


def noise_sigma(y):
    if len(y)<3:return 0.
    differences=np.diff(y)
    return float(np.median(np.abs(differences-np.median(differences)))/(.6744897501960817*math.sqrt(2)))


def robust_polynomial(x,y,degree,weights=None):
    """Centered/scaled polynomial least squares with Huber IRLS (no SciPy optimizer)."""
    x=np.asarray(x,dtype=float);y=np.asarray(y,dtype=float)
    center=float((min(x)+max(x))/2);scale=float(np.ptp(x)/2)
    if len(x)<degree+2 or len(np.unique(x))<degree+1 or (degree and not scale):
        raise ValueError('Not enough distinct background potentials; widen the background windows.')
    scale=scale or 1.
    design=np.polynomial.polynomial.polyvander((x-center)/scale,degree)
    offset=float(np.median(y));yscale=max(float(np.ptp(y)),abs(offset)*1e-12,1e-300)
    target=(y-offset)/yscale
    base=np.ones(len(x)) if weights is None else np.asarray(weights,dtype=float)
    weight=base.copy();coef=np.zeros(degree+1)
    for _ in range(40):
        old=coef.copy()
        coef,_,rank,_=np.linalg.lstsq(design*np.sqrt(weight[:,None]),target*np.sqrt(weight),rcond=None)
        if rank<degree+1:raise ValueError('Background fit is singular; choose separated background windows.')
        residual=target-design@coef
        sigma=float(np.median(np.abs(residual-np.median(residual)))/.6744897501960817)
        if sigma<=1e-14:break
        scaled=np.abs(residual)/(1.345*sigma)
        weight=base/np.maximum(1.,scaled)
        if np.max(np.abs(coef-old))<1e-11:break
    def evaluate(points):
        return offset+yscale*np.polynomial.polynomial.polyval((np.asarray(points)-center)/scale,coef)
    residual=y-evaluate(x)
    info={'coefficients_normalized':coef.tolist(),'x_center':center,'x_scale':scale,
          'y_offset':offset,'y_scale':yscale,'degree':degree,
          'background_residual_mad':float(np.median(np.abs(residual-np.median(residual)))/.6744897501960817)}
    return evaluate,info


def background(x,y,parameters):
    model=parameters.get('cv_model',MODELS[0])
    if model not in MODELS:raise ValueError('Unknown CV background model.')
    lo,hi=float(min(x)),float(max(x));span=hi-lo
    if not span:raise ValueError('This sweep has no potential span.')
    if model=='No subtraction':
        return np.zeros(len(y)),lambda q:np.zeros_like(np.asarray(q,dtype=float)),{
            'model':model,'windows':[],'background_points':0},[lo,hi]
    fraction=_number(parameters.get('cv_fraction'),'background fraction',.15)
    if not .02<=fraction<=.4:
        raise ValueError('Background fraction must be between 0.02 and 0.4.')
    if parameters.get('cv_manual',False):
        windows=[_number(parameters.get(key),'all four background-window bounds')
                 for key in ['cv_left_min','cv_left_max','cv_right_min','cv_right_max']]
        a,b,c,d=windows
        if not a<b<c<d:
            raise ValueError('Background windows must be ordered: left min < left max < right min < right max.')
    else:
        ordered=np.sort(x)
        windows=[lo,max(lo+fraction*span,float(ordered[1])),min(hi-fraction*span,float(ordered[-2])),hi]
        a,b,c,d=windows
    if not a<b<c<d:raise ValueError('Background windows overlap or lack distinct potentials; choose separated manual windows.')
    left=(x>=a)&(x<=b);right=(x>=c)&(x<=d)
    if sum(left)<2 or sum(right)<2:
        raise ValueError('Each background window needs at least two usable samples. Widen it or choose another sweep.')
    mask=left|right
    # Balance windows and repeated potentials so denser sampling does not
    # silently determine the baseline. Duplicate measured rows remain in output.
    weights=np.zeros(len(x))
    for side in [left,right]:
        _,inverse,counts=np.unique(x[side],return_inverse=True,return_counts=True)
        weights[side]=1/counts[inverse]
        weights[side]/=sum(weights[side])
    degree={'Robust linear background':1,'Robust quadratic background':2,'Constant background':0}[model]
    evaluate,info=robust_polynomial(x[mask],y[mask],degree,weights[mask])
    info.update(model=model,windows=windows,background_points=int(sum(mask)),
                left_points=int(sum(left)),right_points=int(sum(right)))
    return evaluate(x),evaluate,info,[b,c]


def detection_signal(corrected,parameters):
    y=np.asarray(corrected,dtype=float).copy();noise=noise_sigma(y)
    floor=max(float(np.max(np.abs(y)))*1e-12,1e-300)
    spikes=[]
    if parameters.get('cv_despike',True):
        for i in range(1,len(y)-1):
            # Only very isolated points: broad/narrow multi-sample peaks are
            # not removed merely for being large. This is detection-only.
            neighbor=max(abs(corrected[i-1]),abs(corrected[i+1]),3*noise,floor)
            if abs(corrected[i])>5*neighbor and abs(corrected[i]-(corrected[i-1]+corrected[i+1])/2)>8*max(noise,floor):
                spikes.append(i)
                y[i]=(corrected[i-1]+corrected[i+1])/2
    requested=_number(parameters.get('cv_smooth'),'detection window',9)
    if requested<1 or int(requested)!=requested or int(requested)%2!=1:
        raise ValueError('Detection window must be a positive odd number of points (1 disables smoothing).')
    window=min(int(requested),len(y) if len(y)%2 else len(y)-1)
    if window>=3:y=gaussian_filter1d(y,sigma=(window-1)/6,radius=(window-1)//2,mode='nearest')
    return y,noise,spikes,window


def fit_peak(x,corrected,detected,k,width,sign,spikes,method):
    half=min(5,max(1,int(width/4)))
    keep=np.arange(max(0,k-half),min(len(x),k+half+1))
    keep=keep[~np.isin(keep,spikes)]
    if len(keep)<3 or len(np.unique(x[keep]))<3:
        keep=np.arange(max(0,k-4),min(len(x),k+5))
        keep=keep[~np.isin(keep,spikes)]
    ep=float(x[k]);ip=float(detected[k]);quality=[];used='smoothed sample'
    if method=='Raw sampled':
        return ep,float(corrected[k]),'raw sampled',[],[int(k)]
    if method=='Local quadratic fit' and len(keep)>=4 and len(np.unique(x[keep]))>=3:
        try:
            evaluate,info=robust_polynomial(x[keep],corrected[keep],2)
            coef=info['coefficients_normalized']
            if sign*coef[2]<0:
                vertex=-coef[1]/(2*coef[2])*info['x_scale']+info['x_center']
                if min(x[keep])<=vertex<=max(x[keep]):
                    ep=float(vertex);ip=float(evaluate(vertex));used='local quadratic fit'
                else:quality.append('Fit apex outside local support; smoothed sample used')
            else:quality.append('Unresolved local curvature; smoothed sample used')
        except ValueError:quality.append('Local fit unavailable; smoothed sample used')
    elif method=='Local quadratic fit':
        quality.append('Too few local samples for a stable fit; smoothed sample used')
    if width<3:quality.append('Under-resolved peak: fewer than 3 samples across half prominence')
    return ep,ip,used,quality,keep.tolist()


def analyze_cv(curves,xcol,ycol,selection,parameters):
    from voltscope_analysis import AnalysisResult, fingerprint, current_unit, potential_factor, derived
    result=AnalysisResult('CV baseline & peaks',copy.deepcopy(parameters),[])
    result.parameters.update(x_column=xcol,y_column=ycol,selection=vars(selection).copy(),cv_algorithm_version='2.0')
    result._hash_cache={};failures=[]
    # Resolve every numerical default in the report rather than leaving them implicit.
    defaults={'cv_model':MODELS[0],'cv_fraction':.15,'cv_manual':False,'cv_polarity':'Both',
              'cv_reporting':'Dominant peak per polarity','cv_method':'Local quadratic fit','cv_smooth':9,'cv_despike':True,'cv_noise_factor':5.}
    for key,value in defaults.items():result.parameters.setdefault(key,value)
    polarity=parameters.get('cv_polarity','Both');method=parameters.get('cv_method','Local quadratic fit')
    if polarity not in ('Both','Positive','Negative'):raise ValueError('Unknown peak polarity.')
    if method not in ('Local quadratic fit','Smoothed apex','Raw sampled'):raise ValueError('Unknown peak measurement method.')
    reporting=parameters.get('cv_reporting','Dominant peak per polarity')
    if reporting not in ('Dominant peak per polarity','All supported peaks'):raise ValueError('Unknown peak reporting mode.')
    if not curves:raise ValueError('Select a CV curve first.')
    for curve in curves:
        try:
            if xcol not in curve.columns or ycol not in curve.columns:
                raise ValueError('The chosen potential/current columns are unavailable.')
            xi,yi=curve.columns.index(xcol),curve.columns.index(ycol)
            xu,yu=curve.units[xi],curve.units[yi]
            potential_factor(xu);current_unit(yu)
            end=len(curve.rows)-1 if selection.end is None else selection.end
            if not 0<=selection.start<=end<len(curve.rows):raise ValueError('Row interval is outside this curve.')
            valid=[];excluded=[]
            for i in range(selection.start,end+1):
                row=curve.rows[i]
                if max(xi,yi)<len(row) and finite_pair(row[xi],row[yi]):valid.append(i)
                else:excluded.append(i+1)
            if len(valid)<7:raise ValueError('At least 7 finite potential/current pairs are needed.')
            x=np.asarray([curve.rows[i][xi] for i in valid],dtype=float)
            y=np.asarray([curve.rows[i][yi] for i in valid],dtype=float)
            ranges,tol=sweep_ranges(x,parameters.get('cv_reversal'))
            result._hash_cache[id(curve)]=fingerprint(curve)
            source={'source':curve.source,'curve':curve.name,'sha256':result._hash_cache[id(curve)],
                    'requested_rows_1_based':[selection.start+1,end+1], 'excluded_rows_1_based':excluded,
                    'x_column':xcol,'x_unit':xu,'y_column':ycol,'y_unit':yu,
                    'effective_reversal_tolerance':tol,'sweeps_detected':len(ranges),'sweeps':[],
                    'source_status':curve.metadata.get('STATUS',''),'abort_flag':curve.metadata.get('EXPERIMENTABORTED','')}
            result.inputs.append(source)
            if excluded:result.notes.append(f'{curve.name}: excluded {len(excluded)} missing/nonfinite potential-current pairs; original data retained. Exact source rows are recorded.')
            if source['source_status'] or source['abort_flag']:
                result.notes.append(f'{curve.name}: source status {source["source_status"]}; abort flag {source["abort_flag"]}.')
            for sweep,(a,b,direction) in enumerate(ranges,1):
                if selection.branch is not None and selection.branch!=sweep:continue
                try:
                    take=np.arange(a,b+1)
                    if selection.lower is not None:take=take[x[take]>=_number(selection.lower,'X minimum')]
                    if selection.upper is not None:take=take[x[take]<=_number(selection.upper,'X maximum')]
                    if len(take)<7:raise ValueError('Fewer than 7 usable samples in this sweep/interval.')
                    sx,sy=x[take],y[take];rows=[valid[int(i)] for i in take]
                    base,evaluate,info,search=background(sx,sy,parameters)
                    corrected=sy-base
                    detect,noise,spikes,window=detection_signal(corrected,parameters)
                    left=_number(parameters.get('cv_peak_min'),'peak search minimum',search[0])
                    right=_number(parameters.get('cv_peak_max'),'peak search maximum',search[1])
                    if left>=right:raise ValueError('Peak search minimum must be below its maximum.')
                    noise_factor=_number(parameters.get('cv_noise_factor'),'noise threshold multiplier',5.)
                    if noise_factor<0:raise ValueError('Noise threshold multiplier cannot be negative.')
                    amplitude=float(np.percentile(detect,98)-np.percentile(detect,2))
                    auto=max(noise_factor*noise,.01*amplitude,float(np.max(np.abs(sy)))*1e-12,1e-300)
                    threshold=_number(parameters.get('cv_prominence'),'minimum prominence',auto)
                    if threshold<0:raise ValueError('Peak prominence cannot be negative.')
                    peak_records=[]
                    for sign in ([1,-1] if polarity=='Both' else [1] if polarity=='Positive' else [-1]):
                        peaks,props=find_peaks(sign*detect,prominence=threshold,plateau_size=(1,None))
                        widths=peak_widths(sign*detect,peaks,rel_height=.5)[0] if len(peaks) else []
                        for n,k in enumerate(peaks):
                            if not left<=sx[k]<=right:continue
                            ep,ip,used,flags,fit_rows=fit_peak(sx,corrected,detect,int(k),float(widths[n]),sign,spikes,method)
                            if not left<=ep<=right:
                                ep,ip=float(sx[k]),float(detect[k]);used='smoothed sample';flags.append('Fit apex outside search window')
                            if sign*ip<=0:continue
                            if props['plateau_sizes'][n]>1:flags.append('Flat top: apex potential is not unique')
                            nearest=int(np.argmin(np.abs(sx-ep)))
                            local=np.asarray(fit_rows,dtype=int)
                            if len(local)>1 and any(rows[j+1]-rows[j]>1 for j in range(max(0,int(local.min())-1),min(len(rows)-1,int(local.max())+1))):
                                flags.append('Missing samples near peak; local estimate needs review')
                            if info.get('background_residual_mad',0)>max(abs(ip)*.1,noise*3):
                                flags.append('Background windows have substantial residuals; inspect baseline')
                            if noise>0 and abs(ip)/noise<5:flags.append('Low signal-to-noise ratio')
                            if min(abs(ep-left),abs(right-ep))<.02*(right-left):flags.append('Near search boundary')
                            if len(excluded)>.2*(end-selection.start+1):flags.append('Many missing input samples')
                            if spikes:flags.append(f'{len(spikes)} isolated spike(s) suppressed for detection only')
                            record={'source_curve':curve.name,'source_file':curve.source,'input_sha256':source['sha256'],
                                    'sweep':sweep,'direction':'increasing' if direction>0 else 'decreasing' if direction<0 else 'constant',
                                    'polarity':'positive' if sign>0 else 'negative','source_row':rows[nearest]+1,
                                    'potential':ep,'potential_unit':xu,'current':ip,'current_unit':yu,
                                    'raw_current_at_row':float(sy[nearest]),'baseline_at_peak':float(evaluate(ep)),
                                    'prominence':float(props['prominences'][n]),'snr':abs(ip)/noise if noise>0 else None,
                                    'quality':'; '.join(flags) or 'OK','method':used,
                                    'fit_source_rows':[rows[i]+1 for i in fit_rows]}
                            peak_records.append(record)
                    candidates=copy.deepcopy(peak_records)
                    if reporting=='Dominant peak per polarity':
                        peak_records=[max([p for p in candidates if p['polarity']==pol],key=lambda p:p['prominence'])
                                      for pol in ['positive','negative'] if any(p['polarity']==pol for p in candidates)]
                    if len(candidates)>6:
                        for p in peak_records:p['quality']=('' if p['quality']=='OK' else p['quality']+'; ')+'Many competing peaks; narrow search window or adjust detection'
                        result.notes.append(f'{curve.name}, sweep {sweep}: {len(candidates)} candidate peaks; inspect noisy/complex structure and baseline before accepting a peak.')
                    peak_records.sort(key=lambda p:p['source_row'])
                    info.update(candidate_peaks=candidates,reporting_mode=reporting,effective_detection_window=window,noise_sigma=noise,effective_prominence=threshold,
                                search_window=[left,right],spike_source_rows=[rows[i]+1 for i in spikes],
                                repeated_potentials=len(sx)-len(np.unique(sx)),source_rows_1_based=[i+1 for i in rows],sweep=sweep)
                    source['sweeps'].append(copy.deepcopy(info))
                    additions=[]
                    names=[]
                    for title,unit,array in [('CV baseline',yu,base),('CV corrected',yu,corrected),('CV detection',yu,detect),
                                             ('CV input row','1',np.asarray(rows)+1)]:
                        title=title if title not in curve.columns else title+' '+result.id[:6]
                        additions.append((title,unit,array));names.append(title)
                    out=derived(result,curve,rows,additions,xcol,names[1],f'CV sweep {sweep} '+('↑' if direction>0 else '↓' if direction<0 else '—'))
                    out.metadata.update(CV_ANALYSIS=True,CV_BACKGROUND=info,CV_COLUMNS={'baseline':names[0],'corrected':names[1],
                                        'detection':names[2],'original':ycol},CV_PEAKS=peak_records)
                    result.peaks.extend(peak_records)
                    result.metric(curve,f'Sweep {sweep} peak count',len(peak_records))
                    result.metric(curve,f'Sweep {sweep} noise estimate',noise,yu)
                    for n,p in enumerate(peak_records,1):
                        result.metric(curve,f'Sweep {sweep} peak {n} current',p['current'],yu)
                        result.metric(curve,f'Sweep {sweep} peak {n} potential',p['potential'],xu)
                    if spikes:result.notes.append(f'{curve.name}, sweep {sweep}: {len(spikes)} isolated spike(s) suppressed for detection only. A genuine single-sample feature can be indistinguishable from a spike; disable suppression to inspect it.')
                    if not peak_records:result.notes.append(f'{curve.name}, sweep {sweep}: no supported interior peak above the threshold. Adjust the search/background windows or sensitivity; no boundary peak is invented.')
                except ValueError as exc:
                    failures.append({'source':curve.source,'curve':curve.name,'sweep':sweep,'reason':str(exc)})
            if selection.branch is not None and not 1<=selection.branch<=len(ranges):
                failures.append({'source':curve.source,'curve':curve.name,'reason':f'Sweep {selection.branch} does not exist.'})
        except ValueError as exc:failures.append({'source':curve.source,'curve':curve.name,'reason':str(exc)})
    result.parameters['skipped_inputs_or_sweeps']=failures
    for fail in failures:result.notes.append(f'Skipped {fail["curve"]}'+(f' sweep {fail["sweep"]}' if 'sweep' in fail else '')+': '+fail['reason'])
    if not result.curves:
        raise ValueError('No CV sweep could be analyzed. '+('; '.join(f['reason'] for f in failures[:3]) or 'Check the selected sweep and bounds.'))
    result.notes.append('Peak-current analysis needs no scan rate or time axis. Review the highlighted background windows on each sweep. Baseline-corrected values are unsmoothed; detection-only filtering and local-fit peak estimates are explicitly recorded. No charge is calculated.')
    return result
