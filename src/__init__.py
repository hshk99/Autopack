"""
Top-level `src` package shim.

This repo uses `PYTHONPATH=src` so imports typically look like `import autopack`.
Some legacy tests/imports use `import src.autopack...`; making `src` a package
keeps those imports working without changing runtime behavior.
"""
