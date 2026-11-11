"""VoltScope desktop entry point."""
import sys
from voltscope_data import Curve, read_dta, read_ivium, read_corrware, read_data, export_csv


def packaging_smoke_test(report_path):
    """Exercise the installed Qt app, import, analysis and bundled data in CI."""
    import json
    from math import exp
    from pathlib import Path
    from tempfile import TemporaryDirectory
    import traceback

    report = Path(report_path)
    try:
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        from voltscope_ui import Viewer
        from voltscope_analysis_ui import run
        from voltscope_biologic import __file__ as biologic_module

        app = QApplication([sys.argv[0]])
        app.setApplicationName('VoltScope')
        window = Viewer()
        window.show()
        app.processEvents()
        with TemporaryDirectory() as tmp:
            cv = Path(tmp) / 'synthetic.csv'
            points = [(i / 20, exp(-((i / 20 - .5) / .1)**2)) for i in range(21)]
            cv.write_text('Vf [V],Im [mA]\n' + '\n'.join(f'{x},{y}' for x, y in points), encoding='utf-8')
            curves = read_data(cv)
            window.loaded(curves, [])
            if not window.plot.series:
                raise RuntimeError('The imported CV was not plotted.')
            result = run('CV baseline & peaks', curves, 'Vf', 'Im', cv_model='No subtraction')
            if len(result.peaks) != 1 or abs(result.peaks[0]['potential'] - .5) > .05:
                raise RuntimeError('The synthetic CV peak was not recovered.')
        columns = Path(biologic_module).parent / 'third_party' / 'biologic_columns.json'
        if not json.loads(columns.read_text(encoding='utf-8')):
            raise RuntimeError('The bundled BioLogic column definitions are missing or empty.')
        window.close()
        window.deleteLater()
        app.sendPostedEvents(window, QEvent.Type.DeferredDelete)
        app.processEvents()
        report.write_text('VoltScope packaging smoke test passed.\n', encoding='utf-8')
        return 0
    except Exception:
        report.write_text(traceback.format_exc(), encoding='utf-8')
        return 1


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--packaging-smoke-test':
        return packaging_smoke_test(sys.argv[2])
    try:
        from PySide6.QtWidgets import QApplication
        from voltscope_ui import Viewer
    except ModuleNotFoundError as exc:
        if exc.name not in ('PySide6', 'shiboken6'):
            raise
        raise SystemExit('PySide6 is required. Run: python -m pip install -r requirements.txt')
    app = QApplication(sys.argv)
    app.setApplicationName('VoltScope')
    window = Viewer()
    window.show()
    if sys.argv[1:]:
        window.load(sys.argv[1:])
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
