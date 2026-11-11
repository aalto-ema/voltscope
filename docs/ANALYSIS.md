# Analysis workbench

Select source curves in the library, then choose **Analyze…**. The workbench
always uses stored column values and units, independently of the main plot's
current display scaling. The original curves remain in the library.

## CV baseline correction and peak current

For potential versus current columns, **Analyze…** opens **CV baseline & peaks**
and calculates a preview automatically. **No scan rate, time axis or electrode
area is required.** Each major forward/reverse sweep is analyzed separately,
including unequal and partial cycles. Choose the sweep in the preview dropdown.

1. Check **Raw + baseline**. Blue bands mark the two background windows. The
   default is a robust straight-line fit to the outer 15% of the potential span
   on each side. This is a starting assumption, not proof of a valid baseline.
2. Use **Set left** or **Set right**, then drag horizontally on the raw plot to
   choose peak-free background regions. The other window is retained. Numeric
   bounds are available under **Use manual windows**. Preview again after edits.
   Choose a quadratic background for justified curvature, a constant background,
   or no subtraction for already corrected data.
3. Inspect **Corrected peaks**. Stored corrected current is unsmoothed. A separate
   detection trace helps distinguish supported peaks from fluctuations. Peak
   markers show the estimated signed current and potential. The table includes
   units, noise ratio and quality warnings.
4. **Set search** limits the peak region by dragging. Default search lies between
   the background windows. Default reporting selects the most prominent positive
   and negative peak per sweep; choose a polarity or **All supported peaks** for
   multiple redox features. All supported candidates remain in JSON provenance.
5. Advanced settings expose detection sensitivity, smoothing, peak measurement,
   isolated-spike handling, reversal tolerance and row/range selection. Ordinary
   CV analysis requires none of these fields. **Add derived curves** and export
   only after reviewing the fit and warnings. Export includes **peaks.csv**.

### CV algorithm 2.0 and validity rules

- Potential/current pairs that are missing or nonfinite are excluded explicitly
  from derived sweeps; exact original row numbers and counts are recorded. Raw
  curves stay intact. At least seven finite pairs per sweep are required.
- Reversals use directional-change hysteresis relative to the running potential
  extremum. Automatic tolerance is the smaller of 15% of the potential span and
  the larger of 1% of the span or three median nonzero steps. Manual tolerance
  is in native potential units. Minor jitter and repeated potentials are retained
  in acquisition order. Adjacent sweeps share the turning point.
- Backgrounds use centered/scaled polynomial least squares with Huber iteratively
  reweighted residuals (1.345 tuning, up to 40 iterations). Windows are balanced,
  as are duplicate potentials within each window. At least two samples in each
  separated window and sufficient distinct potentials are required. Default
  windows expand to two samples for short scans. Fit coefficients, scales,
  residual MAD, actual windows and source rows are exported per sweep.
- Detection optionally suppresses very isolated spikes: a point must exceed five
  times its neighbors' magnitude/noise floor and deviate by eight noise estimates
  from neighbor interpolation. This changes only the detection trace and records
  affected rows. A real single-sample feature can resemble a spike; disable this
  option to inspect it. Measured and corrected currents never change.
- Detection uses a positive-weight Gaussian filter in sample order, default nine
  points, sigma=(window−1)/6, truncated to that window, nearest edge handling.
  Short scans reduce the odd window; one disables filtering. It is not a physical
  potential-width filter and does not resample irregular coordinates.
- Noise is MAD of first current differences divided by 0.67448975√2. Automatic
  prominence is the maximum of five noise estimates, 1% of the detection signal's
  2–98 percentile span and a numeric floor. SciPy local peak prominence detects
  positive and negative candidates independently. Boundary extrema are never
  invented; threshold and search interval are recorded.
- Default peak current/potential are estimated by a local robust quadratic fit
  to **unsmoothed corrected current using actual potentials**, excluding flagged
  isolated spikes. Neighborhood half-width is one quarter of the half-prominence
  width in samples, capped at five points. Insufficient support expands to four
  neighbors per side. A fit needs four samples, three distinct potentials, correct
  curvature and an apex within local support/search limits; otherwise it falls
  back to the smoothed sample with a warning. Alternatives are smoothed apex and
  raw sampled current at the detected apex. Signed current and original units
  are retained; raw sampled current, estimated baseline, nearest source row and
  local fit source rows are separate exported fields.
