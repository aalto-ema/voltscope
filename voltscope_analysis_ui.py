"""Selection, preview, derived-data and audit controls for VoltScope analysis."""
from pathlib import Path
import html
import math

from PySide6.QtCore import Qt, QThread, Signal, QSize, QRectF, QTimer
from PySide6.QtGui import QPainter, QImage, QTextDocument
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QFormLayout, QLineEdit, QSpinBox, QListWidget, QListWidgetItem,
    QSplitter, QWidget, QScrollArea, QTabWidget, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QFileDialog, QMessageBox, QTextEdit, QCheckBox)
from voltscope_analysis import run, Selection, branches, values, export_results
from voltscope_paths import output_directory

TOOLS = {
    'CV baseline & peaks': 'Fit a background on each CV sweep, subtract it, and measure signed peak currents. No scan rate or time is needed. Background windows are shown in blue; you can set them by dragging on the raw plot.',
    'Assign column units': 'Assign explicitly known meanings/units to legacy or unlabelled data. Values are copied unchanged; this does not convert between units.',
    'Normalize area': 'Convert current ↔ current density using an explicit electrode area. Each selected source receives the same stated area.',
    'Reference conversion': 'Convert a selected potential axis using explicit reference offsets, or a pH/temperature-defined RHE target. Optional equilibrium subtraction gives overpotential.',
    'iR correction': 'Correct a potential axis with signed measured current, resistance and compensation fraction. Current-density inputs also need electrode area.',
    'Smooth': 'Savitzky–Golay filtering in acquisition sample order. Window length is a number of points; source data stays unchanged.',
    'Derivative': 'Differentiate a signal with respect to its actual X coordinates. Select one strictly monotonic branch; repeated X values are rejected.',
    'Integrate charge': 'Integrate signed current over measured time with the composite trapezoidal rule. Density produces charge density unless area is supplied.',
    'Peak and charge': 'Analyze a single potential branch. Preview an explicit baseline, detect local signed peaks and integrate charge using measured time or your supplied scan rate.',
    'Tafel fit': 'Fit E versus log10|I| or log10|J| on a chosen monotonic interval of one current sign. Review slope, uncertainty, residuals and R².',
    'Split scans / cycles': 'Use stored cycle IDs or actual potential reversals. No equal-length file slicing. Reversal boundaries are shared explicitly.',
    'Join pulses': 'Join selected time-series in the order below with explicit time shifts and gap. Native time and row/source provenance remain available.',
    'Pulse charges': 'Calculate signed charge for each selected time-series in the order below. No file reversal or interpolation.',
    'Coordinate rotation': 'Rotate dimensionless coordinates using explicit native-unit scales and origins. This is a geometric transform, not a physical correction.',
}


class AnalysisWorker(QThread):
    completed = Signal(object, str)

    def __init__(self, operation, curves, x, y, selection, params, parent):
        super().__init__(parent)
        self.args = operation, curves, x, y, selection
        self.params = params

    def run(self):
        try:
            self.completed.emit(run(*self.args, **self.params), '')
        except Exception as exc:
            self.completed.emit(None, str(exc))


def render_plot(plot, path):
    """Render the current axes/view, including labels, to PNG or vector SVG."""
    path = Path(path)
    if not plot.series:
        raise ValueError('There is no plotted data to save.')
    from voltscope_ui import COLORS
    labels = getattr(plot, 'trace_labels', [])
    if len(labels) != len(plot.series):
        labels = [c.name+' · '+Path(c.source).name for c,_,_,_ in plot.series]
    legend = QTextDocument()
    legend.setDefaultFont(plot.font())
    legend.setTextWidth(max(100,plot.width()-40))
    legend.setHtml(' &nbsp; '.join(f'<span style="color:{COLORS[i%len(COLORS)]}">●</span> '+html.escape(label)
                                 for i,label in enumerate(labels[:20])) +
                   (f' · {len(labels)-20} additional traces' if len(labels)>20 else ''))
    size = QSize(plot.width(),plot.height()+math.ceil(legend.size().height())+20)
    if path.suffix.lower() == '.svg':
        target = QSvgGenerator()
        target.setFileName(str(path))
        target.setSize(size)
        target.setViewBox(QRectF(0,0,size.width(),size.height()).toRect())
        target.setTitle('VoltScope trace explorer')
        target.setDescription(f'{plot.x_label} vs {plot.y_label}')
    elif path.suffix.lower() == '.png':
        target = QImage(size.width()*2, size.height()*2, QImage.Format.Format_ARGB32)
        target.fill(Qt.GlobalColor.white)
        target.setDevicePixelRatio(2)
    else:
        raise ValueError('Choose PNG or SVG.')
    painter = QPainter()
    if not painter.begin(target):
        raise ValueError('Could not open the image output.')
    try:
        plot.render(painter, plot.rect().topLeft())
        painter.translate(20,plot.height())
        legend.drawContents(painter)
    finally:
        painter.end()
    if isinstance(target, QImage) and not target.save(str(path)):
        raise ValueError('Could not save the image output.')


