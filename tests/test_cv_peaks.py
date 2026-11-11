"""Independent known-answer CV cases, never instrument exports."""
import copy
import csv
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import time
import unittest
import numpy as np
from voltscope_data import Curve
from voltscope_analysis import run, Selection, export_results
from voltscope_cv import sweep_ranges


def make(x=None,y=None,xunit='V',yunit='µA',name='Analytical CV'):
    x=np.linspace(-1,1,401) if x is None else np.asarray(x)
    y=2+.3*x+np.exp(-.5*((x-.1)/.08)**2) if y is None else y
    return Curve('synthetic',name,['E','I'],[xunit,yunit],[[float(a),float(b)] for a,b in zip(x,y)],{})


def analyze(c,**p):return run('CV baseline & peaks',[c],'E','I',**p)


class CVKnownAnswers(unittest.TestCase):
    def test_linear_baseline_and_no_scan_rate(self):
        c=make();original=copy.deepcopy(c);r=analyze(c)
        self.assertEqual(len(r.peaks),1)
        p=r.peaks[0];self.assertAlmostEqual(p['potential'],.1,places=4)
        self.assertAlmostEqual(p['current'],1,delta=.001)
        self.assertEqual(p['method'],'local quadratic fit')
        np.testing.assert_allclose(np.array(r.curves[0].rows)[:,-4],2+.3*np.linspace(-1,1,401),atol=1e-10)
        self.assertEqual(c,original);self.assertNotIn('scan_rate',r.parameters)

    def test_quadratic_background_and_manual_windows(self):
        x=np.linspace(-1,1,501);y=4+.3*x+.8*x*x-2*np.exp(-.5*((x+.12)/.075)**2)
        r=analyze(make(x,y),cv_model='Robust quadratic background',cv_manual=True,
                  cv_left_min=-1,cv_left_max=-.65,cv_right_min=.65,cv_right_max=1)
        self.assertEqual(len(r.peaks),1);p=r.peaks[0]
        self.assertAlmostEqual(p['current'],-2,delta=.002);self.assertAlmostEqual(p['potential'],-.12,delta=.001)
        self.assertEqual(p['polarity'],'negative')

    def test_unequal_sweeps_and_multiple_cycles(self):
        arrays=[np.linspace(-1,1,401),np.linspace(1,-1,273)[1:],np.linspace(-1,1,351)[1:],np.linspace(1,-1,299)[1:]]
        x=np.concatenate(arrays);y=np.concatenate([2+.3*a+s*np.exp(-.5*((a-.1*s)/.08)**2) for a,s in zip(arrays,[1,-1,1,-1])])
        r=analyze(make(x,y));self.assertEqual(len(r.curves),4);self.assertEqual(len(r.peaks),4)
        self.assertEqual([p['polarity'] for p in r.peaks],['positive','negative']*2)
        for p in r.peaks:self.assertAlmostEqual(abs(p['current']),1,delta=.003)
        selected=run('CV baseline & peaks',[make(x,y)],'E','I',Selection(branch=2))
        self.assertEqual(len(selected.curves),1);self.assertEqual(selected.peaks[0]['sweep'],2)

    def test_nonuniform_duplicate_jitter_and_invalid_pairs(self):
        rng=np.random.default_rng(12);x=np.sort(rng.uniform(-1,1,700));x[100]=x[99];x[301]=x[300]-.001
        c=make(x);c.rows[25][1]=None;c.rows[80][0]=float('nan');c.rows[200][1]='missing';c.rows[400]=[]
        before=copy.deepcopy(c.rows);r=analyze(c)
        self.assertEqual(len(r.curves),1);self.assertEqual(len(r.peaks),1)
        self.assertAlmostEqual(r.peaks[0]['current'],1,delta=.004)
        self.assertAlmostEqual(r.peaks[0]['potential'],.1,delta=.002)
        self.assertEqual(r.inputs[0]['excluded_rows_1_based'],[26,81,201,401])
        self.assertEqual(len(r.curves[0].rows),696)
        self.assertEqual(r.inputs[0]['sweeps'][0]['repeated_potentials'],1)
        self.assertEqual(repr(c.rows),repr(before))
        self.assertNotIn(401,r.inputs[0]['sweeps'][0]['source_rows_1_based'])

    def test_outlier_background_and_isolated_spike(self):
        c=make();c.rows[10][1]+=40;c.rows[220][1]+=100
        r=analyze(c);self.assertEqual(len(r.peaks),1)
        self.assertAlmostEqual(r.peaks[0]['current'],1,delta=.003)
        self.assertIn(221,r.inputs[0]['sweeps'][0]['spike_source_rows'])
        self.assertIn('spike',r.peaks[0]['quality'])
        self.assertGreater(r.curves[0].rows[220][-3],99) # corrected stored current remains unfiltered

    def test_no_subtraction_and_native_units(self):
        x=np.linspace(-1000,1000,401)
        for unit,scale in [('A',1e-6),('mA',1e-3),('µA',1),('nA',1000),('µA/cm2',1)]:
            c=make(x,scale*np.exp(-.5*((x-100)/80)**2),'mV',unit)
            r=analyze(c,cv_model='No subtraction',cv_manual=True,cv_fraction='bad')
            self.assertAlmostEqual(r.peaks[0]['current']/scale,1,delta=.001)
            self.assertAlmostEqual(r.peaks[0]['potential'],100,delta=.1)
            self.assertEqual(r.peaks[0]['current_unit'],unit)
            self.assertEqual(r.peaks[0]['potential_unit'],'mV')

    def test_short_scan_flat_top_and_resolved_pair(self):
        x=np.linspace(-1,1,15);r=analyze(make(x,np.exp(-.5*((x-.1)/.2)**2)),cv_model='No subtraction',cv_smooth=99)
        self.assertEqual(len(r.peaks),1);self.assertEqual(r.inputs[0]['sweeps'][0]['effective_detection_window'],15)
        x=np.linspace(-1,1,401);y=np.minimum(1,2*np.exp(-.5*(x/.15)**2))
        r=analyze(make(x,y),cv_model='No subtraction',cv_smooth=1)
        self.assertEqual(len(r.peaks),1);self.assertIn('Flat top',r.peaks[0]['quality'])
        y=np.exp(-.5*((x+.25)/.06)**2)+.7*np.exp(-.5*((x-.25)/.07)**2)
        r=analyze(make(x,y),cv_reporting='All supported peaks');self.assertEqual(len(r.peaks),2)
        np.testing.assert_allclose([p['potential'] for p in r.peaks],[-.25,.25],atol=.001)
        np.testing.assert_allclose([p['current'] for p in r.peaks],[1,.7],atol=.002)

    def test_dominant_selection_retains_auditable_candidates_and_gap_flag(self):
        x=np.linspace(-1,1,401);y=np.exp(-.5*((x+.25)/.06)**2)+.7*np.exp(-.5*((x-.25)/.07)**2)
        r=analyze(make(x,y));self.assertEqual(len(r.peaks),1)
        self.assertAlmostEqual(r.peaks[0]['potential'],-.25,delta=.001)
        self.assertEqual(len(r.inputs[0]['sweeps'][0]['candidate_peaks']),2)
        c=make();c.rows[219][1]=None
        r=analyze(c);self.assertIn('Missing samples near peak',r.peaks[0]['quality'])

    def test_underresolved_and_search_boundary_quality(self):
        x=np.linspace(-1,1,101);y=np.exp(-.5*((x-.1)/.008)**2)
        r=analyze(make(x,y),cv_model='No subtraction',cv_smooth=1,cv_despike=False)
        self.assertEqual(len(r.peaks),1);self.assertIn('Under-resolved',r.peaks[0]['quality'])
        r=analyze(make(),cv_peak_min=.099,cv_peak_max=.7)
        self.assertIn('Near search boundary',r.peaks[0]['quality'])

    def test_partial_batch_status_export_and_reanalysis(self):
        good=make();good.metadata={'STATUS':'aborted','EXPERIMENTABORTED':'TRUE'}
        bad=make([0,1,2],[0,1,0],name='Too short')
        r=run('CV baseline & peaks',[bad,good],'E','I')
        self.assertEqual(len(r.curves),1);self.assertTrue(r.parameters['skipped_inputs_or_sweeps'])
        self.assertTrue(any('aborted' in n for n in r.notes))
        second=analyze(r.curves[0]);self.assertEqual(len(second.curves[0].columns),10)
        self.assertEqual(len(set(second.curves[0].columns)),10)
        with tempfile.TemporaryDirectory() as tmp:
            folder=export_results([r],tmp)
            record=json.loads((folder/'provenance.json').read_text())[0]
            self.assertEqual(record['peaks'],r.peaks)
            with (folder/'peaks.csv').open(newline='',encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),1);self.assertAlmostEqual(float(rows[0]['current']),r.peaks[0]['current'])
            self.assertIn('fit_source_rows',rows[0]);self.assertIn('input_sha256',rows[0])

    def test_bad_settings_and_insufficient_support(self):
        for p in [dict(cv_smooth=4),dict(cv_prominence=-1),dict(cv_reversal=-1),dict(cv_noise_factor=-1),
                  dict(cv_manual=True),dict(cv_manual=True,cv_left_min=.1,cv_left_max=.2,cv_right_min=-.2,cv_right_max=0),
                  dict(cv_manual=True,cv_left_min=-3,cv_left_max=-2,cv_right_min=2,cv_right_max=3),
                  dict(cv_peak_min=.2,cv_peak_max=.1),dict(cv_model='bad')]:
            with self.subTest(p=p),self.assertRaises(ValueError):analyze(make(),**p)
        for c in [make([1]*10,[1]*10),make(y=np.full(401,np.nan)),make(xunit='unknown'),make(yunit='unknown')]:
            with self.assertRaises(ValueError):analyze(c)
        self.assertEqual(len(analyze(make(y=2+.3*np.linspace(-1,1,401))).peaks),0)

    def test_seeded_noise_accuracy_and_blank_false_positives(self):
        x=np.linspace(-1,1,401);errors=[];false=0
        for seed in range(100):
            rng=np.random.default_rng(seed);noise=rng.normal(0,.02,len(x))
            r=analyze(make(x,2+.3*x+np.exp(-.5*((x-.1)/.08)**2)+noise))
            self.assertEqual(len(r.peaks),1,f'seed {seed}')
            p=r.peaks[0];errors.append([abs(p['potential']-.1),abs(p['current']-1)])
            false+=len(analyze(make(x,2+.3*x+noise)).peaks)
        errors=np.asarray(errors)
        self.assertLess(errors[:,0].max(),.015)
        self.assertLess(errors[:,1].max(),.05)
        self.assertEqual(false,0)
        self.noise_summary={'trials':100,'max_potential_error_V':float(errors[:,0].max()),'max_relative_current_error':float(errors[:,1].max()),'median_relative_current_error':float(np.median(errors[:,1])),'blank_false_peaks':false}
        print('\nCV noise validation:',json.dumps(self.noise_summary))


class CVWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def wait(self,d):
        from PySide6.QtTest import QTest
        deadline=time.monotonic()+8
        while (d.worker is not None or d.result is None) and time.monotonic()<deadline:
            self.app.processEvents();QTest.qWait(10)
        self.assertIsNone(d.worker);self.assertIsNotNone(d.result,d.feedback.text())

    def test_auto_preview_windows_branch_export_invalidation_and_undo(self):
        from voltscope_ui import Viewer
        from voltscope_analysis_ui import AnalysisDialog
        from PySide6.QtCore import QPoint,Qt
        from PySide6.QtTest import QTest
        w=Viewer();w.loaded([make()],[]);w.show();d=AnalysisDialog(w);d.show()
        try:
            self.wait(d);self.assertEqual(d.tool.currentText(),'CV baseline & peaks')
            self.assertFalse(d.fields['scan_rate'].isVisible());self.assertTrue(d.export.isEnabled())
            self.assertEqual(len(d.result.peaks),1);self.assertTrue(d.view.raw_plot.series)
            d.pick_window('left');p=d.view.raw_plot
            self.app.processEvents();rect=p.rect_plot()
            QTest.mousePress(p,Qt.MouseButton.LeftButton,pos=QPoint(int(rect.left()+10),int(rect.center().y())))
            QTest.mouseMove(p,QPoint(int(rect.left()+50),int(rect.center().y())))
            QTest.mouseRelease(p,Qt.MouseButton.LeftButton,pos=QPoint(int(rect.left()+50),int(rect.center().y())))
            self.assertTrue(d.fields['cv_manual'].isChecked());self.assertFalse(d.apply.isEnabled())
            self.assertTrue(d.fields['cv_left_min'].text());self.assertTrue(d.fields['cv_right_max'].text())
            d.compute();self.wait(d);self.assertTrue(d.apply.isEnabled(),d.feedback.text())
            d.commit();self.assertEqual(len(w.curves),2);w.undo_analysis();self.assertEqual(len(w.curves),1)
        finally:
            if d.worker:d.worker.wait();self.app.processEvents()
            d.close();w.close();self.app.processEvents()

if __name__=='__main__':unittest.main()
