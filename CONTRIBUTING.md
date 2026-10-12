# Contributing to VoltScope

Install the dependencies and run the synthetic tests as described in README.md.
Keep `voltscope.py` as the entry point. Parsers and export are independent of the
PySide6 interface; new instrument formats belong in data modules.

Before opening a pull request:

- Preserve source values, units, signs, acquisition order, and curve metadata.
- Add synthetic tests for a new format or scientific behavior. Never include raw
  experimental data or private instrument exports in the repository or issues.
- Run `python -m unittest discover -s tests -v` with the project dependencies.
- Update the format notes and README when support or dependencies change.
- For UI changes, check opening, curve selection/overlays, axes, zoom/pan, and CSV
  export as relevant. State which operating system was tested.

For bug reports, provide the OS, Python/dependency versions, reproduction steps,
expected behavior, and a synthetic minimal file if needed. A screenshot should
omit private filenames and results. Do not post credentials or private data.

Analysis contributions should document the algorithm, input/output units,
selected interval, parameters, assumptions, and validation with known answers.
Future derived results should remain separate from imported raw values.