class ResultView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        from voltscope_ui import Plot
        layout = QVBoxLayout(self)
        self.choice = QComboBox()
        layout.addWidget(self.choice)
        self.plot = Plot()
        self.plot.setMinimumSize(380,240)
        self.raw_plot = Plot()
        self.raw_plot.setMinimumSize(380,240)
        self.tabs=QTabWidget()
        self.tabs.addTab(self.plot,'Analysis')
        self.tabs.addTab(self.raw_plot,'Raw + baseline')
        self.tabs.setTabVisible(1,False)
        layout.addWidget(self.tabs,1)
        self.legend = QLabel()
        self.legend.setWordWrap(True)
        layout.addWidget(self.legend)
        self.metrics = QTableWidget(0,4)
        self.metrics.setHorizontalHeaderLabels(['Source curve','Result','Value','Unit'])
        self.metrics.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.metrics.setAlternatingRowColors(True)
        self.metrics.setMaximumHeight(180)
        layout.addWidget(self.metrics)
        self.notes = QTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setMaximumHeight(100)
        layout.addWidget(self.notes)
        self.choice.currentIndexChanged.connect(self.draw)
        self.result = None
        self.metrics.hide();self.notes.hide()
        self.plot.empty_message = 'Choose an operation and preview it.\n\nDerived data and comparison traces appear here.'

    def set_result(self, result):
        self.result = result
        self.choice.blockSignals(True)
        self.choice.clear()
        self.choice.addItems([c.name for c in result.curves])
        self.choice.blockSignals(False)
        cv=result.operation=='CV baseline & peaks'
        self.tabs.setTabText(0,'Corrected peaks' if cv else 'Analysis');self.tabs.setTabVisible(1,cv)
        self.metrics.setVisible(bool(result.metrics));self.notes.show()
        if cv:
            self.metrics.setColumnCount(7)
            self.metrics.setHorizontalHeaderLabels(['Curve / sweep','Polarity','Peak E','Peak I','Units (E / I)','SNR','Quality'])
            self.metrics.setRowCount(len(result.peaks))
            for i,peak in enumerate(result.peaks):
                row=[f'{peak["source_curve"]} / {peak["sweep"]}',peak['polarity'],f'{peak["potential"]:.7g}',
                     f'{peak["current"]:.7g}',peak['potential_unit']+' / '+peak['current_unit'],
                     f'{peak["snr"]:.1f}' if peak['snr'] is not None else '—',peak['quality']]
                for j,value in enumerate(row):
                    item=QTableWidgetItem(value);item.setToolTip(value+'\n'+peak['method'])
                    self.metrics.setItem(i,j,item)
            self.metrics.resizeColumnsToContents()
            self.notes.setPlainText('\n'.join(dict.fromkeys(result.notes)))
            self.draw();return
        self.metrics.setColumnCount(4)
        self.metrics.setHorizontalHeaderLabels(['Source curve','Result','Value','Unit'])
        self.metrics.setRowCount(len(result.metrics))
        for i, metric in enumerate(result.metrics):
            for j,value in enumerate([metric['source_curve'],metric['metric'],f"{metric['value']:.8g}",metric['unit']]):
                self.metrics.setItem(i,j,QTableWidgetItem(str(value)))
        self.metrics.resizeColumnsToContents()
        self.notes.setPlainText('\n'.join(dict.fromkeys(result.notes)) +
                                f'\nRun: {result.id} · {result.created}')
        self.draw()

    def draw(self, *_):
        if self.result is None or self.choice.currentIndex() < 0:
            return
        c = self.result.curves[self.choice.currentIndex()]
        x = c.metadata['DEFAULT_X']; y = c.metadata['DEFAULT_Y']
        xi, yi = c.columns.index(x), c.columns.index(y)
        xu, yu = c.units[xi], c.units[yi]
        if c.metadata.get('CV_ANALYSIS'):
            columns=c.metadata['CV_COLUMNS'];info=c.metadata['CV_BACKGROUND']
            raw=c.columns.index(columns['original']);base=c.columns.index(columns['baseline']);det=c.columns.index(columns['detection'])
            raw_series=[(c,[(r[xi],r[raw]) for r in c.rows],xu,yu),(c,[(r[xi],r[base]) for r in c.rows],xu,yu)]
            series=[(c,[(r[xi],r[yi]) for r in c.rows],xu,yu),(c,[(r[xi],r[det]) for r in c.rows],xu,yu)]
            labels=['Unsmoothed corrected current','Detection signal']
            for n,peak in enumerate(c.metadata['CV_PEAKS'],1):
                series.append((c,[(peak['potential'],peak['current'])],xu,yu));labels.append('Peak '+str(n))
            self.plot.trace_labels=labels;self.raw_plot.trace_labels=['Measured current','Fitted background']
            bands=[]
            windows=info['windows']
            if windows:bands=[(windows[0],windows[1],'#0284c7'),(windows[2],windows[3],'#0284c7')]
            self.plot.bands=bands;self.raw_plot.bands=bands
            self.plot.set_series(series,f'{x} [{xu}]',f'Corrected current [{yu}]')
            self.raw_plot.set_series(raw_series,f'{x} [{xu}]',f'Current [{yu}]')
            self.legend.setText('Blue bands: background fit windows · '+ ' · '.join(labels))
            return
        self.plot.bands=[];self.raw_plot.bands=[]
        series = [(c,[(row[xi],row[yi]) for row in c.rows],xu,yu)]
        legends = [y]
        for column in c.metadata.get('ANALYSIS_OVERLAYS',[]):
            if column in c.columns and column != y:
                j=c.columns.index(column)
                if c.units[j] == yu:
                    series.append((c,[(row[xi],row[j]) for row in c.rows],xu,yu)); legends.append(column)
        original_y = self.result.parameters.get('y_column')
        if original_y in c.columns and original_y != y:
            j=c.columns.index(original_y)
            if c.units[j] == yu and x == self.result.parameters.get('x_column'):
                series.append((c,[(row[xi],row[j]) for row in c.rows],xu,yu)); legends.append('Original '+original_y)
        for n,k in enumerate(c.metadata.get('PEAK_INDICES',[]),1):
            if 0 <= k < len(c.rows):
                series.append((c,[(c.rows[k][xi],c.rows[k][yi])],xu,yu));legends.append('Peak '+str(n))
        self.plot.trace_labels = legends
        self.plot.set_series(series,f'{x} [{xu}]',f'{y} [{yu}]')
        self.legend.setText('   ·   '.join(legends))