- Flat tops, under-resolved peaks, missing local samples, low signal/noise,
  competing candidates, substantial baseline residuals and search-edge peaks
  carry quality notes. These are diagnostics, not confidence intervals. Bad
  sweeps/inputs are explicitly listed as skipped; valid sweeps still preview.

A baseline cannot be determined uniquely from a CV with no peak-free background
regions. Inspect and adjust windows rather than assuming every detected feature
is electrochemical. Overlapping/unresolved peaks are not deconvolved; a shoulder
may not form a separate local peak. Filtering and local fits can bias very narrow
features or scans with large missing intervals. No automatic reference, area,
charge, peak pairing, kinetic interpretation or uncertainty estimate is inferred.
For charge, explicitly choose the separate **Peak and charge** workflow, which
still requires measured time or a justified scan rate.

## Workflow

1. Select compatible source curves. The workbench lists the exact input order;
   **Move up/down** controls pulse order. Shared numeric/physical assumptions
   such as area apply to every selected input; run separate analyses if they differ.
2. Choose the operation and explicit X/Y columns. For time integration select
   time and current/density. For peak analysis select potential and current.
   Tafel fitting accepts potential/current or current/potential mapping.
3. Set a 1-based inclusive row interval, optionally a detected X branch and
   lower/upper X bounds in **native units**. Branches are derived from changes
   in X direction, not from half a file. Branch numbers refer to the chosen row
   interval. **Use current plot X range** translates display scaling back to
   native units; this is available only for the same X column.
4. Supply the operation's parameters. No area, reference identity, pH, scan rate,
   resistance, or missing time is inferred. Select a baseline explicitly if needed.
5. Choose **Preview analysis**. Computation runs in a worker thread. Review the
   preview, comparison traces, local peak markers, metrics and assumptions.
   General operations reject invalid rows or incompatible batch inputs. The CV
   tool instead records excluded pairs and skipped sweeps explicitly. Changing a setting invalidates the preview.
6. **Add derived curves** adds the result once, leaving originals intact. Chained
   operations can select these curves and their named derived columns.
   **Analysis → Undo last analysis** removes the most recently added batch and
   its session result record. Undo does not modify exported files.
7. **Export result bundle…** writes a new, uniquely named directory. The bundle
   contains `provenance.json`, `peaks.csv`, a long-form `metrics.csv`, and a data CSV for each
   run. **Results…** revisits added results and exports the current session history.

The last open folder is remembered locally in `outputs/viewer_preferences.json`
under the checkout (source runs) or `%LOCALAPPDATA%\VoltScope` (Windows installer).
Scientific parameters are not taken from this preference. Results are session-local until exported. **Clear library** clears both library
and session analysis history; export any results you want to keep first.

## Selection and data validity

Except for the CV-specific finite-pair handling described above, intervals include only stored samples, with no endpoint interpolation, sorting,
resampling, dropped invalid samples or synthetic padding. Disjoint intervals
across several CV branches are rejected: select a branch or contiguous rows.
Every selected X/Y sample must be numeric and finite. Other original columns
remain on derived tables. An operation that requires monotonic X rejects
repeated or reversing coordinates and explains how to select a valid branch.

In tables with unknown units, use **Assign column units** first. Enter both
column labels and their actual units. This copies numbers unchanged; it is a
user assertion of meaning/units, not a numeric conversion. Original unlabelled
columns remain available. Never label µA values as A without converting them.

Current inputs support A, mA, µA/uA and nA, and the corresponding `/cm2` or `/cm²`
densities. Time supports s, ms and min. Potential supports V and mV, including
explicit reference annotations. Unsupported/unknown units stop physical analysis.

## Implemented algorithms

### Electrode area

**Normalize area** divides current by a positive area in cm², or multiplies an
existing density by that area to obtain total current. Native current prefixes
are retained. Trying to normalize an already normalized density is rejected.
No area is read implicitly from an instrument file or a previous global setting.

### Reference conversion and overpotential

Choose which axis contains potential. Explicit reference conversion uses:

`Etarget(V) = Esource(V) + Eref,source(vs SHE) − Eref,target(vs SHE) − Eeq,target`.

