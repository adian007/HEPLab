"""Export HEPLab display payloads to interchange formats.

The OpenUSD export (``heplab.export.usd``) writes workbench event displays as a
vendor-neutral stage: authoring and inspection are CPU-only and need no NVIDIA
hardware, while the same file is RTX-renderable in NVIDIA Omniverse on CUDA
machines and viewable in usdview/Blender on any OpenGL GPU, including Intel
integrated graphics.
"""
