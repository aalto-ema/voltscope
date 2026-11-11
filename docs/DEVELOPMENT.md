# Development

## Audience and platforms

VoltScope is for the research group and runs locally from Python. Windows and
macOS are required target platforms. The source repository is public under MIT.

## Windows installer

The **Windows installer** Actions workflow runs on changes to app/build inputs
and can be dispatched manually once it is on the default branch. It builds on
Windows Server 2025 with x64 Python 3.13, PyInstaller and the runner's Inno Setup
6. It runs the source suite, installs into a temporary path, exercises a bundled
GUI/import/CV smoke check, and uninstalls before uploading the unsigned installer
and its SHA-256 checksum. It does not create a GitHub Release.

To build locally, use Windows x64, PowerShell 7.4+, Inno Setup 6.3+, and an active
Python 3.13 x64 virtual environment from the repository root:

```powershell
python -m pip install -r installer/requirements.txt
./installer/build-windows.ps1 -Version 0.1.0
```

The installer and checksum are written to `outputs/windows/`; the staging bundle
is under `work/windows/`. Run `installer/test-installation.ps1` only on a clean
Windows VM with `RUNNER_TEMP` set, because setup registers the installed app for
the current user. Installed preferences and default exports are kept outside the
program directory so they survive upgrades and uninstall.

## Current structure

- `voltscope.py`: desktop entry point and compatibility imports for data functions.
- `voltscope_data.py`: UI-independent Curve model, Gamry/Ivium/Corrware parsers, and CSV export.
- `voltscope_ui.py`: PySide6 Viewer, background import thread, and Plot widget.
- `voltscope_biologic.py`, `voltscope_palmsens.py`, `voltscope_zahner.py`: new vendor readers.
- `voltscope_tabular.py`: CSV/XLSX tables; `voltscope_import_utils.py`: shared lossless helpers.
- `third_party/biologic_columns.json`: MIT-attributed binary field definitions.
- `requirements.txt`: PySide6, nrbf, openpyxl, NumPy and SciPy dependencies.
- `tests/test_viewer.py`: synthetic parsing/export and offscreen Qt interaction checks.

## PySide6 implementation

The migration uses Qt Widgets and a custom QPainter plot. This preserves the
existing linear-axis behavior without an additional plotting dependency.
Cached QPainterPath traces retain full point order; no sorting or downsampling
is applied. Plot labels, grid, clipping, wheel zoom, drag pan, and reset are
handled by the Plot widget. The sidebar and wrapping legend identify curves.

Imports run in QThread and return data/errors through signals; widgets are
updated only on the UI thread. File opening and clearing are disabled during
import, and closing is deferred while import is running. Plot preparation and
CSV export still run on the UI thread and may pause interaction for very large
files. Further performance work should be driven by representative measurements.

Install dependencies in a local virtual environment as described in README.md.
The dependency range is PySide6 >=6.8,<7; the macOS migration checks used 6.12.0.
Both launchers prefer the project-local virtual environment.

## Verification

For parser/export changes, use synthetic fixtures that exercise decimal commas
and points, scientific notation, text/status columns, multiple tables, per-scan
metadata, unknown formats, truncated input, and mixed column/unit schemas.
Verify exported row counts, numeric values, blanks, and original units.

For analyses, use synthetic signals with independently known answers. Cover
chosen intervals, scan direction, cycle boundaries, missing data, sign and unit
conventions, and failure cases. Keep fitting assumptions and quality indicators
visible. Export analysis settings with derived results.

For UI work, perform relevant smoke checks on macOS and Windows. Record actual
platform coverage; a PySide import alone does not verify a window.
GUI checks may need desktop/window-server access.

## Data and generated files

Do not commit private raw data or real experimental CSV exports. Use external
local paths for validation with real data. Synthetic test fixtures should state
that they are synthetic. Keep exports and user-facing generated artifacts under
`outputs/`; scratch work belongs under `work/`. Both are ignored by Git.

Update the documentation when behavior or dependencies change. Do not treat
roadmap proposals as implemented features.

## Automated checks

