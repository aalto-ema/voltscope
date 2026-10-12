# Development

## Audience and platforms

VoltScope is for the research group and runs locally from Python. Windows and
macOS are required target platforms. The source repository is public under MIT. A packaged executable is not yet provided.

## Current structure

- `voltscope.py`: desktop entry point and compatibility imports for data functions.
- `voltscope_data.py`: UI-independent Curve model, Gamry/Ivium/Corrware parsers, and CSV export.
- `voltscope_ui.py`: PySide6 Viewer, background import thread, and Plot widget.
- `requirements.txt`: PySide6 dependency.
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
