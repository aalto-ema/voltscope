# Dependencies

Runtime dependencies are installed through requirements.txt:

| Dependency | Purpose | License |
| --- | --- | --- |
| PySide6 | Qt desktop UI and plotting primitives | LGPLv3/GPLv3/commercial options; see the installed package's notices |
| nrbf 0.1.2 | Data-only parsing of NOVA NRBF records | MIT |

VoltScope does not vendor these dependencies or their source. The MIT license
covers VoltScope's code; it does not replace dependency licenses. Any future
bundled executable must include the applicable dependency license notices and
meet their distribution terms. See the package metadata installed by pip.

NOVA import relies on nrbf 0.1.2's record table and stream-position interfaces,
so that package is pinned. PySide6 remains constrained to Qt 6; tests currently
use PySide6 6.12.0 locally. Run the test suite when upgrading dependencies.
