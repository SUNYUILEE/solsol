from __future__ import annotations

import json
import gzip
import hashlib
import os
import shutil
import time
from pathlib import Path
from typing import Any, Iterable

from .utils import Paths, codex_home, json_dump, safe_relpath, sha256_file, utc_now, write_jsonl

TRANSCRIPT_SUFFIXES = {".jsonl", ".json", ".md", ".txt"}
EXCLUDE_NAMES = {"auth.json"}
RAW_CHUNK_MIN_BYTES = 256 * 1024
RAW_CHUNK_MAX_BYTES = 4 * 1024 * 1024
RAW_CHUNK_BOUNDARY_MASK = 0x3F
FINGERPRINT_READ_BYTES = 8 * 1024 * 1024


def _session_meta_from_jsonl(path: Path) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("type") == "session_meta":
                    payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
                    meta = dict(payload)
                    meta.setdefault("timestamp", obj.get("timestamp"))
                    break
    except OSError:
        pass
    return meta


def _count_lines(path: Path) -> int:
    count = 0
    try:
        with path.open("rb") as f:
            for _ in f:
                count += 1
    except OSError:
        return -1
    return count


def _project_path_match(project_root: Path, cwd: Any, scope_roots: Iterable[Path] = ()) -> bool:
    if not cwd:
        return False
    try:
        cwd_path = Path(str(cwd)).resolve()
        roots = (project_root, *(root.resolve() for root in scope_roots))
        return any(cwd_path == root or root in cwd_path.parents or cwd_path in root.parents for root in roots)
    except Exception:
        return any(str(root).lower() in str(cwd).lower() for root in (project_root, *scope_roots))


def _legacy_copy(raw_dir: Path, source: Path, size_bytes: int) -> Path | None:
    """Return a complete file-level copy made by older harness versions, if any."""
    for candidate in raw_dir.glob(f"*/*_{source.name}"):
        try:
            if candidate.is_file() and candidate.stat().st_size == size_bytes:
                return candidate
        except OSError:
            continue
    return None


def _fingerprint(path: Path) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    size = 0
    newlines = 0
    last = None
    with path.open("rb") as f:
        while True:
            block = f.read(FINGERPRINT_READ_BYTES)
            if not block:
                break
            digest.update(block)
            size += len(block)
            newlines += block.count(b"\n")
            last = block[-1]
    line_count = newlines + (1 if size and last != 10 else 0)
    return digest.hexdigest(), size, line_count


def _verify_legacy_copy(copy_path: Path, expected_sha256: str, expected_size: int) -> None:
    observed_sha256, observed_size, _ = _fingerprint(copy_path)
    if observed_size != expected_size or observed_sha256 != expected_sha256:
        raise RuntimeError(f"기존 원본 사본 검증 실패: {copy_path}")


def _hardlink_raw_copy(
    raw_dir: Path,
    source: Path,
    expected_sha256: str,
    expected_size: int,
) -> Path:
    target = raw_dir / "hardlinks_v1" / expected_sha256[:2] / f"{expected_sha256}_{source.name}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        os.link(source, target)
    source_stat = source.stat()
    target_stat = target.stat()
    if (
        source_stat.st_dev != target_stat.st_dev
        or source_stat.st_ino != target_stat.st_ino
        or target_stat.st_size != expected_size
    ):
        raise RuntimeError(f"원본 hardlink file identity 불일치: {target}")
    observed_sha256, observed_size, _ = _fingerprint(target)
    if observed_size != expected_size or observed_sha256 != expected_sha256:
        raise RuntimeError(f"원본 hardlink postread SHA/길이 불일치: {target}")
    return target


def _reuse_exact_hardlink_after_source_fingerprint(
    raw_dir: Path,
    source: Path,
    expected_sha256: str,
    expected_size: int,
) -> Path | None:
    """Reuse a prior same-file hardlink after the source itself was rehashed once.

    The older implementation reread every multi-GB transcript through the
    hardlink even though source and link share the same volume/file identity.
    Exact source SHA plus same inode/device and length is sufficient here;
    strict audit still rehashes the preserved path independently.
    """
    target = raw_dir / "hardlinks_v1" / expected_sha256[:2] / f"{expected_sha256}_{source.name}"
    if not target.is_file():
        return None
    source_stat = source.stat()
    target_stat = target.stat()
    if (
        source_stat.st_dev != target_stat.st_dev
        or source_stat.st_ino != target_stat.st_ino
        or target_stat.st_size != expected_size
    ):
        return None
    return target


