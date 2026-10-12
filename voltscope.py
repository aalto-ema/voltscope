"""VoltScope desktop entry point."""
import sys
from voltscope_data import Curve, read_dta, read_ivium, read_corrware, read_data, export_csv


def main():
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
