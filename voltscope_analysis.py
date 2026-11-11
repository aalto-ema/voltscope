"""Auditable, UI-independent electrochemical transformations and analysis.

Independent implementation; viewPAR was reviewed only as a feature inventory.
All operations return new data. Source Curve objects are never modified.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import uuid
import sys
import scipy

import numpy as np
from scipy.integrate import cumulative_trapezoid
from scipy.signal import savgol_filter, find_peaks
from scipy.stats import linregress, t as student_t

from voltscope_data import Curve, export_csv

VERSION = '2.0'
CURRENT = {'A': 1., 'mA': 1e-3, 'µA': 1e-6, 'uA': 1e-6, 'nA': 1e-9}
TIME = {'s': 1., 'ms': .001, 'min': 60.}


def finite(value, name, positive=False):
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name} must be a number.') from exc
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f'{name} must be finite' + (' and positive.' if positive else '.'))
    return value


def current_unit(unit):
    unit = unit.replace('²', '2').replace('μ', 'µ')
    density = unit.endswith('/cm2')
    base = unit[:-4] if density else unit
    if base not in CURRENT:
        raise ValueError(f'Current unit {unit!r} is unsupported; choose an explicitly labelled current/current-density column.')
    return CURRENT[base], density


def potential_factor(unit):
    if unit == 'V' or unit.startswith(('V vs.', 'V overpotential')):
        return 1.
    if unit == 'mV' or unit.startswith(('mV vs.', 'mV overpotential')):
        return .001
    raise ValueError(f'Expected potential in V or mV, got {unit!r}.')


def values(curve, column, indices):
    if column not in curve.columns:
        raise ValueError(f'{curve.name}: column {column!r} is unavailable.')
    j = curve.columns.index(column)
    result = []
    for i in indices:
        value = curve.rows[i][j]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise ValueError(f'{curve.name}: {column}, row {i + 1} is missing or nonfinite. Choose a valid contiguous interval.')
        result.append(value)
    return np.asarray(result, dtype=float), curve.units[j]


def monotonic(x, name='X'):
    if len(x) < 2 or not (np.all(np.diff(x) > 0) or np.all(np.diff(x) < 0)):
        raise ValueError(f'{name} must be strictly monotonic. Select one branch and exclude repeated coordinates.')


def branches(x, tolerance=0.):
    """Inclusive turning-point ranges; shared extrema are deliberately retained."""
    tolerance = finite(tolerance, 'Turning tolerance')
    if tolerance < 0:
        raise ValueError('Turning tolerance cannot be negative.')
    result, start, direction = [], 0, 0
    for i, delta in enumerate(np.diff(x)):
        new = 1 if delta > tolerance else -1 if delta < -tolerance else 0
        if new and direction and new != direction:
            result.append((start, i, direction))
            start = i
        if new:
            direction = new
    if len(x):
        result.append((start, len(x) - 1, direction))
    return result


@dataclass
class Selection:
    start: int = 0                 # zero-based, inclusive
    end: int | None = None         # inclusive
    lower: float | None = None    # native X units, inclusive
    upper: float | None = None
    branch: int | None = None      # one-based turning-point branch
    tolerance: float = 0.

    def indices(self, curve, xcol):
        end = len(curve.rows) - 1 if self.end is None else self.end
        if not 0 <= self.start <= end < len(curve.rows):
            raise ValueError(f'{curve.name}: row interval is outside the curve.')
        ix = np.arange(self.start, end + 1)
        x, _ = values(curve, xcol, ix)
        if self.branch is not None:
            runs = branches(x, self.tolerance)
            if not 1 <= self.branch <= len(runs):
                raise ValueError(f'{curve.name}: branch {self.branch} does not exist ({len(runs)} found).')
            a, b, _ = runs[self.branch - 1]
            ix, x = ix[a:b+1], x[a:b+1]
        keep = np.ones(len(x), dtype=bool)
        if self.lower is not None:
            keep &= x >= finite(self.lower, 'Lower X bound')
        if self.upper is not None:
            keep &= x <= finite(self.upper, 'Upper X bound')
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError('Lower X bound exceeds upper bound.')
        ix = ix[keep]
        if len(ix) < 2:
            raise ValueError(f'{curve.name}: select at least two points.')
        if not np.all(np.diff(ix) == 1):
            raise ValueError('The interval includes disjoint branches. Select a single branch or a contiguous row interval.')
        return ix.tolist()


@dataclass
class AnalysisResult:
    operation: str
    parameters: dict
    inputs: list
    curves: list = field(default_factory=list)
    metrics: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    peaks: list = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def record(self):
        return {'id': self.id, 'created_utc': self.created, 'algorithm_version': VERSION,
                'software': {'python':sys.version.split()[0], 'numpy':np.__version__, 'scipy':scipy.__version__},
                'operation': self.operation, 'parameters': self.parameters, 'inputs': self.inputs,
                'metrics': self.metrics, 'notes': self.notes, 'peaks':self.peaks,
                'outputs': [{'name':c.name, 'columns':c.columns, 'units':c.units, 'metadata':c.metadata} for c in self.curves]}

    def metric(self, source, name, value, unit='1'):
        sha = self._hash_cache[id(source)]
        value = finite(value, name)
        self.metrics.append({'source_curve':source.name, 'source_file':source.source,
                             'input_sha256':sha, 'metric':name, 'value':float(value), 'unit':unit})


def fingerprint(curve):
    snapshot = {'source':curve.source, 'name':curve.name, 'columns':curve.columns,
                'units':curve.units, 'rows':curve.rows, 'metadata':curve.metadata}
    data = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, default=str, allow_nan=True).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def derived(result, curve, indices, additions, xcol, ycol, suffix=None):
    columns, units = list(curve.columns), list(curve.units)
    arrays = []
    for name, unit, data in additions:
        if name in columns:
            raise ValueError(f'Output column {name!r} already exists; choose the original input or a different analysis.')
        data = np.asarray(data)
        if len(data) != len(indices) or not np.all(np.isfinite(data.astype(float))):
            raise ValueError('Analysis produced nonfinite or misaligned values.')
        columns.append(name); units.append(unit); arrays.append(data)
    rows = [list(curve.rows[i]) + [float(array[j]) for array in arrays] for j,i in enumerate(indices)]
    meta = copy.deepcopy(curve.metadata)
    history = list(meta.get('ANALYSIS_HISTORY', []))
    history.append({'result_id':result.id, 'operation':result.operation, 'version':VERSION,
                    'parameters':copy.deepcopy(result.parameters), 'source_name':curve.name,
                    'source_sha256':result._hash_cache[id(curve)], 'rows_1_based':[indices[0]+1,indices[-1]+1]})
    prior_status = str(meta.get('STATUS', '')).strip()
    meta.update(ANALYSIS_HISTORY=history, ANALYSIS_ID=result.id,
                DEFAULT_X=xcol, DEFAULT_Y=ycol,
                STATUS=(prior_status+' | ' if prior_status else '')+'Derived data · original source retained')
    out = Curve(curve.source, f'{curve.name} · {suffix or result.operation}', columns, units, rows, meta)
    result.curves.append(out)
    return out


def baseline(x, y, mode, constant=0.):
    if mode == 'None':
        return np.zeros(len(y))
    if mode == 'Constant':
        return np.full(len(y), finite(constant, 'Baseline'))
    if mode == 'Endpoint line':
        monotonic(x)
        return y[0] + (y[-1] - y[0]) * (x-x[0])/(x[-1]-x[0])
    raise ValueError('Unknown baseline method.')


def charge_signal(y, unit, area=None):
    factor, density = current_unit(unit)
    if area is not None:
        area = finite(area, 'Area / cm²', True)
        if density:
            return y * factor * area, 'C'
    return y * factor, 'C/cm2' if density else 'C'


def run(operation, curves, xcol, ycol, selection=None, **parameters):
    """Apply a fully specified operation transactionally to the supplied inputs."""
    if not curves:
        raise ValueError('Select source curves first.')
    selection = selection or Selection()
    if operation == 'CV baseline & peaks':
        from voltscope_cv import analyze_cv
        return analyze_cv(curves,xcol,ycol,selection,parameters)
    params = copy.deepcopy(parameters)
    params.update(x_column=xcol, y_column=ycol, selection=vars(selection).copy())
    result = AnalysisResult(operation, params, [])
    chosen = []
    result._hash_cache = {}
    for curve in curves:
        indices = selection.indices(curve, xcol)
        x, xu = values(curve, xcol, indices)
        y, yu = values(curve, ycol, indices)
        chosen.append((curve,indices,x,xu,y,yu))
        result._hash_cache[id(curve)] = fingerprint(curve)
        result.inputs.append({'source':curve.source,'curve':curve.name,'sha256':result._hash_cache[id(curve)],
                              'rows_1_based':[indices[0]+1,indices[-1]+1], 'points':len(indices),
                              'actual_x_bounds':[float(min(x)),float(max(x))],
                              'first_last_x':[float(x[0]),float(x[-1])], 'x_unit':xu,'y_unit':yu,
                              'source_status':copy.deepcopy(curve.metadata.get('STATUS','')),
                              'abort_flag':copy.deepcopy(curve.metadata.get('EXPERIMENTABORTED','')),
                              'experiment_metadata':{k:copy.deepcopy(v) for k,v in curve.metadata.items() if k!='ANALYSIS_HISTORY'}})
    result.notes.append('Intervals use stored samples only; boundaries are not interpolated. Original input curves are unchanged.')
    for source in result.inputs:
        if source['source_status'] or source['abort_flag']:
            result.notes.append(f"{source['curve']}: recorded source status {source['source_status']!s}; abort flag {source['abort_flag']!s}.")
    if operation in ('Join pulses', 'Pulse charges'):
        return _pulses(result, chosen, parameters)
    for curve, ix, x, xu, y, yu in chosen:
        name = curve.name
        if operation == 'Assign column units':
            xlabel, ylabel = parameters.get('x_label','Assigned X').strip(), parameters.get('y_label','Assigned Y').strip()
            xunit, yunit = parameters.get('x_unit','').strip(), parameters.get('y_unit','').strip()
            if not all((xlabel,ylabel,xunit,yunit)) or xlabel == ylabel:
                raise ValueError('Supply distinct column labels and explicit units for both axes.')
            derived(result,curve,ix,[(xlabel,xunit,x),(ylabel,yunit,y)],xlabel,ylabel)
            result.notes.append('Column meanings and units supplied explicitly by the user; values are copied unchanged, not scaled. Original unknown-unit columns remain available.')
        elif operation == 'Normalize area':
            area = finite(parameters.get('area'), 'Area / cm²', True)
            _, density = current_unit(yu)
            mode = parameters.get('mode','To current density')
            if mode == 'To current density':
                if density:
                    raise ValueError('The selected signal is already a current density.')
                output, unit, label = y/area, yu+'/cm2', ycol+' density'
            else:
                if not density:
                    raise ValueError('To total current requires a current-density signal.')
                output, unit, label = y*area, yu.replace('²','2')[:-4], ycol+' total'
            derived(result,curve,ix,[(label,unit,output)],xcol,label)
        elif operation in ('Reference conversion','iR correction'):
            axis = parameters.get('potential_axis','X')
            e, eu = (x,xu) if axis == 'X' else (y,yu)
            ef = potential_factor(eu)
            if operation == 'Reference conversion':
                source = finite(parameters.get('source_offset'), 'Source Eref vs SHE / V')
                if parameters.get('reference_mode') == 'Target RHE':
                    ph = finite(parameters.get('ph'), 'pH')
                    kelvin = finite(parameters.get('temperature'), 'Temperature / K', True)
                    target = -math.log(10)*8.31446261815324*kelvin/96485.33212*ph
                    result.notes.append('RHE target uses ideal Nernst pH dependence at the supplied temperature; source reference offset must match its actual electrolyte and temperature.')
                else:
                    target = finite(parameters.get('target_offset'), 'Target Eref vs SHE / V')
                equilibrium = finite(parameters.get('equilibrium',0), 'Equilibrium potential vs target / V')
                label = (xcol if axis=='X' else ycol) + ' converted'
                target_name = 'RHE' if parameters.get('reference_mode') == 'Target RHE' else str(parameters.get('target_name','target reference')).strip()
                if not target_name:
                    raise ValueError('Enter a target reference label (for example RHE or a named reference/electrolyte).')
                unit = f'V vs. {target_name}' if equilibrium == 0 else f'V overpotential vs. {target_name}'
                output = e*ef + source-target-equilibrium
                result.metric(curve,'Applied shift',source-target-equilibrium,'V')
            else:
                resistance = finite(parameters.get('resistance'), 'Resistance / Ω')
                if resistance < 0:
                    raise ValueError('Resistance cannot be negative.')
                current_col = parameters.get('current_column') or (ycol if axis=='X' else xcol)
                currents, current_units = values(curve,current_col,ix)
                factor, density = current_unit(current_units)
                if density:
                    currents = currents * finite(parameters.get('area'), 'Area / cm²', True)
                fraction = finite(parameters.get('fraction',1), 'Compensation fraction')
                if not 0 <= fraction <= 1:
                    raise ValueError('Compensation fraction must be between 0 and 1.')
                output = e*ef - currents*factor*resistance*fraction
                label, unit = (xcol if axis=='X' else ycol)+' iR corrected', eu.replace('mV','V',1)
                result.notes.append('Ecorrected = Emeasured − I(A) × R(Ω) × fraction, using the stored signed current.')
            derived(result,curve,ix,[(label,unit,output)],label if axis=='X' else xcol, label if axis=='Y' else ycol)
        elif operation == 'Smooth':
            window = int(parameters.get('window',11)); order = int(parameters.get('order',2))
            if window < 3 or window % 2 != 1 or window > len(y) or not 0 <= order < window:
                raise ValueError('Use an odd window ≥3, no longer than the interval, and polynomial order 0 ≤ order < window.')
            output = savgol_filter(y,window,order,mode='interp')
            label = ycol+' smoothed'
            derived(result,curve,ix,[(label,yu,output)],xcol,label)
            result.notes.append('Savitzky–Golay in acquisition sample index; window is points, not an X-unit width. No resampling.')
        elif operation == 'Derivative':
            monotonic(x)
            if len(x) < 3:
                raise ValueError('Derivative requires at least three samples.')
            label = f'd({ycol})/d({xcol})'
            derived(result,curve,ix,[(label,f'({yu})/({xu})',np.gradient(y,x,edge_order=2))],xcol,label)
        elif operation in ('Integrate charge','Peak and charge'):
            base = baseline(x,y,parameters.get('baseline','None'),parameters.get('baseline_value',0))
            corrected = y-base
            currents, qunit = charge_signal(corrected,yu,parameters.get('area'))
            if operation == 'Integrate charge':
                if xu not in TIME:
                    raise ValueError('Charge integration requires an explicit time axis; use Peak and charge for a potential sweep.')
                t = x * TIME[xu]
            else:
                monotonic(x,'Potential')
                ef = potential_factor(xu)
                time_col = parameters.get('time_column')
                if time_col:
                    t, tu = values(curve,time_col,ix)
                    if tu not in TIME:
                        raise ValueError('The selected time column must have explicit time units.')
                    t = t * TIME[tu]
                else:
                    rate = finite(parameters.get('scan_rate'), 'Scan rate / V s⁻¹', True)
                    t = np.r_[0.,np.cumsum(np.abs(np.diff(x))*ef/rate)]
                    result.notes.append('Time increments derived explicitly as |ΔE| / supplied scan rate; not a measured time axis.')
            if not np.all(np.diff(t)>0):
                raise ValueError('Time must increase strictly in acquisition order.')
            q = cumulative_trapezoid(currents,t,initial=0.)
            extra = [('Baseline',yu,base),('Baseline corrected',yu,corrected),('Charge',qunit,q)]
            out_y = 'Charge' if operation=='Integrate charge' else 'Baseline corrected'
            out = derived(result,curve,ix,extra,xcol,out_y)
            result.metric(curve,'Signed charge',q[-1],qunit)
            result.metric(curve,'Duration',t[-1]-t[0],'s')
            result.metric(curve,'Mean signal',np.mean(corrected),yu)
            if operation == 'Peak and charge':
                polarity = parameters.get('polarity','Maximum')
                sign = 1 if polarity=='Maximum' else -1
                prominence = finite(parameters.get('prominence',0),'Peak prominence')
                if prominence < 0:
                    raise ValueError('Peak prominence cannot be negative.')
                peaks, _ = find_peaks(sign*corrected,prominence=prominence)
                for n,k in enumerate(peaks,1):
                    result.metric(curve,f'Peak {n} source row',ix[k]+1)
                    result.metric(curve,f'Peak {n} potential',x[k],xu)
                    result.metric(curve,f'Peak {n} signed height',corrected[k],yu)
                result.metric(curve,'Local peak count',len(peaks))
                if not len(peaks):
                    result.notes.append(f'{name}: no interior local peak met the prominence criterion; no peak was invented at an interval boundary.')
                out.metadata['ANALYSIS_OVERLAYS'] = ['Baseline', 'Baseline corrected']
                out.metadata['PEAK_INDICES'] = [int(i) for i in peaks]
        elif operation == 'Tafel fit':
            try:
                ef = potential_factor(xu); factor, density = current_unit(yu)
                e, amps = x*ef, y*factor
            except ValueError:
                ef = potential_factor(yu); factor, density = current_unit(xu)
                e, amps = y*ef, x*factor
            monotonic(e,'Potential')
            if len(e)<3 or np.any(amps==0) or not (np.all(amps>0) or np.all(amps<0)):
                raise ValueError('Tafel fit needs ≥3 samples with nonzero current of one sign, on one potential branch.')
            logi = np.log10(np.abs(amps))
            if np.ptp(logi) < 1e-12:
                raise ValueError('Current has no logarithmic range for a Tafel regression.')
            fit = linregress(logi,e)
            prediction = fit.intercept + fit.slope*logi
            error = fit.stderr*1000
            for title,val,unit in [('Tafel slope',fit.slope*1000,'mV/dec'),('Slope standard error',error,'mV/dec'),
                                   ('95% slope CI half-width',student_t.ppf(.975,len(e)-2)*error,'mV/dec'),
                                   ('Intercept',fit.intercept,'V'),('R²',fit.rvalue**2,'1'),('Fit points',len(e),'1'),
                                   ('Log current span',np.ptp(logi),'dec')]:
                result.metric(curve,title,val,unit)
            unit = 'log10(|J| / (A/cm2))' if density else 'log10(|I| / A)'
            out = derived(result,curve,ix,[('Log current',unit,logi),('Potential / V','V',e),
                                ('Tafel fitted / V','V',prediction),('Tafel residual / V','V',e-prediction)],'Log current','Potential / V')
            out.metadata['ANALYSIS_OVERLAYS'] = ['Tafel fitted / V']
            result.notes.append('OLS E(V) against log10 absolute current in A or A/cm². Signed slope retained. No kinetic validity, exchange current, baseline, or iR assumption is inferred from R².')
        elif operation == 'Split scans / cycles':
            mode = parameters.get('split_mode','Branches')
            ranges = []
            cycle_column = parameters.get('cycle_column')
            if mode == 'Stored cycle column':
                if not cycle_column:
                    raise ValueError('Choose a stored cycle column.')
                cycles, _ = values(curve,cycle_column,ix)
                starts = np.r_[0,np.flatnonzero(np.diff(cycles)!=0)+1,len(cycles)]
                ranges = [(int(a),int(b)-1,f'cycle {cycles[a]:g}') for a,b in zip(starts[:-1],starts[1:])]
            else:
                runs = branches(x,parameters.get('tolerance',0.))
                if mode == 'Branches':
                    ranges = [(a,b,f'branch {n} '+('increasing' if d>0 else 'decreasing' if d<0 else 'constant')) for n,(a,b,d) in enumerate(runs,1)]
                else:
                    for n in range(0,len(runs),2):
                        a = runs[n][0]; b = runs[min(n+1,len(runs)-1)][1]
                        partial = n+1>=len(runs) or abs(x[b]-x[a]) > finite(parameters.get('tolerance',0.),'Reversal tolerance')
                        ranges.append((a,b,f'cycle {n//2+1}'+(' (partial/open)' if partial else '')))
            for a,b,label in ranges:
                derived(result,curve,ix[a:b+1],[],xcol,ycol,label)
            result.notes.append('Turning-point branches share their boundary sample. Cycles pair consecutive branches from the selected starting row; partial final cycles are labelled. Noise sensitivity follows the supplied tolerance. Stored cycle IDs are grouped contiguously without reordering.')
        elif operation == 'Coordinate rotation':
            sx = finite(parameters.get('x_scale'),'X normalization scale',True)
            sy = finite(parameters.get('y_scale'),'Y normalization scale',True)
            ox = finite(parameters.get('x_origin',0),'X origin'); oy = finite(parameters.get('y_origin',0),'Y origin')
            theta = math.radians(finite(parameters.get('angle'),'Angle / degrees'))
            u,v = (x-ox)/sx,(y-oy)/sy
            derived(result,curve,ix,[('Rotated X','1',u*math.cos(theta)-v*math.sin(theta)),
                                   ('Rotated Y','1',u*math.sin(theta)+v*math.cos(theta))],'Rotated X','Rotated Y')
            result.notes.append('Geometric rotation of dimensionless normalized coordinates; not a physical potential/current conversion. Scales and origins are explicit in native units.')
        else:
            raise ValueError(f'Unknown analysis operation: {operation}')
    return result


def _pulses(result, chosen, parameters):
    if result.operation == 'Pulse charges':
        summaries, qunit = [], None
        for n,(curve,ix,x,xu,y,yu) in enumerate(chosen,1):
            if xu not in TIME:
                raise ValueError('Each pulse requires a time column with known units.')
            t = x*TIME[xu]
            if not np.all(np.diff(t)>0):
                raise ValueError('Pulse time must increase strictly.')
            base = baseline(t,y,parameters.get('baseline','None'),parameters.get('baseline_value',0))
            current, unit = charge_signal(y-base,yu,parameters.get('area'))
            if qunit is not None and qunit != unit:
                raise ValueError('Cannot combine charge and charge density in one summary; supply an area or select compatible inputs.')
            qunit = unit
            q = cumulative_trapezoid(current,t,initial=0.)[-1]
            summaries.append([n,float(q),curve.name,curve.source,ix[0]+1,ix[-1]+1])
            result.metric(curve,'Signed pulse charge',q,unit)
        c = Curve(chosen[0][0].source,'Pulse charge summary',['Pulse','Charge','Input curve','Input source','Start row','End row'],
                  ['1',qunit,'text','text','1','1'],summaries,{'ANALYSIS_ID':result.id,'ANALYSIS_HISTORY':[result.record()],
                   'DEFAULT_X':'Pulse','DEFAULT_Y':'Charge','STATUS':'Derived pulse summary · explicit input order'})
        result.curves.append(c)
        return result
    gap = finite(parameters.get('gap'), 'Inter-pulse gap / s')
    if gap < 0:
        raise ValueError('Gap cannot be negative.')
    first = chosen[0][0]
    rows, previous = [], None
    for curve,ix,x,xu,y,yu in chosen:
        if curve.columns != first.columns or curve.units != first.units:
            raise ValueError('Pulse joining requires identical column schemas and units. Normalize explicitly first.')
        if xu not in TIME or not np.all(np.diff(x)>0):
            raise ValueError('Pulse joining requires strictly increasing, explicitly labelled time.')
        t = x*TIME[xu]
        joined = t-t[0]+(0. if previous is None else previous+gap)
        for n,i in enumerate(ix):
            rows.append(list(curve.rows[i])+[float(joined[n]),curve.name,curve.source,i+1])
        previous = joined[-1]
    reserved = ['Joined time','Input curve','Input source','Input row']
    if set(reserved)&set(first.columns):
        raise ValueError('These inputs already contain joined-pulse columns; select the original pulses.')
    out = Curve(first.source,'Joined pulses',first.columns+reserved,first.units+['s','text','text','1'],rows,
                {'ANALYSIS_ID':result.id,'ANALYSIS_HISTORY':[result.record()],
                 'DEFAULT_X':'Joined time','DEFAULT_Y':result.parameters['y_column'],
                 'STATUS':'Derived joined time · native time retained in its original column'})
    result.curves.append(out)
    result.notes.append('Explicit input order used. Each native time axis is shifted to start after the previous pulse plus the chosen gap; first pulse starts at zero. Zero gap retains duplicate boundary times. Charge should be integrated per pulse, not across unspecified gaps.')
    return result


def export_results(results, parent):
    """Write a new exclusive report directory; never replace an existing file."""
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    directory = parent / ('analysis_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
    directory.mkdir()
    records = [r.record() for r in results]
    with (directory/'provenance.json').open('x',encoding='utf-8') as f:
        json.dump(records,f,indent=2,ensure_ascii=False,allow_nan=False)
    with (directory/'metrics.csv').open('x',newline='',encoding='utf-8') as f:
        writer = csv.DictWriter(f,fieldnames=['result_id','operation','source_curve','source_file','input_sha256','metric','value','unit'])
        writer.writeheader()
        for r in results:
            for metric in r.metrics:
                writer.writerow(dict(result_id=r.id,operation=r.operation,**metric))
    peak_fields = ['result_id','source_curve','source_file','input_sha256','sweep','direction','polarity',
                   'source_row','potential','potential_unit','current','current_unit','raw_current_at_row',
                   'baseline_at_peak','prominence','snr','quality','method','fit_source_rows']
    with (directory/'peaks.csv').open('x',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=peak_fields);writer.writeheader()
        for r in results:
            for peak in r.peaks:
                writer.writerow(dict(result_id=r.id,**peak))
    for r in results:
        export_csv(r.curves,directory/(r.id+'_curves.csv'))
    return directory
