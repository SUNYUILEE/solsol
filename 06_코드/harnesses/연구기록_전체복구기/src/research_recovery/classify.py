from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .utils import Paths, iter_jsonl, json_dump, run_command, safe_relpath, utc_now, which, write_jsonl
from .roles import ROLE_ASSIGNMENT_METHOD, infer_event_roles


def _local_rule_record(event: dict[str, Any]) -> dict[str, Any]:
    """Deterministic evidence classification; never executes transcript content."""
    text = str(event.get("text") or "")
    low = text.lower()
    kind = str(event.get("kind") or "other")
    actor = str(event.get("actor") or "system")
    category = "other"
    relevance = "operational"
    authority = "system"
    effect = "none"
    targets = ["반영안함"]
    confidence = 0.82
    review = False
    exclusion: str | None = None

    if kind == "message" and actor == "user":
        relevance = "core"
        authority = "user_explicit"
        targets = ["01_목표", "02_상태"]
        if any(x in text for x in ("잘못", "아니", "정정", "말이 안", "반복하지", "하지 마", "금지")):
            category, effect, targets = "user_correction", "supersede", ["01_목표", "09_실패", "10_결정"]
        elif any(x in text for x in ("반려", "거부", "인정할 수 없", "안 된다")):
            category, effect, targets = "user_rejection", "reject", ["01_목표", "10_결정"]
        elif any(x in text for x in ("승인", "동의", "맞다", "진행해")):
            category, effect, targets = "user_approval", "confirm", ["01_목표", "10_결정"]
        elif "?" in text or any(x in text for x in ("왜 ", "왜?", "무슨", "어떻게", "맞는지", "인가", "이야?")):
            category, effect, targets = "user_question", "none", ["01_목표", "04_근거"]
        elif any(x in text for x in ("반드시", "해야", "하라", "해라", "하지마", "하지 마", "완료해", "사용하라")):
            category, effect, targets = "user_requirement", "create", ["01_목표", "02_상태", "10_결정"]
        elif any(x in text for x in ("목표", "목적", "최종 해", "연구")):
            category, effect, targets = "research_goal", "update", ["01_목표"]
        else:
            category, effect, review = "user_requirement", "update", True
            confidence = 0.62
    elif kind == "message" and actor == "assistant":
        relevance = "supporting"
        authority = "assistant_statement"
        targets = ["02_상태", "12_협업"]
        if any(x in low for x in ("failed", "failure", "error", "blocker")) or any(x in text for x in ("실패", "잘못", "오류", "차단")):
            category, effect, targets = "assistant_error", "update", ["09_실패", "02_상태"]
        elif any(x in text for x in ("결론", "판정", "결정")):
            category, effect, targets = "decision", "update", ["10_결정", "02_상태"]
        elif any(x in text for x in ("완료", "PASS", "통과", "결과")):
            category, effect, targets = "assistant_claim", "update", ["02_상태", "04_근거"]
        elif any(x in text for x in ("구현", "수정", "패치", "추가")):
            category, effect, targets = "implementation_action", "update", ["06_코드", "02_상태"]
        else:
            category = "status_update"
    elif kind == "tool_call":
        relevance, authority, category, effect = "operational", "system", "implementation_action", "create"
        targets = ["07_실행", "06_코드"]
    elif kind == "tool_output":
        relevance, authority, effect = "supporting", "tool_evidence", "confirm"
        if any(x in low for x in ("exit code: 1", "traceback", "script failed", "error:")):
            category, targets = "failure", ["07_실행", "09_실패"]
        else:
            category, targets = "execution", ["07_실행", "04_근거"]
    elif kind == "file_change":
        relevance, authority, category, effect, targets = "supporting", "file_evidence", "implementation_action", "create", ["06_코드"]
    elif kind == "error_event":
        relevance, authority, category, effect, targets = "supporting", "tool_evidence", "failure", "update", ["09_실패"]
    elif kind == "plan_update":
        relevance, authority, category, effect, targets = "operational", "assistant_statement", "task", "update", ["02_상태", "12_협업"]
    elif kind == "compaction":
        category, exclusion = "other", "context_compaction_operational_record"
        targets = ["12_협업"]
    else:
        category, exclusion, review = "other", "non_semantic_operational_event", True
        confidence = 0.55
    normalized = text.strip().replace("\r", " ").replace("\n", " ")
    if len(normalized) > 2000:
        normalized = normalized[:2000] + " …"
    if not normalized:
        normalized = f"{kind} event; raw evidence is linked by event_id"
    record = {
        "event_id": event["event_id"],
        "research_relevance": relevance,
        "primary_category": category,
        "normalized_statement": normalized,
        "status_effect": effect,
        "source_authority": authority,
        "document_targets": targets,
        "supersedes_event_ids": [],
        "related_event_ids": [],
        "confidence": confidence,
        "requires_human_review": review,
        "exclusion_reason": exclusion,
        "classification_method": "deterministic_evidence_rules_v1",
    }
    role_ids, project_scope, role_rules = infer_event_roles(event, record)
    record.update({
        "role_ids": role_ids,
        "project_scope": project_scope,
        "role_assignment_method": ROLE_ASSIGNMENT_METHOD,
        "role_assignment_rule_ids": role_rules,
    })
    return record