Run `python -m unittest discover -s tests -v` using the installed environment.
Tests use Qt's offscreen platform and temporary synthetic instrument files.
They exercise loading, overlays, axes, display scaling, raw CSV values,
metadata, zoom/pan/reset, failed imports, and protection against overwriting
source files. Offscreen tests complement native desktop smoke checks; they do
not prove native dialog behavior on every OS. Windows remains unverified.

## UI design

A light slate background, white panels, and teal primary action organize the
data library and trace explorer. Plot controls sit with the plot; experiment
metadata sits with curve selection. The UI includes search, file drag/drop,
keyboard shortcuts, import progress, contextual disabled controls, color-matched
curve markers/legend, and a visible compatibility warning. Search changes only
the library view, not the imported dataset. Synthetic interaction checks cover
search, empty selection, and warnings in addition to the original workflow.

Corrware tests use synthetic `.cor` files; real examples are read externally.

## Metrohm import

`voltscope_metrohm.py` contains GPES companion resolution and NOVA extraction.
NOVA uses nrbf==0.1.2 in record mode and relies on its NRBFParser record table
and consumed-stream position; version changes require rerunning synthetic and
real-example checks. `tests/test_metrohm.py` builds synthetic NRBF streams and
GPES tables; no experimental files are committed. UI checks cover overlays,
units, companion deduplication, CSV export, and companion overwrite protection.

## DropView import

`voltscope_dropview.py` reads XML with the standard library; no extra dependency
is required. Tests build synthetic multi-curve files and cover array alignment,
default/explicit units, raw export, malformed XML, axis defaults, and I1/I2
selection. The user confirmed µA for unlabelled I1/I2 arrays in the supplied XML.

## Demo pack

`tools/generate_examples.py` creates reproducible synthetic vendor-format files
in `outputs/examples/`, without reading experimental inputs. See
[EXAMPLES.md](EXAMPLES.md) for generation and the catalog. Tests verify the pack
through the real import/export functions and protect modified output files.

## Public-data readers

`tests/test_new_imports.py` uses independent synthetic binary/JSON/text/workbook
fixtures to check units, multiple scans, metadata/flags, unequal arrays, explicit
programmed potentials, malformed/truncated records, mixed export, EIS defaults,
and the open/export UI. All import entry points share SUPPORTED_SUFFIXES for
file-dialog and drag/drop coverage. CSV/XLSX do not infer electrode properties.
Install the updated requirements to enable XLSX import. No native vendor runtime
or binary executable is needed. New code was tested on macOS with offscreen Qt;
Windows execution of these additions remains to be verified by CI/native checks.

## Analysis architecture

`voltscope_analysis.py` is UI-independent. Selection defines contiguous source
rows, optional direction branch and native-unit bounds. `run` creates a staged
AnalysisResult transactionally; it never modifies the input Curve objects. Each
result has new curves, explicit metrics, parameters, input snapshot hashes and
assumptions. New columns retain all original selected columns. Core algorithms
are documented in [ANALYSIS.md](ANALYSIS.md); the reviewed feature inventory is
in [VIEWPAR_REVIEW.md](VIEWPAR_REVIEW.md).

`voltscope_analysis_ui.py` supplies a background calculation worker, dynamic
parameter forms, comparison/metric preview, result export/history and Qt PNG/SVG
rendering. Applying adds a batch to the library; undo removes it in LIFO order.
Raw and derived CSV values remain separate from display scaling. Results are
session-local until exported. Only window/dialog state is used for convenience;
scientific parameters such as area/reference offsets are explicit.

`tests/test_analysis.py` uses analytical known-answer cases rather than comparing
against viewPAR's assumptions. Local macOS checks cover numeric calculations,
source immutability, invalid batch inputs, result JSON/CSV, preview, invalidation,
apply/undo, and image rendering. No Windows-native execution is claimed here.


### Focused CV analysis

`voltscope_cv.py` isolates the tolerant baseline/peak-current pipeline from the
stricter integration/transformation tools. It dispatches before general selection
validation, preserves source row mappings, and reports individual skipped sweeps.
Do not introduce time or scan-rate requirements into this tool. All automatic
parameters must appear in provenance. `tests/test_cv_peaks.py` includes known
answers, a reproducible 100-signal/100-blank noise study and the automatic-preview,
drag-window and apply/undo Qt workflow. Keep detection-only filtering distinct
from corrected stored values. Algorithm details/limits live in ANALYSIS.md.
