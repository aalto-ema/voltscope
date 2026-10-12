"""Synthetic parser/export checks and offscreen Qt interaction checks."""
import csv
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt, QPoint, QPointF, QCoreApplication, QEvent
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from voltscope_data import read_data, export_csv
from voltscope_ui import Viewer

DTA = ('TAG\tCHRONOA\nEXPERIMENTABORTED\tTOGGLE\tT\nCURVE\tTABLE\t3\n'
       '\tPt\tT\tVf\tIm\tOver\n\t#\ts\tV vs. Ref.\tA\tbits\n'
       '\t0\t0,2\t-0,7\t1,0E-6\t....\n'
       '\t1\t0,4\t-0,3\t2,0E-6\t....\n'
       '\t2\t0,6\t-0,3\t3,0E-6\t....\n')

def ivium(method, rows, serial='SYNTHETIC', start='2026-01-01'):
    return (f'QR=synthetic\r\nMethod={method}\r\nTechnique=ChronoAmperometry\r\nserialnumber={serial}\r\nstarttime={start}\r\n'
            'Report.Process data=endcondition: Scan Aborted\x1c\x1e\r\nprimary_data    \r\x003         \r\n'
            f'{len(rows)}\r\n'+''.join(' '.join(row)+'\r\n' for row in rows)).encode()