def _gzip_snapshot_prefix(
    raw_dir: Path,
    source: Path,
    source_id: str,
    cutoff_size: int,
) -> tuple[Path, str, int, int, str]:
    """Create an independent, verified snapshot of a captured source prefix."""
    target = raw_dir / "gzip_snapshots_v4" / f"{source_id}_{cutoff_size}_{source.name}.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        source_digest = hashlib.sha256()
        source_size = 0
        source_newlines = 0
        source_last = None
        with source.open("rb") as current:
            remaining = cutoff_size
            while remaining:
                block = current.read(min(FINGERPRINT_READ_BYTES, remaining))
                if not block:
                    raise RuntimeError(f"source truncated before reusable snapshot cutoff: {source}")
                source_digest.update(block)
                source_size += len(block)
                source_newlines += block.count(b"\n")
                source_last = block[-1]
                remaining -= len(block)
        restored_digest = hashlib.sha256()
        restored_size = 0
        restored_newlines = 0
        restored_last = None
        with gzip.open(target, "rb") as restored:
            while True:
                block = restored.read(FINGERPRINT_READ_BYTES)
                if not block:
                    break
                restored_digest.update(block)
                restored_size += len(block)
                restored_newlines += block.count(b"\n")
                restored_last = block[-1]
        source_lines = source_newlines + (1 if source_size and source_last != 10 else 0)
        restored_lines = restored_newlines + (1 if restored_size and restored_last != 10 else 0)
        if (
            source_size != cutoff_size
            or restored_size != cutoff_size
            or source_digest.hexdigest() != restored_digest.hexdigest()
            or source_lines != restored_lines
        ):
            raise RuntimeError(f"existing create-once snapshot differs from current source prefix: {target}")
        return target, source_digest.hexdigest(), source_size, source_lines, sha256_file(target)
    digest = hashlib.sha256()
    newlines = 0
    last = None
    remaining = cutoff_size
    with source.open("rb") as src, target.open("xb") as raw_out:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_out, compresslevel=1, mtime=0) as out:
            while remaining:
                block = src.read(min(FINGERPRINT_READ_BYTES, remaining))
                if not block:
                    raise RuntimeError(f"source truncated before snapshot cutoff: {source}")
                out.write(block)
                digest.update(block)
                newlines += block.count(b"\n")
                last = block[-1]
                remaining -= len(block)
        raw_out.flush()
        os.fsync(raw_out.fileno())
    line_count = newlines + (1 if cutoff_size and last != 10 else 0)
    expected_sha = digest.hexdigest()
    verify = hashlib.sha256()
    verified_size = 0
    verified_newlines = 0
    verified_last = None
    with gzip.open(target, "rb") as copied:
        while True:
            block = copied.read(FINGERPRINT_READ_BYTES)
            if not block:
                break
            verify.update(block)
            verified_size += len(block)
            verified_newlines += block.count(b"\n")
            verified_last = block[-1]
    verified_lines = verified_newlines + (1 if verified_size and verified_last != 10 else 0)
    if verify.hexdigest() != expected_sha or verified_size != cutoff_size or verified_lines != line_count:
        raise RuntimeError(f"raw gzip snapshot postread mismatch: {source}")
    return target, expected_sha, cutoff_size, line_count, sha256_file(target)


def _store_chunk(raw_dir: Path, block: bytes, verified: set[str]) -> dict[str, Any]:
    digest = hashlib.sha256(block).hexdigest()
    target = raw_dir / "chunks_v2" / digest[:2] / f"{digest}.bin.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        if shutil.disk_usage(raw_dir).free < 30 * 1024 * 1024 * 1024:
            raise RuntimeError("원본 chunk 보관 중 여유 공간이 30 GiB 미만이 되어 인덱스 공간 보존을 위해 안전 중단")
        compressed = gzip.compress(block, compresslevel=1, mtime=0)
        try:
            with target.open("xb") as f:
                f.write(compressed)
                f.flush()
                os.fsync(f.fileno())
        except FileExistsError:
            pass
    if digest not in verified:
        try:
            restored = gzip.decompress(target.read_bytes())
        except Exception as exc:
            raise RuntimeError(f"원본 chunk 압축 검증 실패: {target}: {exc}") from exc
        if len(restored) != len(block) or hashlib.sha256(restored).hexdigest() != digest:
            raise RuntimeError(f"원본 chunk 복원 SHA 불일치: {target}")
        verified.add(digest)
    return {
        "sha256": digest,
        "size_bytes": len(block),
        "path": str(target.relative_to(raw_dir.parent.parent.parent)).replace("\\", "/"),
        "compressed_size_bytes": target.stat().st_size,
    }