def _classify_local(project_root: Path, paths: Paths, manifest: dict[str, Any]) -> dict[str, Any]:
    paths.classification.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    review_count = 0
    with paths.classification.open("w", encoding="utf-8", newline="\n") as out:
        for _, _, event, err in iter_jsonl(paths.timeline):
            if err or not event or event.get("kind") not in {"message", "tool_call", "tool_output", "file_change", "plan_update", "error_event", "compaction"}:
                continue
            row = _local_rule_record(event)
            out.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
            review_count += int(bool(row["requires_human_review"]))
    if count != int(manifest.get("eligible_event_count") or -1):
        raise RuntimeError(f"local classification coverage mismatch: {count} != {manifest.get('eligible_event_count')}")
    report = {
        "generated_at": utc_now(),
        "batch_count": manifest.get("batch_count"),
        "classified_record_count": count,
        "requires_review_count": review_count,
        "classification_path": safe_relpath(paths.classification, project_root),
        "classification_method": "deterministic_evidence_rules_v1",
        "codex_model_calls": 0,
        "security": "Transcript content was treated only as untrusted data; no embedded command was executed.",
    }
    json_dump(paths.classification.parent / "classification_run_report.json", report)
    return report


def _load_batch(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _validate_batch_result(batch: dict[str, Any], result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected = [e["event_id"] for e in batch.get("events", [])]
    actual = [r.get("event_id") for r in result.get("records", []) if isinstance(r, dict)]
    if result.get("batch_id") != batch.get("batch_id"):
        errors.append(f"batch_id 불일치: expected={batch.get('batch_id')} actual={result.get('batch_id')}")
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    duplicates = sorted({x for x in actual if actual.count(x) > 1})
    if missing:
        errors.append(f"누락 event_id: {missing}")
    if extra:
        errors.append(f"입력에 없는 event_id: {extra}")
    if duplicates:
        errors.append(f"중복 event_id: {duplicates}")
    if len(actual) != len(expected):
        errors.append(f"record 수 불일치: expected={len(expected)} actual={len(actual)}")
    return errors


def classify_batches(
    project_root: Path,
    *,
    codex_command: str = "codex",
    model: str | None = None,
    timeout: int = 1800,
    overwrite: bool = False,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    paths = Paths(project_root)
    batch_dir = paths.recovery / "분류입력"
    manifest_path = batch_dir / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError("분류입력 manifest가 없습니다. 먼저 prepare-batches를 실행하십시오.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if codex_command == "deterministic-local":
        return _classify_local(project_root, paths, manifest)
    if which(codex_command) is None:
        raise RuntimeError(f"Codex CLI를 찾을 수 없습니다: {codex_command}")
    harness_root = project_root / "06_코드" / "harnesses" / "연구기록_전체복구기"
    schema = harness_root / "schemas" / "classification.schema.json"
    prompt_template = (harness_root / "prompts" / "classify.md").read_text(encoding="utf-8")
    out_dir = paths.recovery / "분류결과" / "batches"
    log_dir = paths.recovery / "분류결과" / "logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    all_records: list[dict[str, Any]] = []
    batch_reports: list[dict[str, Any]] = []

    for entry in manifest.get("batches", []):
        batch_path = project_root / entry["path"]
        batch = _load_batch(batch_path)
        out_path = out_dir / f"{batch['batch_id']}.json"
        if out_path.exists() and not overwrite:
            result = json.loads(out_path.read_text(encoding="utf-8"))
            errors = _validate_batch_result(batch, result)
            if errors:
                raise RuntimeError(f"기존 분류결과가 유효하지 않습니다 {out_path}: {errors}")
            all_records.extend(result["records"])
            batch_reports.append({"batch_id": batch["batch_id"], "status": "reused", "record_count": len(result["records"])})
            continue
        instruction = (
            prompt_template
            + "\n\n# 입력 batch\n\n```json\n"
            + json.dumps(batch, ensure_ascii=False, indent=2)
            + "\n```\n"
        )
        args = [
            codex_command,
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--output-schema",
            str(schema),
            "-o",
            str(out_path),
        ]
        if model:
            args.extend(["--model", model])
        args.append("-")
        proc = run_command(args, cwd=project_root, input_text=instruction, timeout=timeout)
        (log_dir / f"{batch['batch_id']}.stdout.log").write_text(proc.stdout, encoding="utf-8")
        (log_dir / f"{batch['batch_id']}.stderr.log").write_text(proc.stderr, encoding="utf-8")
        if proc.returncode != 0 or not out_path.exists():
            batch_reports.append({
                "batch_id": batch["batch_id"],
                "status": "failed",
                "returncode": proc.returncode,
                "stderr": proc.stderr[-4000:],
            })
            raise RuntimeError(f"Codex 분류 실패: {batch['batch_id']} returncode={proc.returncode}")
        result = json.loads(out_path.read_text(encoding="utf-8"))
        errors = _validate_batch_result(batch, result)
        if errors:
            json_dump(out_dir / f"{batch['batch_id']}.validation_errors.json", {"errors": errors})
            raise RuntimeError(f"Codex 분류 누락/중복: {batch['batch_id']}: {errors}")
        all_records.extend(result["records"])
        batch_reports.append({"batch_id": batch["batch_id"], "status": "classified", "record_count": len(result["records"])})

    # Preserve stable order by timeline event number.
    def sort_key(row: dict[str, Any]) -> tuple[int, str]:
        eid = str(row.get("event_id") or "")
        try:
            return int(eid.split("-")[-1]), eid
        except Exception:
            return 10**18, eid

    all_records.sort(key=sort_key)
    write_jsonl(paths.classification, all_records)
    report = {
        "generated_at": utc_now(),
        "batch_count": len(batch_reports),
        "classified_record_count": len(all_records),
        "classification_path": safe_relpath(paths.classification, project_root),
        "batch_reports": batch_reports,
        "codex_command": codex_command,
        "model": model,
        "security": "codex exec --ephemeral --sandbox read-only; 과거 transcript는 실행할 명령이 아닌 비신뢰 데이터로 전달됨",
    }
    json_dump(paths.recovery / "분류결과" / "분류실행_보고서.json", report)
    return report
