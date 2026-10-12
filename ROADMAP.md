# Roadmap

## Agreed direction

- Local Python app for the research group.
- Windows and macOS.
- PySide UI.
- CV and chronoamperometry analysis as the next scientific priority.
- No raw experimental data in Git.

## Current baseline

Gamry/Ivium/Corrware/Metrohm/DropView import, curve overlays, axis selection, current display scaling,
zoom/pan, metadata, and raw CSV export exist in the PySide6 app. The UI now includes library search, drag/drop, color-matched legends, and import feedback.
No analysis algorithms are implemented yet.

## Next development milestones

1. Completed: migrate the desktop UI to PySide6, separate data handling from UI,
   and declare runtime dependencies.
2. Synthetic parser/export and Qt interaction checks exist. Next validate the
   native desktop workflow on Windows; macOS migration checks are complete.
3. Add CV and CA analysis with reproducible parameter/result export. Decide the
   specific analyses before implementing them.

## Analysis candidates to confirm

These are proposals, not agreed requirements or existing features:

- CV: cycle/branch selection, peak positions and currents, baseline subtraction,
  charge integration, and scan-rate comparisons.
- CA: time-window selection, steady-state summaries, charge integration,
  light/dark interval comparisons, and transient fitting.
- Optional normalization by electrode area with explicit inputs and units.

ECSA calculations require a chosen method and its scientific assumptions;
no universal conversion is assumed. EIS fitting, packaged distribution, and a
public release are outside the current priority and have no committed timeline.
