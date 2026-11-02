from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .codex_parser import _event_kind, _extract_role, _identity, _payload, _project_relevance, _timestamp
from .utils import Paths, flatten_text, iter_jsonl, json_dump, json_load, safe_relpath, sha256_file, sha256_text, utc_now, write_jsonl


CLASSIFIABLE_KINDS = {"message", "tool_call", "tool_output", "file_change", "plan_update", "error_event", "compaction"}


def _tail_json(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        pos = handle.tell()
        block = bytearray()
        while pos:
            pos -= 1
            handle.seek(pos)
            char = handle.read(1)
            if char == b"\n" and block:
                break
            if char not in {b"\n", b"\r"}:
                block.extend(char)
        return json.loads(bytes(reversed(block)).decode("utf-8"))


def _assert_prefix_equal(previous: Path, current: Path, expected_lines: int) -> tuple[int, str]:
    previous_hash = hashlib.sha256()
    current_hash = hashlib.sha256()
    previous_bytes = 0
    lines = 0
    with gzip.open(previous, "rb") as old, gzip.open(current, "rb") as new:
        while True:
            old_line = old.readline()
            if not old_line:
                break
            new_line = new.readline()
            if new_line != old_line:
                raise RuntimeError(f"active snapshot prefix differs at line {lines + 1}")
            previous_hash.update(old_line)
            current_hash.update(new_line)
            previous_bytes += len(old_line)
            lines += 1
        if lines != expected_lines or previous_hash.digest() != current_hash.digest():
            raise RuntimeError(f"previous active snapshot line/hash mismatch: {lines} != {expected_lines}")
    return previous_bytes, previous_hash.hexdigest()


def _parts_manifest(path: Path, delta: Path) -> None:
    manifest_path = path.with_name(path.name + ".parts.json")
    if manifest_path.exists():
        raise RuntimeError(f"incremental parts manifest already exists: {manifest_path}")
    json_dump(manifest_path, {
        "schema": "RESEARCH_RECOVERY_JSONL_PARTS_V1",
        "created_at": utc_now(),
        "parts": [path.name, delta.name],
        "base_immutable": True,
        "delta_create_once": True,
    })


def incremental_extract_active_source(
    project_root: Path,
    *,
    max_text_chars: int = 120_000,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    paths = Paths(project_root)
    stats = json_load(paths.timeline.parent / "extraction_stats.json", {})
    if not stats:
        raise RuntimeError("prior complete extraction_stats.json is required for incremental extraction")
    for base in (paths.raw_line_index, paths.timeline, paths.timeline.parent / "duplicate_occurrence_map.jsonl"):
        if not base.is_file() or base.with_name(base.name + ".parts.json").exists():
            raise RuntimeError(f"incremental extraction requires one unchained complete base: {base}")

    sources = [obj for _, _, obj, err in iter_jsonl(paths.source_index) if obj and not err and obj.get("selected")]
    previous_stats = stats.get("source_stats") if isinstance(stats.get("source_stats"), dict) else {}
    changed: list[tuple[dict[str, Any], int, int]] = []
    for source in sources:
        prior = previous_stats.get(source.get("source_id"), {})
        old_lines = int(prior.get("line_count") or 0)
        new_lines = int(source.get("line_count") or 0)
        if new_lines != old_lines:
            changed.append((source, old_lines, new_lines))
    if len(changed) != 1:
        raise RuntimeError(f"incremental extraction requires exactly one changed selected source: {[(r.get('source_id'), a, b) for r, a, b in changed]}")
    source, old_lines, new_lines = changed[0]
    if new_lines <= old_lines:
        raise RuntimeError("changed active source did not grow monotonically")
    current = project_root / str(source.get("copied_path"))
    if current.suffix.lower() != ".gz" or not current.is_file():
        raise RuntimeError("changed source must be a preserved gzip snapshot")
    if sha256_file(current) != source.get("copied_manifest_sha256"):
        raise RuntimeError("current active gzip snapshot bytes differ from source index")
    candidates = sorted((paths.recovery / "원본보관" / "gzip_snapshots_v3").glob(f"{source['source_id']}_*.gz"))
    if len(candidates) != 1:
        raise RuntimeError(f"exactly one prior active snapshot is required: {candidates}")
    previous = candidates[0]
    prefix_bytes, prefix_sha = _assert_prefix_equal(previous, current, old_lines)

    raw_tail = _tail_json(paths.raw_line_index)
    event_tail = _tail_json(paths.timeline)
    dup_path = paths.timeline.parent / "duplicate_occurrence_map.jsonl"
    rec_seq = int(str(raw_tail["source_record_id"]).split("-")[-1])
    event_seq = int(str(event_tail["event_id"]).split("-")[-1])
    if rec_seq != int(stats.get("raw_record_count")) or event_seq != int(stats.get("timeline_event_count")):
        raise RuntimeError("prior extraction tail IDs do not match extraction stats")

    current_turn: str | None = None
    current_cwd: str | None = source.get("cwd")
    session_id: str | None = source.get("session_id")
    local_message_map: dict[tuple[str | None, str, str], str] = {}
    for _, _, event, err in iter_jsonl(paths.timeline):
        if err or not event or event.get("source_id") != source.get("source_id"):
            continue
        current_turn = event.get("turn_id") or current_turn
        current_cwd = event.get("cwd") or current_cwd
        session_id = event.get("session_id") or session_id
        if event.get("kind") == "message" and event.get("text_sha256"):
            local_message_map[(event.get("turn_id"), str(event.get("actor")), str(event.get("text_sha256")))] = str(event["event_id"])

    parsed_new: list[dict[str, Any]] = []
    with gzip.open(current, "rb") as handle:
        for line_no, raw_bytes in enumerate(handle, 1):
            if line_no <= old_lines:
                continue
            line_digest = hashlib.sha256(raw_bytes).hexdigest()
            text_line = raw_bytes.rstrip(b"\r\n").decode("utf-8", errors="replace")
            row: dict[str, Any] = {
                "line_no": line_no,
                "raw_bytes": raw_bytes,
                "line_sha256": line_digest,
                "text_line": text_line,
            }
            if not text_line.strip():
                row["status"] = "blank"
                parsed_new.append(row)
                continue
            try:
                obj = json.loads(text_line)
            except Exception as exc:
                row.update({"status": "parse_failed", "error": f"{type(exc).__name__}: {exc}"})
                parsed_new.append(row)
                continue
            if not isinstance(obj, dict):
                row.update({"status": "parsed_non_object", "json_type": type(obj).__name__})
                parsed_new.append(row)
                continue
            record_type = str(obj.get("type") or "unknown")
            payload = _payload(obj)
            payload_type = str(payload.get("type") or "")
            if record_type == "session_meta":
                session_id = payload.get("id") or payload.get("session_id") or payload.get("thread_id") or session_id
                current_cwd = payload.get("cwd") or payload.get("working_directory") or current_cwd
            elif record_type == "turn_context":
                current_turn = payload.get("turn_id") or obj.get("turn_id") or current_turn
                current_cwd = payload.get("cwd") or payload.get("working_directory") or current_cwd
            kind = _event_kind(record_type, payload)
            actor = _extract_role(record_type, payload)
            text_limit = max_text_chars if kind == "message" else (50_000 if kind in {"error_event", "file_change"} else 20_000)
            if kind in {"session_meta", "turn_context", "system_event"}:
                text_limit = 4_000
            text = flatten_text(payload if payload else obj, max_chars=text_limit)
            text_hash = sha256_text(text) if text else None
            timestamp = _timestamp(obj, payload)
            global_key = None
            if text_hash and kind in {"message", "tool_call", "tool_output", "file_change", "plan_update", "error_event"}:
                global_key = sha256_text("\x1f".join((str(timestamp or ""), kind, actor, text_hash)))
            row.update({
                "status": "parsed", "record_type": record_type, "payload_type": payload_type,
                "timestamp": timestamp, "turn_id": current_turn, "cwd": current_cwd,
                "session_id": session_id, "kind": kind, "actor": actor, "text": text,
                "text_hash": text_hash, "text_limit": text_limit, "identity": _identity(payload),
                "global_key": global_key,
            })
            parsed_new.append(row)
    if len(parsed_new) != new_lines - old_lines:
        raise RuntimeError(f"incremental line count mismatch: {len(parsed_new)} != {new_lines - old_lines}")

    candidate_keys = {str(row["global_key"]) for row in parsed_new if row.get("global_key")}
    existing_global: dict[str, str] = {}
    if candidate_keys:
        for _, _, event, err in iter_jsonl(paths.timeline):
            if err or not event or not event.get("text_sha256") or event.get("kind") not in {"message", "tool_call", "tool_output", "file_change", "plan_update", "error_event"}:
                continue
            key = sha256_text("\x1f".join((str(event.get("timestamp") or ""), str(event.get("kind")), str(event.get("actor")), str(event.get("text_sha256")))))
            if key in candidate_keys and key not in existing_global:
                existing_global[key] = str(event["event_id"])

    suffix = f"incremental_{source['source_id']}_{old_lines + 1}_{new_lines}"
    raw_delta = paths.raw_line_index.with_name(paths.raw_line_index.stem + f".{suffix}.jsonl")
    timeline_delta = paths.timeline.with_name(paths.timeline.stem + f".{suffix}.jsonl")
    dup_delta = dup_path.with_name(dup_path.stem + f".{suffix}.jsonl")
    for target in (raw_delta, timeline_delta, dup_delta):
        if target.exists():
            raise RuntimeError(f"incremental create-once delta already exists: {target}")
    raw_rows: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    dup_rows: list[dict[str, Any]] = []
    delta_stats: Counter[str] = Counter()
    new_global: dict[str, str] = {}
    for row in parsed_new:
        rec_seq += 1
        rec_id = f"REC-{rec_seq:09d}"
        base_raw = {
            "source_record_id": rec_id, "source_id": source["source_id"], "source_path": source["path"],
            "preserved_path": safe_relpath(current, project_root), "line_no": row["line_no"],
            "line_sha256": row["line_sha256"], "raw_bytes_including_line_ending": len(row["raw_bytes"]),
        }
        if row["status"] == "blank":
            raw_rows.append({**base_raw, "status": "blank", "classification_disposition": "explicit_blank_exclusion"})
            continue
        if row["status"] == "parse_failed":
            raw_rows.append({**base_raw, "status": "parse_failed", "error": row["error"], "raw_preview": row["text_line"][:500], "classification_disposition": "parse_failure_blocker"})
            delta_stats["parse_failures"] += 1
            continue
        if row["status"] == "parsed_non_object":
            raw_rows.append({**base_raw, "status": "parsed_non_object", "json_type": row["json_type"], "classification_disposition": "structural_non_event_exclusion"})
            continue
        canonical: str | None = None
        reason: str | None = None
        if row["kind"] == "message" and row.get("text_hash"):
            canonical = local_message_map.get((row.get("turn_id"), str(row["actor"]), str(row["text_hash"])))
            if canonical:
                reason = "same_session_dual_persistence_duplicate"
        if canonical is None and row.get("global_key"):
            canonical = existing_global.get(str(row["global_key"])) or new_global.get(str(row["global_key"]))
            if canonical:
                reason = "cross_session_exact_event_duplicate"
        if canonical:
            dup_rows.append({"occurrence_id": f"OCC-{rec_seq:09d}", "source_record_id": rec_id, "canonical_event_id": canonical, "explicit_exclusion_reason": reason})
            raw_rows.append({**base_raw, "status": "parsed_duplicate", "record_type": row["record_type"], "payload_type": row["payload_type"], "timestamp": row["timestamp"], "session_id": row["session_id"], "canonical_event_id": canonical, "classification_disposition": reason})
            delta_stats["duplicates"] += 1
            continue
        event_seq += 1
        event_id = f"EVT-{event_seq:09d}"
        if row["kind"] == "message" and row.get("text_hash"):
            local_message_map[(row.get("turn_id"), str(row["actor"]), str(row["text_hash"]))] = event_id
        if row.get("global_key"):
            new_global[str(row["global_key"])] = event_id
        event = {
            "event_id": event_id, "source_record_ids": [rec_id], "source_id": source["source_id"],
            "session_id": row["session_id"], "turn_id": row["turn_id"], "sequence": event_seq,
            "timestamp": row["timestamp"], "record_type": row["record_type"], "payload_type": row["payload_type"],
            "kind": row["kind"], "actor": row["actor"], "text": row["text"], "text_sha256": row["text_hash"],
            "text_projection_limit_chars": row["text_limit"], "raw_line_sha256": row["line_sha256"],
            "source_path": source["path"], "cwd": row["cwd"], "identity": row["identity"],
            "project_relevant": _project_relevance(str(row["text"]), project_root, row["cwd"]), "deduplicated_from": [],
        }
        events.append(event)
        raw_rows.append({**base_raw, "status": "parsed", "record_type": row["record_type"], "payload_type": row["payload_type"], "timestamp": row["timestamp"], "turn_id": row["turn_id"], "session_id": row["session_id"], "canonical_event_id": event_id, "classification_disposition": "canonical_event"})
        delta_stats["events"] += 1
        delta_stats[f"kind:{row['kind']}"] += 1
        if row["kind"] == "message":
            delta_stats[f"actor:{row['actor']}"] += 1

    write_jsonl(raw_delta, raw_rows)
    write_jsonl(timeline_delta, events)
    write_jsonl(dup_delta, dup_rows)
    _parts_manifest(paths.raw_line_index, raw_delta)
    _parts_manifest(paths.timeline, timeline_delta)
    _parts_manifest(dup_path, dup_delta)

    active_stats = dict(previous_stats[source["source_id"]])
    active_stats["line_count"] = new_lines
    active_stats["parsed"] = int(active_stats.get("parsed") or 0) + int(delta_stats["events"])
    active_stats["timeline_events"] = int(active_stats.get("timeline_events") or 0) + int(delta_stats["events"])
    active_stats["duplicate_occurrences"] = int(active_stats.get("duplicate_occurrences") or 0) + int(delta_stats["duplicates"])
    active_stats["parse_failures"] = int(active_stats.get("parse_failures") or 0) + int(delta_stats["parse_failures"])
    previous_stats[source["source_id"]] = active_stats
    stats.update({
        "generated_at": utc_now(),
        "raw_record_count": int(stats["raw_record_count"]) + len(parsed_new),
        "timeline_event_count": int(stats["timeline_event_count"]) + int(delta_stats["events"]),
        "duplicate_occurrence_count": int(stats["duplicate_occurrence_count"]) + int(delta_stats["duplicates"]),
        "message_count": int(stats["message_count"]) + int(delta_stats["kind:message"]),
        "user_message_count": int(stats["user_message_count"]) + int(delta_stats["actor:user"]),
        "assistant_message_count": int(stats["assistant_message_count"]) + int(delta_stats["actor:assistant"]),
        "tool_call_count": int(stats["tool_call_count"]) + int(delta_stats["kind:tool_call"]),
        "tool_output_count": int(stats["tool_output_count"]) + int(delta_stats["kind:tool_output"]),
        "parse_failure_count": int(stats["parse_failure_count"]) + int(delta_stats["parse_failures"]),
        "source_stats": previous_stats,
        "incremental_extraction": {
            "source_id": source["source_id"], "previous_lines": old_lines, "current_lines": new_lines,
            "previous_prefix_bytes": prefix_bytes, "previous_prefix_sha256": prefix_sha,
            "delta_raw_records": len(parsed_new), "delta_events": int(delta_stats["events"]),
            "delta_duplicates": int(delta_stats["duplicates"]), "delta_parse_failures": int(delta_stats["parse_failures"]),
            "parts_manifests": [safe_relpath(p.with_name(p.name + '.parts.json'), project_root) for p in (paths.raw_line_index, paths.timeline, dup_path)],
        },
    })
    json_dump(paths.timeline.parent / "extraction_stats.json", stats)
    return stats
