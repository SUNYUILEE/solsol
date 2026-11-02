from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from .cleanup import (
    BLOCKED_NAME,
    CLEANUP_SCHEMA,
    EXTERNAL_NAME,
    INVENTORY_NAME,
    INVENTORY_SCHEMA,
    OUTPUT_REL,
    REPORT_NAME,
    _artifact_id,
    _reference_names,
    _rel,
    _retention,
    cleanup_preflight,
)
from .utils import Paths, iter_jsonl, json_dump, sha256_file, utc_now


DB_NAME = "cleanup_inventory_checkpoint.sqlite3"
PATH_ORDER_NAME = "cleanup_path_order.jsonl"
FAILURE_NAME = "CLEANUP_DRY_RUN_FAILURE_LOG.json"
STATE_SCHEMA = "YEOUIDO_RESEARCH_STORAGE_CLEANUP_STREAM_STATE_V1"


def record_failed_uncheckpointed_scan(
    project_root: Path,
    *,
    elapsed_seconds: float,
    process_id: int,
) -> dict[str, Any]:
    output = project_root.resolve() / OUTPUT_REL
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "YEOUIDO_RESEARCH_STORAGE_CLEANUP_FAILURE_V1",
        "generated_at": utc_now(),
        "status": "FAILED_HARNESS_SCAN_NO_DELETION",
        "failure_signature": "UNBOUNDED_IN_MEMORY_FULL_TREE_SCAN_WITHOUT_DURABLE_CHECKPOINT",
        "failed_command": "research_recovery.py cleanup-dry-run --scope-root ..",
        "observed_elapsed_seconds": elapsed_seconds,
        "observed_process_id": process_id,
        "root_cause": [
            "Every inventory row was accumulated in memory until the full traversal ended.",
            "Small text files were read a second time for embedded IDs after SHA-256 hashing.",
            "No durable progress checkpoint existed, so timeout yielded no reusable inventory rows.",
        ],
        "recurrence_controls": [
            "SQLite durable checkpoint committed in bounded batches.",
            "Streaming inventory export; no all-row Python list.",
            "Explicit --resume required after a bounded incomplete chunk.",
            "No embedded-text second read during the file scan.",
            "No deletion implementation or authorization in the dry-run harness.",
        ],
        "files_deleted": 0,
        "bytes_deleted": 0,
        "optimizer_or_experiment_executed": False,
    }
    json_dump(output / FAILURE_NAME, payload)
    return payload


