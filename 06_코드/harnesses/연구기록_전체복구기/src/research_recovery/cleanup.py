from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .utils import Paths, iter_jsonl, json_dump, json_load, sha256_file, utc_now


CLEANUP_SCHEMA = "YEOUIDO_RESEARCH_STORAGE_CLEANUP_DRY_RUN_V1"
INVENTORY_SCHEMA = "YEOUIDO_RESEARCH_ARTIFACT_INVENTORY_V1"
OUTPUT_REL = Path("08_검증") / "reports" / "저장공간정리"
INVENTORY_NAME = "전체_파일_자산목록.jsonl"
EXTERNAL_NAME = "대용량_외부원본.jsonl"
REPORT_NAME = "FINAL_CLEANUP_DRY_RUN.json"
BLOCKED_NAME = "CLEANUP_BLOCKED.json"

_ID_PATTERNS = {
    "run": re.compile(r"\bRUN-[A-Za-z0-9_.-]+"),
    "req": re.compile(r"\bREQ-[A-Za-z0-9_.-]+"),
    "fail": re.compile(r"\bFAIL-[A-Za-z0-9_.-]+"),
    "role": re.compile(r"\bR0[0-6]\b"),
}
_TEXT_SUFFIXES = {
    ".json", ".jsonl", ".md", ".txt", ".yaml", ".yml", ".toml", ".py",
    ".ps1", ".cmd", ".bat", ".csv", ".tsv", ".html", ".js", ".ts",
}
_TEMP_PARTS = {
    "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".cache",
    "cache", "caches", "tmp", "temp", "scratch", "build", "dist",
}
_PERMANENT_PREFIXES = (
    ".git/",
    "여의도/.agents/skills/연구기록_전체복구/",
    "여의도/01_목표/",
    "여의도/02_상태/",
    "여의도/03_방법/",
    "여의도/04_근거/복구증거/",
    "여의도/06_코드/harnesses/연구기록_전체복구기/",
    "여의도/08_검증/reports/연구기록복구/",
    "여의도/09_실패/",
    "여의도/10_결정/",
    "여의도/11_재현/",
    "여의도/12_협업/",
)


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _artifact_id(relative_path: str) -> str:
    digest = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:20].upper()
    return f"ART-{digest}"


def _walk_files(root: Path, output_root: Path) -> Iterable[Path]:
    output_root = output_root.resolve()
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        kept_dirs: list[str] = []
        for name in dirs:
            candidate = current_path / name
            try:
                if candidate.is_symlink():
                    continue
                kept_dirs.append(name)
            except OSError:
                continue
        dirs[:] = sorted(kept_dirs, key=str.casefold)
        for name in sorted(files, key=str.casefold):
            candidate = current_path / name
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            try:
                resolved.relative_to(output_root)
                continue
            except ValueError:
                pass
            if candidate.is_symlink() or not candidate.is_file():
                continue
            yield candidate


