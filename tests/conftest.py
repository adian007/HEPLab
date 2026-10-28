"""Make src/ importable without installing the package.

Phase-0 tests are stdlib-only by design (fast CI, no heavy deps); this keeps
`pytest` runnable directly from a fresh checkout. CI additionally installs
the package editable (`pip install -e . --no-deps`).
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