def _fingerprint_and_store_chunks(
    source: Path,
    raw_dir: Path,
    verified: set[str],
) -> tuple[str, int, int, list[dict[str, Any]]]:
    digest = hashlib.sha256()
    size = 0
    line_count = 0
    chunks: list[dict[str, Any]] = []
    current = bytearray()

    def flush() -> None:
        if current:
            chunks.append(_store_chunk(raw_dir, bytes(current), verified))
            current.clear()

    with source.open("rb") as f:
        for line in f:
            digest.update(line)
            size += len(line)
            line_count += 1
            if current and len(current) + len(line) > RAW_CHUNK_MAX_BYTES:
                flush()
            if len(line) > RAW_CHUNK_MAX_BYTES:
                # A JSONL record is indivisible recovery evidence. Preserve a
                # very large record as one exact chunk rather than splitting it.
                chunks.append(_store_chunk(raw_dir, line, verified))
                continue
            current.extend(line)
            natural_boundary = hashlib.sha256(line).digest()[0] & RAW_CHUNK_BOUNDARY_MASK == 0
            if len(current) >= RAW_CHUNK_MAX_BYTES or (
                len(current) >= RAW_CHUNK_MIN_BYTES and natural_boundary
            ):
                flush()
    flush()
    return digest.hexdigest(), size, line_count, chunks


