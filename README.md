# VoltScope

**Electrochemistry Data Visualization & Analysis**

VoltScope is a local Python desktop viewer from the Aalto EMA research group.
Open electrochemical measurements from several instrument vendors, compare
curves, inspect experiment metadata, and export the original data to CSV.

The app uses PySide6. Alongside visualization and CSV export, an analysis
workbench provides CV/CA charge, peaks/baselines, Tafel regression, smoothing,
derivatives, explicit reference/iR/area corrections, cycle splitting and pulse
workflows. Original measurements remain separate from derived results.

## Supported files

| Instrument/software | Files | Notes |
| --- | --- | --- |
| Gamry | `.DTA` | Separate curve tables and decimal commas/points |
| Ivium | `.idf`, `.ids` | Stored primary-data tables; separate scans |
| PAR / Corrware | `.cor` | CV, potentiostatic, and galvanostatic examples |
| Metrohm Autolab / NOVA | `.nox` | Stored measurement signal arrays |
| Metrohm Autolab / GPES | `.ocw`, `.ici`, `.icw` | OCW holds data; companions must stay together |
| DropSens / DropView | `.mtc`, `.mta`, `.mtd` | CV, amperometric detection, and DPV XML |
| BioLogic EC-Lab / BT-Lab | `.mpt`, `.mpr`, `.txt` | ASCII tables and binary data modules v2/v3 |
| PalmSens PSTrace | `.pssession` | UTF-8/UTF-16 JSON sessions; CV, pulse, CA and EIS arrays |
| Zahner | `.ism` | Stored impedance magnitude, phase, timestamps and acquisition signals |
| Explicit data tables | `.csv`, `.xlsx` | Header-based tables; each nonempty workbook sheet is a table |

Support has been checked against representative files, not every instrument
technique or software version. See [format details](docs/DATA_FORMATS.md).

## Install and launch

Clone or download this repository. Use Python 3.10 or newer and install the
dependencies into a virtual environment. Python 3.11 or 3.13 is recommended for
the development/test environment. PySide6 platform requirements apply.

### macOS

```sh
git clone https://github.com/aalto-ema/voltscope.git
cd voltscope
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python voltscope.py
```

After installation, double-click `Launch VoltScope.command` to start the app.

### Windows

