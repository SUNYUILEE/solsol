from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .utils import Paths, append_jsonl, codex_home, sha256_file, utc_now


def fast_checkpoint(project_root: Path, *, explicit_codex_home: str | None = None) -> dict[str, Any]:
    """SessionEnd hook용 3초 이내 경량 체크포인트. 전체 복구를 수행하지 않는다."""
    project_root = project_root.resolve()
    ch = codex_home(explicit_codex_home)
    files: list[Path] = []
    sessions = ch / "sessions"
    if sessions.exists():
        files = sorted(sessions.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
    row = {
        "checkpoint_at": utc_now(),
        "project_root": str(project_root),
        "recent_sessions": [
            {
                "path": str(p),
                "size_bytes": p.stat().st_size,
                "modified_at": p.stat().st_mtime,
                "sha256": sha256_file(p) if p.stat().st_size < 50_000_000 else None,
            }
            for p in files
        ],
        "note": "세션 종료 시 원본 위치만 보존한 경량 체크포인트. 전체 문서 복구는 research_recovery.py all로 수행한다.",
    }
    append_jsonl(project_root / "04_근거" / "복구증거" / "원본목록" / "세션종료_체크포인트.jsonl", row)
    return row
