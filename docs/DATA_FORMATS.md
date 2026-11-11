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
signs are not converted. Import does not apply normalization or background correction. Explicit derived
operations, including area conversion and selected baseline subtraction, are
available in the [analysis workbench](ANALYSIS.md).

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

## Analysis conventions

The analysis workbench records input columns, units, selected curve/cycle and
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

## BioLogic EC-Lab / BT-Lab MPT, TXT, MPR

ASCII MPT reads the declared header-line count, technique description, all
columns and numeric rows. Header-only TXT exports must have distinctive
BioLogic signal headers, such as `Ewe/V`; arbitrary text is rejected. UTF-8,
Windows-1252, decimal commas and decimal points are supported. `Ewe`/`<Ewe>`
map to Vf, `I`/`<I>` to Im, `time` to T, and an explicit voltage control column
to Vset. Original units (including mA) remain unchanged. Duplicate signal names
get distinct suffixes; unknown columns are retained.

Binary MPR reads length-delimited MODULE records and data-module versions 2/3.
A versioned ID/type table from the MIT-licensed cheminfo biologic-converter
project identifies signal widths. Shared flag bytes are decoded into their
recorded logical columns. Row size and count must match exactly. Unknown IDs,
unsupported versions and truncated records fail explicitly; export MPT from
EC-Lab if a binary layout is unsupported. A separate Curve is created for each
stored data module. Cycle and step fields are retained without inferred splitting.
Technique IDs select CV/CA/CP/EIS defaults where known. Recorded error flags are
shown as STATUS. Opaque settings/log/loop modules remain in in-memory metadata
as hexadecimal bytes, with module descriptors; arbitrary settings fields are
not guessed. These metadata blobs are not columns in CSV exports.

The format table and license notice are in `third_party/`. References:
[BioLogic converter source](https://github.com/cheminfo/biologic-converter) and
[EC-Lab manual](https://12bm.xray.aps.anl.gov/files/EC-Lab_software_manual.pdf).

## PalmSens PSTrace PSSESSION

The reader uses JSON only, with no deserialization of executable objects or .NET
runtime dependency. Both key capitalization variants, UTF-8/UTF-16 BOMs and a
trailing BOM are supported. Every measurement and named scan is retained.
Stored raw DataSet arrays take precedence over processed display curves. Stored
plot arrays are used only if no supported raw dataset is available, and this is
marked in STATUS. Distinct EIS datasets are retained; duplicates of the same
raw dataset in EIS plot wrappers are not imported twice.

Explicit Unit.Type takes precedence over Unit.S: MicroAmpere means µA even if
the base symbol is A. Ordinary CV current values are already in µA; current
range C and reading/status fields are retained as extra columns, not applied as
multipliers. For legacy EIS Idc/midc/Iac readings whose range interpretation is
not established, raw values and range codes are retained with unknown current
units. No range conversion is guessed. The source unit object remains metadata.
Frequency, impedance and phase labels preserve the stored sign convention.

Arrays are grouped by explicit scan name and stored length. Unequal arrays are
kept in separate tables, with STATUS explaining the split; no points are trimmed
or padded. A shared time array is not assigned to multiple named scans based
only on equal lengths; it remains a separate table unless a scan association is
explicit. Single-dataset non-scan arrays may share their stored time array.
Measurement settings, native timestamp ticks, device details and array properties
remain metadata. Timestamp timezone conversions, baseline corrections and pulse
subtraction are not performed. Unsupported nonempty measurements stop the import
with an explicit error rather than being silently skipped.

Reference: [PalmSens data documentation](https://dev.palmsens.com/python/latest/_attachments/data/).

## Zahner ISM

ISM reads the stored frequency, impedance magnitude, phase in **radians**,
seconds since 1980-01-01 (timezone unspecified), and significance arrays.
Classic headers 0xFFFFFFFF/0xFFFFFFFE and version 2 are recognized. All stored
points, including overlapping/repeated frequencies, remain in acquisition order.
The reader does not apply the vendor library's default frequency trimming or
reordering. Optional case-encoded strings, acquisition flags, parameter values,
and voltage/current acquisition channels are read where present. Undecoded
trailing metadata is retained as hex. Truncated arrays/metadata fail clearly.
Real/imaginary impedance is not derived from magnitude and phase.

Reference: [Zahner's reader](https://github.com/Zahner-elektrik/zahner-analysis-python);
its MIT notice is retained in `third_party/Zahner-LICENSE.txt`.

## CSV and XLSX tables

CSV supports comma, semicolon or tab delimiters and decimal commas inside
appropriately delimited cells. The first nonempty row is the header. Units can
be in brackets, parentheses or slash labels; otherwise they remain unknown.
A separate unit row is recognized when every populated cell is a recognized
unit. Empty header cells receive generic column names, never inferred potential
or current meanings. Text/status columns, empty cells and row order are retained.
Each nonempty XLSX worksheet is one table, including wide multi-series tables;
select the desired columns with the axis controls. Empty sheets are reported.
Formula cells are rejected to avoid using stale or missing calculation caches.
No macros or calculations are executed. Plot data always comes from the stored
numeric values, and CSV export retains all columns, including text/status data.
There is no automatic extraction from charts, merged layouts or arbitrary
multi-block spreadsheets; those require a clean header-based table first.

## Public-data validation for these importers

Local macOS checks used eight MPR files and their TXT counterparts from
[Zenodo 6560384](https://zenodo.org/records/6560384), an independent MPR/MPT CV
pair from cheminfo, the NIST ferrocyanide session/XLSX from
[NIST mds2-3388](https://data.nist.gov/od/id/mds2-3388), and manufacturer-provided
PalmSens mixed CV/DPV/EIS and Zahner examples. The Zahner li-ion-battery example
is labelled Simulation by the vendor; a separate 500 µΩ measurement example
also validates acquisition channels. Some deposited MPR/TXT pairs have different
sampling counts, and some NIST spreadsheet currents differ from their native
session readings. Imports preserve each source independently, without forcing
agreement or resampling. Generated checks are in ignored outputs; downloaded
real files stay in ignored work storage. Committed tests contain only synthetic
fixtures. Windows native interaction has not been tested for these additions.

## Headerless legacy CSV and derived data

Wholly numeric headerless CSV is read as adjacent X/Y pairs with unknown units;
the first row is retained. Entirely empty pairs in a row are placeholders and
are omitted only from that pair, with the original source row recorded. Partial
pairs and inconsistent widths fail. UTF-16 tab-delimited numeric CSV is also
supported. Assign units explicitly in Analysis before physical calculations.

Analysis adds columns/tables without overwriting imported values. Derived curves
carry analysis IDs/history and named default axes. Ordinary CSV export retains
stored values; result bundles additionally retain parameters, curve-snapshot
hashes, units and assumptions. See [ANALYSIS.md](ANALYSIS.md) for algorithms.


## CV analysis and incomplete samples

Import continues to preserve stored rows and values. The **CV baseline & peaks**
analysis may omit nonfinite/missing potential-current pairs from its derived
sweeps, with exact excluded source rows in provenance and visible warnings.
Duplicates and minor potential jitter remain in acquisition order. Other analysis
tools retain their stricter contiguous/finite requirements. This distinction never
changes the original imported curve or raw CSV export; see [ANALYSIS.md](ANALYSIS.md).
