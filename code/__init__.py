"""Local `code` package for research modules.

This repo includes `code/research_orchestrator.py` which is referenced by tests
as `from code.research_orchestrator import ...`.

Making `code/` a package ensures those imports resolve to this directory (not
the Python stdlib `code` module).
"""


