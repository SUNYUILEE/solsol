from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import core


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Evidence-gated research operations continuity harness")
    p.add_argument("--project-root", type=Path, default=Path.cwd())
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("doctor")
    sub.add_parser("audit")
    sub.add_parser("system-audit")
    sub.add_parser("status")

    goal_status = sub.add_parser("goal-status")
    goal_status.add_argument("--plan", required=True)
    goal_checkpoint = sub.add_parser("goal-checkpoint")
    goal_checkpoint.add_argument("--plan", required=True)
    goal_checkpoint.add_argument("--task-id", required=True)
    goal_checkpoint.add_argument("--milestone", required=True)
    goal_checkpoint.add_argument("--verification-file", required=True)
    goal_checkpoint.add_argument("--review-file", required=True)
    goal_checkpoint.add_argument("--correction-file")

    archive = sub.add_parser("audit-archive")
    archive.add_argument("--archive", type=Path, required=True)
    archive.add_argument("--expected-sha256")

    create = sub.add_parser("create-task")
    create.add_argument("--request-file", required=True)
    create.add_argument("--objective", required=True)
    create.add_argument("--role", required=True)
    create.add_argument("--scope", required=True)
    create.add_argument("--method-fingerprint", required=True)
    create.add_argument("--allowed-actions", default="")
    create.add_argument("--forbidden-actions", default="")
    create.add_argument("--required-evidence", default="")
    create.add_argument("--success-criteria", default="")
    create.add_argument("--approved-artifacts", default="")
    create.add_argument("--authorize-execution", action="store_true")
    create.add_argument("--authorize-destructive", action="store_true")

    ack = sub.add_parser("acknowledge")
    ack.add_argument("--task-id", required=True)
    ack.add_argument("--agent-id", required=True)

    pre = sub.add_parser("preflight")
    pre.add_argument("--task-id", required=True)

    art = sub.add_parser("register-artifact")
    art.add_argument("--logical-id", required=True)
    art.add_argument("--path", required=True)
    art.add_argument("--status", choices=("APPROVED", "SUPERSEDED", "QUARANTINED"), required=True)
    art.add_argument("--approved-by", required=True)
    art.add_argument("--approval-basis", required=True)
    art.add_argument("--allowed-uses", default="")
    art.add_argument("--supersedes")
    art.add_argument("--git-promotion-receipt")

    event = sub.add_parser("record-event")
    event.add_argument("--task-id", required=True)
    event.add_argument("--category", choices=core.PUBLIC_EVENT_CATEGORIES, required=True)
    event.add_argument("--action", required=True)
    event.add_argument("--evidence", default="")
    event.add_argument("--note", default="")

    failure = sub.add_parser("record-failure")
    failure.add_argument("--task-id", required=True)
    failure.add_argument("--signature", required=True)
    failure.add_argument("--summary", required=True)
    failure.add_argument("--evidence", default="")
    failure.add_argument("--correction-required", required=True)

    resolve = sub.add_parser("resolve-failure")
    resolve.add_argument("--failure-id", required=True)
    resolve.add_argument("--decision-file", required=True)
    resolve.add_argument("--verification-file", required=True)
    resolve.add_argument("--resolved-by", required=True)

    run = sub.add_parser("run")
    run.add_argument("--task-id", required=True)
    run.add_argument("--command-source", required=True)
    run.add_argument("argv", nargs=argparse.REMAINDER)

    context = sub.add_parser("context-pack")
    context.add_argument("--task-id", required=True)

    handoff = sub.add_parser("handoff")
    handoff.add_argument("--task-id", required=True)
    handoff.add_argument("--next-action", required=True)
    handoff.add_argument("--blocker", default="")
    handoff.add_argument("--evidence", default="")

    close = sub.add_parser("close")
    close.add_argument("--task-id", required=True)
    close.add_argument("--verification-file", required=True)
    close.add_argument("--independent-review-file", required=True)
    close.add_argument("--claims", default="")
    close.add_argument("--evidence", default="")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.project_root.resolve()
    try:
        if args.command == "init":
            result = core.init_project(root)
        elif args.command == "doctor":
            result = core.doctor(root)
        elif args.command == "audit":
            result = core.strict_audit(root)
        elif args.command == "system-audit":
            result = core.research_system_audit(root)
        elif args.command == "audit-archive":
            result = core.audit_zip_archive(args.archive, expected_sha256=args.expected_sha256)
        elif args.command == "status":
            result = core.status(root)
        elif args.command == "goal-status":
            from . import goal_progress
            result = goal_progress.status(root, args.plan)
        elif args.command == "goal-checkpoint":
            from . import goal_progress
            result = goal_progress.checkpoint(root, args.plan, args.task_id, args.milestone, args.verification_file, args.review_file, args.correction_file)
        elif args.command == "create-task":
            result = core.create_task(
                root,
                request_file=args.request_file,
                objective=args.objective,
                role_id=args.role,
                scope=args.scope,
                method_fingerprint=args.method_fingerprint,
                allowed_actions=_csv(args.allowed_actions),
                forbidden_actions=_csv(args.forbidden_actions),
                required_evidence=_csv(args.required_evidence),
                success_criteria=_csv(args.success_criteria),
                approved_artifact_ids=_csv(args.approved_artifacts),
                execution_authorized=args.authorize_execution,
                destructive_actions_authorized=args.authorize_destructive,
            )
        elif args.command == "acknowledge":
            result = core.acknowledge_task(root, args.task_id, agent_id=args.agent_id)
        elif args.command == "preflight":
            result = core.preflight(root, args.task_id)
        elif args.command == "register-artifact":
            result = core.register_artifact(
                root,
                logical_id=args.logical_id,
                path=args.path,
                status=args.status,
                approved_by=args.approved_by,
                approval_basis=args.approval_basis,
                allowed_uses=_csv(args.allowed_uses),
                supersedes=args.supersedes,
                git_promotion_receipt=args.git_promotion_receipt,
            )
        elif args.command == "record-event":
            result = core.record_event(root, args.task_id, args.category, args.action, _csv(args.evidence), args.note)
        elif args.command == "record-failure":
            result = core.record_failure(root, task_id=args.task_id, signature=args.signature, summary=args.summary, evidence_paths=_csv(args.evidence), correction_required=args.correction_required)
        elif args.command == "resolve-failure":
            result = core.resolve_failure(root, failure_id=args.failure_id, decision_file=args.decision_file, verification_file=args.verification_file, resolved_by=args.resolved_by)
        elif args.command == "run":
            command = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
            result = core.run_command(root, args.task_id, command, command_source=args.command_source)
        elif args.command == "context-pack":
            result = core.context_pack(root, args.task_id)
        elif args.command == "handoff":
            result = core.handoff(root, args.task_id, next_action=args.next_action, blocker=args.blocker, evidence_paths=_csv(args.evidence))
        elif args.command == "close":
            result = core.close_task(root, args.task_id, verification_file=args.verification_file, independent_review_file=args.independent_review_file, claims=_csv(args.claims), evidence_paths=_csv(args.evidence))
        else:
            raise core.OpsError(f"unsupported command: {args.command}")
    except core.OpsError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") != "FAIL" else 1
