"""Statistics layer: fits and systematics (ADR-0007, ADR-0010 Tier 2).

- ``zfit`` + ``iminuit`` is the stable fitting API.
- A JAX backend provides likelihood autodiff, GPU fits, and large toy-MC
  systematics ensembles (the dominant compute cost of honest systematics).
  It sits *behind* the same API — see ``heplab.stats.fits``.
"""
