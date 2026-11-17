"""Optional native desktop workbench built with PySide6."""

from __future__ import annotations


def main() -> int:
    """Launch the native desktop workbench."""
    try:
        from .main_window import run
    except ImportError as exc:
        raise SystemExit(
            "The native desktop UI needs PySide6. Install with "
            "`pip install 'heplab[native-desktop]'`."
        ) from exc
    return run()


__all__ = ["main"]
