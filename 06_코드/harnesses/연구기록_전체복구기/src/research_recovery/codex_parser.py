from __future__ import annotations

import json
import gzip
import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .utils import Paths, flatten_text, iter_jsonl, json_load, safe_relpath, sha256_file, sha256_text, utc_now, write_jsonl

MESSAGE_TYPES = {"message", "user_message", "agent_message"}
TOOL_CALL_TYPES = {"function_call", "custom_tool_call", "shell_command", "command_execution", "apply_patch", "mcp_tool_call", "web_search_call"}
TOOL_OUTPUT_TYPES = {"function_call_output", "custom_tool_call_output", "command_execution_output", "mcp_tool_call_output"}


def _payload(obj: dict[str, Any]) -> dict[str, Any]:
    p = obj.get("payload")
    return p if isinstance(p, dict) else {}


def _timestamp(obj: dict[str, Any], payload: dict[str, Any]) -> str | None:
    return obj.get("timestamp") or payload.get("timestamp") or payload.get("created_at")


def _extract_role(kind: str, payload: dict[str, Any]) -> str:
    role = payload.get("role")
    if isinstance(role, str):
        return role.lower()
    ptype = str(payload.get("type") or "").lower()
    if ptype == "user_message":
        return "user"
    if ptype in {"agent_message", "assistant_message"}:
        return "assistant"
    if kind == "event_msg" and ptype == "user_message":
        return "user"
    return "system"


def _event_kind(record_type: str, payload: dict[str, Any]) -> str:
    ptype = str(payload.get("type") or "").lower()
    if record_type == "session_meta":
        return "session_meta"
    if record_type == "turn_context":
        return "turn_context"
    if record_type == "compacted":
        return "compaction"
    if ptype in MESSAGE_TYPES or (record_type == "response_item" and payload.get("role") in {"user", "assistant", "developer", "system"}):
        return "message"
    if ptype in TOOL_CALL_TYPES or ptype.endswith("_call"):
        return "tool_call"
    if ptype in TOOL_OUTPUT_TYPES or ptype.endswith("_output") or ptype.endswith("_end"):
        return "tool_output"
    if "patch" in ptype or "file_change" in ptype:
        return "file_change"
    if "plan" in ptype or "goal" in ptype:
        return "plan_update"
    if "error" in ptype or "failed" in ptype or "aborted" in ptype:
        return "error_event"
    return "system_event"


