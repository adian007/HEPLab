"""Make src/ importable without installing the package.

Phase-0 tests are stdlib-only by design (fast CI, no heavy deps); this keeps
`pytest` runnable directly from a fresh checkout. CI additionally installs
the package editable (`pip install -e . --no-deps`).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def pytest_collection_modifyitems(config, items):
    """Fail instead of skipping kernel tests when CI requires the wheel."""
    import os

    if os.environ.get("HEPLAB_REQUIRE_KERNELS") != "1":
        return
    try:
        import heplab_kernels  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("HEPLAB_REQUIRE_KERNELS=1 but heplab_kernels is not installed") from exc
