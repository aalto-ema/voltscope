# Roadmap

## Agreed direction

- Local Python app for the research group.
- Windows and macOS.
- PySide UI.
- CV and chronoamperometry analysis as the next scientific priority.
- No raw experimental data in Git.

## Current baseline

Gamry/Ivium/Corrware/Metrohm/DropView/BioLogic/PalmSens/Zahner import,
CSV/XLSX header-table import, curve overlays, axis selection, current display scaling,
zoom/pan, metadata, and raw CSV export exist in the PySide6 app. The UI now includes library search, drag/drop, color-matched legends, and import feedback.
EIS signals can be viewed on linear axes with original sign conventions.
The analysis workbench implements area/reference/iR transformations, smoothing,
derivatives, local peaks and baseline-relative charge, time integration,
Tafel regression, scan/cycle splitting, pulse joining/charge summaries,
explicit column-unit assignment and normalized coordinate rotation.
Result bundles and PNG/SVG plot export are available. EIS fitting is not implemented.
GitHub Actions builds a per-user Windows x64 installer as a workflow artifact.

## Next development milestones

1. Completed: migrate the desktop UI to PySide6, separate data handling from UI,
   and declare runtime dependencies.
2. Synthetic parser/export and Qt interaction checks exist. Next validate the
   native desktop workflow on Windows; macOS migration checks are complete.
3. Completed: initial CV/CA/viewPAR analysis workflows with preview, derived
   curves, undo, and reproducible parameter/result export. Validate on the group's
   real workflows and on native Windows before broadening the algorithms.

## Further analysis candidates

The initial functions above are implemented; these are possible extensions:

- Completed: dedicated CV baseline/peak workflow without scan rate, per-sweep
  robust linear/quadratic backgrounds, visual window selection, local apex fits,
  quality flags, missing-pair handling and peak CSV/provenance exports.
- CV next: validate background assumptions with group measurements; automated
  scan-rate comparisons, overlapping-peak models and uncertainty estimates remain planned.
- CA: time-weighted/steady-state models, light/dark interval comparisons, and transient fitting.
- Nonlinear fitting with explicit uncertainty and diagnostic reporting.

ECSA calculations require a chosen method and its scientific assumptions;
no universal conversion is assumed. EIS fitting, macOS packaging, code signing,
and a public release have no committed timeline.
