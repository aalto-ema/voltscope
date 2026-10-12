# Data formats and scientific conventions

## Shared model and export

Each imported table is a separate `Curve` containing its source path, name,
column labels, units, rows, and metadata. Data remains in acquisition order.
Unknown units are labeled `unknown`. CSV adds source filename and table name,
then includes the union of original columns with unit-qualified headers.
Source filename provenance does not currently include a file hash or full path.

Plots skip curves with unavailable axes or units incompatible with the first
plotted curve and report skipped curves in the status bar. Changing the current
display unit does not change exported raw data. Reference electrodes and current
signs are not converted. Current-density normalization and background correction
are not implemented.

## Gamry DTA

The parser reads tab-separated `TABLE` sections, column headers, unit rows, and
numeric rows, including multiple CV tables. It handles decimal commas/points,
scientific notation, UTF-8 and Windows-1252 text, and nonnumeric status fields.

Common columns in the supplied files:

| Column | Meaning | Unit |
| --- | --- | --- |
| T | Time | s |
| Vf | Measured potential versus reference | V vs. Ref. |
| Im | Current | A |
| Pt | Point index | # |

Other columns are retained with the source labels and units. Metadata includes
experiment type, title, instrument, date, and abort flag where available.

Local checks covered one CA table with 46,586 points and a CV file with three
tables of 1,401, 1,400, and 1,400 points. This is not validation of all Gamry
techniques or file versions.

## Ivium IDF and IDS

The supplied files contain binary container fields and embedded ASCII
`primary_data` tables. The parser reads declared column/row counts and preserves
each primary-data block. It does not import auxiliary objects such as `Q_data`.

Mapped three-column layouts:

| Experiment | First column | Second column | Third column |
| --- | --- | --- | --- |
| CyclicVoltammetry / LinearSweep | Vset: programmed potential (V vs. Ref.) | Im: current (A) | Vf: measured potential (V vs. Ref.) |
| Transients / ChronoAmperometry | T: time (s) | Im: current (A) | Vf: measured potential (V vs. Ref.) |

These mappings are based on the inspected examples; they are not a complete
Ivium format specification. Unknown methods/layouts retain generic `Column1`,
`Column2`, etc. with unknown units. No CV time axis is synthesized.

The supplied IDS file contains ten 1,400-point CV scans and an all-zero 10-row
container table. The parser labels the container table and keeps it available
for selection/export; initial selection prefers a measurement scan. Container
identification is currently a heuristic based on IDS extension, missing start
time, and all-zero values, and may need refinement for other datasets.

The supplied CA IDF records `Scan Aborted` and has 27 points from 0.2 to 5.4 s.
Its programmed duration is longer, but missing measurements are not fabricated.
Metadata is read per scan, including title, method, start time, instrument, and
recorded completion/abort status. Other Ivium layouts and versions are not yet
individually validated.

## Future analysis conventions

Before adding an analysis, specify input columns, units, selected curve/cycle and
interval, sign conventions, preprocessing, algorithm, parameters, and validity
conditions. Keep derived results separate from raw data. Require explicit inputs
for electrode area or reference-electrode conversion where source metadata is
insufficient. Export enough settings to reproduce the result.

## PAR / Corrware COR

`CORRW ASCII` files are read using the explicit header before `End Comments`
and the `Data Points` count. UTF-8 and Windows-1252 text, decimal points/commas,
and scientific notation are supported. A malformed row, missing header, or
row-count mismatch produces an import error. Each file becomes one curve; CV
cycles are not inferred or split. Appended multi-header datasets are not supported.

| Source header | Viewer column | Unit |
| --- | --- | --- |
| E(Volts) | Vf | V |
| I(A/cm2) | J | A/cm2 |
| I(A) | Im | A |
| T(Seconds) | T | s |

Other explicit headers retain their labels and units. Potential is labeled V
as written in the header; reference metadata is retained without conversions.
Current density is kept separate from current, with no multiplication by surface
area. Display prefixes apply to both A and A/cm2; CSV retains original units.
Incompatible current/current-density or potential unit overlays are skipped.