Enter the actual reference offsets for the electrolyte, concentration and
temperature in use, and a target label. Subtracting a nonzero equilibrium
potential labels the output as overpotential. A zero Eeq leaves it as potential
versus the target. No universal Ag/AgCl, Hg/HgO or SCE offset is assumed.

For **Target RHE**, supply the source offset, pH and absolute temperature:
`Eref,target = −ln(10) RT pH/F`, with R = 8.31446261815324 J mol⁻¹ K⁻¹ and
F = 96485.33212 C mol⁻¹. This is ideal Nernst pH dependence. The source offset
must be appropriate for its actual electrolyte/temperature; liquid-junction
potentials and activity corrections are not inferred.

### iR correction

`Ecorrected(V) = Emeasured(V) − I(A) R(Ω) f`, where the user supplies R and a
fraction f between 0 and 1. The chosen measured-current column's actual sign
is retained. A density requires an explicit area to obtain total current.
The original and corrected potential remain separate columns. Programmed and
measured potentials are never silently substituted.

### Smoothing and differentiation

Smoothing uses SciPy's Savitzky–Golay filter, odd window length ≥3, polynomial
order less than the window, and `mode='interp'`. The window is **samples in
acquisition order**, not a physical X width. It does not resample irregular X.
Filtering across scan reversals may distort features; choose the interval and
window appropriate to the data. Edge values use the documented polynomial fit.

The derivative uses NumPy's coordinate-aware gradient with second-order edges.
It needs ≥3 samples and strictly monotonic, nonduplicate X, and returns the
same number of samples. Actual unequal X spacing is used. Derived units are
Y-unit/X-unit; no smoothing is applied automatically.

### Time integration, peaks and charge

Time integration uses the cumulative composite trapezoidal rule on the actual
strictly increasing times. Initial cumulative charge is zero at the first
selected sample. Signed current is converted to A for calculation. Density
produces C/cm², or C if an explicit area is supplied. Current inputs already in A
are not multiplied by area. Reported mean signal is an arithmetic sample mean,
not a time-weighted average or a fitted steady-state estimate.

For charge tools, baseline options are **None**, **Constant** in native Y units, or a straight
**Endpoint line** through the selected interval's first and last samples. The
baseline and baseline-corrected signal are separate columns; no iterative
baseline estimator or hidden smoothing is applied.

**Peak and charge** requires one strictly monotonic potential branch. Time is
either an explicitly chosen stored column, or is derived using positive user
scan rate v in V/s: `Δt = |ΔE(V)|/v`. Derived time is an explicit constant-rate
assumption, not a measured axis. Cathodic/descending sweeps keep their signed
charge; the absolute potential increment does not invert current.

Local maxima/minima use SciPy `find_peaks` on the corrected signal (or its
negative for minima), with user prominence in native Y units. Only interior
local peaks are reported. Each peak has its original 1-based row, sampled
potential and signed baseline-relative height. No peak is fabricated at a
boundary, Gaussian interpolation or multi-peak fitting is assumed. The preview
shows corrected data, baseline, original signal and detected peak markers.

### Tafel regression

Select one potential branch and an interval with ≥3 finite points of one
nonzero current sign. The fit is ordinary least squares of potential in V
against `log10(|I|/A)` or `log10(|J|/(A/cm²))`. Current may vary nonmonotonically;
its logarithmic span must be nonzero. The sign is recorded in original columns,
while the logarithm is explicitly of magnitude. Outputs include the signed
slope in mV/decade, slope standard error, 95% Student-t confidence interval
half-width (n−2 degrees of freedom), intercept, R², point count, logarithmic
span, fitted potential and residuals. The confidence interval uses the usual
OLS residual assumptions; it does not establish electrochemical validity.

No absolute-value slope, automatic exchange-current estimate, iR compensation,
reference conversion, baseline subtraction, mass-transport correction or
selection of a physically valid kinetic region is implied. Apply any justified
corrections explicitly before fitting. High R² alone is not kinetic validation.

### Splitting scans and cycles

**Branches** uses changes in the sign of consecutive X increments with a
user-specified tolerance in native X units. Plateaus are retained, not discarded.
Adjacent branches share the turning point. **Cycles from reversals** pairs
consecutive branches from the chosen starting row; an unmatched branch or a
pair that does not return within tolerance to its starting X is labelled
partial/open. Choose the starting row and tolerance deliberately, especially
for noisy potentials. There is no assumed equal number of points per cycle.