def _connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
          relative_path TEXT PRIMARY KEY,
          absolute_path TEXT NOT NULL,
          file_name TEXT NOT NULL,
          size_bytes INTEGER NOT NULL,
          sha256 TEXT NOT NULL,
          mtime_ns INTEGER NOT NULL,
          ctime_ns INTEGER NOT NULL,
          device INTEGER NOT NULL,
          inode INTEGER NOT NULL,
          hash_source TEXT NOT NULL,
          retention_class TEXT NOT NULL,
          retention_reason TEXT NOT NULL,
          referenced INTEGER NOT NULL,
          regenerable INTEGER NOT NULL,
          regeneration_command TEXT,
          deletion_candidate INTEGER NOT NULL,
          status TEXT NOT NULL,
          error TEXT
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS files_sha ON files(sha256)")
    db.execute("CREATE INDEX IF NOT EXISTS files_inode ON files(device,inode)")
    db.execute("CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
    db.commit()
    return db


def _metadata(db: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
    return default if row is None else json.loads(row[0])


def _set_metadata(db: sqlite3.Connection, key: str, value: Any) -> None:
    db.execute(
        "INSERT INTO metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value, ensure_ascii=False, separators=(",", ":"))),
    )


def _is_reparse(path: Path) -> bool:
    try:
        stat = path.lstat()
    except OSError:
        return True
    attrs = getattr(stat, "st_file_attributes", 0)
    return path.is_symlink() or bool(attrs & 0x400)


def _walk_live(root: Path, output: Path) -> Iterator[Path]:
    output = output.resolve()
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        kept: list[str] = []
        for name in dirs:
            child = current_path / name
            try:
                if _is_reparse(child):
                    continue
                if child.resolve() == output:
                    continue
            except OSError:
                continue
            kept.append(name)
        dirs[:] = sorted(kept, key=str.casefold)
        for name in sorted(files, key=str.casefold):
            yield current_path / name


def _walk(root: Path, output: Path) -> Iterator[Path]:
    order = output / PATH_ORDER_NAME
    if not order.is_file():
        yield from _walk_live(root, output)
        return
    with order.open("r", encoding="utf-8") as handle:
        for line in handle:
            relative = json.loads(line)
            if not isinstance(relative, str):
                raise RuntimeError("cleanup path-order row is not a string")
            yield root / Path(relative)


def build_cleanup_path_order(project_root: Path, scope_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    scope_root = scope_root.resolve()
    output = project_root / OUTPUT_REL
    output.mkdir(parents=True, exist_ok=True)
    order = output / PATH_ORDER_NAME
    if order.exists():
        raise RuntimeError(f"cleanup path order already exists; preserve it and resume: {order}")
    temporary = order.with_suffix(order.suffix + ".tmp")
    count = 0
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for path in _walk_live(scope_root, output):
            handle.write(json.dumps(_rel(path, scope_root), ensure_ascii=False) + "\n")
            count += 1
    os.replace(temporary, order)
    result = {
        "schema": "YEOUIDO_RESEARCH_STORAGE_CLEANUP_PATH_ORDER_V1",
        "generated_at": utc_now(), "status": "PASS_PATH_ORDER_FROZEN",
        "scope_root": str(scope_root), "path_count": count,
        "path_order": str(order), "bytes": order.stat().st_size,
        "sha256": sha256_file(order), "files_deleted": 0, "bytes_deleted": 0,
    }
    json_dump(output / "CLEANUP_PATH_ORDER_MANIFEST.json", result)
    return result


def _certified_hashes(project_root: Path, scope_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    paths = Paths(project_root)
    for source in (paths.source_index, paths.project_files):
        if not source.is_file():
            continue
        for _, _, row, error in iter_jsonl(source):
            if error or not row:
                continue
            if source == paths.source_index and not row.get("selected"):
                continue
            absolute = Path(str(row.get("path") or row.get("absolute_path") or ""))
            sha = row.get("sha256")
            if absolute.is_absolute() and isinstance(sha, str) and len(sha) == 64:
                try:
                    result[_rel(absolute.resolve(), scope_root)] = sha
                except ValueError:
                    pass
    return result


def _scan_chunk(
    db: sqlite3.Connection,
    project_root: Path,
    scope_root: Path,
    output: Path,
    *,
    max_seconds: float,
) -> dict[str, Any]:
    start = time.monotonic()
    references = _reference_names(project_root)
    certified = _certified_hashes(project_root, scope_root)
    existing_index = {
        str(relative): (int(size), int(mtime), str(status))
        for relative, size, mtime, status in db.execute(
            "SELECT relative_path,size_bytes,mtime_ns,status FROM files"
        )
    }
    inode_sha: dict[tuple[int, int, int, int], str] = {}
    cursor_ordinal = int(_metadata(db, "cursor_ordinal", len(existing_index)))
    ordinal = 0
    cursor_skipped = scanned = skipped = unreadable = 0
    batch = 0
    complete = True
    for path in _walk(scope_root, output):
        if ordinal < cursor_ordinal:
            ordinal += 1
            cursor_skipped += 1
            continue
        if time.monotonic() - start >= max_seconds:
            complete = False
            break
        if _is_reparse(path):
            ordinal += 1
            continue
        try:
            stat = path.stat()
            relative = _rel(path, scope_root)
            existing = existing_index.get(relative)
            if existing and existing[0] == stat.st_size and existing[1] == stat.st_mtime_ns and existing[2] == "readable":
                skipped += 1
                ordinal += 1
                continue
            identity = (int(stat.st_dev), int(stat.st_ino), int(stat.st_size), int(stat.st_mtime_ns))
            sha = certified.get(relative)
            source = "strict_or_project_inventory"
            if not sha:
                sha = inode_sha.get(identity)
                source = "same_physical_file_identity" if sha else "live_sha256"
            if not sha:
                sha = sha256_file(path)
            inode_sha[identity] = sha
            referenced = path.name.casefold() in references
            retention, reason, candidate, regen = _retention(relative, path, referenced)
            values = (
                relative, str(path.resolve()), path.name, int(stat.st_size), sha,
                int(stat.st_mtime_ns), int(stat.st_ctime_ns), int(stat.st_dev), int(stat.st_ino),
                source, retention, reason, int(referenced), int(regen is not None), regen,
                int(candidate), "readable", None,
            )
            db.execute(
                """INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(relative_path) DO UPDATE SET
                  absolute_path=excluded.absolute_path,file_name=excluded.file_name,
                  size_bytes=excluded.size_bytes,sha256=excluded.sha256,mtime_ns=excluded.mtime_ns,
                  ctime_ns=excluded.ctime_ns,device=excluded.device,inode=excluded.inode,
                  hash_source=excluded.hash_source,retention_class=excluded.retention_class,
                  retention_reason=excluded.retention_reason,referenced=excluded.referenced,
                  regenerable=excluded.regenerable,regeneration_command=excluded.regeneration_command,
                  deletion_candidate=excluded.deletion_candidate,status=excluded.status,error=excluded.error""",
                values,
            )
            existing_index[relative] = (int(stat.st_size), int(stat.st_mtime_ns), "readable")
            scanned += 1
            batch += 1
            ordinal += 1
        except OSError as exc:
            unreadable += 1
            relative = str(path)
            db.execute(
                "INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (relative, str(path), path.name, 0, "", 0, 0, 0, 0, "unreadable", "PERMANENT",
                 "unreadable artifact", 0, 0, None, 0, "unreadable", f"{type(exc).__name__}: {exc}"),
            )
            batch += 1
            ordinal += 1
        if batch >= 250:
            _set_metadata(db, "last_commit_at", utc_now())
            db.commit()
            batch = 0
    _set_metadata(db, "scan_complete", complete)
    _set_metadata(db, "cursor_ordinal", ordinal)
    _set_metadata(db, "last_chunk", {"at": utc_now(), "cursor_fast_skipped": cursor_skipped, "scanned": scanned, "skipped": skipped, "unreadable": unreadable, "elapsed_seconds": time.monotonic() - start})
    db.commit()
    return {"complete": complete, "cursor_fast_skipped": cursor_skipped, "scanned": scanned, "skipped": skipped, "unreadable": unreadable, "elapsed_seconds": time.monotonic() - start, "database_rows": db.execute("SELECT COUNT(*) FROM files").fetchone()[0], "cursor_ordinal": ordinal}


def _duplicate_maps(db: sqlite3.Connection) -> tuple[dict[str, tuple[str, str]], dict[str, int]]:
    member: dict[str, tuple[str, str]] = {}
    stats = {"groups": 0, "logical_bytes": 0, "physical_bytes": 0}
    groups = db.execute("SELECT sha256 FROM files WHERE status='readable' AND size_bytes>0 GROUP BY sha256 HAVING COUNT(*)>1")
    priority = {"PERMANENT": 0, "EVIDENCE": 1, "REPRODUCIBLE": 2, "TEMP": 3}
    for (sha,) in groups:
        rows = db.execute("SELECT relative_path,retention_class,referenced,size_bytes,device,inode FROM files WHERE sha256=?", (sha,)).fetchall()
        rows.sort(key=lambda r: (priority.get(r[1], 9), -int(r[2]), len(r[0]), r[0]))
        keeper = rows[0][0]
        group_id = f"DUP-{sha[:16].upper()}"
        stats["groups"] += 1
        seen_physical = {(rows[0][4], rows[0][5])}
        for index, row in enumerate(rows):
            member[row[0]] = (group_id, keeper)
            if index:
                stats["logical_bytes"] += int(row[3])
                physical = (row[4], row[5])
                if physical not in seen_physical:
                    stats["physical_bytes"] += int(row[3])
                    seen_physical.add(physical)
    return member, stats


def _export_and_report(db: sqlite3.Connection, project_root: Path, scope_root: Path, output: Path) -> dict[str, Any]:
    duplicate, duplicate_stats = _duplicate_maps(db)
    inventory = output / INVENTORY_NAME
    temp = inventory.with_suffix(inventory.suffix + ".tmp")
    class_counts: Counter[str] = Counter()
    class_bytes: Counter[str] = Counter()
    inode_sizes: dict[tuple[int, int], int] = {}
    candidate_inodes: dict[tuple[int, int], int] = {}
    top_candidates: list[dict[str, Any]] = []
    top_protected: list[dict[str, Any]] = []
    count = 0
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in db.execute("SELECT * FROM files ORDER BY relative_path"):
            (relative, absolute, name, size, sha, mtime, ctime, dev, ino, hash_source,
             retention, reason, referenced, regenerable, regen, candidate, status, error) = row
            dup = duplicate.get(relative)
            is_keeper = bool(dup and dup[1] == relative)
            if dup and not is_keeper and retention != "PERMANENT" and not referenced:
                candidate = 1
                reason = "non-authoritative exact-SHA duplicate; approval and recheck still required"
            item = {
                "schema": INVENTORY_SCHEMA, "artifact_id": _artifact_id(relative),
                "absolute_path": absolute, "relative_path": relative, "file_name": name,
                "size_bytes": size, "sha256": sha, "sha256_evidence_source": hash_source,
                "created_at_epoch": ctime / 1e9 if ctime else None,
                "modified_at_epoch": mtime / 1e9 if mtime else None,
                "physical_identity": {"device": dev, "inode": ino},
                "producer_run_ids": [], "role_ids": [], "related_req_ids": [], "related_fail_ids": [],
                "related_validation": relative if "audit" in relative.lower() else None,
                "canonical_result_referenced": False, "referenced_by_other_artifact": bool(referenced),
                "regenerable": bool(regenerable), "regeneration_command": regen,
                "retention_class": retention, "retention_reason": reason,
                "deletion_candidate": bool(candidate), "deletion_authorized": False,
                "deletion_basis": reason if candidate else None,
                "deletion_prohibited_reason": None if candidate else reason,
                "status": status, "error": error,
            }
            if dup:
                item.update({"duplicate_group_id": dup[0], "duplicate_keeper_artifact_id": _artifact_id(dup[1]), "duplicate_is_keeper": is_keeper})
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
            class_counts[retention] += 1
            class_bytes[retention] += int(size)
            physical = (dev, ino)
            inode_sizes.setdefault(physical, int(size))
            summary = {"artifact_id": item["artifact_id"], "relative_path": relative, "size_bytes": size, "retention_class": retention, "reason": reason}
            target = top_candidates if candidate else top_protected
            target.append(summary)
            target.sort(key=lambda x: x["size_bytes"], reverse=True)
            del target[50:]
            if candidate:
                candidate_inodes.setdefault(physical, int(size))
    os.replace(temp, inventory)

    source_paths = Paths(project_root)
    external: list[dict[str, Any]] = []
    if source_paths.source_index.is_file():
        for _, _, row, error in iter_jsonl(source_paths.source_index):
            if error or not row or not row.get("selected"):
                continue
            original = Path(str(row.get("path") or row.get("absolute_path") or ""))
            external.append({"schema": "YEOUIDO_EXTERNAL_REFERENCE_V1", "artifact_id": f"EXT-{row.get('source_id')}", "source_id": row.get("source_id"), "absolute_path": str(original), "size_bytes": row.get("size_bytes"), "sha256": row.get("sha256"), "version_or_date": row.get("mtime") or row.get("modified_at"), "accessible": original.is_file(), "retention_class": "PERMANENT"})
    with (output / EXTERNAL_NAME).open("w", encoding="utf-8", newline="\n") as handle:
        for row in external:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    preflight = cleanup_preflight(project_root, scope_root)
    disk = shutil.disk_usage(scope_root)
    report = {
        "schema": CLEANUP_SCHEMA, "generated_at": utc_now(), "status": "CLEANUP_BLOCKED" if preflight["blockers"] else "FINAL_CLEANUP_DRY_RUN_READY_FOR_USER_REVIEW",
        "mode": "DRY_RUN_ONLY", "project_root": str(project_root), "scope_root": str(scope_root), "preflight": preflight,
        "inventory": {"path": str(inventory.relative_to(project_root)).replace("\\", "/"), "file_count": count, "logical_total_bytes": sum(class_bytes.values()), "estimated_unique_physical_file_bytes": sum(inode_sizes.values()), "retention_counts": dict(class_counts), "retention_bytes": dict(class_bytes)},
        "external_references": {"path": str((output / EXTERNAL_NAME).relative_to(project_root)).replace("\\", "/"), "count": len(external)},
        "duplicates": {"sha256_group_count": duplicate_stats["groups"], "logical_duplicate_bytes": duplicate_stats["logical_bytes"], "estimated_physical_reclaimable_bytes": duplicate_stats["physical_bytes"]},
        "tentative_deletion": {"file_count": db.execute("SELECT COUNT(*) FROM files WHERE deletion_candidate=1").fetchone()[0], "estimated_reclaimable_bytes": sum(candidate_inodes.values()), "expected_physical_usage_after_bytes": max(0, sum(inode_sizes.values()) - sum(candidate_inodes.values())), "expected_free_space_after_bytes": disk.free + sum(candidate_inodes.values()), "actual_deletion_performed": False, "actual_deletion_authorized": False},
        "disk": {"capacity_bytes": disk.total, "free_bytes": disk.free, "used_bytes": disk.used},
        "top_50_deletion_candidates": top_candidates, "top_50_protected_large_files": top_protected,
        "canonical_reproduction_required_files": [], "canonical_reproduction_status": "BLOCKED_NO_CANONICAL_SCIENTIFIC_RUN" if not preflight["canonical_run_ids"] else "REGISTERED",
        "approval_required": "User must explicitly say 최종 정리 실행 after blockers are cleared and this dry-run is reviewed.",
        "tombstone_path_reserved": str((output / "tombstones.jsonl").relative_to(project_root)).replace("\\", "/"),
        "deletion_code_present": False,
    }
    json_dump(output / REPORT_NAME, report)
    if preflight["blockers"]:
        json_dump(output / BLOCKED_NAME, {"schema": "YEOUIDO_RESEARCH_STORAGE_CLEANUP_BLOCKED_V1", "generated_at": report["generated_at"], "status": "CLEANUP_BLOCKED", "blockers": preflight["blockers"], "deleted_file_count": 0, "deleted_bytes": 0})
    return report


def run_streaming_cleanup_dry_run(
    project_root: Path,
    scope_root: Path,
    *,
    max_seconds: float,
    resume: bool,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    scope_root = scope_root.resolve()
    output = project_root / OUTPUT_REL
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = output / DB_NAME
    if checkpoint.exists() and not resume:
        raise RuntimeError(f"Cleanup checkpoint already exists; use --resume, never overwrite progress: {checkpoint}")
    if not checkpoint.exists() and resume:
        raise RuntimeError("--resume requested but no cleanup checkpoint exists")
    work_name = hashlib.sha256(str(scope_root).encode("utf-8")).hexdigest()[:16]
    database = Path(tempfile.gettempdir()) / f"research_cleanup_{work_name}_{os.getpid()}.sqlite3"
    if resume:
        database.write_bytes(checkpoint.read_bytes())
    elif database.exists():
        database.unlink()
    db = _connect(database)
    try:
        _set_metadata(db, "schema", STATE_SCHEMA)
        _set_metadata(db, "scope_root", str(scope_root))
        db.commit()
        chunk = _scan_chunk(db, project_root, scope_root, output, max_seconds=max_seconds)
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.commit()
        snapshot = database.with_suffix(".snapshot.sqlite3")
        snapshot.unlink(missing_ok=True)
        snapshot_db = sqlite3.connect(snapshot)
        try:
            db.backup(snapshot_db)
        finally:
            snapshot_db.close()
        checkpoint.write_bytes(snapshot.read_bytes())
        snapshot.unlink(missing_ok=True)
        if not chunk["complete"]:
            result = {
                "schema": STATE_SCHEMA, "generated_at": utc_now(), "status": "INCOMPLETE_CHECKPOINTED",
                "chunk": chunk, "checkpoint_database": str(checkpoint), "resume_required": True,
                "exact_resume": f"python -B research_recovery.py --project-root . cleanup-dry-run-stream --scope-root .. --max-seconds {max_seconds:g} --resume",
                "files_deleted": 0, "bytes_deleted": 0, "deletion_authorized": False,
            }
            json_dump(output / "CLEANUP_SCAN_INCOMPLETE.json", result)
            return result
        return _export_and_report(db, project_root, scope_root, output)
    finally:
        db.close()
        database.unlink(missing_ok=True)
        Path(str(database) + "-wal").unlink(missing_ok=True)
        Path(str(database) + "-shm").unlink(missing_ok=True)