class Checks(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.dta = self.base/'synthetic.DTA'
        self.dta.write_text(DTA)
        self.ids = self.base/'synthetic.ids'
        self.ids.write_bytes(ivium('CyclicVoltammetry',[['-.7','1e-6','-.699'],['.7','2e-6','.699']])+ivium('CyclicVoltammetry',[['.7','3e-6','.699']],serial='SECOND',start='2026-01-02'))
        self.idf = self.base/'synthetic.idf'
        self.idf.write_bytes(ivium('Transients',[['.2','2e-5','-.7'],['.4','3e-5','-.3']]))
        self.window = Viewer()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        if self.window.importer:
            self.window.importer.wait()
            self.app.processEvents()
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.tmp.cleanup()

    def wait_import(self):
        deadline = time.monotonic()+5
        while self.window.importer is not None and time.monotonic()<deadline:
            self.app.processEvents()
            QTest.qWait(10)
        self.assertIsNone(self.window.importer)

    def test_parse_and_export(self):
        curves=read_data(self.dta)+read_data(self.ids)+read_data(self.idf)
        self.assertEqual([len(c.rows) for c in curves],[3,2,1,2])
        self.assertEqual(curves[0].rows[0],[0.,.2,-.7,1e-6,'....'])
        self.assertEqual(curves[2].metadata['PSTAT'],'SECOND')
        self.assertEqual(curves[-1].metadata['STATUS'],'Scan Aborted')
        out=self.base/'export.csv'
        export_csv(curves,out)
        with out.open() as f: rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),8)
        self.assertEqual(rows[0]['Im [A]'],'1e-06')
        self.assertEqual(rows[-1]['Vset [V vs. Ref.]'],'')
        self.assertEqual(rows[0]['Over [bits]'],'....')
        bad=self.base/'bad.idf'
        bad.write_bytes(self.idf.read_bytes().replace(b'2\r\n.2',b'3\r\n.2'))
        with self.assertRaises(ValueError): read_data(bad)

    def test_controls_plot_and_csv_dialog(self):
        w=self.window
        with patch.object(QFileDialog,'getOpenFileNames',return_value=([str(self.dta),str(self.ids)],'')):
            QTest.mouseClick(w.open_button,Qt.MouseButton.LeftButton)
        self.wait_import()
        self.assertEqual(len(w.curves),3)
        self.assertEqual(w.xbox.currentText(),'T')
        self.assertIn('EXPERIMENTABORTED: T',w.details.toPlainText())
        w.list.selectAll()
        w.xbox.setCurrentText('Vf')
        self.assertEqual(len(w.plot.series),3)
        self.assertEqual(w.plot.series[0][1][0][1],1.)
        w.scale.setCurrentText('mA')
        self.assertAlmostEqual(w.plot.series[0][1][0][1],.001)
        self.assertEqual(w.curves[0].rows[0][3],1e-6)
        original=w.plot.bounds
        center=w.plot.rect_plot().center()
        wheel=QWheelEvent(center,center,QPoint(0,0),QPoint(0,120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
        self.app.sendEvent(w.plot,wheel)
        self.assertLess(w.plot.bounds[1]-w.plot.bounds[0],original[1]-original[0])
        before=w.plot.bounds
        QTest.mousePress(w.plot,Qt.MouseButton.LeftButton,pos=center.toPoint())
        QTest.mouseMove(w.plot,center.toPoint()+QPoint(30,20))
        QTest.mouseRelease(w.plot,Qt.MouseButton.LeftButton,pos=center.toPoint()+QPoint(30,20))
        self.assertNotEqual(w.plot.bounds,before)
        QTest.mouseDClick(w.plot,Qt.MouseButton.LeftButton,pos=center.toPoint())
        self.assertEqual(w.plot.bounds,original)
        out=self.base/'ui.csv'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(out),'')):
            w.export()
        with out.open() as f: rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),6)
        self.assertEqual(rows[0]['Im [A]'],'1e-06')
        self.assertFalse(w.plot.grab().isNull())
        w.xbox.setCurrentText('T')
        self.assertIn('Skipped',w.statusBar().currentMessage())
        w.clear()
        self.assertEqual(w.curves,[])
        self.assertIsNone(w.plot.bounds)

    def test_corrware_modes_units_and_validation(self):
        w=self.window
        for experiment,tag,yaxis in [('Cyclic Voltammogram','CV','J'),('Potentiostatic','CHRONOA','J'),('Galvanostatic','CHRONOP','Vf')]:
            path=self.base/'synthetic.cor'
            text=('CORRW ASCII\nCorrWare for Windows: Version synthetic\n'+experiment+'\n'
                  'Date: 01-01-2026    Time: 12:00:00\n'
                  'Begin Experiment: '+experiment+'\nSurface Area: 2\nPstat Title: Synthetic PAR\n'
                  'Data Points: 3\nE(Volts)\tI(A/cm2)\tT(Seconds)\nEnd Comments\n'
                  '-0,5\t-2,0E-3\t0\n0.5\t3e-3\t1\n-0.5\t4e-3\t2\n')
            path.write_text(text)
            curve=read_data(path)[0]
            self.assertEqual(curve.columns,['Vf','J','T'])
            self.assertEqual(curve.units,['V','A/cm2','s'])
            self.assertEqual(curve.metadata['TAG'],tag)
            self.assertEqual(curve.rows[0],[-.5,-.002,0.])
            w.clear()
            w.load([str(path)])
            self.wait_import()
            self.assertEqual(w.ybox.currentText(),yaxis)
            self.assertEqual(w.xbox.currentText(),'Vf' if tag=='CV' else 'T')
            if yaxis == 'J':
                self.assertEqual(w.plot.y_label,'J [µA/cm²]')
                self.assertEqual(w.plot.series[0][1][0][1],-2000.)
            output=self.base/'cor.csv'
            export_csv([curve],output)
            with output.open() as f: exported=list(csv.DictReader(f))
            self.assertEqual(exported[0]['J [A/cm2]'],'-0.002')
            self.assertNotIn('Im [A]',exported[0])
            path.write_text(text.replace('Data Points: 3','Data Points: 4'))
            with self.assertRaises(ValueError): read_data(path)
            path.write_text(text.replace('3e-3','invalid'))
            with self.assertRaises(ValueError): read_data(path)

    def test_metrohm_ui_and_companion_deduplication(self):
        from test_metrohm import synthetic_nox
        nova=self.base/'synthetic.nox'
        nova.write_bytes(synthetic_nox())
        ocw=self.base/'old.ocw';ici=self.base/'old.ici';icw=self.base/'old.icw'
        ocw.write_text('E / V,I / A\n-.5 1e-6\n.5 2e-6\n')
        ici.write_text('[CV]\nxaxis.axtext=E / V\nyaxis.axtext=I / A\n')
        icw.write_text('200,40\n')
        w=self.window
        w.load([str(nova),str(ocw),str(ici),str(icw)])
        self.wait_import()
        self.assertEqual(len(w.curves),2)
        self.assertEqual(w.xbox.currentText(),'Vf')
        self.assertEqual(w.ybox.currentText(),'Im')
        w.list.selectAll()
        self.assertEqual(len(w.plot.series),2)
        self.assertEqual(w.plot.y_label,'Im [µA]')
        self.assertFalse(w.plot.grab().isNull())
        out=self.base/'metrohm.csv'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(out),'')):
            w.export()
        with out.open() as f: rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),4)
        original=ici.read_bytes()
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(ici),'')), patch.object(QMessageBox,'critical') as error:
            w.export()
            error.assert_called_once()
        self.assertEqual(ici.read_bytes(),original)

    def test_dropview_axes_arrays_and_microampere_units(self):
        from test_dropview import document,curve_xml
        w=self.window
        for tech,extension,xaxis in [('CV','.mtc','Vf'),('AD','.mta','T'),('DPV','.mtd','Vf')]:
            path=self.base/('synthetic'+extension)
            path.write_text(document(curve_xml(tech)))
            w.clear();w.load([str(path)]);self.wait_import()
            self.assertEqual(w.xbox.currentText(),xaxis)
            self.assertEqual(w.ybox.currentText(),'I1')
            self.assertEqual(w.plot.series[0][1][0][1],1.25)
            self.assertEqual(w.plot.y_label,'I1 [µA]')
            self.assertTrue(w.scale.isEnabled())
            w.ybox.setCurrentText('I2')
            self.assertEqual(w.plot.series[0][1][0][1],0.)
            self.assertFalse(w.plot.grab().isNull())
        path.write_text(document(curve_xml('CV',units='unit="µA"')))
        w.clear();w.load([str(path)]);self.wait_import()
        self.assertTrue(w.scale.isEnabled())
        w.scale.setCurrentText('mA')
        self.assertAlmostEqual(w.plot.series[0][1][0][1],.00125)
        self.assertEqual(w.curves[0].rows[0][2],1.25)

    def test_library_search_and_empty_controls(self):
        w=self.window
        self.assertFalse(w.export_button.isEnabled())
        self.assertFalse(w.xbox.isEnabled())
        w.load([str(self.dta),str(self.ids)])
        self.wait_import()
        w.search.setText('synthetic.DTA')
        self.assertFalse(w.list.item(0).isHidden())
        self.assertTrue(w.list.item(1).isHidden())
        self.assertEqual(len(w.curves),3)
        w.search.clear()
        self.assertFalse(w.list.item(1).isHidden())
        w.list.clearSelection()
        self.assertFalse(w.export_button.isEnabled())
        self.assertIsNone(w.plot.bounds)
        w.list.selectAll()
        self.assertTrue(w.export_button.isEnabled())
        w.xbox.setCurrentText('T')
        self.assertFalse(w.warning.isHidden())
        w.xbox.setCurrentText('Vf')
        self.assertTrue(w.warning.isHidden())
        self.assertIn('●',w.legend.text())

    def test_import_failure_and_source_protection(self):
        w=self.window
        with patch.object(QMessageBox,'warning') as warning:
            w.load([str(self.dta),str(self.base/'missing.DTA')])
            self.wait_import()
            warning.assert_called_once()
        original=self.dta.read_bytes()
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(self.dta),'')), patch.object(QMessageBox,'critical') as error:
            w.export()
            error.assert_called_once()
        self.assertEqual(self.dta.read_bytes(),original)

if __name__=='__main__': unittest.main()