**Stored cycle column** groups contiguous runs of explicit cycle IDs. It keeps
all rows, their order and changing group lengths; IDs recurring later remain
separate runs. Already separated imported tables remain independent inputs.

### Pulse joining and per-pulse charge

Inputs use the displayed order, never a reversed filename order. **Join pulses**
requires identical source column schemas/units and strictly increasing native
time within each pulse. It adds a new seconds axis: first pulse starts at zero;
subsequent pulses start at the previous joined endpoint plus the chosen gap.
Original time remains in its original column, with input source/curve/row
provenance per output row. A zero gap retains duplicate boundary times. This
is an explicit reconstruction, not a claim that unrecorded inter-file time is
known. Integrate each pulse separately rather than treating unknown gaps as
measurements.

**Pulse charges** integrates each source's signed current independently using
the same baseline/area/unit rules as time integration. It produces a pulse-number
summary with source identities and selected row intervals. Charge and charge
density are not combined into one summary without an explicit area conversion.

### Coordinate rotation

The experimental rotation action in viewPAR is replaced by an explicit geometric
transform: `u=(X−Xorigin)/Xscale`, `v=(Y−Yorigin)/Yscale`, then apply the ordinary
2D rotation matrix to u,v at the chosen angle. Scales must be positive and are
in the original X/Y units. Output coordinates are dimensionless and labelled
accordingly. This does not mix raw volts and amperes or claim an electrochemical
correction. Original physical columns remain available.

## CV validation

`tests/test_cv_peaks.py` uses analytical signals with independently known peak
positions/heights and linear/quadratic backgrounds. Cases cover positive/negative
peaks, multiple unequal sweeps, repeated/jittered/nonuniform potentials, missing
and nonnumeric samples, background outliers, isolated spikes, flat tops, resolved
multiple peaks, short scans, invalid settings, units/density, source immutability,
partial batches, row provenance, JSON/CSV, automatic Qt preview, drag-window
selection, invalidation and apply/undo.

A fixed 100-seed simulation adds independent Gaussian noise σ=0.02 to a unit
Gaussian peak (width σE=0.08 V, Ep=0.1 V, 401 samples over −1…1 V) on a linear
background. Every trial detects one peak; maximum absolute Ep error is 0.01041 V,
maximum current error 3.43%, median current error 0.69%. The same 100 noisy
backgrounds without a peak produce zero detections. These are bounded synthetic
checks, not universal performance guarantees or experimental validation.

Local smoke checks also run public BioLogic ASCII/binary CV examples and 64
PalmSens ferrocyanide curves without modifying inputs. They verify execution,
finite outputs and provenance; experimental peak ground truth was not supplied.
Native Windows validation remains pending; local checks used macOS/offscreen Qt.

## Export and reproducibility

Run IDs, UTC timestamps, algorithm/software versions, chosen source/column/unit
mappings, source-curve snapshot SHA-256 hashes, selected source rows, requested
and actual X bounds, parameters, assumptions and derived-column history are
exported. These are hashes of imported curve snapshots, not raw-file hashes.
Sources with the same short curve name are distinguished by path and snapshot
hash in metric exports. Bundles use exclusive new directories; experimental
files are not overwritten. Ordinary **Export CSV…** exports selected stored
columns, but use a **result bundle** to retain full analysis provenance.

**Export → Save plot image…** saves the current plotted view as high-resolution
PNG or vector SVG, including axis labels and a trace legend (first 20 trace
labels if there are more). Zoom/pan affects this image, not analysis or data CSV.
No smoothing or interpolation is performed by image export.

Tests use independent known-answer synthetic cases for charge, signed CV peaks,
120 mV/decade Tafel slope, reference shifts, iR units, nonuniform differentiation,
polynomial smoothing, cycle boundaries, pulse order and immutability. Qt tests
cover preview/apply, invalidation, undo, report bundles and image export. Tested
locally on macOS with offscreen Qt; native Windows validation remains pending.

References: [SciPy Savitzky–Golay](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.savgol_filter.html),
[SciPy local peaks](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.find_peaks.html),
[SciPy regression](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.linregress.html).
