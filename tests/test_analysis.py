"""Known-answer scientific cases; fixtures are analytical and wholly synthetic."""
import copy
import json
import math
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import QCoreApplication, QEvent
from voltscope_data import Curve
from voltscope_analysis import run, Selection, branches, export_results, fingerprint


def curve(x,y,xunit='s',yunit='A',name='Synthetic'):
    return Curve('synthetic.source',name,['X','Y'],[xunit,yunit],[[float(a),float(b)] for a,b in zip(x,y)],{})


def metric(result,name):
    return next(m['value'] for m in result.metrics if m['metric']==name)


class ScientificAnalysis(unittest.TestCase):
    def test_area_and_ir_units_and_immutable_source(self):
        c=curve([0,1,2],[1000,2000,3000],'V vs. Ag/AgCl','µA')
        c.metadata['STATUS']='Scan aborted'
        original=copy.deepcopy(c)
        normalized=run('Normalize area',[c],'X','Y',area=.5)
        d=normalized.curves[0]
        self.assertIn('Scan aborted',d.metadata['STATUS'])
        self.assertEqual(normalized.inputs[0]['source_status'],'Scan aborted')
        self.assertEqual(d.units[-1],'µA/cm2')
        self.assertEqual(d.rows[0][-1],2000.)
        back=run('Normalize area',[d],'X','Y density',area=.5,mode='To total current').curves[0]
        self.assertEqual([r[-1] for r in back.rows],[1000,2000,3000])
        corrected=run('iR correction',[d],'X','Y density',resistance=10,area=.5,fraction=.8).curves[0]
        self.assertAlmostEqual(corrected.rows[1][-1],.984)
        self.assertEqual(corrected.units[-1],'V vs. Ag/AgCl')
        self.assertEqual(c,original)
        self.assertEqual(normalized.inputs[0]['sha256'],fingerprint(c))
        with self.assertRaises(ValueError):run('Normalize area',[c],'X','Y',area=0)
        with self.assertRaises(ValueError):run('iR correction',[d],'X','Y density',resistance=10)

    def test_reference_bidirectional_rhe_overpotential_and_y_axis(self):
        c=curve([0,1,2],[100,200,300],'s','mV')
        r=run('Reference conversion',[c],'X','Y',potential_axis='Y',source_offset=.197,target_offset=.241,target_name='SCE',equilibrium=.05)
        self.assertAlmostEqual(r.curves[0].rows[0][-1],.006)
        back=run('Reference conversion',r.curves,'X','Y converted',potential_axis='Y',source_offset=.241,target_offset=.197,target_name='Ag/AgCl',equilibrium=-.05)
        self.assertAlmostEqual(back.curves[0].rows[0][-1],.1)
        rhe=run('Reference conversion',[c],'X','Y',potential_axis='Y',source_offset=.197,reference_mode='Target RHE',ph=7,temperature=298.15,target_name='RHE')
        self.assertAlmostEqual(rhe.curves[0].rows[0][-1],.1+.197+.0591593497*7,places=8)
        with self.assertRaises(ValueError):run('Reference conversion',[c],'X','Y',potential_axis='Y',source_offset=.197)

    def test_derivative_nonuniform_polynomial_and_smoothing(self):
        x=np.array([0.,.1,.4,1.,2.]);c=curve(x,x*x)
        d=run('Derivative',[c],'X','Y').curves[0]
        np.testing.assert_allclose([r[-1] for r in d.rows],2*x,atol=1e-12)
        x=np.arange(15.);c=curve(x,3*x*x+2*x+1)
        s=run('Smooth',[c],'X','Y',window=5,order=2).curves[0]
        np.testing.assert_allclose([r[-1] for r in s.rows],3*x*x+2*x+1,atol=1e-10)
        for window,order in [(4,2),(19,2),(5,5)]:
            with self.assertRaises(ValueError):run('Smooth',[c],'X','Y',window=window,order=order)
        for x in [[0,0,1],[0,1,0]]:
            with self.assertRaises(ValueError):run('Derivative',[curve(x,[1,2,3])],'X','Y')

    def test_signed_time_charge_density_and_baseline(self):
        c=curve([0,.5,2],[-2,-2,-2],'s','mA')
        r=run('Integrate charge',[c],'X','Y')
        self.assertAlmostEqual(metric(r,'Signed charge'),-.004)
        self.assertEqual(r.curves[0].units[-1],'C')
        c=curve([0,1,2],[4,4,4],'s','µA/cm2')
        r=run('Integrate charge',[c],'X','Y',baseline='Constant',baseline_value=1)
        self.assertAlmostEqual(metric(r,'Signed charge'),6e-6)
        self.assertEqual(r.curves[0].units[-1],'C/cm2')
        r=run('Integrate charge',[c],'X','Y',area=.25)
        self.assertAlmostEqual(metric(r,'Signed charge'),2e-6)
        for unit in ['unknown','V']:
            with self.assertRaises(ValueError):run('Integrate charge',[curve([0,1],[1,1],unit)],'X','Y')
        with self.assertRaises(ValueError):run('Integrate charge',[curve([0,0,1],[1,1,1])],'X','Y')

    def test_peak_triangle_known_charge_and_decreasing_cathodic(self):
        c=curve([0,.5,1],[1,3,1],'V','mA')
        r=run('Peak and charge',[c],'X','Y',baseline='Endpoint line',scan_rate=.5)
        self.assertAlmostEqual(metric(r,'Signed charge'),.002)
        self.assertEqual(metric(r,'Peak 1 potential'),.5)
        self.assertEqual(metric(r,'Peak 1 signed height'),2.)
        c=curve([1,.5,0],[-1,-3,-1],'V','mA')
        r=run('Peak and charge',[c],'X','Y',baseline='Endpoint line',scan_rate=.5,polarity='Minimum')
        self.assertAlmostEqual(metric(r,'Signed charge'),-.002)
        self.assertEqual(metric(r,'Peak 1 signed height'),-2.)
        with self.assertRaises(ValueError):run('Peak and charge',[c],'X','Y')
        r=run('Peak and charge',[curve([0,.5,1],[1,2,3],'V','A')],'X','Y',scan_rate=1)
        self.assertEqual(metric(r,'Local peak count'),0)

    def test_tafel_known_120_mV_per_decade_and_swapped_axes(self):
        amps=np.geomspace(1e-6,1e-3,20);e=.12*np.log10(amps)+.8
        c=curve(e,amps*1000,'V','mA')
        r=run('Tafel fit',[c],'X','Y')
        self.assertAlmostEqual(metric(r,'Tafel slope'),120.,places=10)
        self.assertAlmostEqual(metric(r,'Intercept'),.8,places=12)
        self.assertAlmostEqual(metric(r,'R²'),1.)
        self.assertAlmostEqual(metric(r,'Slope standard error'),0.,places=4)
        inverse=curve(-amps,e,'A','V')
        rr=run('Tafel fit',[inverse],'X','Y')
        self.assertAlmostEqual(metric(rr,'Tafel slope'),120.)
        for bad in [[0,1,2],[1,-1,2],[1,1,1]]:
            with self.assertRaises(ValueError):run('Tafel fit',[curve([0,1,2],bad,'V','A')],'X','Y')
        with self.assertRaises(ValueError):run('Tafel fit',[curve([0,1,0],[1,2,3],'V','A')],'X','Y')

    def test_branches_cycles_variable_length_and_selection(self):
        c=curve([0,.5,1,.8,.3,0,.6,1,.5,0],range(10),'V','A')
        r=run('Split scans / cycles',[c],'X','Y',split_mode='Cycles from reversals')
        self.assertEqual([len(x.rows) for x in r.curves],[6,5])
        self.assertEqual(r.curves[0].rows[-1],r.curves[1].rows[0])
        s=Selection(branch=2,lower=.2,upper=.9)
        self.assertEqual(s.indices(c,'X'),[3,4])
        with self.assertRaises(ValueError):Selection(lower=.2,upper=.9).indices(c,'X')
        with self.assertRaises(ValueError):Selection(branch=99).indices(c,'X')
        c.columns.append('cycle');c.units.append('1')
        for i,row in enumerate(c.rows):row.append(1 if i<3 else 2)
        r=run('Split scans / cycles',[c],'X','Y',split_mode='Stored cycle column',cycle_column='cycle')
        self.assertEqual([len(x.rows) for x in r.curves],[3,7])
        self.assertEqual(sum(len(x.rows) for x in r.curves),len(c.rows))

    def test_pulse_order_join_gap_charge_and_dimensionless_rotation(self):
        a=curve([5,6,7],[1,1,1],name='A');b=curve([10,12],[2,2],name='B')
        r=run('Join pulses',[b,a],'X','Y',gap=1)
        self.assertEqual([row[-4] for row in r.curves[0].rows],[0.,2.,3.,4.,5.])
        self.assertEqual(r.curves[0].rows[0][0],10.)
        q=run('Pulse charges',[b,a],'X','Y')
        self.assertEqual([row[1] for row in q.curves[0].rows],[4.,2.])
        self.assertEqual([row[2] for row in q.curves[0].rows],['B','A'])
        rotated=run('Coordinate rotation',[curve([1,2],[3,4],'V','mA')],'X','Y',angle=90,x_scale=1,y_scale=1).curves[0]
        np.testing.assert_allclose([r[-2:] for r in rotated.rows],[[-3,1],[-4,2]],atol=1e-12)
        self.assertEqual(rotated.units[-2:],['1','1'])

    def test_legacy_paired_csv_first_row_alignment_and_explicit_units(self):
        from voltscope_data import read_data
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'legacy.csv'
            p.write_text('0;1;0;10\n1;2;2;20\n2;3;;\n',encoding='utf-8')
            cs=read_data(p)
            self.assertEqual([len(c.rows) for c in cs],[3,2])
            self.assertEqual(cs[0].rows[0],[0.,1.,1])
            self.assertEqual(cs[1].rows[-1],[2.,20.,2])
            with self.assertRaises(ValueError):run('Integrate charge',[cs[0]],'X','Y')
            assigned=run('Assign column units',[cs[0]],'X','Y',x_label='Time',y_label='Current',x_unit='s',y_unit='mA')
            charge=run('Integrate charge',assigned.curves,'Time','Current')
            self.assertAlmostEqual(metric(charge,'Signed charge'),.004)
            self.assertEqual(cs[0].units[:2],['unknown','unknown'])
            p.write_bytes('0\t1\n1\t2\n'.encode('utf-16'))
            self.assertEqual(len(read_data(p)[0].rows),2)

    def test_invalid_rows_atomic_batch_and_report_provenance(self):
        good=curve([0,1,2],[1,2,3]);bad=curve([0,1,2],[1,2,float('nan')])
        original=copy.deepcopy(good)
        with self.assertRaises(ValueError):run('Derivative',[good,bad],'X','Y')
        self.assertEqual(good,original)
        r=run('Integrate charge',[good],'X','Y',Selection(start=1))
        with tempfile.TemporaryDirectory() as temp:
            folder=export_results([r],temp)
            record=json.loads((folder/'provenance.json').read_text())[0]
            self.assertEqual(record['inputs'][0]['rows_1_based'],[2,3])
            self.assertEqual(record['inputs'][0]['sha256'],fingerprint(good))
            self.assertEqual(record['metrics'][0]['source_file'],'synthetic.source')
            self.assertTrue((folder/'metrics.csv').exists())
            self.assertNotEqual(export_results([r],temp),folder)
            self.assertTrue(list(folder.glob('*_curves.csv')))


class AnalysisUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def dispose(self, viewer):
        viewer.close()
        viewer.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_workbench_preview_commit_undo_export_and_invalidation(self):
        from voltscope_ui import Viewer
        from voltscope_analysis_ui import AnalysisDialog, render_plot
        from PySide6.QtTest import QTest
        w=Viewer();w.show()
        c=curve([0,1,2,3,4],[0,1,4,9,16],'s','A');w.loaded([c],[])
        dialog=AnalysisDialog(w);dialog.show()
        try:
            dialog.tool.setCurrentText('Derivative');dialog.compute()
            deadline=time.monotonic()+5
            while dialog.worker is not None and time.monotonic()<deadline:
                self.app.processEvents();QTest.qWait(10)
            self.assertIsNone(dialog.worker)
            self.assertTrue(dialog.apply.isEnabled(),dialog.feedback.text())
            self.assertTrue(dialog.view.plot.series)
            dialog.commit();self.assertEqual(len(w.curves),2)
            self.assertEqual(len(w.analysis_results),1)
            self.assertEqual(w.ybox.currentText(),'d(Y)/d(X)')
            self.assertEqual(c.rows[2],[2.,4.])
            with tempfile.TemporaryDirectory() as temp:
                for ext in ['png','svg']:
                    path=Path(temp)/('plot.'+ext);render_plot(dialog.view.plot,path)
                    self.assertGreater(path.stat().st_size,100)
                with patch('voltscope_analysis_ui.QFileDialog.getExistingDirectory',return_value=temp):
                    dialog.save_results()
                self.assertTrue(list(Path(temp).glob('analysis_*/provenance.json')))
            dialog.fields['window'].setValue(7)
            self.assertFalse(dialog.apply.isEnabled())
            w.undo_analysis();self.assertEqual(w.curves,[c]);self.assertEqual(w.analysis_results,[])
        finally:
            if dialog.worker:
                dialog.worker.wait();self.app.processEvents()
            dialog.close();self.dispose(w)

    def test_density_display_scaling_preserves_derived_values(self):
        from voltscope_ui import Viewer
        w=Viewer()
        try:
            a=curve([0,1,2],[1,2,3],'V','A/cm2',name='A')
            b=curve([0,1,2],[1000,2000,3000],'V','mA/cm2',name='mA')
            w.loaded([a,b],[]);w.list.selectAll()
            self.assertEqual(len(w.plot.series),2)
            self.assertEqual(w.plot.series[0][1],w.plot.series[1][1])
            self.assertEqual(b.rows[0][1],1000.)
        finally:self.dispose(w)

    def test_rejected_parameters_do_not_add_curves(self):
        from voltscope_ui import Viewer
        from voltscope_analysis_ui import AnalysisDialog
        from PySide6.QtTest import QTest
        w=Viewer();c=curve([0,1,2],[1,2,3]);w.loaded([c],[])
        dialog=AnalysisDialog(w)
        try:
            dialog.tool.setCurrentText('Normalize area')
            dialog.compute()  # normalization without an explicit area
            deadline=time.monotonic()+5
            while dialog.worker is not None and time.monotonic()<deadline:
                self.app.processEvents();QTest.qWait(10)
            self.assertFalse(dialog.apply.isEnabled())
            self.assertIn('Area',dialog.feedback.text())
            self.assertEqual(w.curves,[c])
        finally:
            if dialog.worker:
                dialog.worker.wait();self.app.processEvents()
            dialog.close();self.dispose(w)
