# Dependencies

Runtime dependencies are installed through requirements.txt:

| Dependency | Purpose | License |
| --- | --- | --- |
| PySide6 | Qt desktop UI and plotting primitives | LGPLv3/GPLv3/commercial options; see the installed package's notices |
| nrbf 0.1.2 | Data-only parsing of NOVA NRBF records | MIT |
| openpyxl >=3.1.5,<4 | Read XLSX measurement tables | MIT |
| NumPy >=1.26,<3 | Numeric arrays and coordinate-aware differentiation | BSD-3-Clause |
| SciPy >=1.14,<2 | Savitzky–Golay, local peaks, regression and integration | BSD-3-Clause |

VoltScope does not vendor these dependencies or their source. The MIT license
covers VoltScope's code; it does not replace dependency licenses. Any future
bundled executable must include the applicable dependency license notices and
meet their distribution terms. See the package metadata installed by pip.

The Windows installer build also uses PyInstaller (pinned in
`installer/requirements.txt`) and Inno Setup 6. These are build tools; end users
do not install them. The bundle includes runtime package metadata and the
project's third-party notices.

NOVA import relies on nrbf 0.1.2's record table and stream-position interfaces,
so that package is pinned. PySide6 remains constrained to Qt 6; tests currently
use PySide6 6.12.0 locally. Run the test suite when upgrading dependencies.

BioLogic, PalmSens and Zahner decoding otherwise uses the standard library.
The distributed MPR ID/type mapping is adapted from cheminfo/biologic-converter
(MIT, copyright 2022 cheminfo); its original notice is included at
`third_party/biologic-converter-LICENSE.txt`. The Zahner binary layout follows
the manufacturer's MIT reader, with its notice retained at
`third_party/Zahner-LICENSE.txt`. No GPL parser code is bundled or required.

Analysis is independently implemented against the documented NumPy/SciPy APIs.
viewPAR is referenced for feature review, not linked, copied, or imported. Its
GPL license does not replace VoltScope's MIT license. Numerical-library wheels
may contain additional bundled numerical-library notices; retain those notices
if producing an executable distribution.
