from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .utils import Paths, iter_jsonl, json_dump, run_command, utc_now, which, write_jsonl


def _review_local(project_root: Path, p: Paths) -> dict[str, Any]:
    """Independent structural/authority audit without model calls or transcript execution."""
    class_iter = (obj for _, _, obj, err in iter_jsonl(p.classification) if obj and not err)
    reviewed = 0
    findings = 0
    user_count = 0
    tool_evidence_count = 0
    review_path = p.recovery / "감사결과" / "독립분류감사_항목.jsonl"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    reviewed_classification = p.classification.with_suffix(".review_tmp")
    changed = 0
    with review_path.open("w", encoding="utf-8", newline="\n") as out, reviewed_classification.open(
        "w", encoding="utf-8", newline="\n"
    ) as classified_out:
        for _, _, event, err in iter_jsonl(p.timeline):
            if err or not event or event.get("kind") not in {"message", "tool_call", "tool_output", "file_change", "plan_update", "error_event", "compaction"}:
                continue
            try:
                row = next(class_iter)
            except StopIteration as exc:
                raise RuntimeError("classification ended before timeline") from exc
            if row.get("event_id") != event.get("event_id"):
                raise RuntimeError(f"classification order/id mismatch: {row.get('event_id')} != {event.get('event_id')}")
            issues: list[str] = []
            actor = event.get("actor")
            kind = event.get("kind")
            cat = row.get("primary_category")
            if actor == "user" and kind == "message":
                user_count += 1
                if row.get("source_authority") != "user_explicit":
                    issues.append("user_message_not_user_explicit")
                if cat not in {"research_goal", "user_requirement", "scope_rule", "completion_criterion", "user_correction", "user_question", "user_approval", "user_rejection"}:
                    issues.append("user_message_category_invalid")
            if kind == "tool_output":
                tool_evidence_count += 1
                if row.get("source_authority") != "tool_evidence":
                    issues.append("tool_output_not_tool_evidence")
            if actor == "assistant" and row.get("source_authority") == "tool_evidence":
                issues.append("assistant_statement_mislabeled_as_tool_evidence")
            if not row.get("document_targets"):
                issues.append("document_target_missing")
            role_ids = row.get("role_ids")
            if not isinstance(role_ids, list) or not role_ids:
                issues.append("role_ids_missing")
            if row.get("project_scope") not in {"GLOBAL", "ROLE_SCOPED"}:
                issues.append("project_scope_missing_or_invalid")
            if row.get("research_relevance") == "non_research" and not row.get("exclusion_reason"):
                issues.append("non_research_exclusion_reason_missing")
            resolution = None
            if row.get("requires_human_review"):
                if actor == "user" and kind == "message" and cat == "user_requirement":
                    resolution = "confirmed_default_user_requirement"
                elif actor in {"system", "developer"} and kind == "message" and cat == "other":
                    row["primary_category"] = "scope_rule"
                    row["research_relevance"] = "operational"
                    row["document_targets"] = ["01_목표", "02_상태"]
                    resolution = "system_or_developer_context_classified_as_scope_rule"
                if resolution:
                    row["requires_human_review"] = False
                    row["independent_review_resolution"] = resolution
                    row["independent_review_method"] = "independent_authority_and_coverage_rules_v1"
                    row["confidence"] = max(float(row.get("confidence") or 0.0), 0.8)
                    changed += 1
            reviewed += 1
            findings += len(issues)
            classified_out.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            if issues or resolution or row.get("requires_human_review"):
                out.write(json.dumps({
                    "event_id": event["event_id"],
                    "issues": issues,
                    "requires_human_review": bool(row.get("requires_human_review")),
                    "resolution": resolution,
                    "audit_method": "independent_authority_and_coverage_rules_v1",
                }, ensure_ascii=False, separators=(",", ":")) + "\n")
        try:
            extra = next(class_iter)
        except StopIteration:
            extra = None
        if extra is not None:
            raise RuntimeError(f"classification has extra row after timeline: {extra.get('event_id')}")
    if findings:
        reviewed_classification.unlink(missing_ok=True)
        raise RuntimeError(f"independent classification audit found {findings} structural findings")
    os.replace(reviewed_classification, p.classification)
    report = {
        "generated_at": utc_now(),
        "reviewed": reviewed,
        "changed": changed,
        "structural_findings": findings,
        "user_messages_reviewed": user_count,
        "tool_outputs_reviewed": tool_evidence_count,
        "review_method": "independent_authority_and_coverage_rules_v1",
        "codex_model_calls": 0,
        "review_item_path": str(review_path.relative_to(project_root)).replace("\\", "/"),
    }
    json_dump(p.recovery / "감사결과" / "독립분류감사_보고서.json", report)
    return report


