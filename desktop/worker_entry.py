"""Entry point for the frozen desktop worker."""

import multiprocessing

from heplab.desktop.worker import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    # Load native reader libraries on the main thread before accepting jobs.
    import awkward  # noqa: F401
    import numpy  # noqa: F401
    import uproot  # noqa: F401

    raise SystemExit(main())
