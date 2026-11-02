from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .audit import audit_recovery
from .batching import prepare_batches, prepare_incremental_batches
from .checkpoint import fast_checkpoint
from .classify import classify_batches
from .cleanup import audit_cleanup_dry_run, build_cleanup_dry_run, cleanup_preflight
from .cleanup_stream import build_cleanup_path_order, record_failed_uncheckpointed_scan, run_streaming_cleanup_dry_run
from .codex_parser import extract_all
from .conflicts import detect_conflicts
from .discover import discover_sources
from .project_scan import scan_project
from .render import render_research_docs
from .review import review_conflicts
from .review_classification import review_classifications
from .roles import assign_roles, audit_role_recovery, render_role_views
from .incremental import incremental_extract_active_source
from .utils import Paths, iter_jsonl, json_dump, utc_now, which, write_jsonl


def _root(value: str) -> Path:
    return Path(value).expanduser().resolve()


def select_sources(project_root: Path, *, source_ids: list[str], session_ids: list[str], select_all: bool, clear: bool) -> dict[str, Any]:
    p = Paths(project_root)
    rows: list[dict[str, Any]] = []
    for _, _, obj, err in iter_jsonl(p.source_index):
        if obj and not err:
            rows.append(obj)
    if clear:
        for row in rows:
            row["selected"] = False
    for row in rows:
        if select_all or row.get("source_id") in source_ids or (row.get("session_id") and row.get("session_id") in session_ids):
            row["selected"] = True
    write_jsonl(p.source_index, rows)
    report = {
        "generated_at": utc_now(),
        "source_count": len(rows),
        "selected_count": sum(bool(r.get("selected")) for r in rows),
        "selected_sources": [r.get("source_id") for r in rows if r.get("selected")],
    }
    json_dump(p.recovery / "원본목록" / "원본선택_보고서.json", report)
    return report


