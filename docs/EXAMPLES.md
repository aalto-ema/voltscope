# Synthetic examples

Generate the demo pack after installing VoltScope. From the repository folder,
with the virtual environment active, run:

```sh
python tools/generate_examples.py
```

The files appear in `outputs/examples/`. On macOS you can use
`.venv/bin/python tools/generate_examples.py`; on Windows use
`.venv\Scripts\python.exe tools\generate_examples.py`.
This original pack covers Gamry, Ivium, Corrware, Metrohm and DropView.
The generator uses only the Python standard library and works from any current
directory. `--destination PATH` chooses another folder. Repeated runs verify
identical files; modified existing files are never replaced.

Every signal is generated from illustrative formulas, without experimental
inputs. These files demonstrate the reader's supported format subsets; they
are not vendor-certified files or physical calibration standards. Generated
instrument files remain excluded from Git; the reproducible generator is shared.

| File | Demonstration | Curves × points |
| --- | --- | --- |
| `gamry_cv_cycles.DTA` | Three separate CV tables with increasing peak amplitude | 3 × 241 |
| `gamry_ca_light_steps.DTA` | Current decay with two light-like current steps | 1 × 201 |
| `ivium_cv_cycles.ids` | Three CV blocks; programmed and measured potential stored separately | 3 × 241 |
| `ivium_ca_light_steps.idf` | Chronoamperometry with an explicit time axis | 1 × 201 |
| `corrware_cv.cor` | CV current density | 1 × 241 |
| `corrware_potentiostatic.cor` | Current density vs time | 1 × 201 |
| `corrware_galvanostatic.cor` | Rising potential at constant current density | 1 × 201 |
| `metrohm_nova_cv.nox` | Binary NRBF stored CV signals | 1 × 241 |
| `metrohm_gpes_cv.ocw` | CV with matching `.ici` and `.icw` companions | 1 × 241 |
| `dropview_cv.mtc` | CV with explicit microampere units | 1 × 241 |
| `dropview_amperometry.mta` | Amperometry with explicit microampere units | 1 × 201 |
| `dropview_pulse.mtd` | Illustrative stored pulse peak with I2 zero | 1 × 121 |

Keep all three GPES files together; opening any companion loads the same OCW
measurement. Selecting all companions in one import does not duplicate it.

## Try the viewer

1. Start VoltScope and open `gamry_cv_cycles.DTA`. Select all three curves to
   overlay them. The peaks grow by 8% per cycle; acquisition order is preserved.
2. Open `gamry_ca_light_steps.DTA` separately. Plot T vs Im: steps occur at
   20, 40, 60, and 80 seconds. Scroll to zoom, drag to pan, and reset the view.
3. Try the Corrware galvanostatic file: its default axes are T vs Vf. Corrware
   examples store **current density in A/cm²**, without assuming electrode area.
4. Open DropView amperometry and choose I1. Switching µA to mA changes the
   display only. I2 is explicitly zero in these demos; no pulse subtraction is
   performed. The DPV example is an illustrative peak, not a pulse simulation.
5. Export selected curves to a new CSV in `outputs/`. The full stored rows and
   original units are exported, even when the plot is zoomed. CSV is an export
   format; header-based CSV reimport is supported.

The CV sweeps run from −0.6 to +0.6 V and back at a synthetic 50 mV/s with
0.2-second samples. The CA signal has 0.5-second samples through 100 seconds.
Potential reference identity is unspecified; no electrode conversion is implied.
Cross-format overlays require compatible column names and unit labels; trying
files separately is the easiest way to explore their default axes.
