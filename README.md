# VoltScope

**Electrochemistry Data Visualization & Analysis**

VoltScope is a local Python desktop viewer from the Aalto EMA research group.
Open electrochemical measurements from several instrument vendors, compare
curves, inspect experiment metadata, and export the original data to CSV.

The app uses PySide6. Visualization and raw CSV export are available now;
CV and chronoamperometry analysis are planned, not yet implemented.

## Supported files

| Instrument/software | Files | Notes |
| --- | --- | --- |
| Gamry | `.DTA` | Separate curve tables and decimal commas/points |
| Ivium | `.idf`, `.ids` | Stored primary-data tables; separate scans |
| PAR / Corrware | `.cor` | CV, potentiostatic, and galvanostatic examples |
| Metrohm Autolab / NOVA | `.nox` | Stored measurement signal arrays |
| Metrohm Autolab / GPES | `.ocw`, `.ici`, `.icw` | OCW holds data; companions must stay together |
| DropSens / DropView | `.mtc`, `.mta`, `.mtd` | CV, amperometric detection, and DPV XML |

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

```bat
git clone https://github.com/aalto-ema/voltscope.git
cd voltscope
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe voltscope.py
```

After installation, double-click `Launch VoltScope.bat`. Both launchers prefer
the local `.venv`. Activate that environment before using plain `python` commands.
No standalone executable is provided yet.

To open files at startup:

```sh
python voltscope.py "/path/to/experiment.DTA" "/path/to/scan.idf"
```

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
   beside the application. Export includes every selected row and original column,
   regardless of zoom, with source filename, table name, and unit-qualified headers.

Exported numbers use decimal points. Mixed datasets use a union of columns and
blanks where a curve lacks a column. Display scaling does not alter source data
or exported values. Clear library removes curves only from the current session.

## Scientific conventions and limitations

- Current (A) and current density (A/cm²) are distinct. No area normalization or
  reference-electrode conversion is applied.
- DropView unlabelled I1/I2 values use µA, as confirmed for the example datasets.
  Explicit XML unit attributes take precedence. Both arrays are retained;
  smoothing and pulse subtraction are not applied.
- GPES files with blank labels use matching ICI labels where available. Unknown
  column meanings/units remain explicit; missing time axes are not fabricated.
- Imports preserve acquisition order and stored curve boundaries. CV cycles
  within a single table are not inferred or split. Compatible selected curves
  overlay; incompatible axes/units are reported visibly.
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
