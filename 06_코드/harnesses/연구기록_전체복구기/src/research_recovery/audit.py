from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator

from .utils import Paths, iter_jsonl, json_dump, safe_relpath, utc_now
from .roles import audit_role_recovery


CLASSIFIABLE_KINDS = {
    "message",
    "tool_call",
    "tool_output",
    "file_change",
    "plan_update",
    "error_event",
    "compaction",
}


def _objects(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    for line_no, _, obj, err in iter_jsonl(path):
        if err or not isinstance(obj, dict):
            raise RuntimeError(f"invalid JSONL row: {path}:{line_no}: {err or 'not an object'}")
        yield obj


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"JSON report is not an object: {path}")
    return data


def _numeric_id(value: Any, prefix: str) -> int | None:
    text = str(value or "")
    if not text.startswith(prefix):
        return None
    try:
        return int(text[len(prefix) :])
    except ValueError:
        return None


def _sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(8 * 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            digest.update(chunk)
    return total, digest.hexdigest()


def _sha256_gzip_content(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    with gzip.open(path, "rb") as handle:
        while True:
            chunk = handle.read(8 * 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            digest.update(chunk)
    return total, digest.hexdigest()


def _verify_preserved_source(
    project_root: Path, source: dict[str, Any]
) -> tuple[bool, str | None]:
    rel = source.get("copied_path")
    if not isinstance(rel, str) or not rel:
        return False, "selected source has no copied_path"
    candidate = (project_root / rel).resolve()
    try:
        candidate.relative_to(project_root)
    except ValueError:
        return False, f"preserved source escapes project root: {rel}"
    if not candidate.is_file():
        return False, f"preserved source missing or not a file: {rel}"
    expected_size = source.get("size_bytes")
    expected_sha = source.get("sha256")
    mode = source.get("copied_storage_mode")
    if isinstance(mode, str) and mode.startswith(
        "independent_gzip_prefix_snapshot_v"
    ):
        # A live source may grow between discovery stat and the immutable prefix
        # copy. The snapshot's explicit cutoff size, not the earlier stat, is the
        # authority for its uncompressed byte count.
        expected_size = source.get("snapshot_cutoff_size")
        compressed_size, compressed_sha = _sha256_file(candidate)
        if source.get("copied_manifest_sha256") != compressed_sha:
            return False, f"compressed preserved SHA mismatch: {rel}"
        if compressed_size <= 0:
            return False, f"empty compressed preserved source: {rel}"
        observed_size, observed_sha = _sha256_gzip_content(candidate)
    else:
        observed_size, observed_sha = _sha256_file(candidate)
    if observed_size != expected_size or observed_sha != expected_sha:
        return False, (
            f"preserved source content mismatch: {rel}: "
            f"{observed_size}/{observed_sha} != {expected_size}/{expected_sha}"
        )
    return True, None


def audit_recovery(project_root: Path, *, strict: bool = False) -> dict[str, Any]:
    """Audit the recovery with bounded memory and exact streaming joins.

    The previous implementation materialized multi-gigabyte JSONL files and several
    duplicate ID sets. This implementation keeps only per-source counters and the
    current timeline/classification/coverage rows.
    """

    project_root = project_root.resolve()
    paths = Paths(project_root)
    errors: list[str] = []
    warnings: list[str] = []

    source_count = 0
    selected_source_count = 0
    unselected_project_matches = 0
    selected_source_ids: set[str] = set()
    selected_expected_lines: dict[str, int] = {}
    preserved_verified = 0
    storage_modes: Counter[str] = Counter()
    for source in _objects(paths.source_index):
        source_count += 1
        if source.get("status") != "readable":
            continue
        if source.get("project_path_match") and not source.get("selected"):
            unselected_project_matches += 1
        if not source.get("selected"):
            continue
        selected_source_count += 1
        source_id = str(source.get("source_id"))
        selected_source_ids.add(source_id)
        selected_expected_lines[source_id] = int(source.get("line_count") or 0)
        storage_modes[str(source.get("copied_storage_mode") or "unknown")] += 1
        if strict and (
            source.get("copy_status") not in {"complete", "copied"}
            or not source.get("copied_original_verified")
        ):
            errors.append(f"selected source was not verified during discovery: {source_id}")
            continue
        if strict:
            ok, detail = _verify_preserved_source(project_root, source)
            if not ok:
                errors.append(detail or f"preserved source verification failed: {source_id}")
            else:
                preserved_verified += 1

    if source_count == 0:
        errors.append("no transcript sources were discovered")
    if selected_source_count == 0:
        errors.append("no readable project transcript sources were selected")
    if unselected_project_matches:
        errors.append(
            f"프로젝트 경로가 일치하지만 선택되지 않은 세션: {unselected_project_matches}"
        )

    raw_count = 0
    parse_failures = 0
    raw_status: Counter[str] = Counter()
    raw_by_source: defaultdict[str, int] = defaultdict(int)
    for raw in _objects(paths.raw_line_index):
        raw_count += 1
        rec_no = _numeric_id(raw.get("source_record_id"), "REC-")
        if rec_no != raw_count:
            errors.append(
                f"REC sequence mismatch at row {raw_count}: {raw.get('source_record_id')}"
            )
            break
        status = str(raw.get("status") or "unknown")
        raw_status[status] += 1
        if status == "parse_failed":
            parse_failures += 1
        raw_by_source[str(raw.get("source_id"))] += 1
    if parse_failures:
        errors.append(f"JSONL parse failures: {parse_failures}")
    missing_source_extraction = sorted(selected_source_ids - set(raw_by_source))
    if missing_source_extraction:
        errors.append(f"selected sources without REC rows: {missing_source_extraction[:20]}")
    for source_id, expected in selected_expected_lines.items():
        observed = raw_by_source.get(source_id, 0)
        if observed != expected:
            errors.append(f"source line accounting mismatch: {source_id}: {observed} != {expected}")
            if len(errors) > 100:
                break

    classification_iter = iter(_objects(paths.classification))
    coverage_iter = iter(_objects(paths.coverage_map))
    timeline_count = 0
    classifiable_count = 0
    classified_count = 0
    mapped_count = 0
    user_message_count = 0
    assistant_message_count = 0
    tool_call_count = 0
    tool_output_count = 0
    silent_exclusions = 0
    human_review_required = 0
    for event in _objects(paths.timeline):
        timeline_count += 1
        event_no = _numeric_id(event.get("event_id"), "EVT-")
        if event_no != timeline_count:
            errors.append(f"EVT sequence mismatch at row {timeline_count}: {event.get('event_id')}")
            break
        kind = event.get("kind")
        actor = event.get("actor")
        if kind == "message" and actor == "user":
            user_message_count += 1
        elif kind == "message" and actor == "assistant":
            assistant_message_count += 1
        elif kind == "tool_call":
            tool_call_count += 1
        elif kind == "tool_output":
            tool_output_count += 1
        if kind not in CLASSIFIABLE_KINDS:
            continue
        classifiable_count += 1
        try:
            classification = next(classification_iter)
        except StopIteration:
            if kind == "message" and actor == "user":
                errors.append(f"사용자 메시지 분류 누락: {event.get('event_id')}")
            else:
                errors.append(f"classification ended before EVT {event.get('event_id')}")
            break
        classified_count += 1
        try:
            mapping = next(coverage_iter)
        except StopIteration:
            errors.append(f"coverage map ended before EVT {event.get('event_id')}")
            break
        mapped_count += 1
        event_id = event.get("event_id")
        if classification.get("event_id") != event_id:
            errors.append(
                f"classification join mismatch: {event_id} != {classification.get('event_id')}"
            )
            break
        if mapping.get("event_id") != event_id:
            errors.append(f"coverage join mismatch: {event_id} != {mapping.get('event_id')}")
            break
        if classification.get("requires_human_review"):
            human_review_required += 1
        relevance = classification.get("research_relevance")
        if relevance in {"non_research", "duplicate"} and not classification.get("exclusion_reason"):
            silent_exclusions += 1
        targets = mapping.get("document_targets")
        if not isinstance(targets, list) or not targets:
            errors.append(f"coverage target missing: {event_id}")
            break
        if mapping.get("status") == "excluded_with_reason" and not mapping.get("exclusion_reason"):
            silent_exclusions += 1

    try:
        extra_class = next(classification_iter)
    except StopIteration:
        extra_class = None
    try:
        extra_map = next(coverage_iter)
    except StopIteration:
        extra_map = None
    if extra_class is not None:
        errors.append(f"classification has extra row: {extra_class.get('event_id')}")
    if extra_map is not None:
        errors.append(f"coverage map has extra row: {extra_map.get('event_id')}")
    if silent_exclusions:
        errors.append(f"items excluded without explicit reason: {silent_exclusions}")
    if human_review_required:
        errors.append(f"classifications still marked for human review: {human_review_required}")

    duplicate_map = paths.timeline.parent / "duplicate_occurrence_map.jsonl"
    duplicate_count = 0
    for duplicate in _objects(duplicate_map):
        duplicate_count += 1
        canonical_no = _numeric_id(duplicate.get("canonical_event_id"), "EVT-")
        if canonical_no is None or canonical_no < 1 or canonical_no > timeline_count:
            errors.append(
                f"duplicate occurrence points outside canonical EVT range: row {duplicate_count}"
            )
            break
    if raw_count != timeline_count + duplicate_count:
        errors.append(
            "raw/canonical/duplicate accounting mismatch: "
            f"{raw_count} != {timeline_count} + {duplicate_count}"
        )

    unresolved_conflicts = 0
    conflict_count = 0
    for conflict in _objects(paths.conflict_report):
        conflict_count += 1
        if conflict.get("status") == "unresolved":
            unresolved_conflicts += 1
    if unresolved_conflicts:
        errors.append(f"unresolved conflicts: {unresolved_conflicts}")

    review_path = paths.recovery / "감사결과" / "독립분류감사_보고서.json"
    review_report = _load_json(review_path)
    if review_report:
        review_ok = (
            review_report.get("reviewed") == classifiable_count
            and review_report.get("structural_findings") == 0
            and review_report.get("user_messages_reviewed") == user_message_count
            and review_report.get("tool_outputs_reviewed") == tool_output_count
        )
        if not review_ok:
            errors.append("independent classification review does not cover the final classified corpus")

    extraction_stats = _load_json(paths.timeline.parent / "extraction_stats.json")
    expected_stats = {
        "source_count": source_count,
        "selected_source_count": selected_source_count,
        "raw_record_count": raw_count,
        "timeline_event_count": timeline_count,
        "duplicate_occurrence_count": duplicate_count,
        "user_message_count": user_message_count,
        "assistant_message_count": assistant_message_count,
        "tool_call_count": tool_call_count,
        "tool_output_count": tool_output_count,
        "parse_failure_count": parse_failures,
    }
    for key, observed in expected_stats.items():
        if extraction_stats.get(key) != observed:
            errors.append(f"extraction stats mismatch: {key}: {extraction_stats.get(key)} != {observed}")

    project_scan = _load_json(paths.project_files.parent / "프로젝트스캔_보고서.json")
    project_file_count = sum(1 for _ in _objects(paths.project_files))
    if project_scan and project_scan.get("file_count") != project_file_count:
        errors.append(
            f"project file inventory mismatch: {project_scan.get('file_count')} != {project_file_count}"
        )
    if project_scan and not project_scan.get("git", {}).get("available"):
        warnings.append(
            "Git metadata unavailable: the accessible project root is not a valid Git repository; "
            "commit/reflog/stash history remains unrecovered."
        )

    required_documents = [
        project_root / "03_방법" / "연구기록" / "연구전체연혁.md",
        project_root / "01_목표" / "요구사항_전체이력.md",
        project_root / "03_방법" / "연구기록" / "연구방법_변경이력.md",
        project_root / "07_실행" / "실행이력.md",
        project_root / "09_실패" / "실패요약.md",
        project_root / "10_결정" / "결정이력.md",
        project_root / "12_협업" / "협업이력.md",
        project_root / "05_데이터" / "복구된_자료목록.md",
        project_root / "06_코드" / "복구된_코드목록.md",
        project_root / "12_협업" / "복구세션_목록.md",
        project_root / "04_근거" / "claims.jsonl",
        project_root / "09_실패" / "failures.jsonl",
        project_root / "09_실패" / "rejected_results.jsonl",
    ]
    missing_documents = [
        safe_relpath(path, project_root)
        for path in required_documents
        if not path.is_file() or (path.suffix.lower() != ".jsonl" and path.stat().st_size == 0)
    ]
    if missing_documents:
        errors.append(f"required rendered documents missing/empty: {missing_documents}")

    if classified_count != classifiable_count or mapped_count != classifiable_count:
        errors.append(
            "classification/document coverage is not one-to-one: "
            f"{classifiable_count}/{classified_count}/{mapped_count}"
        )

    role_audit = audit_role_recovery(project_root)
    if role_audit.get("status") != "PASS":
        errors.extend(f"role recovery audit: {item}" for item in role_audit.get("errors", []))

    status = "PASS" if not errors else "FAIL"
    report = {
        "generated_at": utc_now(),
        "status": status,
        "strict": strict,
        "audit_engine": "streaming_exact_join_v2",
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "sources_discovered": source_count,
            "sources_selected": selected_source_count,
            "preserved_sources_rehashed": preserved_verified if strict else None,
            "preserved_storage_modes": dict(storage_modes),
            "raw_records": raw_count,
            "raw_status": dict(raw_status),
            "timeline_events": timeline_count,
            "duplicate_occurrences": duplicate_count,
            "classifiable_events": classifiable_count,
            "classified_events": classified_count,
            "mapped_events": mapped_count,
            "user_messages": user_message_count,
            "assistant_messages": assistant_message_count,
            "tool_calls": tool_call_count,
            "tool_outputs": tool_output_count,
            "parse_failures": parse_failures,
            "human_review_required": human_review_required,
            "independent_reviewed": review_report.get("reviewed"),
            "conflicts": conflict_count,
            "unresolved_conflicts": unresolved_conflicts,
            "project_files": project_file_count,
            "missing_documents": len(missing_documents),
            "items_excluded_without_reason": silent_exclusions,
            "roles": role_audit.get("counts", {}).get("roles"),
            "role_assigned_events": role_audit.get("counts", {}).get("role_assigned_events"),
            "role_reference_rows": role_audit.get("counts", {}).get("role_reference_rows"),
            "role_handoffs": role_audit.get("counts", {}).get("handoffs"),
        },
        "coverage": {
            "raw_line_index": 1.0 if raw_count and parse_failures == 0 else 0.0,
            "user_message_classification": 1.0 if user_message_count and classified_count == classifiable_count else 0.0,
            "classifiable_event_classification": 1.0 if classified_count == classifiable_count else 0.0,
            "classification_to_document_map": 1.0 if mapped_count == classifiable_count else 0.0,
            "selected_source_extraction": 1.0 if not missing_source_extraction else 0.0,
            "role_assignment": 1.0 if role_audit.get("checks", {}).get("all_classified_events_have_roles") else 0.0,
            "role_capsule_integrity": 1.0 if role_audit.get("status") == "PASS" else 0.0,
        },
        "limitations": [
            f"Preserved storage modes are {dict(storage_modes)}; NTFS hardlinks survive name deletion but share in-place mutations, so strict audit rehashes every preserved path.",
            "Active transcripts are independent gzip prefix snapshots at discovery cutoff; messages appended after that cutoff require a later explicit recovery run.",
            "Git history is unavailable because the accessible project root is not a valid Git repository.",
            "Deleted or never-persisted chats and private reasoning are not reconstructible; private reasoning is represented only by recorded hashes/lengths where present.",
        ],
        "scope_statement": (
            f"PASS certifies complete accounting of the {selected_source_count} selected immutable discovery snapshots: "
            "source line -> REC -> canonical EVT or explicit duplicate -> classification -> document mapping. "
            "It does not assert recovery of deleted, inaccessible, or never-saved material."
        ),
        "key_files": {
            "source_index": safe_relpath(paths.source_index, project_root),
            "raw_line_index": safe_relpath(paths.raw_line_index, project_root),
            "timeline": safe_relpath(paths.timeline, project_root),
            "duplicate_occurrence_map": safe_relpath(duplicate_map, project_root),
            "classification": safe_relpath(paths.classification, project_root),
            "coverage_map": safe_relpath(paths.coverage_map, project_root),
            "role_audit": safe_relpath(paths.recovery / "감사결과" / "역할복구_감사.json", project_root),
            "role_registry": safe_relpath(project_root / "12_협업" / "역할목록.yaml", project_root),
            "role_handoff_ledger": safe_relpath(project_root / "12_협업" / "역할간_인계기록.jsonl", project_root),
        },
        "role_audit": role_audit,
    }
    json_dump(paths.coverage_report, report)
    json_dump(paths.recovery_report, report)
    if status == "PASS" and strict:
        project_contract_path = project_root / "project.yaml"
        governance_state_path = project_root / "02_상태" / "state.json"
        try:
            project_contract = _load_json(project_contract_path)
            governance_state = _load_json(governance_state_path)
            if project_contract:
                project_contract.setdefault("project", {})["status"] = "RECOVERY_COMPLETE"
                project_contract.setdefault("recovery", {})["strict_status"] = "PASS"
                project_contract["recovery"]["strict_audit_report"] = safe_relpath(
                    paths.recovery_report, project_root
                )
                json_dump(project_contract_path, project_contract)
            if governance_state:
                governance_state["phase"] = "RECOVERY_COMPLETE"
                governance_state["status"] = "RECOVERY_COMPLETE"
                governance_state["updated_at_utc"] = report["generated_at"]
                json_dump(governance_state_path, governance_state)
            from research_guard.render import render as render_governance_docs

            render_governance_docs(project_root)
        except Exception as exc:
            # Completion documents are part of the strict contract. Convert a
            # late synchronization failure into an explicit failed report.
            report["status"] = "FAIL"
            report["errors"].append(
                f"strict completion governance synchronization failed: {type(exc).__name__}: {exc}"
            )
            status = "FAIL"
            json_dump(paths.coverage_report, report)
            json_dump(paths.recovery_report, report)
    state_path = project_root / "02_상태" / "복구_현재상태.json"
    json_dump(
        state_path,
        {
            "schema_version": "1.0",
            "status": "FULL_RESEARCH_RECORD_RECOVERY_COMPLETE" if status == "PASS" and strict else "RECOVERY_AUDIT_FAILED",
            "generated_at": report["generated_at"],
            "strict_audit_status": status,
            "strict": strict,
            "counts": report["counts"],
            "coverage": report["coverage"],
            "warnings": warnings,
            "limitations": report["limitations"],
            "audit_report": safe_relpath(paths.recovery_report, project_root),
            "canonical_research_state_overwritten": False,
        },
    )
    validation_path = project_root / "08_검증" / "복구검증_대기.md"
    if status == "PASS" and strict:
        validation_path.write_text(
            "# 복구 검증 상태\n\n"
            "`audit --strict` PASS. 누락 0, parse failure 0, 미해결 충돌 0.\n\n"
            f"- 감사 보고서: `{safe_relpath(paths.recovery_report, project_root)}`\n"
            f"- 선택 원본: {selected_source_count}\n"
            f"- 원본 REC: {raw_count}\n"
            f"- classifiable EVT / 분류 / 문서반영: {classifiable_count} / {classified_count} / {mapped_count}\n",
            encoding="utf-8",
        )
    else:
        validation_path.write_text(
            "# 복구 검증 상태\n\n`audit --strict` FAIL. 감사 보고서의 errors를 해결하기 전에는 완료로 판정할 수 없습니다.\n",
            encoding="utf-8",
        )
    return report