For a standalone x64 installer, sign in to GitHub and open the [Windows installer workflow](https://github.com/aalto-ema/voltscope/actions/workflows/windows-installer.yml).
Open a successful run for the branch you want, download **VoltScope-Windows-x64**
under **Artifacts**, unzip it, and run `VoltScope-Setup-x64.exe`. Setup installs
for your Windows account and adds VoltScope to the Start menu. Python and admin
rights are not required. The installer is unsigned. An SHA-256 checksum is
included, and artifacts expire after 30 days.

To run from source instead:

```bat
git clone https://github.com/aalto-ema/voltscope.git
cd voltscope
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe voltscope.py
```

After installation, double-click `Launch VoltScope.bat`. Both launchers prefer
the local `.venv`. Activate that environment before using plain `python` commands.

To open files at startup:

```sh
python voltscope.py "/path/to/experiment.DTA" "/path/to/scan.idf"
```

## Try synthetic examples

Generate the original synthetic demo pack (Gamry, Ivium, Corrware, Metrohm and DropView) with:

```sh
python tools/generate_examples.py
```

With your virtual environment active, start the app and open files from
`outputs/examples/`. The pack includes CV cycles, light-step amperometry,
galvanostatic data, and a pulse peak, all generated without experimental inputs.
See the [example catalog and walkthrough](docs/EXAMPLES.md).

## Explore and export

1. Choose **Open data**, press Ctrl/Cmd+O, or drop supported files into the window.
2. Search the data library by filename or curve name. Ctrl/Cmd-click or
   Shift-click selects curves for overlays. Colored markers match the legend.
   Hover over a compact library row to see its complete label and point count.
3. Choose X/Y axes and the current display unit. CV/DPV opens against potential;
   amperometry opens against time; Corrware galvanostatic opens as potential
   against time. The curve metadata remains visible in the sidebar.
4. Scroll to zoom, drag to pan, and double-click or choose **Reset view** to reset.
5. Choose **Export CSV…** or Ctrl/Cmd+Shift+E. The dialog defaults to `outputs/`
   beside the source checkout, or `%LOCALAPPDATA%\VoltScope\outputs` in the
   Windows installer build. Export includes every selected row and original column,
   regardless of zoom, with source filename, table name, and unit-qualified headers.

Exported numbers use decimal points. Mixed datasets use a union of columns and
blanks where a curve lacks a column. Display scaling does not alter source data
or exported values. Clear library removes curves only from the current session.

New public-data formats open through the same controls. For CSV/XLSX, use a
header row such as `T [s],Vf [V],Im [µA]`, or series names followed by a separate
unit row. Unknown labels remain explicit. XLSX formula cells are rejected;
export a values-only workbook first. TXT import recognizes BioLogic headers,
not arbitrary unlabelled text.

## Analyze measurements

For CV, select source curves and choose **Analyze…**. The **CV baseline & peaks**
tool previews automatically without a scan rate or time axis. Inspect **Raw +
baseline**, drag to choose background windows, then review signed peak currents
on **Corrected peaks**. Each sweep is processed separately; missing samples,
spikes and questionable peaks are reported. Export includes a peak table and
full analysis provenance. See the [CV workflow](docs/ANALYSIS.md#cv-baseline-correction-and-peak-current).

For other operations, select source curves and choose **Analyze…**. Pick the raw-unit columns,
interval/branch and parameters, then **Preview analysis**. Review comparison
traces, metrics and assumptions before **Add derived curves**. **Results…**
revisits added analyses; **Analysis → Undo last analysis** removes the last batch.
Export a result bundle to retain metric CSVs, derived data and JSON provenance.
**Export → Save plot image…** provides PNG and SVG output.

Area, reference offsets, resistance, pH/temperature and scan rate are explicit
inputs when needed. For legacy headerless CSV pairs, use **Assign column units**
first; values are not guessed or silently rescaled. See the
[analysis guide and algorithms](docs/ANALYSIS.md) and
[viewPAR feature review](docs/VIEWPAR_REVIEW.md).

## Scientific conventions and limitations

- Current (A) and current density (A/cm²) are distinct. Import never applies area normalization or
  reference conversion; those are explicit derived-data operations in Analysis.
- DropView unlabelled I1/I2 values use µA, as confirmed for the example datasets.
  Explicit XML unit attributes take precedence. Both arrays are retained;
  smoothing and pulse subtraction are not applied.
- GPES files with blank labels use matching ICI labels where available. Unknown
  column meanings/units remain explicit; missing time axes are not fabricated.
- Imports preserve acquisition order and stored curve boundaries. Import does not split CV cycles
  within a table; Analysis can split explicit cycle IDs or selected reversals. Compatible selected curves
  overlay; incompatible axes/units are reported visibly.
- PalmSens scan arrays retain their original values and reading flags. Unaligned
  arrays become separate tables; shared time is kept separately when a scan
  association is unspecified. Legacy EIS range-dependent current stays raw with
  unknown units rather than assuming a range conversion.
- EIS opens as frequency versus stored magnitude or real impedance, on linear
  axes. Stored phase/sign conventions are retained; no impedance fitting, log
  axes, sign inversion, or synthetic time axes are added.
- Imports run in a background thread. Plot preparation and CSV export remain in
  the UI thread and can pause interaction with very large datasets.
- Native macOS rendering and automated offscreen workflows have been checked.
  Native Windows interaction remains to be verified. CI tests both platforms.

## Development

With dependencies installed, run:

```sh
python -m unittest discover -s tests -v
```

Tests create synthetic data in temporary directories. **Do not commit raw
experimental files, private instrument exports, or outputs.** These are excluded
by `.gitignore`. Include a synthetic minimal reproducer when reporting a bug.

- [Contributing](CONTRIBUTING.md)
- [Architecture and validation](docs/DEVELOPMENT.md)
- [Data-format conventions](docs/DATA_FORMATS.md)
- [Roadmap](ROADMAP.md)
- [Agent instructions](AGENTS.md)

## License

VoltScope is available under the [MIT license](LICENSE). Installed dependencies
retain their own licenses; see [dependency notes](docs/DEPENDENCIES.md).
