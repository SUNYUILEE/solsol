from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = [
    ROOT / "06_코드" / "harnesses" / "연구기록_전체복구기" / "src",
    ROOT / "06_코드" / "src",
]
for source in SOURCES:
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from research_recovery.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
