# VoltScope

Electrochemistry Data Visualization & Analysis.

## Project scope

Build a local Python desktop tool for the user's research group. Support Windows
and macOS. Prioritize cyclic voltammetry (CV) and chronoamperometry (CA) analysis.
Maintain Gamry DTA, Ivium IDF/IDS, and PAR/Corrware COR and Metrohm NOVA/GPES and DropView import and CSV export.

## Workspace and outputs

- Project root: the repository containing this file.
- Keep `voltscope.py` as the application entry point.
- Keep source and supporting files within this project.
- Save generated user-facing deliverables and exported results to `outputs/`.
- Use `work/` for temporary files and scratch analysis.
- Resolve application paths relative to the application or selected files;
  do not hard-code the owner's filesystem paths into portable application code.

## UI and dependencies

- PySide is the requested UI framework. Prefer PySide6 for the migration unless
  compatibility requirements justify another version.
- The current app uses PySide6; parsing/export live in voltscope_data.py and
  the UI lives in voltscope_ui.py.
- Implement future UI work toward PySide; retain existing functionality through
  the migration. Keep parsing, export, and analysis independent of the UI.
- Document dependencies and installation steps when adding packages.
- Treat Windows and macOS as required platforms. Report which platform was
  actually tested; do not claim cross-platform validation from one OS.

## Scientific data integrity

- Never overwrite source experimental files.
- Preserve original values, units, signs, row order, curve boundaries, and relevant
  metadata. Separate measured and programmed potentials.
- Never infer reference electrode conversions, electrode area, current density,
  baseline correction, or missing time axes without explicit metadata or input.
- Keep display scaling separate from exported raw values.
- Label unknown column meanings and units explicitly rather than guessing.
- Show import failures, skipped curves, and recorded abort status clearly.
- For analysis, record the source curve, chosen interval, parameters, units,
  transformations, and assumptions. Describe an implemented algorithm in the docs.

## Repository data policy

- Do not commit raw experimental data to Git, including Gamry DTA and Ivium
  IDF/IDS and Corrware COR files. Do not commit private instrument exports disguised as CSV.
- Use synthetic fixtures for committed tests. Real examples may be used locally
  with external paths; do not copy them into tracked fixtures.
- Exclude generated exports, scratch files, environments, and caches from Git.
- Do not introduce a public release, publication, or license decision without a
  user request. The repository is public under MIT; the primary audience is the research group.

## Verification and documentation

- For parser/export changes, check numeric conversion, units, row counts, curve
  boundaries, metadata, malformed/truncated input, and mixed-format CSV output.
- For analysis changes, use independent synthetic cases with known answers and
  verify units and handling of insufficient or invalid data.
- For UI changes, verify opening files, selection/overlays, axis choices, zoom,
  and export as relevant. Do not add tests that merely repeat implementation.
- Keep README.md, docs/DATA_FORMATS.md, docs/DEVELOPMENT.md, and ROADMAP.md aligned
  with actual functionality. Clearly mark plans and limitations.
