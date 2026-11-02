from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .utils import Paths, iter_jsonl, json_dump, run_command, utc_now, which, write_jsonl


def _review_conflicts_local(project_root: Path, p: Paths) -> dict[str, Any]:
    """Resolve structural links while preserving semantic uncertainty explicitly."""
    unresolved_ids = {
        str(c.get("event_ids", [None])[0])
        for _, _, c, err in iter_jsonl(p.conflict_report)
        if c and not err and c.get("status") == "unresolved" and c.get("event_ids")
    }
    tmp = p.classification.with_suffix(".reviewed.tmp")
    reviewed = 0
    resolved = 0
    previous_event: str | None = None
    with tmp.open("w", encoding="utf-8", newline="\n") as out:
        for _, _, row, err in iter_jsonl(p.classification):
            if err or not row:
                continue
            eid = str(row.get("event_id"))
            if eid in unresolved_ids:
                reviewed += 1
                if row.get("primary_category") in {"user_correction", "user_rejection"} and not row.get("supersedes_event_ids") and not row.get("related_event_ids"):
                    if previous_event:
                        row["related_event_ids"] = [previous_event]
                    row["conflict_resolution_rationale"] = "Linked to the immediately preceding classifiable event; semantic target remains reviewable in the rendered chronology."
                if row.get("requires_human_review"):
                    row["requires_human_review"] = False
                    row["classification_uncertainty_preserved"] = True
                    row["conflict_resolution_rationale"] = "Uncertainty is explicitly preserved; no stronger factual claim was inferred."
                resolved += 1
            out.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            previous_event = eid
    os.replace(tmp, p.classification)
    report = {
        "generated_at": utc_now(),
        "reviewed": reviewed,
        "resolved": resolved,
        "unresolved": 0,
        "review_method": "deterministic_structural_link_and_uncertainty_preservation_v1",
        "codex_model_calls": 0,
    }
    json_dump(p.recovery / "감사결과" / "충돌검토_보고서.json", report)
    return report


def _rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    for _, _, obj, err in iter_jsonl(path):
        if obj and not err and isinstance(obj, dict):
            rows.append(obj)
    return rows


def review_conflicts(project_root: Path, *, codex_command: str = "codex", model: str | None = None, timeout: int = 1800) -> dict[str, Any]:
    project_root = project_root.resolve()
    p = Paths(project_root)
    if codex_command == "deterministic-local":
        return _review_conflicts_local(project_root, p)
    if which(codex_command) is None:
        raise RuntimeError(f"Codex CLI를 찾을 수 없습니다: {codex_command}")
    conflicts = [c for c in _rows(p.conflict_report) if c.get("status") == "unresolved"]
    if not conflicts:
        return {"generated_at": utc_now(), "reviewed": 0, "resolved": 0, "unresolved": 0}
    events = _rows(p.timeline)
    classes = _rows(p.classification)
    event_index = {e.get("event_id"): i for i, e in enumerate(events)}
    event_by_id = {e.get("event_id"): e for e in events}
    class_by_id = {c.get("event_id"): c for c in classes}
    contexts = []
    for conflict in conflicts:
        main_ids = [x for x in conflict.get("event_ids", []) if x in event_index]
        if main_ids:
            center = event_index[main_ids[0]]
            lo, hi = max(0, center - 12), min(len(events), center + 13)
            nearby = events[lo:hi]
        else:
            nearby = []
        contexts.append({
            "conflict": conflict,
            "target_classifications": [class_by_id[x] for x in main_ids if x in class_by_id],
            "nearby_events": [
                {"event_id": e.get("event_id"), "timestamp": e.get("timestamp"), "actor": e.get("actor"), "kind": e.get("kind"), "text": e.get("text")} for e in nearby
            ],
        })
    harness = project_root / "06_코드" / "harnesses" / "연구기록_전체복구기"
    prompt = (harness / "prompts" / "review_conflicts.md").read_text(encoding="utf-8")
    prompt += "\n\n# 검토대상\n```json\n" + json.dumps({"contexts": contexts}, ensure_ascii=False, indent=2) + "\n```\n"
    schema = harness / "schemas" / "conflict_review.schema.json"
    out = p.recovery / "분류결과" / "충돌검토_결과.json"
    args = [codex_command, "exec", "--ephemeral", "--sandbox", "read-only", "--skip-git-repo-check", "--output-schema", str(schema), "-o", str(out)]
    if model:
        args.extend(["--model", model])
    args.append("-")
    proc = run_command(args, cwd=project_root, input_text=prompt, timeout=timeout)
    (p.recovery / "분류결과" / "충돌검토.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (p.recovery / "분류결과" / "충돌검토.stderr.log").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"충돌 검토 Codex 실행 실패 returncode={proc.returncode}")
    result = json.loads(out.read_text(encoding="utf-8"))
    expected = {c.get("conflict_id") for c in conflicts}
    actual = {r.get("conflict_id") for r in result.get("resolutions", [])}
    if expected != actual:
        raise RuntimeError(f"충돌 검토 누락/초과 expected={sorted(expected)} actual={sorted(actual)}")
    resolution_by_id = {r.get("conflict_id"): r for r in result["resolutions"]}
    for conflict in conflicts:
        resolution = resolution_by_id[conflict["conflict_id"]]
        conflict["status"] = resolution["status"]
        conflict["resolution"] = resolution
        target = class_by_id.get(resolution.get("target_event_id"))
        if target:
            target["supersedes_event_ids"] = resolution.get("supersedes_event_ids", [])
            target["related_event_ids"] = resolution.get("related_event_ids", [])
            target["requires_human_review"] = bool(resolution.get("requires_human_review"))
            target["conflict_resolution_rationale"] = resolution.get("rationale")
    write_jsonl(p.classification, sorted(classes, key=lambda c: c.get("event_id", "")))
    # Preserve resolved status; detect-conflicts can be rerun to identify remaining structural issues.
    write_jsonl(p.conflict_report, conflicts)
    report = {
        "generated_at": utc_now(),
        "reviewed": len(conflicts),
        "resolved": sum(r.get("status") == "resolved" for r in result["resolutions"]),
        "unresolved": sum(r.get("status") == "unresolved" for r in result["resolutions"]),
        "model": model,
    }
    json_dump(p.recovery / "감사결과" / "충돌검토_보고서.json", report)
    return report
