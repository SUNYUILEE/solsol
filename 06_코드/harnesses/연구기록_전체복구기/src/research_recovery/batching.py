from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import Paths, iter_jsonl, json_dump, safe_relpath, utc_now

CLASSIFIABLE_KINDS = {"message", "tool_call", "tool_output", "file_change", "plan_update", "error_event", "compaction"}


def prepare_batches(project_root: Path, *, max_events: int = 60, max_chars: int = 90_000, include_non_project: bool = False) -> dict[str, Any]:
    project_root = project_root.resolve()
    paths = Paths(project_root)
    batch_dir = paths.recovery / "분류입력"
    batch_dir.mkdir(parents=True, exist_ok=True)
    for old in batch_dir.glob("BATCH-*.json"):
        old.unlink()
    batches: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0

    def flush() -> None:
        nonlocal current, current_chars
        if not current:
            return
        batch_id = f"BATCH-{len(batches)+1:05d}"
        payload = {
            "batch_id": batch_id,
            "generated_at": utc_now(),
            "event_count": len(current),
            "events": [
                {
                    "event_id": e.get("event_id"),
                    "timestamp": e.get("timestamp"),
                    "session_id": e.get("session_id"),
                    "turn_id": e.get("turn_id"),
                    "actor": e.get("actor"),
                    "kind": e.get("kind"),
                    "payload_type": e.get("payload_type"),
                    "text": e.get("text", ""),
                    "source_path": e.get("source_path"),
                    "source_record_ids": e.get("source_record_ids", []),
                }
                for e in current
            ],
        }
        out = batch_dir / f"{batch_id}.json"
        json_dump(out, payload)
        batches.append({"batch_id": batch_id, "path": safe_relpath(out, project_root), "event_count": len(current)})
        current = []
        current_chars = 0

    eligible_event_count = 0
    for _, _, event, err in iter_jsonl(paths.timeline):
        if err or not event or event.get("kind") not in CLASSIFIABLE_KINDS:
            continue
        eligible_event_count += 1
        chars = len(str(event.get("text") or "")) + 500
        if current and (len(current) >= max_events or current_chars + chars > max_chars):
            flush()
        current.append(event)
        current_chars += chars
    flush()
    manifest = {
        "generated_at": utc_now(),
        "source_timeline": safe_relpath(paths.timeline, project_root),
        "eligible_event_count": eligible_event_count,
        "batch_count": len(batches),
        "max_events": max_events,
        "max_chars": max_chars,
        "batches": batches,
    }
    json_dump(batch_dir / "manifest.json", manifest)
    return manifest


def prepare_incremental_batches(project_root: Path) -> dict[str, Any]:
    """Append batches only for the active-source delta produced by incremental extraction."""
    project_root = project_root.resolve()
    paths = Paths(project_root)
    batch_dir = paths.recovery / "분류입력"
    manifest_path = batch_dir / "manifest.json"
    manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8-sig"))
    stats = __import__("json").loads((paths.timeline.parent / "extraction_stats.json").read_text(encoding="utf-8-sig"))
    incremental = stats.get("incremental_extraction")
    if not isinstance(incremental, dict):
        raise RuntimeError("incremental extraction metadata is required")
    parts_path = paths.timeline.with_name(paths.timeline.name + ".parts.json")
    parts = __import__("json").loads(parts_path.read_text(encoding="utf-8-sig")).get("parts")
    if not isinstance(parts, list) or len(parts) != 2:
        raise RuntimeError("exact base+delta timeline parts are required")
    delta_path = paths.timeline.parent / str(parts[1])
    max_events = int(manifest.get("max_events") or 5000)
    max_chars = int(manifest.get("max_chars") or 5_000_000)
    batches = list(manifest.get("batches") or [])
    old_eligible = int(manifest.get("eligible_event_count") or 0)
    if sum(int(row.get("event_count") or 0) for row in batches) != old_eligible:
        raise RuntimeError("existing batch manifest does not exactly cover the prior classifiable corpus")
    current: list[dict[str, Any]] = []
    current_chars = 0
    added = 0

    def flush() -> None:
        nonlocal current, current_chars
        if not current:
            return
        batch_id = f"BATCH-{len(batches)+1:05d}"
        payload = {
            "batch_id": batch_id, "generated_at": utc_now(), "event_count": len(current),
            "events": [{
                "event_id": e.get("event_id"), "timestamp": e.get("timestamp"), "session_id": e.get("session_id"),
                "turn_id": e.get("turn_id"), "actor": e.get("actor"), "kind": e.get("kind"),
                "payload_type": e.get("payload_type"), "text": e.get("text", ""), "source_path": e.get("source_path"),
                "source_record_ids": e.get("source_record_ids", []),
            } for e in current],
        }
        out = batch_dir / f"{batch_id}.json"
        if out.exists():
            raise RuntimeError(f"incremental batch target already exists: {out}")
        json_dump(out, payload)
        batches.append({"batch_id": batch_id, "path": safe_relpath(out, project_root), "event_count": len(current)})
        current = []
        current_chars = 0

    for _, _, event, err in iter_jsonl(delta_path):
        if err or not event or event.get("kind") not in CLASSIFIABLE_KINDS:
            continue
        added += 1
        chars = len(str(event.get("text") or "")) + 500
        if current and (len(current) >= max_events or current_chars + chars > max_chars):
            flush()
        current.append(event)
        current_chars += chars
    flush()
    manifest.update({
        "generated_at": utc_now(), "eligible_event_count": old_eligible + added,
        "batch_count": len(batches), "batches": batches,
        "incremental_batching": {"prior_eligible": old_eligible, "added_eligible": added, "delta_path": safe_relpath(delta_path, project_root)},
    })
    json_dump(manifest_path, manifest)
    return manifest
