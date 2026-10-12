"""PySide6 controls and a Qt painter-based plot; no plotting dependency."""
import math
import html
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, QPointF, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QKeySequence, QShortcut, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QLabel,
    QListWidget, QMainWindow, QMessageBox, QPushButton, QSplitter,
    QTextEdit, QVBoxLayout, QWidget, QLineEdit, QProgressBar, QListWidgetItem,
)
from voltscope_data import read_data, export_csv

COLORS = ['#0077b6', '#e76f51', '#2a9d8f', '#9b5de5', '#b58900', '#e63986']
FACTORS = {'A': 1, 'mA': 1e3, 'µA': 1e6, 'nA': 1e9}


def display_unit(unit, scale):
    if unit in FACTORS: return scale
    if unit == 'A/cm2': return f'{scale}/cm²'
    return unit


def display_factor(unit, scale):
    if unit in FACTORS: return FACTORS[scale] / FACTORS[unit]
    if unit == 'A/cm2': return FACTORS[scale]
    return 1


STYLE = """
QMainWindow { background: #f1f5f9; }
QWidget { color: #172b45; font-size: 13px; }
QWidget#Card { background: #ffffff; border: 1px solid #dce4ed; border-radius: 12px; }
QLabel { border: none; background: transparent; }
QLabel#Brand { font-size: 28px; font-weight: 700; color: #102a43; }
QLabel#Muted { color: #52677e; font-size: 12px; }
QLabel#Section { color: #52677e; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#Warning { background: #fff7e6; color: #805b18; padding: 10px; border-radius: 6px; }
QPushButton { background: #fff; border: 1px solid #d4deea; border-radius: 7px; padding: 9px 14px; font-weight: 600; }
QPushButton:hover { background: #edf3fa; border-color: #9cb1ca; }
QPushButton:pressed { background: #dbe8f5; }
QPushButton#Primary { background: #176b78; border-color: #176b78; color: white; }
QPushButton#Primary:hover { background: #125762; }
QPushButton:disabled { color: #94a3b8; background: #f5f7fa; border-color: #e2e8f0; }
QLineEdit, QComboBox { background: #f8fafc; border: 1px solid #dce4ed; border-radius: 6px; padding: 8px; min-height: 18px; }
QLineEdit:focus, QComboBox:focus, QPushButton:focus { border: 1px solid #176b78; }
QComboBox:disabled { color: #94a3b8; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #dceef1; selection-color: #102a43; }
QListWidget { border: none; background: white; outline: none; }
QListWidget::item { padding: 4px 6px; border-radius: 4px; border: 1px solid transparent; }
QListWidget::item:hover { background: #f1f5f9; }
QListWidget::item:selected { background: #e4f1f3; color: #123e49; border-color: #b8dadd; }
QTextEdit { background: #f8fafc; border: none; border-radius: 6px; padding: 8px; font-size: 12px; }
QSplitter::handle { background: transparent; }
QStatusBar { background: #f1f5f9; color: #52677e; border: none; }
QProgressBar { border: none; background: #dce4ed; }
QProgressBar::chunk { background: #176b78; }
"""


def section_label(text):
    label = QLabel(text)
    label.setObjectName('Section')
    return label


class ImportThread(QThread):
    result = Signal(object, object)

    def __init__(self, paths, parent):
        super().__init__(parent)
        self.paths = paths

    def run(self):
        curves, errors = [], []
        for path in self.paths:
            try:
                imported = read_data(path)
                for curve in imported:
                    if not any((Path(c.source).resolve(),c.name) == (Path(curve.source).resolve(),curve.name) for c in curves):
                        curves.append(curve)
            except (OSError, ValueError) as exc:
                errors.append(f'{path}\n{exc}')
        self.result.emit(curves, errors)