def discover_sources(
    project_root: Path,
    *,
    explicit_codex_home: str | None = None,
    extra_transcripts: Iterable[str] = (),
    copy_raw: bool = False,
    select_all: bool = False,
    scope_roots: Iterable[str] = (),
) -> dict[str, Any]:
    project_root = project_root.resolve()
    paths = Paths(project_root)
    ch = codex_home(explicit_codex_home)
    resolved_scope_roots = tuple(Path(value).expanduser().resolve() for value in scope_roots)
    candidates: list[tuple[str, Path]] = []

    for source_type, base in [
        ("codex_session", ch / "sessions"),
        ("codex_archived_session", ch / "archived_sessions"),
    ]:
        if base.exists():
            for p in base.rglob("*.jsonl"):
                if p.name not in EXCLUDE_NAMES and p.is_file():
                    candidates.append((source_type, p))

    history = ch / "history.jsonl"
    if history.exists():
        candidates.append(("codex_history", history))

    for raw in extra_transcripts:
        p = Path(raw).expanduser().resolve()
        if p.is_dir():
            for child in p.rglob("*"):
                if child.is_file() and child.suffix.lower() in TRANSCRIPT_SUFFIXES and child.name not in EXCLUDE_NAMES:
                    candidates.append(("user_supplied_transcript", child))
        elif p.is_file() and p.name not in EXCLUDE_NAMES:
            candidates.append(("user_supplied_transcript", p))

    seen: set[Path] = set()
    rows: list[dict[str, Any]] = []
    raw_dir = paths.recovery / "원본보관"
    verified_chunks: set[str] = set()
    # Pass 1 is metadata-only. Persist the complete accessible-source universe
    # before any selected source can hit the fail-closed disk guard.
    for idx, (source_type, p) in enumerate(sorted(candidates, key=lambda x: str(x[1]).lower()), 1):
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        try:
            stat = rp.stat()
        except OSError as exc:
            rows.append({
                "source_id": f"SRC-{idx:06d}",
                "source_type": source_type,
                "path": str(rp),
                "status": "unreadable",
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue
        meta = _session_meta_from_jsonl(rp) if rp.suffix.lower() == ".jsonl" else {}
        cwd = meta.get("cwd") or meta.get("working_directory") or meta.get("workdir")
        session_id = meta.get("id") or meta.get("session_id") or meta.get("thread_id")
        project_match = _project_path_match(project_root, cwd, resolved_scope_roots)
        selected = bool(select_all or project_match or source_type == "user_supplied_transcript")
        rows.append({
            "source_id": f"SRC-{idx:06d}",
            "source_type": source_type,
            "path": str(rp),
            "copied_path": None,
            "copied_storage_mode": None,
            "copied_original_verified": False,
            "copied_manifest_sha256": None,
            "copy_status": "pending" if selected else "not_selected",
            "sha256": None,
            "size_bytes": stat.st_size,
            "modified_at": stat.st_mtime,
            "line_count": None,
            "session_id": session_id,
            "session_meta": meta,
            "cwd": cwd,
            "project_path_match": project_match,
            "selected": selected,
            "status": "readable",
            "exclusion_reason": None if selected else "session cwd가 현재 프로젝트 계보와 일치하지 않아 본문 미선택",
        })
    write_jsonl(paths.source_index, rows)

    # Pass 2 reads, fingerprints, and preserves selected sources only.
    for row in rows:
        if row.get("status") != "readable" or not row.get("selected"):
            continue
        rp = Path(str(row["path"]))
        try:
            before = rp.stat()
            if copy_raw:
                recently_active = time.time() - before.st_mtime <= 6 * 3600
                if recently_active:
                    snapshot, digest, observed_size, line_count, copied_manifest_sha256 = _gzip_snapshot_prefix(
                        raw_dir, rp, str(row["source_id"]), int(before.st_size)
                    )
                    copied_path = safe_relpath(snapshot, project_root)
                    copied_storage_mode = "independent_gzip_prefix_snapshot_v4"
                    copied_original_verified = True
                else:
                    digest, observed_size, line_count = _fingerprint(rp)
                    stable_after_read = rp.stat()
                    if (
                        stable_after_read.st_size != before.st_size
                        or stable_after_read.st_mtime_ns != before.st_mtime_ns
                    ):
                        snapshot, digest, observed_size, line_count, copied_manifest_sha256 = _gzip_snapshot_prefix(
                            raw_dir, rp, str(row["source_id"]), int(before.st_size)
                        )
                        copied_path = safe_relpath(snapshot, project_root)
                        copied_storage_mode = "independent_gzip_prefix_snapshot_v4"
                    else:
                        hardlink = _reuse_exact_hardlink_after_source_fingerprint(
                            raw_dir, rp, digest, observed_size
                        ) or _hardlink_raw_copy(raw_dir, rp, digest, observed_size)
                        copied_path = safe_relpath(hardlink, project_root)
                        copied_storage_mode = "stable_source_ntfs_hardlink_v1"
                        copied_manifest_sha256 = digest
                    copied_original_verified = True
            else:
                digest, observed_size, line_count = _fingerprint(rp)
                copied_path = None
                copied_storage_mode = None
                copied_original_verified = False
                copied_manifest_sha256 = None
            after = rp.stat()
            if after.st_size < observed_size:
                raise RuntimeError(f"원본이 발견/보관 도중 변경됨: {rp}")
            row.update({
                "copied_path": copied_path,
                "copied_storage_mode": copied_storage_mode,
                "copied_original_verified": copied_original_verified,
                "copied_manifest_sha256": copied_manifest_sha256,
                "copy_status": "complete" if copy_raw else "not_requested",
                "sha256": digest,
                "line_count": line_count,
                "snapshot_cutoff_size": observed_size,
                "source_size_after_snapshot": after.st_size,
                "source_grew_during_snapshot": after.st_size > observed_size,
            })
        except Exception as exc:
            row["copy_status"] = "incomplete"
            row["copy_error"] = f"{type(exc).__name__}: {exc}"
            raise

    write_jsonl(paths.source_index, rows)
    report = {
        "generated_at": utc_now(),
        "project_root": str(project_root),
        "project_scope_roots": [str(root) for root in (project_root, *resolved_scope_roots)],
        "codex_home": str(ch),
        "source_count": len(rows),
        "readable_count": sum(r.get("status") == "readable" for r in rows),
        "project_path_match_count": sum(bool(r.get("project_path_match")) for r in rows),
        "copy_raw": copy_raw,
        "select_all": select_all,
        "selected_count": sum(bool(r.get("selected")) for r in rows),
        "selected_logical_bytes": sum(int(r.get("size_bytes") or 0) for r in rows if r.get("selected")),
        "selected_copied_count": sum(bool(r.get("copied_path")) for r in rows if r.get("selected")),
        "raw_storage_modes": {
            mode: sum(r.get("copied_storage_mode") == mode for r in rows)
            for mode in {r.get("copied_storage_mode") for r in rows if r.get("copied_storage_mode")}
        },
        "source_index": safe_relpath(paths.source_index, project_root),
        "warning": "이 목록은 접근 가능한 로컬 원본만 포함한다. 삭제되었거나 저장되지 않은 세션은 자동 복구할 수 없다.",
    }
    json_dump(paths.recovery / "원본목록" / "발견보고서.json", report)
    return report