Defaults: CV uses Vf versus J/Im; potentiostatic uses T versus J/Im; galvanostatic
uses T versus Vf. Metadata retains experiment settings, instrument, date/time,
surface area, reference fields, and original column labels. A programmed
duration is not a guarantee of recorded duration, and no abort flag is invented.

The six supplied CorrWare 3.5b/3.5c examples passed row-count checks: CV 10,840
and 5,200; potentiostatic 151 and 1,009; galvanostatic 1,285 and 301 points.
All six explicitly label I as A/cm2. Synthetic tests cover the three experiment
modes, axis defaults, density scaling, CSV units/values, and invalid data.
Other Corrware variants have not been individually validated.

## Metrohm Autolab: GPES and NOVA

GPES OCW is a whitespace-delimited data table with comma-separated axis labels.
ICI contains plot settings, not measurement rows; ICW contains experiment
settings. Opening either companion loads the matching OCW file. Explicit
`E / V` and `I / A` labels map to Vf [V] and Im [A]. If OCW labels are blank,
the matching ICI axis labels supply the mapping. Missing labels remain unknown;
no time axis is synthesized. ICW date/time strings are retained without locale
conversion; unlabeled numeric settings are not interpreted. Values and row order
are preserved. One table produces one curve; cycles are not inferred.

The three supplied GPES tables contain 738, 410, and 1,230 rows. Each dataset
loads through OCW, ICI, or ICW. Keep companions together. Companion provenance is
retained in metadata, and companion files are protected against UI export
overwrite. Selecting them together deduplicates within that import batch.

The supplied NOVA NOX files contain two consecutive .NET NRBF streams. Import
uses the pinned pure-Python nrbf parser in record mode; no .NET objects execute.
References are resolved only for fields needed for measurement arrays, avoiding
cycles in the command graph. Base CommandParameterDataArray records are grouped
by owning command; List buffers are limited to their explicit `_size`, excluding
unused capacity. Signals of unequal lengths are rejected rather than truncated.
Plot previews and windowed/derived signal records are not imported.

Explicit NOVA names map SetpointApplied to Vset, CalcTime to T,
EI_0.CalcCurrent to Im, EI_0.CalcPotential to Vf, and ScanNumber to Scan.
Units come from each signal; missing units remain unknown. A group must contain
measured potential and current to be imported. Other numeric base signals are
retained with their original names. The two supplied NOX examples contain one
nonempty measurement group each: 326 and 1,557 rows, with Vset [V], T [s],
Im [A], Vf [V], Scan [unknown], and Index [unknown].

Support is validated for these layouts, not every NOVA/GPES version. Truncated
streams and invalid references produce errors. No procedure is run, and no
reference-electrode, current-sign, or normalization conversion is applied.

## DropSens DropView XML

MTC, MTA, and MTD files contain XML with a root/file descriptor and curves. Each
curve becomes a separate library item. Technique IDs are taken from XML rather
than inferred from the extension: CV, AD (amperometric detection), and DPV are
covered by the supplied files. Defaults are Vf/I1 for CV and DPV, T/I1 for AD.

Point arrays time, potential, i1, and i2 map to T, Vf, I1, and I2. Time and
potential use the DropView conventions s and V; explicit unit attributes take
precedence. Unlabelled I1/I2 arrays use µA, confirmed by the user for the supplied DropView
data. Explicit XML units take precedence. This convention is recorded in
metadata. Stored values remain unchanged; plot scaling converts only display
values, and CSV exports retain µA. I1/I2 are kept
as stored arrays; their pulse/channel meanings are not inferred. No difference
current, smoothing, reference conversion, normalization, or cycle splitting is
applied. Unknown additional point arrays retain their names and unknown units.

Arrays must be numeric, nonempty, unique, and equal in length. Malformed XML and
DTD/entity declarations are rejected. Device/version, technique, channel, title,
curve name, interval, user parameters, stored color, and stored smoothing settings
are retained as metadata. Stored smoothing settings do not modify imported data.

All nine supplied examples were checked against every source-array value: three
CV files with 451 rows each; two AD files with 121 each; four DPV files with 426
each. XML descriptor versions 2 and 1.0 occur in these examples. Other DropView
layouts are not yet individually validated.
