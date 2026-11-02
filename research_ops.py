from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "06_code" / "harnesses" / "research_operations" / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from research_ops.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
