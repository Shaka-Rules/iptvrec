#!/usr/bin/env python3
"""One-command launcher for the IPTVrec Dashboard."""
import sys
from pathlib import Path

# Add iptvrec src to path
_root = Path(__file__).resolve().parent.parent
_src = _root / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

# Add dashboard parent to path (so 'dashboard' package is importable)
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from backend.main import run
run()