class Plot(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(420, 300)
        self.series, self.paths, self.bounds, self.origin = [], [], None, None
        self.x_label = self.y_label = ''
        self.empty_message = 'Your experiments, in focus.\n\nOpen or drop potentiostat data files to begin.'

    def rect_plot(self):
        return QRectF(90, 30, max(1, self.width()-120), max(1, self.height()-110))

    def set_series(self, series, x_label, y_label):
        self.series = series
        self.x_label, self.y_label = x_label, y_label
        self.paths = []
        for _, points, _, _ in series:
            path = QPainterPath()
            for i, (x, y) in enumerate(points):
                if i == 0: path.moveTo(x, y)
                else: path.lineTo(x, y)
            self.paths.append(path)
        self.reset()

    def reset(self):
        self.origin = None
        points = [p for _, pts, _, _ in self.series for p in pts]
        if points:
            a, z = min(p[0] for p in points), max(p[0] for p in points)
            c, d = min(p[1] for p in points), max(p[1] for p in points)
            dx, dy = z-a or max(abs(a)*.1, 1e-6), d-c or max(abs(c)*.1, 1e-6)
            self.bounds = (a-dx*.04, z+dx*.04, c-dy*.06, d+dy*.06)
        else: self.bounds = None
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('white'))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.bounds is None:
            p.setPen(QColor('#64748b'))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.empty_message)
            return
        r = self.rect_plot()
        a, z, c, d = self.bounds
        for j in range(6):
            t = j/5
            x, y = r.left()+t*r.width(), r.bottom()-t*r.height()
            p.setPen(QColor('#e5e7eb'))
            p.drawLine(QPointF(x,r.top()), QPointF(x,r.bottom()))
            p.drawLine(QPointF(r.left(),y), QPointF(r.right(),y))
            p.setPen(QColor('#334155'))
            p.drawText(QRectF(x-45,r.bottom()+5,90,22), Qt.AlignmentFlag.AlignCenter, f'{a+t*(z-a):.4g}')
            p.drawText(QRectF(2,y-12,80,24), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f'{c+t*(d-c):.4g}')
        p.save()
        p.setClipRect(r)
        p.translate(r.left(), r.bottom())
        p.scale(r.width()/(z-a), -r.height()/(d-c))
        p.translate(-a, -c)
        for i, path in enumerate(self.paths):
            pen = QPen(QColor(COLORS[i % len(COLORS)]), 1.5)
            pen.setCosmetic(True)
            p.setPen(pen)
            if len(self.series[i][1]) == 1:
                pen.setWidthF(4)
                p.setPen(pen)
                p.drawPoint(QPointF(*self.series[i][1][0]))
            else: p.drawPath(path)
        p.restore()
        p.setPen(QColor('#64748b'))
        p.drawRect(r)
        p.drawText(QRectF(r.left(),self.height()-35,r.width(),25), Qt.AlignmentFlag.AlignCenter, self.x_label)
        p.save()
        p.translate(20, r.center().y())
        p.rotate(-90)
        p.drawText(QRectF(-r.height()/2,-12,r.height(),24), Qt.AlignmentFlag.AlignCenter, self.y_label)
        p.restore()

    def wheelEvent(self, event):
        r = self.rect_plot()
        if self.bounds is None or not r.contains(event.position()):
            event.ignore()
            return
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if not delta: return
        factor = .8 if delta > 0 else 1.25
        a,z,c,d = self.bounds
        x = a+(event.position().x()-r.left())/r.width()*(z-a)
        y = d-(event.position().y()-r.top())/r.height()*(d-c)
        new = (x+(a-x)*factor,x+(z-x)*factor,y+(c-y)*factor,y+(d-y)*factor)
        if new[1] > new[0] and new[3] > new[2] and all(math.isfinite(v) for v in new):
            self.bounds = new
            self.update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect_plot().contains(event.position()):
            self.origin = (event.position(), self.bounds)

    def mouseMoveEvent(self, event):
        if self.origin is None or self.origin[1] is None: return
        pos, (a,z,c,d) = self.origin
        r = self.rect_plot()
        dx = (event.position().x()-pos.x())/r.width()*(z-a)
        dy = (event.position().y()-pos.y())/r.height()*(d-c)
        self.bounds = (a-dx,z-dx,c+dy,d+dy)
        self.update()

    def mouseReleaseEvent(self, event):
        self.origin = None

    def mouseDoubleClickEvent(self, event):
        self.reset()


class Viewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.curves, self.importer = [], None
        self.setWindowTitle('VoltScope')
        self.resize(1280,820)
        self.setMinimumSize(960,640)
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLE)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24,20,24,12)
        layout.setSpacing(18)
        self.setCentralWidget(central)
        header = QHBoxLayout()
        brand = QVBoxLayout()
        brand.setSpacing(3)
        title = QLabel('VoltScope')
        title.setObjectName('Brand')
        brand.addWidget(title)
        subtitle = QLabel('Electrochemistry Data Visualization & Analysis')
        subtitle.setObjectName('Muted')
        brand.addWidget(subtitle)
        header.addLayout(brand)
        header.addStretch()
        self.open_button = QPushButton('＋  Open data')
        self.open_button.setObjectName('Primary')
        self.export_button = QPushButton('Export CSV…')
        self.open_button.clicked.connect(self.open)
        self.export_button.clicked.connect(self.export)
        self.open_button.setToolTip('Open Gamry DTA, Ivium IDF/IDS, or Corrware COR files (Ctrl/Cmd+O). You can also drop files into this window.')
        self.export_button.setToolTip('Export every row and original column of the selected curves, in original units.')
        header.addWidget(self.open_button)
        header.addWidget(self.export_button)
        layout.addLayout(header)
        body = QSplitter()
        body.setHandleWidth(12)
        layout.addWidget(body,1)
        sidebar = QWidget()
        sidebar.setObjectName('Card')
        sidebar.setMinimumWidth(260)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16,18,16,16)
        side.setSpacing(12)
        side.addWidget(section_label('DATA LIBRARY'))
        self.library_count = QLabel('No curves loaded')
        self.library_count.setObjectName('Muted')
        side.addWidget(self.library_count)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search files or curves…')
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter_curves)
        side.addWidget(self.search)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setWordWrap(False)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setSpacing(1)
        side.addWidget(self.list,3)
        self.list.itemSelectionChanged.connect(self.draw)
        hint = QLabel('Ctrl/Cmd-click to overlay • Shift-click for a range')
        hint.setObjectName('Muted')
        hint.setWordWrap(True)
        side.addWidget(hint)
        buttons = QHBoxLayout()
        side.addLayout(buttons)
        self.select_button = QPushButton('Select all')
        self.clear_button = QPushButton('Clear library')
        self.select_button.clicked.connect(self.list.selectAll)
        self.clear_button.clicked.connect(self.clear)
        buttons.addWidget(self.select_button)
        buttons.addWidget(self.clear_button)
        side.addWidget(section_label('EXPERIMENT DETAILS'))
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText('Select a curve to view its experiment metadata.')
        side.addWidget(self.details,2)
        body.addWidget(sidebar)
        plot_area = QWidget()
        plot_area.setObjectName('Card')
        plot_layout = QVBoxLayout(plot_area)
        plot_layout.setContentsMargins(18,18,18,12)
        plot_layout.setSpacing(12)
        heading = QHBoxLayout()
        heading.addWidget(section_label('TRACE EXPLORER'))
        heading.addStretch()
        self.plot_count = QLabel('Ready to explore')
        self.plot_count.setObjectName('Muted')
        heading.addWidget(self.plot_count)
        plot_layout.addLayout(heading)
        controls = QHBoxLayout()
        self.xbox, self.ybox, self.scale = QComboBox(), QComboBox(), QComboBox()
        self.scale.addItems(list(FACTORS))
        self.scale.setCurrentText('µA')
        for label, box in [('X axis',self.xbox),('Y axis',self.ybox),('Current unit',self.scale)]:
            field = QVBoxLayout()
            field.setSpacing(5)
            caption = QLabel(label)
            caption.setObjectName('Muted')
            if box is self.scale: self.scale_caption = caption
            field.addWidget(caption)
            field.addWidget(box)
            controls.addLayout(field,1)
            box.currentTextChanged.connect(self.draw)
        self.xbox.setToolTip('T: time • Vf: measured potential • Vset: programmed potential. Units follow the imported data.')
        self.ybox.setToolTip('Im: current • J: current density. Choose another imported numeric column to explore it.')
        self.scale.setToolTip('Changes the plot display only; CSV retains original units.')
        reset = QPushButton('Reset view')
        reset.clicked.connect(lambda: self.plot.reset())
        reset.setToolTip('Restore the full data range. You can also double-click the plot.')
        controls.addWidget(reset,0,Qt.AlignmentFlag.AlignBottom)
        plot_layout.addLayout(controls)
        self.warning = QLabel()
        self.warning.setObjectName('Warning')
        self.warning.setWordWrap(True)
        self.warning.hide()
        plot_layout.addWidget(self.warning)
        self.legend = QLabel()
        self.legend.setWordWrap(True)
        self.legend.setTextFormat(Qt.TextFormat.RichText)
        plot_layout.addWidget(self.legend)
        self.plot = Plot()
        plot_layout.addWidget(self.plot,1)
        foot = QLabel('Scroll to zoom  ·  Drag to pan  ·  Double-click to reset')
        foot.setObjectName('Muted')
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plot_layout.addWidget(foot)
        body.addWidget(plot_area)
        body.setSizes([300,900])
        self.progress = QProgressBar()
        self.progress.setRange(0,0)
        self.progress.setMaximumWidth(150)
        self.progress.setMaximumHeight(5)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        for key, callback in [(QKeySequence.StandardKey.Open,self.open),('Ctrl+Shift+E',self.export)]:
            shortcut = QShortcut(QKeySequence(key),self)
            shortcut.activated.connect(callback)
        self.draw()
        self.statusBar().showMessage('Ready • Open or drop Gamry, Ivium, Corrware, Metrohm, or DropView files to begin.')

    def filter_curves(self, text):
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(text.casefold() not in item.text().casefold())

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in ('.dta','.idf','.ids','.cor','.nox','.ocw','.ici','.icw','.mtc','.mta','.mtd') for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in ('.dta','.idf','.ids','.cor','.nox','.ocw','.ici','.icw','.mtc','.mta','.mtd')]
        if paths and self.importer is None:
            self.load(paths)
            event.acceptProposedAction()

    def selected(self):
        return [self.curves[self.list.row(item)] for item in self.list.selectedItems()]

    def open(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Open potentiostat data', '', 'Potentiostat data (*.DTA *.dta *.idf *.IDF *.ids *.IDS *.cor *.COR *.nox *.NOX *.ocw *.OCW *.ici *.ICI *.icw *.ICW *.mtc *.MTC *.mta *.MTA *.mtd *.MTD);;All files (*)')
        if paths: self.load(paths)

    def load(self, paths):
        if self.importer is not None: return
        for button in [self.open_button,self.clear_button]: button.setEnabled(False)
        self.progress.show()
        self.open_button.setText('Importing…')
        self.statusBar().showMessage('Importing data…')
        self.importer = ImportThread(paths,self)
        self.importer.result.connect(self.loaded)
        self.importer.finished.connect(self.import_finished)
        self.importer.start()

    def import_finished(self):
        self.importer.deleteLater()
        self.importer = None
        self.open_button.setEnabled(True)
        self.clear_button.setEnabled(bool(self.curves))
        self.progress.hide()
        self.open_button.setText('＋  Open data')

    def loaded(self, curves, errors):
        start = len(self.curves)
        self.list.blockSignals(True)
        self.curves.extend(curves)
        for c in curves:
            item = QListWidgetItem(f'{c.name} · {Path(c.source).name}')
            item.setToolTip(f'{c.name}\n{c.source}\n{len(c.rows):,} points')
            self.list.addItem(item)
        cols = sorted({col for c in self.curves for j,col in enumerate(c.columns) if any(isinstance(row[j],(int,float)) for row in c.rows)})
        for box in [self.xbox,self.ybox]:
            box.blockSignals(True)
            box.clear()
            box.addItems(cols)
        if curves:
            chosen = next((i for i in range(start,len(self.curves)) if not self.curves[i].metadata.get('CONTAINER')),start)
            c = self.curves[chosen]
            self.list.clearSelection()
            self.list.item(chosen).setSelected(True)
            self.xbox.setCurrentText('Vf' if c.metadata.get('TAG') in ('CV','DPV') and 'Vf' in c.columns else 'T' if 'T' in c.columns else cols[0])
            self.ybox.setCurrentText('Vf' if c.metadata.get('TAG') == 'CHRONOP' and 'Vf' in c.columns else 'Im' if 'Im' in c.columns else 'J' if 'J' in c.columns else 'I1' if 'I1' in c.columns else cols[-1])
        self.list.blockSignals(False)
        for box in [self.xbox,self.ybox]: box.blockSignals(False)
        self.filter_curves(self.search.text())
        self.draw()
        if errors: QMessageBox.warning(self,'Import errors','\n\n'.join(errors))

    def clear(self):
        self.list.blockSignals(True)
        self.list.clear()
        self.curves.clear()
        self.search.clear()
        self.list.blockSignals(False)
        self.xbox.clear()
        self.ybox.clear()
        self.draw()

    def draw(self, *_):
        if not hasattr(self,'plot'): return
        series, skipped, details = [], [], []
        x,y,scale = self.xbox.currentText(),self.ybox.currentText(),self.scale.currentText()
        for c in self.selected():
            details.append(f'{Path(c.source).name}\n{c.name}: {len(c.rows):,} rows')
            details.extend(f'{key}: {c.metadata[key]}' for key in ['TAG','TITLE','DATE','TIME','PSTAT','AREA','SCANRATE','EXPERIMENTABORTED','STATUS','SOURCE_COLUMNS','UNIT_NOTE','TECHNIQUE','CHANNEL','COLUMN_SOURCE','Reference Type','Reference Potential'] if key in c.metadata)
            details.append('')
            if x not in c.columns or y not in c.columns:
                skipped.append(c.name)
                continue
            xi,yi = c.columns.index(x),c.columns.index(y)
            xu,yu = c.units[xi],c.units[yi]
            if series and (xu,yu) != series[0][2:4]:
                skipped.append(c.name)
                continue
            xf,yf = display_factor(xu, scale), display_factor(yu, scale)
            points = [(r[xi]*xf,r[yi]*yf) for r in c.rows if isinstance(r[xi],(int,float)) and isinstance(r[yi],(int,float)) and math.isfinite(r[xi]) and math.isfinite(r[yi])]
            if points: series.append((c,points,xu,yu))
            else: skipped.append(c.name)
        self.details.setPlainText('\n'.join(details))
        xu,yu = series[0][2:4] if series else ('','')
        self.scale_caption.setText('Current density unit' if 'A/cm2' in (xu,yu) else 'Current unit')
        self.scale.setToolTip('Scales current (A) or current density (A/cm²) for display only; CSV retains original units.')
        self.plot.empty_message = ('Select curves in the data library to begin.' if not self.selected() else 'No compatible data for these axes.\nChoose different axes or curves.') if self.curves else 'Your experiments, in focus.\n\nOpen or drop potentiostat data files to begin.'
        self.plot.set_series(series,f'{x} [{display_unit(xu, scale)}]',f'{y} [{display_unit(yu, scale)}]')
        self.legend.setText(' &nbsp; &nbsp; '.join(f'<span style="color:{COLORS[i % len(COLORS)]}">●</span> {html.escape(c.name)} <span style="color:#64748b">{html.escape(Path(c.source).name)}</span>' for i,(c,_,_,_) in enumerate(series)))
        self.legend.setVisible(bool(series))
        self.library_count.setText(f'{len({c.source for c in self.curves})} files · {len(self.curves)} curves' if self.curves else 'No curves loaded')
        self.plot_count.setText(f'{len(series)} traces · {sum(len(pts) for _,pts,_,_ in series):,} points' if series else 'Ready to explore')
        self.export_button.setEnabled(bool(self.selected()))
        self.select_button.setEnabled(bool(self.curves))
        self.clear_button.setEnabled(bool(self.curves) and self.importer is None)
        for box in [self.xbox,self.ybox,self.scale]: box.setEnabled(bool(self.curves))
        self.scale.setEnabled(bool(series) and any(u in FACTORS or u == 'A/cm2' for u in (xu,yu)))
        self.warning.setText('Some selected curves cannot be plotted with these axes or units: ' + ', '.join(skipped))
        self.warning.setVisible(bool(skipped))
        for i in range(self.list.count()):
            c = self.curves[i]
            index = next((j for j,(curve,_,_,_) in enumerate(series) if curve is c),None)
            pixmap = QPixmap(12,12)
            pixmap.fill(QColor(COLORS[index % len(COLORS)] if index is not None else '#cbd5e1'))
            self.list.item(i).setIcon(QIcon(pixmap))
        self.statusBar().showMessage(f'{len(series)} curves • {sum(len(pts) for _,pts,_,_ in series):,} points • Wheel: zoom • Drag: pan • Double-click: reset' + (f' • Skipped incompatible axes/units or empty data: {", ".join(skipped)}' if skipped else ''))

    def export(self):
        curves = self.selected()
        if not curves:
            QMessageBox.information(self,'Select curves','Select one or more curves to export.')
            return
        try:
            output = Path(__file__).resolve().parent/'outputs'
            output.mkdir(exist_ok=True)
            path, _ = QFileDialog.getSaveFileName(self,'Export selected CSV',str(output/'voltscope_data.csv'),'CSV (*.csv)')
            if not path: return
            if not Path(path).suffix: path += '.csv'
            protected = {Path(c.source).resolve() for c in self.curves}
            protected.update(Path(p).resolve() for c in self.curves for p in c.metadata.get('COMPANION_FILES', []))
            if Path(path).resolve() in protected:
                raise ValueError('Choose a different path; source experimental files cannot be overwritten.')
            export_csv(curves,path)
            self.statusBar().showMessage(f'Exported {sum(len(c.rows) for c in curves):,} rows to {path}. Original units and all columns retained.')
        except (OSError,ValueError) as exc: QMessageBox.critical(self,'Export failed',str(exc))

    def closeEvent(self,event):
        if self.importer is not None and self.importer.isRunning():
            self.statusBar().showMessage('Import is still running. Close the window after it finishes.')
            event.ignore()
        else: event.accept()