class AnalysisDialog(QDialog):
    def __init__(self, viewer):
        super().__init__(viewer)
        self.viewer = viewer
        self.result = None
        self.worker = None
        self.setWindowTitle('VoltScope · Analysis workbench')
        self.resize(1120,800)
        self.setMinimumSize(940,680)
        layout = QVBoxLayout(self)
        heading = QLabel('Analyze selected curves')
        heading.setObjectName('Brand')
        layout.addWidget(heading)
        self.tool = QComboBox(); self.tool.addItems(TOOLS)
        layout.addWidget(self.tool)
        self.description = QLabel(); self.description.setWordWrap(True)
        layout.addWidget(self.description)
        split=QSplitter(); layout.addWidget(split,1)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setMinimumWidth(330)
        config=QWidget(); self.config=config; self.form=QFormLayout(config)
        self.sources=QListWidget();self.sources.setMaximumHeight(105)
        for c in viewer.selected():
            item=QListWidgetItem(c.name+' · '+Path(c.source).name)
            item.setData(Qt.ItemDataRole.UserRole,c)
            self.sources.addItem(item)
        self.form.addRow('Input order',self.sources)
        order=QWidget();buttons=QHBoxLayout(order);buttons.setContentsMargins(0,0,0,0)
        for label,delta in [('Move up',-1),('Move down',1)]:
            b=QPushButton(label);b.clicked.connect(lambda _,d=delta:self.reorder(d));buttons.addWidget(b)
        self.form.addRow(order)
        self.form.setRowVisible(order,self.sources.count()>1)
        self.sources.setMaximumHeight(min(105,max(36,self.sources.count()*24+8)))
        sources=[self.sources.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.sources.count())]
        common=[col for col in sources[0].columns if all(col in c.columns for c in sources)]
        self.x=QComboBox();self.y=QComboBox();self.x.addItems(common);self.y.addItems(common)
        self.x.setCurrentText(viewer.xbox.currentText());self.y.setCurrentText(viewer.ybox.currentText())
        self.form.addRow('X column (raw units)',self.x);self.form.addRow('Y column (raw units)',self.y)
        self.first=QSpinBox();self.first.setRange(1,100000000);self.first.setValue(1)
        self.last=QLineEdit();self.last.setPlaceholderText('End of each curve')
        self.form.addRow('First row (1-based)',self.first);self.form.addRow('Last row (inclusive)',self.last)
        self.branch=QComboBox();self.form.addRow('X branch',self.branch)
        self.low=QLineEdit();self.high=QLineEdit()
        self.low.setPlaceholderText('No lower bound');self.high.setPlaceholderText('No upper bound')
        self.form.addRow('X minimum (native unit)',self.low);self.form.addRow('X maximum (native unit)',self.high)
        self.range_button=QPushButton('Use current plot X range')
        self.range_button.clicked.connect(self.plot_range);self.form.addRow(self.range_button)
        self.fields={};self.field_tools={}
        for key,label,text in [('x_label','Assigned X column label','Assigned X'),('y_label','Assigned Y column label','Assigned Y'),('x_unit','X unit (explicit; e.g. V)',''),('y_unit','Y unit (e.g. A, mA/cm2)','')]:
            self.add(key,label,QLineEdit(text),['Assign column units'])
        self.add('area','Area / cm²',QLineEdit(),['Normalize area','iR correction','Integrate charge','Peak and charge','Pulse charges'])
        self.combo('mode','Area conversion',['To current density','To total current'],['Normalize area'])
        self.combo('potential_axis','Potential axis',['X','Y'],['Reference conversion','iR correction'])
        self.combo('reference_mode','Reference definition',['Explicit offsets','Target RHE'],['Reference conversion'])
        for key,label,text in [('source_offset','Source Eref vs SHE / V',''),('target_offset','Target Eref vs SHE / V',''),
            ('target_name','Target reference label',''),('ph','pH (RHE only)',''),('temperature','Temperature / K (RHE)',''),
            ('equilibrium','Eeq vs target / V (0: E)','0')]:
            self.add(key,label,QLineEdit(text),['Reference conversion'])
        self.add('resistance','Uncompensated R / Ω',QLineEdit(),['iR correction'])
        self.add('fraction','Compensation fraction (0–1)',QLineEdit('1'),['iR correction'])
        current=QComboBox();current.addItems(common);current.setCurrentText(self.y.currentText())
        self.add('current_column','Measured current column',current,['iR correction'])
        for key,label,value in [('window','Window / points (odd)',11),('order','Polynomial order',2)]:
            field=QSpinBox();field.setRange(0,100001);field.setValue(value);self.add(key,label,field,['Smooth'])
        self.combo('baseline','Baseline',['None','Endpoint line','Constant'],['Integrate charge','Peak and charge','Pulse charges'])
        self.add('baseline_value','Constant baseline (native Y)',QLineEdit('0'),['Integrate charge','Peak and charge','Pulse charges'])
        times=QComboBox();times.addItem('Use supplied scan rate','')
        for col in common:
            if sources[0].units[sources[0].columns.index(col)] in ('s','ms','min'):
                times.addItem(col,col)
        self.add('time_column','Time for CV charge',times,['Peak and charge'])
        self.add('scan_rate','Scan rate / V s⁻¹',QLineEdit(),['Peak and charge'])
        self.combo('polarity','Peak polarity',['Maximum','Minimum'],['Peak and charge'])
        self.add('prominence','Min. prominence (native Y)',QLineEdit('0'),['Peak and charge'])
        self.combo('split_mode','Split definition',['Branches','Cycles from reversals','Stored cycle column'],['Split scans / cycles'])
        cycles=QComboBox();cycles.addItem('Choose stored column','');
        for col in common:cycles.addItem(col,col)
        self.add('cycle_column','Cycle ID column',cycles,['Split scans / cycles'])
        self.add('tolerance','X reversal tolerance (native X)',QLineEdit('0'),['Split scans / cycles'])
        self.add('gap','Gap between pulses / s',QLineEdit('0'),['Join pulses'])
        for key,label,text in [('angle','Rotation / degrees',''),('x_scale','X normalization scale',''),
            ('y_scale','Y normalization scale',''),('x_origin','X origin','0'),('y_origin','Y origin','0')]:
            self.add(key,label,QLineEdit(text),['Coordinate rotation'])
        from voltscope_cv import MODELS
        self.combo('cv_model','Background model',MODELS,['CV baseline & peaks'])
        self.combo('cv_reporting','Report',['Dominant peak per polarity','All supported peaks'],['CV baseline & peaks'])
        self.combo('cv_polarity','Peak polarity',['Both','Positive','Negative'],['CV baseline & peaks'])
        self.add('cv_peak_min','Search from (potential)',QLineEdit(),['CV baseline & peaks'])
        self.add('cv_peak_max','Search to (potential)',QLineEdit(),['CV baseline & peaks'])
        self.fields['cv_peak_min'].setPlaceholderText('Between background windows')
        self.fields['cv_peak_max'].setPlaceholderText('Between background windows')
        self.add('cv_manual','Background windows',QCheckBox('Use manual windows'),['CV baseline & peaks'])
        for key,label in [('cv_left_min','Left window start'),('cv_left_max','Left window end'),('cv_right_min','Right window start'),('cv_right_max','Right window end')]:
            self.add(key,label,QLineEdit(),['CV baseline & peaks'])
        self.pickers=QWidget();pick_layout=QHBoxLayout(self.pickers);pick_layout.setContentsMargins(0,0,0,0)
        for label,target in [('Set left','left'),('Set right','right'),('Set search','search')]:
            button=QPushButton(label);button.clicked.connect(lambda _,t=target:self.pick_window(t));pick_layout.addWidget(button)
        self.form.addRow(self.pickers)
        self.cv_advanced=QCheckBox('Advanced settings')
        self.form.addRow(self.cv_advanced)
        self.combo('cv_method','Peak measurement',['Local quadratic fit','Smoothed apex','Raw sampled'],['CV baseline & peaks'])
        for key,label,value in [('cv_fraction','Auto background fraction','.15'),('cv_smooth','Detection window / points','9'),
            ('cv_noise_factor','Auto threshold / noise σ','5'),('cv_prominence','Minimum prominence (current)',''),('cv_reversal','Reversal tolerance (potential)','')]:
            self.add(key,label,QLineEdit(value),['CV baseline & peaks'])
        self.fields['cv_prominence'].setPlaceholderText('Automatic noise threshold')
        self.fields['cv_reversal'].setPlaceholderText('Automatic hysteresis')
        self.add('cv_despike','Isolated spikes',QCheckBox('Suppress for detection only'),['CV baseline & peaks'])
        self.fields['cv_despike'].setChecked(True)
        self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for label in config.findChildren(QLabel):
            label.setWordWrap(True);label.setMaximumWidth(150)
        for combo in config.findChildren(QComboBox):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)
        self.sources.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.sources.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(config);split.addWidget(scroll)
        self.view=ResultView();split.addWidget(self.view);split.setSizes([370,700])
        self.feedback=QLabel('Choose columns and an interval, then preview. Display scaling is not used for analysis.')
        self.feedback.setWordWrap(True);layout.addWidget(self.feedback)
        actions=QHBoxLayout();layout.addLayout(actions)
        self.preview=QPushButton('Preview analysis');self.preview.setObjectName('Primary')
        self.preview.clicked.connect(self.compute);actions.addWidget(self.preview)
        self.apply=QPushButton('Add derived curves');self.apply.setEnabled(False);self.apply.clicked.connect(self.commit);actions.addWidget(self.apply)
        self.export=QPushButton('Export result bundle…');self.export.setEnabled(False);self.export.clicked.connect(self.save_results);actions.addWidget(self.export)
        close=QPushButton('Close');close.clicked.connect(self.reject);actions.addWidget(close)
        from voltscope_analysis import potential_factor, current_unit
        default_tool='Assign column units'
        try:
            first_curve=self.sources.item(0).data(Qt.ItemDataRole.UserRole)
            potential_factor(first_curve.units[first_curve.columns.index(self.x.currentText())])
            current_unit(first_curve.units[first_curve.columns.index(self.y.currentText())])
            default_tool='CV baseline & peaks'
        except (ValueError, IndexError, AttributeError):
            if viewer.xbox.currentText()=='T':default_tool='Integrate charge'
        self.tool.setCurrentText(default_tool)
        self.tool.currentTextChanged.connect(self.configure)
        self.x.currentTextChanged.connect(self.axis_labels)
        self.y.currentTextChanged.connect(self.axis_labels)
        self.x.currentTextChanged.connect(self.refresh_branches)
        self.first.valueChanged.connect(self.refresh_branches);self.last.editingFinished.connect(self.refresh_branches)
        for key in ['baseline','reference_mode','time_column','split_mode']:
            self.fields[key].currentIndexChanged.connect(self.configure)
        self.fields['cv_reversal'].editingFinished.connect(self.refresh_branches)
        self.fields['cv_manual'].toggled.connect(self.configure)
        self.fields['cv_model'].currentTextChanged.connect(self.configure)
        self.cv_advanced.toggled.connect(self.configure)
        self.view.raw_plot.windowSelected.connect(self.window_picked)
        self.configure();self.refresh_branches();self.axis_labels()
        for field in [self.x,self.y,self.branch,*self.fields.values()]:
            if isinstance(field,QCheckBox):field.toggled.connect(self.invalidate)
            elif isinstance(field,QComboBox):field.currentIndexChanged.connect(self.invalidate)
            elif isinstance(field,QSpinBox):field.valueChanged.connect(self.invalidate)
            elif isinstance(field,QLineEdit):field.textChanged.connect(self.invalidate)
        for field in [self.low,self.high,self.last]:field.textChanged.connect(self.invalidate)
        self.first.valueChanged.connect(self.invalidate)
        if self.tool.currentText()=='CV baseline & peaks':QTimer.singleShot(0,self.compute)

    def add(self,key,label,widget,tools):
        self.fields[key]=widget;self.field_tools[key]=tools;self.form.addRow(label,widget)

    def combo(self,key,label,choices,tools):
        widget=QComboBox();widget.addItems(choices);self.add(key,label,widget,tools)

    def configure(self,*_):
        self.view.raw_plot.range_pick=False
        self.view.raw_plot._pick_start=None;self.view.raw_plot._pick_span=None
        self.view.raw_plot.unsetCursor()
        op=self.tool.currentText();self.description.setText(TOOLS[op])
        for key,widget in self.fields.items():self.form.setRowVisible(widget,op in self.field_tools[key])
        self.fields['area'].setPlaceholderText('Required for normalization' if op=='Normalize area' else 'Required for density inputs' if op=='iR correction' else 'For density → total charge')
        if op in ('Integrate charge','Peak and charge','Pulse charges'):
            self.form.setRowVisible(self.fields['baseline_value'],self.fields['baseline'].currentText()=='Constant')
        if op == 'Reference conversion':
            rhe=self.fields['reference_mode'].currentText()=='Target RHE'
            for key in ['ph','temperature']:self.form.setRowVisible(self.fields[key],rhe)
            self.form.setRowVisible(self.fields['target_offset'],not rhe)
            self.fields['target_name'].setEnabled(not rhe)
            if rhe:self.fields['target_name'].setText('RHE')
        if op == 'Peak and charge':
            self.form.setRowVisible(self.fields['scan_rate'],not self.fields['time_column'].currentData())
        if op == 'Split scans / cycles':
            self.form.setRowVisible(self.fields['cycle_column'],self.fields['split_mode'].currentText()=='Stored cycle column')
        cv=op=='CV baseline & peaks'
        self.form.setRowVisible(self.pickers,cv)
        self.form.setRowVisible(self.cv_advanced,cv)
        if cv:
            advanced=self.cv_advanced.isChecked();manual=self.fields['cv_manual'].isChecked()
            for widget in [self.first,self.last,self.low,self.high,self.range_button]:self.form.setRowVisible(widget,advanced)
            for key in ['cv_method','cv_fraction','cv_smooth','cv_noise_factor','cv_prominence','cv_reversal','cv_despike']:
                self.form.setRowVisible(self.fields[key],advanced)
            for key in ['cv_left_min','cv_left_max','cv_right_min','cv_right_max']:
                self.form.setRowVisible(self.fields[key],manual)
        else:
            for widget in [self.first,self.last,self.low,self.high,self.range_button]:self.form.setRowVisible(widget,True)
        self.refresh_branches()
        self.invalidate()

    def axis_labels(self,*_):
        for box,axis in [(self.x,'X'),(self.y,'Y')]:
            units=[]
            for i in range(self.sources.count()):
                c=self.sources.item(i).data(Qt.ItemDataRole.UserRole)
                if box.currentText() in c.columns:
                    units.append(c.units[c.columns.index(box.currentText())])
            unit=units[0] if units and len(set(units))==1 else 'mixed native units' if units else 'unknown'
            self.form.labelForField(box).setText(f'{axis} column [{unit}]')
            box.setToolTip('Analysis uses stored values, not main-plot display scaling. For mixed native units, numeric native-unit bounds/baselines apply separately; analyze in separate runs if those parameters differ.')

    def invalidate(self,*_):
        self.apply.setEnabled(False);self.export.setEnabled(False)
        if self.result is not None:
            self.feedback.setText('Settings changed. Preview again before adding or exporting this result.')

    def reorder(self,delta):
        row=self.sources.currentRow();other=row+delta
        if row>=0 and 0<=other<self.sources.count():
            item=self.sources.takeItem(row);self.sources.insertItem(other,item);self.sources.setCurrentRow(other)
            self.invalidate();self.refresh_branches()

    def refresh_branches(self,*_):
        old=self.branch.currentData()
        cv=self.tool.currentText()=='CV baseline & peaks'
        self.branch.blockSignals(True);self.branch.clear();self.branch.addItem('All sweeps (separately)' if cv else 'All selected rows',None)
        try:
            c=self.sources.item(0).data(Qt.ItemDataRole.UserRole)
            a=self.first.value()-1;b=int(self.last.text()) if self.last.text().strip() else len(c.rows)
            if cv:
                from voltscope_cv import sweep_ranges,finite_pair
                xi,yi=c.columns.index(self.x.currentText()),c.columns.index(self.y.currentText())
                usable=[i for i in range(a,b) if max(xi,yi)<len(c.rows[i]) and finite_pair(c.rows[i][xi],c.rows[i][yi])]
                x=[c.rows[i][xi] for i in usable]
                runs,_=sweep_ranges(x,self.fields['cv_reversal'].text())
            else:
                x,_=values(c,self.x.currentText(),range(a,b));runs=branches(x)
            for n,(lo,hi,d) in enumerate(runs,1):
                self.branch.addItem(f'{n}: '+('↑' if d>0 else '↓' if d<0 else '—')+f' · rows {(usable[lo] if cv else a+lo)+1}–{(usable[hi] if cv else a+hi)+1}',n)
        except (ValueError,IndexError):pass
        if old is not None:
            index=self.branch.findData(old)
            if index>=0:self.branch.setCurrentIndex(index)
        self.branch.blockSignals(False)

    def pick_window(self,target):
        if not self.view.raw_plot.series:
            self.feedback.setText('Preview the CV first, then drag on Raw + baseline to choose windows.');return
        self._pick_target=target
        self.view.tabs.setCurrentIndex(1)
        self.view.raw_plot.range_pick=True;self.view.raw_plot.setCursor(Qt.CursorShape.CrossCursor)
        self.feedback.setText('Drag horizontally on the raw plot to set the '+target+' window. Then preview again.')

    def window_picked(self,lo,hi):
        target=getattr(self,'_pick_target','search')
        if target in ('left','right'):
            # Seed the other window from the current displayed sweep, so a
            # first drag does not leave an invisible half-defined fit.
            if self.result and self.view.choice.currentIndex()>=0:
                windows=self.result.curves[self.view.choice.currentIndex()].metadata['CV_BACKGROUND']['windows']
                if windows:
                    for key,value in zip(['cv_left_min','cv_left_max','cv_right_min','cv_right_max'],windows):
                        if not self.fields[key].text().strip():self.fields[key].setText(f'{value:.12g}')
            self.fields['cv_manual'].setChecked(True)
            self.fields[f'cv_{target}_min'].setText(f'{lo:.12g}')
            self.fields[f'cv_{target}_max'].setText(f'{hi:.12g}')
        else:
            self.fields['cv_peak_min'].setText(f'{lo:.12g}');self.fields['cv_peak_max'].setText(f'{hi:.12g}')
        self.feedback.setText('Window selected. Preview again to recalculate the baseline and peaks.')

    def plot_range(self):
        from voltscope_ui import display_factor
        if self.viewer.plot.bounds is None or self.x.currentText()!=self.viewer.xbox.currentText():
            self.feedback.setText('Choose the same X column as the main plot to use its visible interval.');return
        c=self.sources.item(0).data(Qt.ItemDataRole.UserRole)
        unit=c.units[c.columns.index(self.x.currentText())]
        factor=display_factor(unit,self.viewer.scale.currentText())
        a,b,_,_=self.viewer.plot.bounds
        self.low.setText(f'{a/factor:.12g}');self.high.setText(f'{b/factor:.12g}')

    def compute(self):
        if self.worker is not None:return
        self.view.raw_plot.range_pick=False
        self.view.raw_plot._pick_start=None;self.view.raw_plot._pick_span=None
        self.view.raw_plot.unsetCursor()
        try:
            p={}
            for key,w in self.fields.items():
                if self.tool.currentText() not in self.field_tools[key]:continue
                if isinstance(w,QCheckBox):p[key]=w.isChecked()
                elif isinstance(w,QSpinBox):p[key]=w.value()
                elif isinstance(w,QComboBox):p[key]=w.currentData() if key in ('time_column','cycle_column') else w.currentText()
                else:p[key]=w.text().strip()
            if not p.get('area'):p.pop('area',None)
            if not p.get('time_column'):p.pop('time_column',None)
            selection=Selection(self.first.value()-1,int(self.last.text())-1 if self.last.text().strip() else None,
                float(self.low.text()) if self.low.text().strip() else None,float(self.high.text()) if self.high.text().strip() else None,
                self.branch.currentData())
            sources=[self.sources.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.sources.count())]
            self.worker=AnalysisWorker(self.tool.currentText(),sources,self.x.currentText(),self.y.currentText(),selection,p,self)
            self.worker.completed.connect(self.computed);self.worker.finished.connect(self.finished_work)
            self.preview.setEnabled(False);self.apply.setEnabled(False);self.export.setEnabled(False)
            self.config.setEnabled(False);self.tool.setEnabled(False)
            self.feedback.setText('Calculating…');self.worker.start()
        except ValueError as exc:self.feedback.setText(str(exc))

    def computed(self,result,error):
        if error:
            self.feedback.setText('Cannot analyze: '+error);return
        self.result=result;self.view.set_result(result)
        self.apply.setEnabled(True);self.export.setEnabled(True)
        self.feedback.setText(f'{len(result.peaks)} peaks in {len(result.curves)} sweeps. Review the blue background windows, raw baseline and corrected peaks.' if result.operation=='CV baseline & peaks' else f'{len(result.curves)} derived table(s) ready. Review the preview, metrics and assumptions before adding.')

    def finished_work(self):
        self.worker.deleteLater();self.worker=None;self.preview.setEnabled(True)
        self.config.setEnabled(True);self.tool.setEnabled(True)

    def commit(self):
        if self.result is None:return
        self.viewer.add_analysis(self.result)
        self.apply.setEnabled(False);self.feedback.setText('Derived curves added. Originals remain in the library. Use Undo analysis to remove this batch.')

    def save_results(self):
        if self.result is None:return
        try:
            output=output_directory()
            output.mkdir(parents=True, exist_ok=True)
            parent=QFileDialog.getExistingDirectory(self,'Choose parent folder for a new result bundle',str(output))
            if not parent:return
            directory=export_results([self.result],parent);self.feedback.setText('Saved '+str(directory))
        except (OSError,ValueError) as exc:self.feedback.setText('Export failed: '+str(exc))

    def reject(self):
        if self.worker is not None:
            self.feedback.setText('Wait for the current calculation to finish before closing.');return
        super().reject()

    def closeEvent(self,event):
        if self.worker is not None:event.ignore()
        else:event.accept()


class HistoryDialog(QDialog):
    def __init__(self,viewer):
        super().__init__(viewer);self.setWindowTitle('VoltScope · Analysis results');self.resize(1000,780)
        layout=QVBoxLayout(self)
        choice=QComboBox();layout.addWidget(choice)
        view=ResultView();layout.addWidget(view,1)
        for result in viewer.analysis_results:choice.addItem(result.operation+' · '+result.created,result)
        choice.currentIndexChanged.connect(lambda i:view.set_result(choice.itemData(i)))
        if choice.count():view.set_result(choice.currentData())
        export=QPushButton('Export all result bundles…');layout.addWidget(export)
        def save():
            try:
                output=output_directory()
                output.mkdir(parents=True, exist_ok=True)
                parent=QFileDialog.getExistingDirectory(self,'Export analysis history',str(output))
                if parent:
                    folder=export_results(viewer.analysis_results,parent)
                    QMessageBox.information(self,'Analysis exported',str(folder))
            except (ValueError,OSError) as exc:QMessageBox.critical(self,'Export failed',str(exc))
        export.clicked.connect(save)