def _rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    for _, _, obj, err in iter_jsonl(path):
        if obj and not err and isinstance(obj, dict):
            rows.append(obj)
    return rows


def review_classifications(project_root: Path, *, codex_command: str = "codex", model: str | None = None, timeout: int = 1800, overwrite: bool = False) -> dict[str, Any]:
    project_root = project_root.resolve()
    p = Paths(project_root)
    if codex_command == "deterministic-local":
        return _review_local(project_root, p)
    if which(codex_command) is None:
        raise RuntimeError(f"Codex CLI를 찾을 수 없습니다: {codex_command}")
    manifest = json.loads((p.recovery / "분류입력" / "manifest.json").read_text(encoding="utf-8"))
    first = {r.get("event_id"): r for r in _rows(p.classification)}
    harness = project_root / "06_코드" / "harnesses" / "연구기록_전체복구기"
    schema = harness / "schemas" / "classification_review.schema.json"
    prompt_base = (harness / "prompts" / "review_classification.md").read_text(encoding="utf-8")
    out_dir = p.recovery / "분류결과" / "independent_review"
    log_dir = out_dir / "logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    final_records: list[dict[str, Any]] = []
    changed = 0
    reviewed = 0
    reports = []
    for entry in manifest.get("batches", []):
        batch = json.loads((project_root / entry["path"]).read_text(encoding="utf-8"))
        payload = {
            "batch_id": batch["batch_id"],
            "events": batch["events"],
            "first_classifications": [first[e["event_id"]] for e in batch["events"] if e["event_id"] in first],
        }
        out = out_dir / f"{batch['batch_id']}.json"
        if out.exists() and not overwrite:
            result = json.loads(out.read_text(encoding="utf-8"))
        else:
            prompt = prompt_base + "\n\n# 입력\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```\n"
            args = [codex_command, "exec", "--ephemeral", "--sandbox", "read-only", "--skip-git-repo-check", "--output-schema", str(schema), "-o", str(out)]
            if model:
                args.extend(["--model", model])
            args.append("-")
            proc = run_command(args, cwd=project_root, input_text=prompt, timeout=timeout)
            (log_dir / f"{batch['batch_id']}.stdout.log").write_text(proc.stdout, encoding="utf-8")
            (log_dir / f"{batch['batch_id']}.stderr.log").write_text(proc.stderr, encoding="utf-8")
            if proc.returncode != 0 or not out.exists():
                raise RuntimeError(f"독립 분류감사 실패 {batch['batch_id']} returncode={proc.returncode}")
            result = json.loads(out.read_text(encoding="utf-8"))
        expected = {e["event_id"] for e in batch["events"]}
        actual = [r.get("event_id") for r in result.get("reviews", [])]
        if set(actual) != expected or len(actual) != len(expected):
            raise RuntimeError(f"독립감사 event 누락/중복 {batch['batch_id']}")
        for review in result["reviews"]:
            fr = review["final_record"]
            if fr.get("event_id") != review.get("event_id"):
                raise RuntimeError(f"독립감사 final_record event_id 불일치: {review.get('event_id')}")
            final_records.append(fr)
            reviewed += 1
            changed += int(bool(review.get("changed")))
        reports.append({"batch_id": batch["batch_id"], "reviewed": len(result["reviews"]), "changed": sum(bool(r.get("changed")) for r in result["reviews"])})
    final_records.sort(key=lambda r: r.get("event_id", ""))
    write_jsonl(p.classification, final_records)
    report = {"generated_at": utc_now(), "reviewed": reviewed, "changed": changed, "batch_reports": reports, "model": model}
    json_dump(p.recovery / "감사결과" / "독립분류감사_보고서.json", report)
    return report