def _load_certified_hashes(project_root: Path, scope_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    paths = Paths(project_root)
    if paths.source_index.exists():
        for _, _, row, err in iter_jsonl(paths.source_index):
            if err or not row or not row.get("selected"):
                continue
            copied = row.get("copied_path")
            sha = row.get("sha256")
            if isinstance(copied, str) and isinstance(sha, str):
                absolute = (project_root / copied).resolve()
                if absolute.is_file():
                    result[_rel(absolute, scope_root)] = sha
    if paths.project_files.exists():
        for _, _, row, err in iter_jsonl(paths.project_files):
            if err or not row or row.get("status") != "readable":
                continue
            rel = row.get("path")
            sha = row.get("sha256")
            if isinstance(rel, str) and isinstance(sha, str):
                absolute = (project_root / rel).resolve()
                if absolute.is_file():
                    result[_rel(absolute, scope_root)] = sha
    return result


def _recursive_find(obj: Any, key: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(obj, dict):
        for item_key, value in obj.items():
            if item_key == key:
                found.append(value)
            found.extend(_recursive_find(value, key))
    elif isinstance(obj, list):
        for value in obj:
            found.extend(_recursive_find(value, key))
    return found


def cleanup_preflight(project_root: Path, scope_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    scope_root = scope_root.resolve()
    required_json = {
        "project": project_root / "project.yaml",
        "state": project_root / "02_상태" / "state.json",
        "queue": project_root / "02_상태" / "queue.json",
        "blockers": project_root / "02_상태" / "blockers.json",
        "strict_audit": project_root / "08_검증" / "reports" / "연구기록복구" / "연구기록_복구감사.json",
        "role_audit": project_root / "04_근거" / "복구증거" / "감사결과" / "역할복구_감사.json",
    }
    parsed: dict[str, Any] = {}
    checks: dict[str, bool] = {}
    blockers: list[dict[str, str]] = []
    for name, path in required_json.items():
        try:
            parsed[name] = json_load(path)
            checks[f"{name}_readable"] = isinstance(parsed[name], dict)
        except Exception:
            parsed[name] = None
            checks[f"{name}_readable"] = False
        if not checks[f"{name}_readable"]:
            blockers.append({"id": f"CLEANUP-PRE-{name.upper()}-MISSING", "reason": f"Required central artifact is missing or invalid: {path}"})

    strict = parsed.get("strict_audit") or {}
    checks["strict_recovery_pass"] = strict.get("status") == "PASS" and strict.get("strict") is True and not strict.get("errors")
    if not checks["strict_recovery_pass"]:
        blockers.append({"id": "CLEANUP-PRE-STRICT-NOT-PASS", "reason": "Full recovery strict audit is not exact PASS."})

    role = parsed.get("role_audit") or {}
    role_root = project_root / "12_협업" / "역할별_연구"
    role_dirs = [p for p in role_root.iterdir() if p.is_dir()] if role_root.is_dir() else []
    checks["role_capsules_complete"] = role.get("status") == "PASS" and len(role_dirs) == 7 and all(len(list(p.glob("*"))) >= 11 for p in role_dirs)
    if not checks["role_capsules_complete"]:
        blockers.append({"id": "CLEANUP-PRE-ROLE-CAPSULES", "reason": "Seven audited role capsules with required records are not complete."})

    project = parsed.get("project") or {}
    requirements = project.get("requirements") if isinstance(project, dict) else []
    unverified = [r for r in requirements or [] if isinstance(r, dict) and r.get("status") != "verified"]
    checks["important_requirements_verified"] = bool(requirements) and not unverified
    if not checks["important_requirements_verified"]:
        blockers.append({"id": "CLEANUP-PRE-REQUIREMENTS-UNVERIFIED", "reason": f"Central project has {len(unverified)} requirements not verified; recovered links alone do not prove acceptance."})

    canonical_values: list[Any] = []
    for obj in parsed.values():
        canonical_values.extend(_recursive_find(obj, "canonical_run_id"))
        canonical_values.extend(_recursive_find(obj, "canonical_run"))
    canonical_ids = sorted({str(x) for x in canonical_values if isinstance(x, str) and x.startswith("RUN-")})
    run_dirs = sorted((project_root / "07_실행").glob("RUN-*")) if (project_root / "07_실행").is_dir() else []
    checks["canonical_run_selected_or_reasoned"] = bool(canonical_ids)
    if not checks["canonical_run_selected_or_reasoned"]:
        blockers.append({"id": "CLEANUP-PRE-CANONICAL-RUN-UNSELECTED", "reason": f"No scientific canonical_run_id is registered; {len(run_dirs)} RUN directory/directories exist but are not a cleanup authority."})

    method_path = project_root / "03_방법" / "연구방법.md"
    checks["method_current_code_contract_alignment_proven"] = False
    if not method_path.is_file():
        blockers.append({"id": "CLEANUP-PRE-METHOD-MISSING", "reason": "Current METHOD document is missing."})
    else:
        blockers.append({"id": "CLEANUP-PRE-METHOD-ALIGNMENT-UNPROVEN", "reason": "Recovery audit accounts for METHOD text but does not independently prove it matches every active code/contract hash."})

    failure_path = project_root / "09_실패" / "failures.jsonl"
    failure_rows = 0
    formal_failure_rows = 0
    if failure_path.is_file():
        for _, _, row, err in iter_jsonl(failure_path):
            if row and not err:
                failure_rows += 1
                if row.get("failure_id") and (row.get("run_id") or row.get("related_run_ids")):
                    formal_failure_rows += 1
    checks["major_failures_formally_linked"] = failure_rows > 0 and formal_failure_rows == failure_rows
    if not checks["major_failures_formally_linked"]:
        blockers.append({"id": "CLEANUP-PRE-FAILURE-LINKAGE-INCOMPLETE", "reason": f"Failure registry rows with complete FAIL-ID/RUN-ID linkage: {formal_failure_rows}/{failure_rows}."})

    checks["final_results_artifact_linked"] = bool(canonical_ids)
    if not checks["final_results_artifact_linked"]:
        blockers.append({"id": "CLEANUP-PRE-FINAL-RESULT-LINKAGE", "reason": "Without a canonical scientific RUN, final-result-to-artifact deletion safety cannot be proven."})

    checks["unrecovered_scope_documented"] = bool(strict.get("limitations"))
    parent_git = (scope_root / ".git").is_dir()
    strict_git_unavailable = any("Git metadata unavailable" in str(w) for w in strict.get("warnings", []))
    checks["git_scope_consistent"] = not (parent_git and strict_git_unavailable)
    if not checks["git_scope_consistent"]:
        blockers.append({"id": "CLEANUP-PRE-GIT-SCOPE-MISMATCH", "reason": "The cleanup scope root contains .git, but recovery strict audit says Git metadata was unavailable because only the child root was probed."})

    return {
        "schema": "YEOUIDO_RESEARCH_STORAGE_CLEANUP_PREFLIGHT_V1",
        "generated_at": utc_now(),
        "status": "PASS" if not blockers else "CLEANUP_BLOCKED",
        "project_root": str(project_root),
        "scope_root": str(scope_root),
        "checks": checks,
        "blockers": blockers,
        "canonical_run_ids": canonical_ids,
        "run_directory_count": len(run_dirs),
        "unverified_requirement_count": len(unverified),
        "failure_registry_rows": failure_rows,
        "formally_linked_failure_rows": formal_failure_rows,
        "actual_deletion_authorized": False,
    }


def _read_small_text(path: Path, limit: int = 4_000_000) -> str:
    try:
        if path.suffix.lower() not in _TEXT_SUFFIXES or path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def _retention(relative: str, path: Path, referenced: bool) -> tuple[str, str, bool, str | None]:
    low = relative.lower()
    parts = {part.lower() for part in Path(relative).parts}
    if any(part in _TEMP_PARTS for part in parts) or path.suffix.lower() in {".pyc", ".pyo", ".tmp", ".temp"}:
        return "TEMP", "cache/build/temp artifact; safe only after reference and path checks", not referenced, "Regenerated by the producing tool or interpreter."
    if any(relative.startswith(prefix) for prefix in _PERMANENT_PREFIXES):
        return "PERMANENT", "central recovery, source, method, failure, validation, role, or Git authority", False, None
    if any(token in low for token in ("/runs/", "/outputs/", "failure", "audit", "probe", "diagnostic", "checkpoint", "ledger")):
        return "EVIDENCE", "run/failure/probe/audit evidence; metadata must remain even if a body is later approved for removal", False, None
    if any(token in low for token in ("intermediate", "generated", "rendered", "chunk", "shard")):
        return "REPRODUCIBLE", "name indicates generated intermediate; regeneration command is not yet proven", False, None
    return "PERMANENT", "conservative hold: retention/reproducibility is not proven", False, None


def _reference_names(project_root: Path) -> set[str]:
    result: set[str] = set()
    authority = [
        project_root / "project.yaml",
        project_root / "02_상태" / "state.json",
        project_root / "02_상태" / "queue.json",
        project_root / "02_상태" / "blockers.json",
        project_root / "12_협업" / "역할간_인계기록.jsonl",
        project_root / "04_근거" / "claims.jsonl",
        project_root / "09_실패" / "failures.jsonl",
    ]
    quoted = re.compile(r"[\"'`]([^\"'`\r\n]{1,1000}\.[A-Za-z0-9]{1,12})[\"'`]")
    for path in authority:
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
                for line in handle:
                    for match in quoted.finditer(line):
                        result.add(Path(match.group(1).replace("\\", "/")).name.casefold())
        except OSError:
            continue
    return result


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    count = 0
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    os.replace(temp, path)
    return count


def build_cleanup_dry_run(project_root: Path, scope_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    scope_root = scope_root.resolve()
    try:
        project_root.relative_to(scope_root)
    except ValueError as exc:
        raise RuntimeError("project root must be within cleanup scope root") from exc
    output_root = project_root / OUTPUT_REL
    preflight = cleanup_preflight(project_root, scope_root)
    certified = _load_certified_hashes(project_root, scope_root)
    reference_names = _reference_names(project_root)
    rows: list[dict[str, Any]] = []
    inode_sha: dict[tuple[int, int, int], str] = {}
    unreadable = 0
    for path in _walk_files(scope_root, output_root):
        relative = _rel(path.resolve(), scope_root)
        try:
            stat = path.stat()
            inode_key = (int(stat.st_dev), int(stat.st_ino), int(stat.st_size))
            sha = certified.get(relative)
            hash_source = "strict_or_project_inventory"
            if not sha:
                sha = inode_sha.get(inode_key)
                hash_source = "same_physical_file_identity" if sha else "live_sha256"
            if not sha:
                sha = sha256_file(path)
            inode_sha[inode_key] = sha
        except OSError as exc:
            unreadable += 1
            rows.append({"schema": INVENTORY_SCHEMA, "artifact_id": _artifact_id(relative), "absolute_path": str(path.resolve()), "relative_path": relative, "file_name": path.name, "status": "unreadable", "error": f"{type(exc).__name__}: {exc}", "retention_class": "PERMANENT", "deletion_candidate": False, "deletion_prohibited_reason": "unreadable artifact"})
            continue
        referenced = path.name.casefold() in reference_names
        retention, reason, tentative, regen = _retention(relative, path, referenced)
        text = _read_small_text(path)
        producer_runs = sorted(set(_ID_PATTERNS["run"].findall(relative + "\n" + text)))
        req_ids = sorted(set(_ID_PATTERNS["req"].findall(text)))
        fail_ids = sorted(set(_ID_PATTERNS["fail"].findall(relative + "\n" + text)))
        role_ids = sorted(set(_ID_PATTERNS["role"].findall(relative + "\n" + text)))
        rows.append({
            "schema": INVENTORY_SCHEMA, "artifact_id": _artifact_id(relative),
            "absolute_path": str(path.resolve()), "relative_path": relative, "file_name": path.name,
            "size_bytes": int(stat.st_size), "sha256": sha, "sha256_evidence_source": hash_source,
            "created_at_epoch": float(stat.st_ctime), "modified_at_epoch": float(stat.st_mtime),
            "physical_identity": {"device": int(stat.st_dev), "inode": int(stat.st_ino)},
            "producer_run_ids": producer_runs, "role_ids": role_ids, "related_req_ids": req_ids,
            "related_fail_ids": fail_ids, "related_validation": relative if "audit" in relative.lower() or "검증" in relative else None,
            "canonical_result_referenced": False, "referenced_by_other_artifact": referenced,
            "regenerable": regen is not None, "regeneration_command": regen,
            "retention_class": retention, "retention_reason": reason,
            "deletion_candidate": bool(tentative), "deletion_authorized": False,
            "deletion_basis": reason if tentative else None,
            "deletion_prohibited_reason": None if tentative else reason, "status": "readable",
        })

    by_sha: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("status") == "readable" and row.get("size_bytes", 0) > 0:
            by_sha[str(row["sha256"])].append(row)
    duplicate_groups = 0
    logical_duplicate_bytes = 0
    physical_duplicate_reclaimable = 0
    for sha, group in by_sha.items():
        if len(group) < 2:
            continue
        duplicate_groups += 1
        group.sort(key=lambda row: (not bool(row.get("canonical_result_referenced")), row.get("retention_class") != "PERMANENT", not str(row.get("relative_path", "")).startswith("여의도/"), len(str(row.get("relative_path", ""))), str(row.get("relative_path", ""))))
        keeper = group[0]
        group_id = f"DUP-{sha[:16].upper()}"
        keeper_inode = tuple(keeper["physical_identity"].values())
        for index, row in enumerate(group):
            row["duplicate_group_id"] = group_id
            row["duplicate_keeper_artifact_id"] = keeper["artifact_id"]
            row["duplicate_is_keeper"] = index == 0
            if index:
                logical_duplicate_bytes += int(row["size_bytes"])
                inode = tuple(row["physical_identity"].values())
                row["duplicate_is_hardlink_same_physical_file"] = inode == keeper_inode
                row["duplicate_physical_reclaimable_bytes"] = 0 if inode == keeper_inode else int(row["size_bytes"])
                physical_duplicate_reclaimable += int(row["duplicate_physical_reclaimable_bytes"])
                if row["retention_class"] != "PERMANENT" and not row["referenced_by_other_artifact"]:
                    row["deletion_candidate"] = True
                    row["deletion_basis"] = "non-authoritative exact-SHA duplicate; approval and recheck still required"

    inode_sizes: dict[tuple[int, int], int] = {}
    class_bytes: Counter[str] = Counter()
    class_counts: Counter[str] = Counter()
    candidate_inodes: dict[tuple[int, int], int] = {}
    candidates: list[dict[str, Any]] = []
    protected: list[dict[str, Any]] = []
    indeterminate: list[dict[str, Any]] = []
    logical_total = 0
    for row in rows:
        if row.get("status") != "readable":
            continue
        size = int(row["size_bytes"])
        logical_total += size
        identity = (int(row["physical_identity"]["device"]), int(row["physical_identity"]["inode"]))
        inode_sizes.setdefault(identity, size)
        klass = str(row["retention_class"])
        class_bytes[klass] += size
        class_counts[klass] += 1
        brief = {"artifact_id": row["artifact_id"], "relative_path": row["relative_path"], "size_bytes": size, "retention_class": klass, "reason": row.get("deletion_basis") or row.get("deletion_prohibited_reason")}
        if row.get("deletion_candidate"):
            candidates.append(brief)
            candidate_inodes.setdefault(identity, size)
        else:
            protected.append(brief)
        if klass == "PERMANENT" and str(row.get("retention_reason", "")).startswith("conservative hold"):
            indeterminate.append(brief)

    _write_jsonl(output_root / INVENTORY_NAME, rows)
    source_paths = Paths(project_root)
    external_rows: list[dict[str, Any]] = []
    if source_paths.source_index.exists():
        for _, _, row, err in iter_jsonl(source_paths.source_index):
            if err or not row or not row.get("selected"):
                continue
            original = Path(str(row.get("path") or row.get("absolute_path") or ""))
            external_rows.append({"schema": "YEOUIDO_EXTERNAL_REFERENCE_V1", "artifact_id": f"EXT-{str(row.get('source_id') or '')}", "source_id": row.get("source_id"), "absolute_path": str(original), "size_bytes": row.get("size_bytes"), "sha256": row.get("sha256"), "version_or_date": row.get("mtime") or row.get("modified_at"), "accessible": original.is_file(), "ownership_or_storage": "local Codex session store; project recovery holds an immutable selected snapshot/reference", "reacquirable": False, "retention_class": "PERMANENT"})
    _write_jsonl(output_root / EXTERNAL_NAME, external_rows)

    disk = shutil.disk_usage(scope_root)
    physical_total = sum(inode_sizes.values())
    tentative_reclaim = sum(candidate_inodes.values())
    report = {
        "schema": CLEANUP_SCHEMA, "generated_at": utc_now(),
        "status": "CLEANUP_BLOCKED" if preflight["blockers"] else "FINAL_CLEANUP_DRY_RUN_READY_FOR_USER_REVIEW",
        "mode": "DRY_RUN_ONLY", "project_root": str(project_root), "scope_root": str(scope_root),
        "preflight": preflight,
        "inventory": {"path": str((output_root / INVENTORY_NAME).relative_to(project_root)).replace("\\", "/"), "file_count": len(rows), "unreadable_count": unreadable, "logical_total_bytes": logical_total, "estimated_unique_physical_file_bytes": physical_total, "retention_counts": dict(class_counts), "retention_bytes": dict(class_bytes)},
        "external_references": {"path": str((output_root / EXTERNAL_NAME).relative_to(project_root)).replace("\\", "/"), "count": len(external_rows)},
        "duplicates": {"sha256_group_count": duplicate_groups, "logical_duplicate_bytes": logical_duplicate_bytes, "estimated_physical_reclaimable_bytes": physical_duplicate_reclaimable, "hardlink_note": "Same-device/inode links consume one physical file; removing a nonfinal link normally reclaims zero bytes until the last link is removed."},
        "tentative_deletion": {"file_count": len(candidates), "estimated_reclaimable_bytes": tentative_reclaim, "expected_physical_usage_after_bytes": max(0, physical_total - tentative_reclaim), "expected_free_space_after_bytes": disk.free + tentative_reclaim, "actual_deletion_performed": False, "actual_deletion_authorized": False},
        "disk": {"capacity_bytes": disk.total, "free_bytes": disk.free, "used_bytes": disk.used},
        "top_50_deletion_candidates": sorted(candidates, key=lambda x: x["size_bytes"], reverse=True)[:50],
        "top_50_protected_large_files": sorted(protected, key=lambda x: x["size_bytes"], reverse=True)[:50],
        "canonical_reproduction_required_files": [],
        "canonical_reproduction_status": "BLOCKED_NO_CANONICAL_SCIENTIFIC_RUN" if not preflight["canonical_run_ids"] else "REGISTERED",
        "dangerous_deletion_candidates": [x for x in candidates if x["size_bytes"] >= 1_000_000_000],
        "indeterminate_artifact_count": len(indeterminate),
        "top_50_indeterminate_artifacts": sorted(indeterminate, key=lambda x: x["size_bytes"], reverse=True)[:50],
        "approval_required": "User must explicitly say 최종 정리 실행 or equivalent after blockers are cleared and the dry-run is reviewed.",
        "tombstone_path_reserved": str((output_root / "tombstones.jsonl").relative_to(project_root)).replace("\\", "/"),
        "deletion_code_present": False,
    }
    json_dump(output_root / REPORT_NAME, report)
    if preflight["blockers"]:
        json_dump(output_root / BLOCKED_NAME, {"schema": "YEOUIDO_RESEARCH_STORAGE_CLEANUP_BLOCKED_V1", "generated_at": report["generated_at"], "status": "CLEANUP_BLOCKED", "blockers": preflight["blockers"], "dry_run_report": str((output_root / REPORT_NAME).relative_to(project_root)).replace("\\", "/"), "deleted_file_count": 0, "deleted_bytes": 0})
    return report


def audit_cleanup_dry_run(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    output_root = project_root / OUTPUT_REL
    report_path = output_root / REPORT_NAME
    inventory_path = output_root / INVENTORY_NAME
    report = json_load(report_path)
    required = {
        "schema", "artifact_id", "absolute_path", "relative_path", "file_name",
        "retention_class", "deletion_candidate", "deletion_authorized", "status",
    }
    row_count = 0
    invalid_rows: list[dict[str, Any]] = []
    missing_live_paths: list[str] = []
    authorized_rows: list[str] = []
    for line_no, _, row, error in iter_jsonl(inventory_path):
        row_count += 1
        if error or not row or not required.issubset(row):
            invalid_rows.append({"line": line_no, "error": error or "required fields missing"})
            continue
        if row.get("deletion_authorized") is not False:
            authorized_rows.append(str(row.get("relative_path")))
        absolute = Path(str(row.get("absolute_path")))
        if row.get("status") == "readable" and not absolute.is_file():
            missing_live_paths.append(str(absolute))
    checks = {
        "report_is_dry_run": report.get("mode") == "DRY_RUN_ONLY",
        "deletion_code_absent": report.get("deletion_code_present") is False,
        "actual_deletion_false": report.get("tentative_deletion", {}).get("actual_deletion_performed") is False,
        "authorization_false": report.get("tentative_deletion", {}).get("actual_deletion_authorized") is False and not authorized_rows,
        "inventory_count_exact": row_count == report.get("inventory", {}).get("file_count"),
        "inventory_rows_valid": not invalid_rows,
        "inventoried_files_still_present": not missing_live_paths,
        "blocked_receipt_present_when_required": report.get("status") != "CLEANUP_BLOCKED" or (output_root / BLOCKED_NAME).is_file(),
        "tombstones_absent_before_approval": not (output_root / "tombstones.jsonl").exists(),
    }
    result = {
        "schema": "YEOUIDO_RESEARCH_STORAGE_CLEANUP_DRY_RUN_AUDIT_V1",
        "generated_at": utc_now(),
        "status": "PASS_DRY_RUN_NON_DESTRUCTIVE" if all(checks.values()) else "FAIL",
        "checks": checks,
        "inventory_row_count": row_count,
        "invalid_rows": invalid_rows[:100],
        "missing_live_paths": missing_live_paths[:100],
        "authorized_rows": authorized_rows[:100],
        "cleanup_status": report.get("status"),
        "actual_deletion_performed": False,
    }
    json_dump(output_root / "FINAL_CLEANUP_DRY_RUN_AUDIT.json", result)
    return result
