# viewPAR feature review and VoltScope implementation

Reviewed [yerga/viewPAR](https://github.com/yerga/viewPAR) at revision
[`3cc579f1626c64d4489422c18382c92188b5304a`](https://github.com/yerga/viewPAR/tree/3cc579f1626c64d4489422c18382c92188b5304a).
The review covered README, all connected actions/implementations in viewPAR.py,
viewwindow.ui and the extraction/helper modules. VoltScope implements the
behavior independently; no GPL source or dependencies are copied into its MIT
codebase. The downloaded review reference stays in ignored work storage.

| viewPAR feature | Finding | VoltScope implementation |
| --- | --- | --- |
| COR opening, overlays and clear | Labels/current scaling/area were partly hard-coded | Existing multi-vendor library; explicit labels and units, compatible overlays, session clear |
| Paired CSV / HPLC text data | Headerless semicolon X/Y pairs; UTF-16 tab-delimited numeric data; first-row/units needed care | Generic header-table import plus headerless paired numeric CSV; first row retained, unknown units labelled; explicit unit assignment before physical analysis |
| Area normalization | Shared area default 1, applied during extraction without reliable density recognition | Explicit current ↔ density transformation; rejects double normalization; no implicit area |
| Reference conversion / overpotential | Several named paths, fixed offsets and per-curve pH strings; same-reference and other paths incomplete | Explicit source/target offsets; ideal RHE from user pH/temperature; either axis; optional equilibrium subtraction; source retained |
| iR correction | Assumed mA and density-to-current conversion | Unit-aware signed I×R correction, explicit density area and compensation fraction |
| Smooth | Savitzky–Golay | Validated odd window/order, preview, original data retained |
| Derivative | First differences, division by duplicate X possible, one sample dropped | Coordinate-aware second-order gradient; nonuniform X supported, duplicate/reversing X rejected, point count retained |
| Peak/baseline/charge | First plotted curve; hidden smoothing; half-file branch assumption; fixed mA/scan-rate assumptions | Explicit branch/rows/units, selected baseline, local sampled peaks and signed charge; measured time or stated scan rate; peak markers and metrics |
| Tafel slope | First plotted curve; log of raw signed values and half-curve assumptions | Selected curves and intervals, one-sign current validation, log magnitude, signed slope/uncertainty/R²/residuals, raw/current-density unit support |
| Multi-CV separation | Equal-length slicing with lost endpoints | Actual reversal branches/cycles or explicit contiguous cycle IDs; partial/open cycles labelled; turning points retained |
| Integrate over time | Cubic interpolation plus implicit area/current assumptions | Trapezoidal cumulative charge on actual stored times; no resampling; C versus C/cm² explicit |
| Open multi-pulse | Reversed input list; time offsets assumed | User-visible reorderable input list, explicit inter-pulse gap; native time and per-row source retained |
| Charge multi-pulse | Interpolation, reversed charges and ambiguous density units | Independent signed integrations in explicit order, unit-aware pulse summary and provenance |
| Rotate | Action calls a method with incompatible arguments; implementation uses hard-coded 45° | Working coordinate rotation with explicit angle, unit-based normalization scales/origins and dimensionless outputs |
| Export CSV | Adjacent unlabelled columns with no analysis history | Unit-qualified selected tables plus metric/provenance bundles; originals protected |
| Save image / plot navigation | Matplotlib toolbar | Existing Qt zoom/pan/reset plus PNG and vector SVG export with axes and legend |
| Last-file path preference | QSettings remembers a folder | Last open folder stored locally in ignored outputs/viewer_preferences.json; preferences never supply scientific parameters |

The extraction module also contains calibration means/std, spectral-matrix,
dot-plot and spectra-evolution helper classes with no connected desktop actions.
The spectral TXT route is unreachable through its extension dispatch bug. These
are not functioning viewPAR electrochemistry-analysis workflows; no dormant,
unexposed spectral/calibration APIs are claimed as implemented analysis in
VoltScope. Generic CSV/XLSX import supports explicit tabular data without
filename-based assumptions such as treating every filename containing HPLC as
minutes/counts.

There is no multi-Gaussian/nonlinear peak-fitting feature in the active viewPAR
application: those alternatives are commented-out experiments. VoltScope does
not claim nonlinear deconvolution or spectroscopy calibration. Its actual
analysis algorithms and limitations are described in [ANALYSIS.md](ANALYSIS.md).