def _identity(payload: dict[str, Any]) -> str | None:
    for key in ("id", "item_id", "call_id", "turn_id", "thread_id"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            return val
    return None


def _project_relevance(text: str, project_root: Path, cwd: str | None) -> bool:
    if cwd:
        try:
            cp = Path(cwd).resolve()
            if cp == project_root or project_root in cp.parents or cp in project_root.parents:
                return True
        except Exception:
            if str(project_root).lower() in str(cwd).lower():
                return True
    pr = str(project_root).replace("\\", "/").lower()
    tx = text.replace("\\", "/").lower()
    return pr in tx or project_root.name.lower() in tx


def _extract_all_streaming(
    project_root: Path,
    *,
    include_all_sessions: bool,
    max_text_chars: int,
) -> dict[str, Any]:
    """Extract millions of records without retaining the corpus in memory."""
    paths = Paths(project_root)
    sources: list[dict[str, Any]] = []
    for _, _, obj, err in iter_jsonl(paths.source_index):
        if obj and not err:
            sources.append(obj)
    paths.raw_line_index.parent.mkdir(parents=True, exist_ok=True)
    paths.timeline.parent.mkdir(parents=True, exist_ok=True)
    duplicate_map = paths.timeline.parent / "duplicate_occurrence_map.jsonl"
    source_stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    global_event_dedup: dict[str, str] = {}
    rec_seq = 0
    event_seq = 0
    duplicate_count = 0
    parse_failures = 0
    counters: dict[str, int] = defaultdict(int)

    def emit(handle: Any, row: dict[str, Any]) -> None:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    with (
        paths.raw_line_index.open("w", encoding="utf-8", newline="\n") as raw_out,
        paths.timeline.open("w", encoding="utf-8", newline="\n") as event_out,
        duplicate_map.open("w", encoding="utf-8", newline="\n") as dup_out,
    ):
        for src in sources:
            if src.get("status") != "readable":
                continue
            if not include_all_sessions and not src.get("selected"):
                continue
            copied_path = src.get("copied_path")
            path = (project_root / str(copied_path)).resolve() if copied_path else Path(str(src["path"]))
            if not path.exists():
                raise RuntimeError(f"preserved transcript path missing: {path}")
            if path.suffix.lower() == ".gz":
                expected_gzip_sha = src.get("copied_manifest_sha256")
                if expected_gzip_sha and sha256_file(path) != expected_gzip_sha:
                    raise RuntimeError(f"preserved gzip bytes changed before extraction: {path}")
                binary = gzip.open(path, "rb")
            else:
                binary = path.open("rb")
            source_hasher = hashlib.sha256()
            source_bytes = 0
            before = path.stat()
            current_turn: str | None = None
            current_cwd: str | None = src.get("cwd")
            session_id: str | None = src.get("session_id")
            message_dedup: dict[tuple[str | None, str, str], str] = {}
            with binary:
                for line_no, raw_bytes in enumerate(binary, 1):
                    rec_seq += 1
                    rec_id = f"REC-{rec_seq:09d}"
                    source_hasher.update(raw_bytes)
                    source_bytes += len(raw_bytes)
                    line_digest = hashlib.sha256(raw_bytes).hexdigest()
                    content_bytes = raw_bytes.rstrip(b"\r\n")
                    text_line = content_bytes.decode("utf-8-sig" if line_no == 1 else "utf-8", errors="replace")
                    base_raw = {
                        "source_record_id": rec_id,
                        "source_id": src["source_id"],
                        "source_path": src["path"],
                        "preserved_path": safe_relpath(path, project_root),
                        "line_no": line_no,
                        "line_sha256": line_digest,
                        "raw_bytes_including_line_ending": len(raw_bytes),
                    }
                    source_stats[src["source_id"]]["line_count"] += 1
                    if not text_line.strip():
                        emit(raw_out, {**base_raw, "status": "blank", "classification_disposition": "explicit_blank_exclusion"})
                        continue
                    try:
                        obj = json.loads(text_line)
                    except Exception as exc:
                        parse_failures += 1
                        source_stats[src["source_id"]]["parse_failures"] += 1
                        emit(raw_out, {
                            **base_raw,
                            "status": "parse_failed",
                            "error": f"{type(exc).__name__}: {exc}",
                            "raw_preview": text_line[:500],
                            "classification_disposition": "parse_failure_blocker",
                        })
                        continue
                    if not isinstance(obj, dict):
                        emit(raw_out, {
                            **base_raw,
                            "status": "parsed_non_object",
                            "json_type": type(obj).__name__,
                            "classification_disposition": "structural_non_event_exclusion",
                        })
                        continue
                    record_type = str(obj.get("type") or "unknown")
                    payload = _payload(obj)
                    if record_type == "unknown" and not payload and any(k in obj for k in ("text", "message", "prompt")):
                        payload = dict(obj)
                        payload.setdefault("message", payload.get("text") or payload.get("prompt"))
                        payload["type"] = "user_message"
                        payload.setdefault("role", "user")
                        record_type = "history_item"
                        session_id = payload.get("session_id") or payload.get("thread_id") or session_id
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
                    canonical_event: str | None = None
                    duplicate_reason: str | None = None
                    if kind == "message" and text_hash:
                        message_key = (current_turn, actor, text_hash)
                        canonical_event = message_dedup.get(message_key)
                        if canonical_event:
                            duplicate_reason = "same_session_dual_persistence_duplicate"
                    global_key = None
                    if canonical_event is None and text_hash and kind in {
                        "message", "tool_call", "tool_output", "file_change", "plan_update", "error_event"
                    }:
                        global_key = sha256_text("\x1f".join((str(timestamp or ""), kind, actor, text_hash)))
                        canonical_event = global_event_dedup.get(global_key)
                        if canonical_event:
                            duplicate_reason = "cross_session_exact_event_duplicate"
                    if canonical_event:
                        duplicate_count += 1
                        source_stats[src["source_id"]]["duplicate_occurrences"] += 1
                        emit(dup_out, {
                            "occurrence_id": f"OCC-{rec_seq:09d}",
                            "source_record_id": rec_id,
                            "canonical_event_id": canonical_event,
                            "explicit_exclusion_reason": duplicate_reason,
                        })
                        emit(raw_out, {
                            **base_raw,
                            "status": "parsed_duplicate",
                            "record_type": record_type,
                            "payload_type": payload_type,
                            "timestamp": timestamp,
                            "session_id": session_id,
                            "canonical_event_id": canonical_event,
                            "classification_disposition": duplicate_reason,
                        })
                        continue
                    event_seq += 1
                    event_id = f"EVT-{event_seq:09d}"
                    if kind == "message" and text_hash:
                        message_dedup[(current_turn, actor, text_hash)] = event_id
                    if global_key:
                        global_event_dedup[global_key] = event_id
                    event = {
                        "event_id": event_id,
                        "source_record_ids": [rec_id],
                        "source_id": src["source_id"],
                        "session_id": session_id,
                        "turn_id": current_turn,
                        "sequence": event_seq,
                        "timestamp": timestamp,
                        "record_type": record_type,
                        "payload_type": payload_type,
                        "kind": kind,
                        "actor": actor,
                        "text": text,
                        "text_sha256": text_hash,
                        "text_projection_limit_chars": text_limit,
                        "raw_line_sha256": line_digest,
                        "source_path": src["path"],
                        "cwd": current_cwd,
                        "identity": _identity(payload),
                        "project_relevant": _project_relevance(text, project_root, current_cwd),
                        "deduplicated_from": [],
                    }
                    emit(event_out, event)
                    emit(raw_out, {
                        **base_raw,
                        "status": "parsed",
                        "record_type": record_type,
                        "payload_type": payload_type,
                        "timestamp": timestamp,
                        "turn_id": current_turn,
                        "session_id": session_id,
                        "canonical_event_id": event_id,
                        "classification_disposition": "canonical_event",
                    })
                    source_stats[src["source_id"]]["parsed"] += 1
                    source_stats[src["source_id"]]["timeline_events"] += 1
                    counters[f"kind:{kind}"] += 1
                    if kind == "message":
                        counters[f"actor:{actor}"] += 1
            observed_sha = source_hasher.hexdigest()
            expected_sha = str(src.get("sha256") or "")
            if observed_sha != expected_sha or source_bytes != int(src.get("snapshot_cutoff_size") or src.get("size_bytes") or -1):
                raise RuntimeError(f"preserved transcript content mismatch during extraction: {path}")
            after = path.stat()
            if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
                raise RuntimeError(f"preserved transcript changed during extraction: {path}")

    stats_path = paths.timeline.parent / "extraction_stats.json"
    report = {
        "generated_at": utc_now(),
        "source_count": len(sources),
        "selected_source_count": sum(bool(s.get("selected")) for s in sources),
        "raw_record_count": rec_seq,
        "timeline_event_count": event_seq,
        "duplicate_occurrence_count": duplicate_count,
        "message_count": counters["kind:message"],
        "user_message_count": counters["actor:user"],
        "assistant_message_count": counters["actor:assistant"],
        "tool_call_count": counters["kind:tool_call"],
        "tool_output_count": counters["kind:tool_output"],
        "parse_failure_count": parse_failures,
        "source_stats": {k: dict(v) for k, v in source_stats.items()},
        "raw_line_index": safe_relpath(paths.raw_line_index, project_root),
        "timeline": safe_relpath(paths.timeline, project_root),
        "duplicate_occurrence_map": safe_relpath(duplicate_map, project_root),
        "completeness_statement": "Every preserved JSONL line is indexed once; duplicate event occurrences are explicitly linked to one canonical EVT.",
    }
    from .utils import json_dump
    json_dump(stats_path, report)
    return report


def extract_all(project_root: Path, *, include_all_sessions: bool = False, max_text_chars: int = 120_000) -> dict[str, Any]:
    project_root = project_root.resolve()
    return _extract_all_streaming(
        project_root,
        include_all_sessions=include_all_sessions,
        max_text_chars=max_text_chars,
    )
    paths = Paths(project_root)
    sources = []
    if paths.source_index.exists():
        for _, _, obj, err in iter_jsonl(paths.source_index):
            if obj and not err:
                sources.append(obj)
    raw_rows: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    parse_failures = 0
    source_stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    event_seq = 0
    global_event_dedup: dict[tuple[str, str, str, str], int] = {}

    for src in sources:
        if src.get("status") != "readable":
            continue
        if not include_all_sessions and not src.get("selected"):
            continue
        copied_path = src.get("copied_path")
        path = (project_root / str(copied_path)).resolve() if copied_path else Path(src["path"])
        if path.suffix.lower() not in {".jsonl", ".json"}:
            # Plain text exports are preserved as one source event.
            try:
                text = path.read_text(encoding="utf-8-sig", errors="replace")
            except OSError as exc:
                raw_rows.append({"source_record_id": f"REC-{len(raw_rows)+1:09d}", "source_id": src["source_id"], "line_no": 0, "status": "unreadable", "error": str(exc)})
                continue
            event_seq += 1
            events.append({
                "event_id": f"EVT-{event_seq:09d}",
                "source_record_ids": [],
                "source_id": src["source_id"],
                "session_id": src.get("session_id"),
                "turn_id": None,
                "sequence": event_seq,
                "timestamp": None,
                "record_type": "text_export",
                "payload_type": "text_export",
                "kind": "message",
                "actor": "unknown",
                "text": text[:max_text_chars],
                "text_sha256": sha256_text(text),
                "source_path": src["path"],
                "project_relevant": True,
                "deduplicated_from": [],
            })
            continue

        current_turn: str | None = None
        current_cwd: str | None = src.get("cwd")
        session_id: str | None = src.get("session_id")
        message_dedup: dict[tuple[str | None, str, str], int] = {}

        for line_no, raw, obj, err in iter_jsonl(path):
            rec_id = f"REC-{len(raw_rows)+1:09d}"
            line_hash = sha256_text(raw)
            source_stats[src["source_id"]]["line_count"] += 1
            if err:
                parse_failures += 1
                source_stats[src["source_id"]]["parse_failures"] += 1
                raw_rows.append({
                    "source_record_id": rec_id,
                    "source_id": src["source_id"],
                    "source_path": src["path"],
                    "line_no": line_no,
                    "line_sha256": line_hash,
                    "status": "parse_failed",
                    "error": err,
                    "raw_preview": raw[:500],
                })
                continue
            if obj is None:
                raw_rows.append({
                    "source_record_id": rec_id,
                    "source_id": src["source_id"],
                    "source_path": src["path"],
                    "line_no": line_no,
                    "line_sha256": line_hash,
                    "status": "blank",
                })
                continue
            if not isinstance(obj, dict):
                raw_rows.append({
                    "source_record_id": rec_id,
                    "source_id": src["source_id"],
                    "source_path": src["path"],
                    "line_no": line_no,
                    "line_sha256": line_hash,
                    "status": "parsed_non_object",
                    "json_type": type(obj).__name__,
                })
                continue
            record_type = str(obj.get("type") or "unknown")
            payload = _payload(obj)
            # history.jsonl and exported prompt logs may use a flat object rather than rollout envelopes.
            if record_type == "unknown" and not payload and any(k in obj for k in ("text", "message", "prompt")):
                payload = dict(obj)
                if "message" not in payload:
                    payload["message"] = payload.get("text") or payload.get("prompt")
                payload["type"] = "user_message"
                payload.setdefault("role", "user")
                record_type = "history_item"
                session_id = payload.get("session_id") or payload.get("thread_id") or session_id
            payload_type = str(payload.get("type") or "")
            if record_type == "session_meta":
                session_id = payload.get("id") or payload.get("session_id") or payload.get("thread_id") or session_id
                current_cwd = payload.get("cwd") or payload.get("working_directory") or current_cwd
            elif record_type == "turn_context":
                current_turn = payload.get("turn_id") or obj.get("turn_id") or current_turn
                current_cwd = payload.get("cwd") or payload.get("working_directory") or current_cwd
            kind = _event_kind(record_type, payload)
            actor = _extract_role(record_type, payload)
            text = flatten_text(payload if payload else obj, max_chars=max_text_chars)
            raw_rows.append({
                "source_record_id": rec_id,
                "source_id": src["source_id"],
                "source_path": src["path"],
                "line_no": line_no,
                "line_sha256": line_hash,
                "status": "parsed",
                "record_type": record_type,
                "payload_type": payload_type,
                "timestamp": _timestamp(obj, payload),
                "turn_id": current_turn,
                "session_id": session_id,
                "text_sha256": sha256_text(text) if text else None,
                "text_chars": len(text),
            })
            source_stats[src["source_id"]]["parsed"] += 1

            # Every parsed line is accounted in raw_rows; timeline keeps semantically useful records.
            if kind in {"session_meta", "turn_context"} and not text:
                continue
            event_seq += 1
            event = {
                "event_id": f"EVT-{event_seq:09d}",
                "source_record_ids": [rec_id],
                "source_id": src["source_id"],
                "session_id": session_id,
                "turn_id": current_turn,
                "sequence": event_seq,
                "timestamp": _timestamp(obj, payload),
                "record_type": record_type,
                "payload_type": payload_type,
                "kind": kind,
                "actor": actor,
                "text": text,
                "text_sha256": sha256_text(text) if text else None,
                "source_path": src["path"],
                "cwd": current_cwd,
                "identity": _identity(payload),
                "project_relevant": _project_relevance(text, project_root, current_cwd),
                "deduplicated_from": [],
            }
            # Codex stores the same user/assistant message as response_item and event_msg.
            if kind == "message" and text:
                key = (current_turn, actor, sha256_text(text))
                prior_idx = message_dedup.get(key)
                if prior_idx is not None:
                    events[prior_idx]["source_record_ids"].append(rec_id)
                    events[prior_idx]["deduplicated_from"].append(event["event_id"])
                    source_stats[src["source_id"]]["deduplicated_messages"] += 1
                    event_seq -= 1
                    continue
                message_dedup[key] = len(events)
            # Forked/subagent sessions may persist the full parent history again.
            # Exact timestamp+kind+actor+text duplicates are linked to the first event, never silently discarded.
            if text and kind in {"message", "tool_call", "tool_output", "file_change", "plan_update", "error_event"}:
                gkey = (str(event.get("timestamp") or ""), kind, actor, sha256_text(text))
                prior_global = global_event_dedup.get(gkey)
                if prior_global is not None:
                    events[prior_global]["source_record_ids"].append(rec_id)
                    events[prior_global].setdefault("cross_session_duplicates", []).append({
                        "session_id": session_id,
                        "source_id": src["source_id"],
                        "source_record_id": rec_id,
                    })
                    source_stats[src["source_id"]]["cross_session_duplicates"] += 1
                    event_seq -= 1
                    continue
                global_event_dedup[gkey] = len(events)
            events.append(event)
            source_stats[src["source_id"]]["timeline_events"] += 1

    write_jsonl(paths.raw_line_index, raw_rows)
    write_jsonl(paths.timeline, events)
    stats_path = paths.recovery / "대화색인" / "추출통계.json"
    report = {
        "generated_at": utc_now(),
        "source_count": len(sources),
        "raw_record_count": len(raw_rows),
        "timeline_event_count": len(events),
        "message_count": sum(e["kind"] == "message" for e in events),
        "user_message_count": sum(e["kind"] == "message" and e["actor"] == "user" for e in events),
        "assistant_message_count": sum(e["kind"] == "message" and e["actor"] == "assistant" for e in events),
        "tool_call_count": sum(e["kind"] == "tool_call" for e in events),
        "tool_output_count": sum(e["kind"] == "tool_output" for e in events),
        "parse_failure_count": parse_failures,
        "source_stats": {k: dict(v) for k, v in source_stats.items()},
        "raw_line_index": safe_relpath(paths.raw_line_index, project_root),
        "timeline": safe_relpath(paths.timeline, project_root),
        "completeness_statement": "모든 접근 가능한 원본 JSONL 줄은 parsed, blank, parse_failed 중 하나로 색인된다. parse_failed가 1건이라도 있으면 엄격 복구는 실패한다.",
    }
    from .utils import json_dump
    json_dump(stats_path, report)
    return report
