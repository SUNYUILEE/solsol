from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import Paths, iter_jsonl, utc_now, write_jsonl


def _rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for _, _, obj, err in iter_jsonl(path):
        if obj and not err and isinstance(obj, dict):
            rows.append(obj)
    return rows


def detect_conflicts(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    paths = Paths(project_root)
    ids: set[str] = set()
    for _, _, c, err in iter_jsonl(paths.classification):
        if c and not err:
            ids.add(str(c.get("event_id")))
    paths.conflict_report.parent.mkdir(parents=True, exist_ok=True)
    seq = 0
    unresolved = 0
    with paths.conflict_report.open("w", encoding="utf-8", newline="\n") as out:
      for _, _, c, err in iter_jsonl(paths.classification):
        if not c or err:
            continue
        eid = str(c.get("event_id"))
        cat = c.get("primary_category")
        supersedes = [str(x) for x in c.get("supersedes_event_ids") or []]
        related = [str(x) for x in c.get("related_event_ids") or []]
        new_conflicts: list[dict[str, Any]] = []
        if cat in {"user_correction", "user_rejection"} and not supersedes and not related:
            seq += 1
            new_conflicts.append({
                "conflict_id": f"CNF-{seq:06d}",
                "type": "unlinked_correction_or_rejection",
                "event_ids": [eid],
                "statement": c.get("normalized_statement"),
                "status": "unresolved",
                "reason": "정정·반려가 어떤 이전 기록을 대체하는지 연결되지 않음",
            })
        invalid_refs = [x for x in supersedes + related if x not in ids]
        if invalid_refs:
            seq += 1
            new_conflicts.append({
                "conflict_id": f"CNF-{seq:06d}",
                "type": "invalid_event_reference",
                "event_ids": [eid, *invalid_refs],
                "statement": c.get("normalized_statement"),
                "status": "unresolved",
                "reason": "분류 결과가 존재하지 않는 EVT를 참조함",
            })
        if c.get("requires_human_review"):
            seq += 1
            new_conflicts.append({
                "conflict_id": f"CNF-{seq:06d}",
                "type": "human_review_required",
                "event_ids": [eid],
                "statement": c.get("normalized_statement"),
                "status": "unresolved",
                "reason": "분류기가 맥락 충돌 또는 낮은 확신을 표시함",
            })
        for conflict in new_conflicts:
            out.write(__import__("json").dumps(conflict, ensure_ascii=False, separators=(",", ":")) + "\n")
            unresolved += int(conflict.get("status") == "unresolved")
    return {
        "generated_at": utc_now(),
        "conflict_count": seq,
        "unresolved_count": unresolved,
        "path": str(paths.conflict_report),
    }