def doctor(project_root: Path, codex_home: str | None) -> dict[str, Any]:
    from .utils import codex_home as resolve_codex_home
    ch = resolve_codex_home(codex_home)
    report = {
        "generated_at": utc_now(),
        "project_root": str(project_root),
        "project_exists": project_root.exists(),
        "git_repository": (project_root / ".git").exists(),
        "codex_cli": which("codex"),
        "codex_home": str(ch),
        "sessions_exists": (ch / "sessions").exists(),
        "archived_sessions_exists": (ch / "archived_sessions").exists(),
        "history_exists": (ch / "history.jsonl").exists(),
        "skill_exists": (project_root / ".agents" / "skills" / "연구기록_전체복구" / "SKILL.md").exists(),
        "harness_exists": (project_root / "06_코드" / "harnesses" / "연구기록_전체복구기" / "manifest.json").exists(),
    }
    json_dump(Paths(project_root).recovery / "감사결과" / "doctor.json", report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research_recovery.py",
        description="Codex 전체 대화·명령·파일·실행증거를 전수 색인하고 연구 문서 구조를 자동으로 채웁니다.",
    )
    parser.add_argument("--project-root", default=".", help="복구할 프로젝트 루트")
    parser.add_argument("--codex-home", default=None, help="CODEX_HOME 경로. 기본값은 환경변수 또는 ~/.codex")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Codex session·Git·Skill·Harness 접근상태 점검")

    d = sub.add_parser("discover", help="접근 가능한 Codex transcript 원본 전수 발견")
    d.add_argument("--transcript", action="append", default=[], help="추가 transcript 파일 또는 폴더. 반복 가능")
    d.add_argument("--copy-raw", action="store_true", help="원본 transcript를 99_보관이 아닌 복구증거/원본보관에 해시명으로 복사")
    d.add_argument("--select-all", action="store_true", help="발견된 모든 Codex 세션을 선택. 다른 프로젝트 세션 혼입 주의")
    d.add_argument("--scope-root", action="append", default=[], help="세션 cwd 귀속 판정에 추가할 프로젝트 루트. 반복 가능")

    s = sub.add_parser("select-sources", help="발견된 원본 중 이 프로젝트에 사용할 세션을 명시적으로 선택")
    s.add_argument("--source-id", action="append", default=[])
    s.add_argument("--session-id", action="append", default=[])
    s.add_argument("--all", action="store_true")
    s.add_argument("--clear", action="store_true", help="기존 선택을 모두 해제한 뒤 적용")

    e = sub.add_parser("extract", help="선택된 transcript의 모든 JSONL 줄과 대화·도구 이벤트 전수 색인")
    e.add_argument("--include-all-sessions", action="store_true", help="selected 표시와 무관하게 모든 원본 처리")
    e.add_argument("--max-text-chars", type=int, default=120000)
    sub.add_parser("extract-incremental", help="완료 base와 active snapshot prefix를 byte 검증하고 증가 line만 delta 색인")

    sub.add_parser("scan-project", help="프로젝트 파일·Git 이력 전수 색인")

    b = sub.add_parser("prepare-batches", help="모든 연구 이벤트를 누락 없는 Codex 분류 batch로 생성")
    b.add_argument("--max-events", type=int, default=60)
    b.add_argument("--max-chars", type=int, default=90000)
    b.add_argument("--include-non-project", action="store_true")
    sub.add_parser("prepare-batches-incremental", help="기존 batch corpus는 보존하고 incremental EVT delta만 새 batch로 추가")

    c = sub.add_parser("classify", help="codex exec 구조화 출력으로 모든 event를 정확히 한 번씩 분류")
    c.add_argument("--codex-command", default="codex")
    c.add_argument("--model", default=None)
    c.add_argument("--timeout", type=int, default=1800)
    c.add_argument("--overwrite", action="store_true")

    rv = sub.add_parser("review-classifications", help="독립 Codex pass로 모든 1차 분류를 원문과 다시 대조")
    rv.add_argument("--codex-command", default="codex")
    rv.add_argument("--model", default=None)
    rv.add_argument("--timeout", type=int, default=1800)
    rv.add_argument("--overwrite", action="store_true")

    sub.add_parser("detect-conflicts", help="정정·반려·낮은 확신·잘못된 EVT 참조를 충돌목록으로 생성")

    sub.add_parser("assign-roles", help="각 classifiable EVT에 다중 role_ids와 GLOBAL/ROLE_SCOPED를 근거 기반 부여")

    rc = sub.add_parser("review-conflicts", help="Codex 독립 검토로 정정·반려가 대체하는 이전 EVT를 연결")
    rc.add_argument("--codex-command", default="codex")
    rc.add_argument("--model", default=None)
    rc.add_argument("--timeout", type=int, default=1800)

    r = sub.add_parser("render", help="분류된 전체 대화에서 연구 폴더의 문서·원장을 자동 생성")
    r.add_argument("--no-backup", action="store_true", help="기존 문서 백업을 생략")

    a = sub.add_parser("audit", help="원본 줄→event→분류→문서반영 전수 누락검사")
    a.add_argument("--strict", action="store_true")

    sub.add_parser("render-roles", help="중앙 EVT/RUN/FAIL/REQ 참조 기반 역할별 연구 capsule과 인계계약 생성")
    sub.add_parser("audit-roles", help="역할분류·capsule·handoff·중앙 ID·물리복제 금지 무결성 감사")

    cleanup_check = sub.add_parser(
        "cleanup-preflight",
        help="삭제 없이 연구기록·실행근거·Git 범위의 저장공간 정리 선행조건을 검사",
    )
    cleanup_check.add_argument("--scope-root", required=True)

    cleanup_dry = sub.add_parser(
        "cleanup-dry-run",
        help="삭제 없이 전 파일 자산목록·중복·보존등급·예상 회수량을 생성",
    )
    cleanup_dry.add_argument("--scope-root", required=True)

    cleanup_stream = sub.add_parser(
        "cleanup-dry-run-stream",
        help="내구 SQLite 체크포인트를 사용하는 bounded 전체 파일 dry-run",
    )
    cleanup_stream.add_argument("--scope-root", required=True)
    cleanup_stream.add_argument("--max-seconds", type=float, default=900.0)
    cleanup_stream.add_argument("--resume", action="store_true")

    cleanup_order = sub.add_parser(
        "cleanup-build-path-order",
        help="전체 scope 경로 순서를 1회 고정해 resume의 반복 tree traversal을 제거",
    )
    cleanup_order.add_argument("--scope-root", required=True)

    failed_scan = sub.add_parser(
        "record-cleanup-scan-failure",
        help="구 uncheckpointed scanner timeout을 zero-deletion 실패로그로 기록",
    )
    failed_scan.add_argument("--elapsed-seconds", type=float, required=True)
    failed_scan.add_argument("--process-id", type=int, required=True)

    sub.add_parser(
        "audit-cleanup-dry-run",
        help="dry-run inventory completeness and zero-deletion guarantees을 독립 재검증",
    )

    allp = sub.add_parser("all", help="발견부터 문서생성·누락감사까지 전체 파이프라인")
    allp.add_argument("--transcript", action="append", default=[])
    allp.add_argument("--copy-raw", action="store_true")
    allp.add_argument("--select-all", action="store_true")
    allp.add_argument("--scope-root", action="append", default=[])
    allp.add_argument("--include-all-sessions", action="store_true")
    allp.add_argument("--codex-command", default="codex")
    allp.add_argument("--model", default=None)
    allp.add_argument("--timeout", type=int, default=1800)
    allp.add_argument("--overwrite", action="store_true")
    allp.add_argument("--strict", action="store_true")
    allp.add_argument("--no-backup", action="store_true")
    allp.add_argument("--skip-double-review", action="store_true", help="독립 2차 분류감사를 생략. 완전복구에는 권장하지 않음")

    sub.add_parser("checkpoint", help="SessionEnd hook용 경량 세션 위치 체크포인트")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = _root(args.project_root)
    root.mkdir(parents=True, exist_ok=True)
    try:
        if args.command == "doctor":
            result = doctor(root, args.codex_home)
        elif args.command == "discover":
            result = discover_sources(root, explicit_codex_home=args.codex_home, extra_transcripts=args.transcript, copy_raw=args.copy_raw, select_all=args.select_all, scope_roots=args.scope_root)
        elif args.command == "select-sources":
            result = select_sources(root, source_ids=args.source_id, session_ids=args.session_id, select_all=args.all, clear=args.clear)
        elif args.command == "extract":
            result = extract_all(root, include_all_sessions=args.include_all_sessions, max_text_chars=args.max_text_chars)
        elif args.command == "extract-incremental":
            result = incremental_extract_active_source(root)
        elif args.command == "scan-project":
            result = scan_project(root)
        elif args.command == "prepare-batches":
            result = prepare_batches(root, max_events=args.max_events, max_chars=args.max_chars, include_non_project=args.include_non_project)
        elif args.command == "prepare-batches-incremental":
            result = prepare_incremental_batches(root)
        elif args.command == "classify":
            result = classify_batches(root, codex_command=args.codex_command, model=args.model, timeout=args.timeout, overwrite=args.overwrite)
        elif args.command == "review-classifications":
            result = review_classifications(root, codex_command=args.codex_command, model=args.model, timeout=args.timeout, overwrite=args.overwrite)
        elif args.command == "assign-roles":
            result = assign_roles(root)
        elif args.command == "detect-conflicts":
            result = detect_conflicts(root)
        elif args.command == "review-conflicts":
            result = review_conflicts(root, codex_command=args.codex_command, model=args.model, timeout=args.timeout)
        elif args.command == "render":
            result = {
                "central": render_research_docs(root, backup_existing=not args.no_backup),
                "roles": render_role_views(root),
            }
        elif args.command == "audit":
            result = audit_recovery(root, strict=args.strict)
        elif args.command == "render-roles":
            result = render_role_views(root)
        elif args.command == "audit-roles":
            result = audit_role_recovery(root)
        elif args.command == "cleanup-preflight":
            result = cleanup_preflight(root, _root(args.scope_root))
        elif args.command == "cleanup-dry-run":
            result = build_cleanup_dry_run(root, _root(args.scope_root))
        elif args.command == "cleanup-dry-run-stream":
            result = run_streaming_cleanup_dry_run(
                root, _root(args.scope_root), max_seconds=args.max_seconds, resume=args.resume
            )
        elif args.command == "cleanup-build-path-order":
            result = build_cleanup_path_order(root, _root(args.scope_root))
        elif args.command == "record-cleanup-scan-failure":
            result = record_failed_uncheckpointed_scan(
                root, elapsed_seconds=args.elapsed_seconds, process_id=args.process_id
            )
        elif args.command == "audit-cleanup-dry-run":
            result = audit_cleanup_dry_run(root)
        elif args.command == "checkpoint":
            result = fast_checkpoint(root, explicit_codex_home=args.codex_home)
        elif args.command == "all":
            stages: dict[str, Any] = {}
            stages["doctor"] = doctor(root, args.codex_home)
            stages["discover"] = discover_sources(root, explicit_codex_home=args.codex_home, extra_transcripts=args.transcript, copy_raw=args.copy_raw, select_all=args.select_all, scope_roots=args.scope_root)
            selected = stages["discover"].get("selected_count", 0)
            if not selected and not args.include_all_sessions:
                raise RuntimeError(
                    "프로젝트 경로와 일치하는 session이 자동 선택되지 않았습니다. "
                    "discover 후 select-sources --session-id <ID> 또는 all --select-all을 사용하십시오."
                )
            stages["extract"] = extract_all(root, include_all_sessions=args.include_all_sessions)
            stages["scan_project"] = scan_project(root)
            stages["prepare_batches"] = prepare_batches(root)
            stages["classify"] = classify_batches(root, codex_command=args.codex_command, model=args.model, timeout=args.timeout, overwrite=args.overwrite)
            if not args.skip_double_review:
                stages["classification_review"] = review_classifications(root, codex_command=args.codex_command, model=args.model, timeout=args.timeout, overwrite=args.overwrite)
            stages["role_assignment"] = assign_roles(root)
            stages["conflicts_initial"] = detect_conflicts(root)
            if stages["conflicts_initial"].get("unresolved_count", 0):
                stages["conflict_review"] = review_conflicts(root, codex_command=args.codex_command, model=args.model, timeout=args.timeout)
                stages["conflicts_final"] = detect_conflicts(root)
            stages["render"] = render_research_docs(root, backup_existing=not args.no_backup)
            stages["role_render"] = render_role_views(root)
            stages["audit"] = audit_recovery(root, strict=args.strict)
            result = {"status": stages["audit"]["status"], "stages": stages}
            json_dump(Paths(root).recovery / "감사결과" / "전체복구_실행보고서.json", result)
        else:
            parser.error(f"지원하지 않는 명령: {args.command}")
            return 2
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if isinstance(result, dict) and result.get("status") == "FAIL":
        return 2
    return 0
