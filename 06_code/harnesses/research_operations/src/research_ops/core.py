from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any


OPS_DIR = "00_research_ops"
TASK_STATES = (
    "PREREGISTERED",
    "READ_ACKNOWLEDGED",
    "PREFLIGHT_PASS",
    "RUNNING",
    "VERIFYING",
    "COMPLETE",
    "BLOCKED",
    "FAILED",
)
PUBLIC_EVENT_CATEGORIES = (
    "USER_INSTRUCTION",
    "REQUIREMENT",
    "METHOD",
    "EVIDENCE",
    "IMPLEMENTATION",
    "EXECUTION",
    "RESULT",
    "FAILURE",
    "DECISION",
    "BLOCKER",
    "COLLABORATION",
    "HANDOFF",
    "EXCLUSION",
)
PRIVATE_REASONING_KEYS = {
    "chain_of_thought",
    "hidden_reasoning",
    "private_reasoning",
    "internal_monologue",
}
V7_GATE_ORDER = tuple(f"G{index:02d}" for index in range(12))
RESEARCH_SYSTEM_BINDING_PATHS = ("00_research_ops/contracts/RECORD_STRUCTURE_BINDING_V2.json", "00_research_ops/contracts/RECORD_STRUCTURE_BINDING_V1.json")
V7_GATE_CATALOG_PATH = "00_research_ops/contracts/GATE_CATALOG_V7.json"
V7_ARCHIVE_REVIEW_PATH = "00_research_ops/evidence/V7_ARCHIVE_REVIEW.json"


class OpsError(RuntimeError):
    """Fail-closed research operations error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise OpsError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json_bytes(data: bytes, *, label: str) -> Any:
    if not data or data.startswith(b"\xef\xbb\xbf") or b"\x00" in data:
        raise OpsError(f"invalid strict JSON bytes: {label}")
    try:
        text = data.decode("utf-8", errors="strict")
        return json.loads(text, object_pairs_hook=_pairs_no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpsError(f"invalid strict JSON: {label}: {exc}") from exc


def load_json(path: Path) -> Any:
    return strict_json_bytes(read_ordinary_bytes(path, label=str(path)), label=str(path))


def read_ordinary_bytes(path: Path, *, label: str) -> bytes:
    if not path.exists() or not path.is_file() or path.is_symlink():
        raise OpsError(f"required ordinary file is missing or unsafe: {label}")
    return path.read_bytes()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_workspace_path(project_root: Path, relative_path: str) -> Path:
    if type(relative_path) is not str or not relative_path or "\x00" in relative_path:
        raise OpsError("path must be a non-empty string")
    profile_path = project_root / OPS_DIR / "PROJECT_PROFILE.json"
    workspace_root = project_root
    if profile_path.exists():
        profile = load_json(profile_path)
        workspace_root = (project_root / profile.get("workspace_root", ".")).resolve()
    target = (project_root / relative_path).resolve()
    if not is_within(target, workspace_root):
        raise OpsError(f"path escapes configured workspace root: {relative_path}")
    return target


def descriptor(project_root: Path, relative_path: str) -> dict[str, Any]:
    path = resolve_workspace_path(project_root, relative_path)
    data = read_ordinary_bytes(path, label=relative_path)
    return {
        "path": relative_path.replace("\\", "/"),
        "bytes": len(data),
        "sha256": sha256_bytes(data),
    }


def create_once_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        fd = os.open(os.fspath(path), flags, 0o600)
    except FileExistsError as exc:
        raise OpsError(f"create-once target already exists: {path}") from exc
    except PermissionError:
        if os.name != "nt" or path.exists():
            raise
        _windows_create_new_fallback(path, data)
        if read_ordinary_bytes(path, label=str(path)) != data:
            raise OpsError(f"create-once fallback postread mismatch: {path}")
        return
    try:
        view = memoryview(data)
        written = 0
        while written < len(view):
            count = os.write(fd, view[written:])
            if count <= 0:
                raise OpsError(f"write made no progress: {path}")
            written += count
        os.fsync(fd)
    finally:
        os.close(fd)
    if read_ordinary_bytes(path, label=str(path)) != data:
        raise OpsError(f"create-once postread mismatch: {path}")


def _windows_create_new_fallback(path: Path, data: bytes) -> None:
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not powershell.is_file():
        raise OpsError("canonical Windows PowerShell executable is unavailable")
    expected_sha = sha256_bytes(data)
    source_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="research_ops_", suffix=".bin", delete=False) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            source_path = Path(handle.name)
        script = r"""
$ErrorActionPreference='Stop'
$Target=$env:RESEARCH_OPS_TARGET
$Source=$env:RESEARCH_OPS_SOURCE
$ExpectedSha=$env:RESEARCH_OPS_SHA256
$ExpectedLength=[long]$env:RESEARCH_OPS_LENGTH
$sourceBytes=[System.IO.File]::ReadAllBytes($Source)
$sha=[System.Security.Cryptography.SHA256]::Create()
try { $sourceHash=([BitConverter]::ToString($sha.ComputeHash($sourceBytes)) -replace '-','').ToLowerInvariant() } finally { $sha.Dispose() }
if ($sourceBytes.LongLength -ne $ExpectedLength -or $sourceHash -ne $ExpectedSha) { throw 'source payload mismatch before create' }
$stream=[System.IO.FileStream]::new($Target,[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::ReadWrite,[System.IO.FileShare]::None)
try {
  $stream.Write($sourceBytes,0,$sourceBytes.Length)
  $stream.Flush($true)
  if ($stream.Length -ne $ExpectedLength) { throw 'same-handle length mismatch' }
  $stream.Position=0
  $reread=New-Object byte[] $sourceBytes.Length
  $offset=0
  while ($offset -lt $reread.Length) {
    $count=$stream.Read($reread,$offset,$reread.Length-$offset)
    if ($count -le 0) { throw 'same-handle read made no progress' }
    $offset += $count
  }
  $sha2=[System.Security.Cryptography.SHA256]::Create()
  try { $writtenHash=([BitConverter]::ToString($sha2.ComputeHash($reread)) -replace '-','').ToLowerInvariant() } finally { $sha2.Dispose() }
  if ($writtenHash -ne $ExpectedSha) { throw 'same-handle SHA mismatch' }
} finally { $stream.Dispose() }
"""
        child_env = os.environ.copy()
        child_env.update(
            {
                "RESEARCH_OPS_TARGET": str(path),
                "RESEARCH_OPS_SOURCE": str(source_path),
                "RESEARCH_OPS_SHA256": expected_sha,
                "RESEARCH_OPS_LENGTH": str(len(data)),
            }
        )
        proc = subprocess.run(
            [
                str(powershell),
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ],
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0:
            raise OpsError(
                "Windows create-new fallback failed; preserve any created target and do not retry: "
                + proc.stderr.decode("utf-8", errors="replace")[-1000:]
            )
    finally:
        if source_path is not None:
            try:
                source_path.unlink()
            except FileNotFoundError:
                pass


def create_once_json(path: Path, payload: Any) -> None:
    create_once_bytes(path, canonical_json_bytes(payload))


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    _reject_private_reasoning(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    data = read_ordinary_bytes(path, label=str(path))
    for line_no, raw in enumerate(data.splitlines(), 1):
        if not raw.strip():
            raise OpsError(f"blank JSONL line: {path}:{line_no}")
        row = strict_json_bytes(raw, label=f"{path}:{line_no}")
        if type(row) is not dict:
            raise OpsError(f"JSONL row must be object: {path}:{line_no}")
        rows.append(row)
    return rows


def _reject_private_reasoning(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in PRIVATE_REASONING_KEYS:
                raise OpsError(f"private reasoning field is forbidden: {key}")
            _reject_private_reasoning(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_private_reasoning(nested)


def ops_root(project_root: Path) -> Path:
    return project_root / OPS_DIR


def task_root(project_root: Path, task_id: str) -> Path:
    if not re.fullmatch(r"TASK-[0-9A-Z-]{8,64}", task_id):
        raise OpsError(f"invalid task id: {task_id}")
    return ops_root(project_root) / "tasks" / task_id


def default_policy() -> dict[str, Any]:
    return {
        "schema": "RESEARCH_OPERATIONS_POLICY_V1",
        "version": "1.0.0",
        "task_states": list(TASK_STATES),
        "public_event_categories": list(PUBLIC_EVENT_CATEGORIES),
        "required_task_sequence": [
            "TASK_PACKET",
            "READ_RECEIPT",
            "PREFLIGHT",
            "EXECUTION_OR_READONLY_WORK",
            "VERIFICATION",
            "HANDOFF_OR_FINAL_REPORT",
        ],
        "mandatory_read_paths": ["AGENTS.md", "00_research_ops/START_HERE.md"],
        "default_resource_budget": {
            "max_command_count": 20,
            "max_wallclock_seconds": 1800,
            "max_retries_per_failure_signature": 0,
        },
        "hard_rules": {
            "no_action_before_preflight": True,
            "no_transcript_command_execution": True,
            "no_claim_without_evidence": True,
            "no_unapproved_artifact_substitution": True,
            "no_identical_failure_retry_without_resolution": True,
            "no_private_reasoning_storage": True,
            "no_destructive_action_without_explicit_authority": True,
            "no_new_research_during_recovery": True,
        },
    }


def default_profile() -> dict[str, Any]:
    return {
        "schema": "RESEARCH_OPERATIONS_PROJECT_PROFILE_V1",
        "project_id": "UNCONFIGURED_PROJECT",
        "workspace_root": ".",
        "research_domain": "UNCONFIGURED",
        "mandatory_project_instructions": ["AGENTS.md", "00_research_ops/START_HERE.md"],
        "recovery_harness": "research_recovery.py",
        "roles_path": "00_research_ops/ROLE_REGISTRY.json",
        "approved_artifacts_path": "00_research_ops/approved_artifacts.jsonl",
        "failure_registry_path": "00_research_ops/failures/failure_registry.jsonl",
    }


def default_roles() -> dict[str, Any]:
    return {
        "schema": "RESEARCH_OPERATIONS_ROLE_REGISTRY_V1",
        "roles": [
            {"role_id": "R00", "name": "coordinator", "may_approve_own_work": False},
            {"role_id": "R01", "name": "domain_and_inputs", "may_approve_own_work": False},
            {"role_id": "R02", "name": "method_and_model", "may_approve_own_work": False},
            {"role_id": "R03", "name": "execution", "may_approve_own_work": False},
            {"role_id": "R04", "name": "verification", "may_approve_own_work": False},
            {"role_id": "R05", "name": "integration_and_products", "may_approve_own_work": False},
            {"role_id": "R06", "name": "independent_audit", "may_approve_own_work": False},
        ],
    }


def init_project(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    paths = {
        "policy": ops_root(root) / "POLICY.json",
        "profile": ops_root(root) / "PROJECT_PROFILE.json",
        "roles": ops_root(root) / "ROLE_REGISTRY.json",
    }
    for directory in (
        ops_root(root),
        ops_root(root) / "tasks",
        ops_root(root) / "failures",
        ops_root(root) / "decisions",
        ops_root(root) / "contexts",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    defaults = {
        "policy": default_policy(),
        "profile": default_profile(),
        "roles": default_roles(),
    }
    created: list[str] = []
    for key, path in paths.items():
        if not path.exists():
            create_once_json(path, defaults[key])
            created.append(str(path.relative_to(root)).replace("\\", "/"))
    start_path = ops_root(root) / "START_HERE.md"
    if not start_path.exists():
        create_once_bytes(
            start_path,
            (
                "# Research operations start\n\n"
                "Run `python -B research_ops.py --project-root . doctor`, freeze the exact user "
                "request in a task packet, acknowledge mandatory inputs, and require a passing "
                "preflight before research action. Record failures before retrying and create a "
                "context packet before handoff.\n"
            ).encode("utf-8"),
        )
        created.append(str(start_path.relative_to(root)).replace("\\", "/"))
    return {"status": "PASS", "created": created, "ops_root": str(ops_root(root))}


def load_policy(project_root: Path) -> dict[str, Any]:
    path = ops_root(project_root) / "POLICY.json"
    policy = load_json(path)
    if policy.get("schema") != "RESEARCH_OPERATIONS_POLICY_V1":
        raise OpsError("unsupported research operations policy")
    return policy


def load_profile(project_root: Path) -> dict[str, Any]:
    profile = load_json(ops_root(project_root) / "PROJECT_PROFILE.json")
    if profile.get("schema") not in {"RESEARCH_OPERATIONS_PROJECT_PROFILE_V1", "RESEARCH_OPERATIONS_PROJECT_PROFILE_V3"}:
        raise OpsError("unsupported project profile")
    return profile


def _new_task_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"TASK-{stamp}-{uuid.uuid4().hex[:8].upper()}"


def create_task(
    project_root: Path,
    *,
    request_file: str,
    objective: str,
    role_id: str,
    scope: str,
    method_fingerprint: str,
    allowed_actions: list[str],
    forbidden_actions: list[str],
    required_evidence: list[str],
    success_criteria: list[str],
    approved_artifact_ids: list[str],
    execution_authorized: bool,
    destructive_actions_authorized: bool = False,
) -> dict[str, Any]:
    load_policy(project_root)
    roles = load_json(ops_root(project_root) / "ROLE_REGISTRY.json")
    if role_id not in {row["role_id"] for row in roles["roles"]}:
        raise OpsError(f"unknown role: {role_id}")
    if not objective.strip() or not scope.strip() or not method_fingerprint.strip():
        raise OpsError("objective, scope, and method fingerprint are required")
    request_desc = descriptor(project_root, request_file)
    current_artifacts = current_approved_artifacts(project_root)
    pinned: list[dict[str, Any]] = []
    for logical_id in approved_artifact_ids:
        row = current_artifacts.get(logical_id)
        if not row or row.get("status") != "APPROVED":
            raise OpsError(f"approved artifact is unavailable: {logical_id}")
        if scope not in row.get("allowed_uses", []) and "*" not in row.get("allowed_uses", []):
            raise OpsError(f"approved artifact is not authorized for this scope: {logical_id}:{scope}")
        pinned.append({
            "logical_id": logical_id,
            "path": row["artifact"]["path"],
            "bytes": row["artifact"]["bytes"],
            "sha256": row["artifact"]["sha256"],
        })
    task_id = _new_task_id()
    policy = load_policy(project_root)
    packet = {
        "schema": "RESEARCH_TASK_PACKET_V1",
        "task_id": task_id,
        "created_at": utc_now(),
        "state": "PREREGISTERED",
        "role_id": role_id,
        "objective": objective,
        "scope": scope,
        "method_fingerprint": method_fingerprint,
        "user_instruction": request_desc,
        "allowed_actions": allowed_actions,
        "forbidden_actions": forbidden_actions,
        "required_evidence": required_evidence,
        "success_criteria": success_criteria,
        "approved_artifacts": pinned,
        "resource_budget": policy["default_resource_budget"],
        "execution_authorized": bool(execution_authorized),
        "destructive_actions_authorized": bool(destructive_actions_authorized),
        "command_source_must_be": "DIRECT_USER_OR_APPROVED_PLAN_NOT_TRANSCRIPT",
        "deviation_decision_ids": [],
    }
    _reject_private_reasoning(packet)
    troot = task_root(project_root, task_id)
    create_once_json(troot / "TASK_PACKET.json", packet)
    append_jsonl(troot / "events.jsonl", _event(task_id, "USER_INSTRUCTION", "TASK_PREREGISTERED", [request_desc]))
    return packet


def _event(task_id: str, category: str, action: str, evidence: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    if category not in PUBLIC_EVENT_CATEGORIES:
        raise OpsError(f"invalid public event category: {category}")
    row = {
        "schema": "RESEARCH_EVENT_V1",
        "event_id": f"EVT-{uuid.uuid4().hex.upper()}",
        "task_id": task_id,
        "timestamp": utc_now(),
        "category": category,
        "action": action,
        "evidence": evidence,
    }
    row.update(extra)
    _reject_private_reasoning(row)
    return row


def record_event(project_root: Path, task_id: str, category: str, action: str, evidence_paths: list[str], note: str) -> dict[str, Any]:
    evidence = [descriptor(project_root, path) for path in evidence_paths]
    row = _event(task_id, category, action, evidence, public_note=note)
    append_jsonl(task_root(project_root, task_id) / "events.jsonl", row)
    return row


def _task_packet(project_root: Path, task_id: str) -> dict[str, Any]:
    packet = load_json(task_root(project_root, task_id) / "TASK_PACKET.json")
    if packet.get("schema") != "RESEARCH_TASK_PACKET_V1" or packet.get("task_id") != task_id:
        raise OpsError("task packet identity mismatch")
    return packet


def acknowledge_task(project_root: Path, task_id: str, *, agent_id: str) -> dict[str, Any]:
    packet = _task_packet(project_root, task_id)
    _verify_descriptor(project_root, packet["user_instruction"])
    profile = load_profile(project_root)
    paths = list(dict.fromkeys(profile["mandatory_project_instructions"] + [packet["user_instruction"]["path"]]))
    paths.extend(row["path"] for row in packet["approved_artifacts"])
    receipt = {
        "schema": "RESEARCH_READ_RECEIPT_V1",
        "task_id": task_id,
        "created_at": utc_now(),
        "agent_id": agent_id,
        "instruction_precedence_acknowledged": True,
        "private_reasoning_will_not_be_recorded": True,
        "files": [descriptor(project_root, path) for path in dict.fromkeys(paths)],
    }
    create_once_json(task_root(project_root, task_id) / "READ_RECEIPT.json", receipt)
    append_jsonl(task_root(project_root, task_id) / "events.jsonl", _event(task_id, "EVIDENCE", "MANDATORY_READING_ACKNOWLEDGED", receipt["files"]))
    return receipt


def _verify_git_promotion_receipt(
    project_root: Path,
    *,
    receipt_path: str,
    artifact_descriptor: dict[str, Any],
    logical_id: str,
) -> dict[str, Any]:
    receipt = load_json(resolve_workspace_path(project_root, receipt_path))
    if receipt.get("schema") != "GIT_PROMOTION_RECEIPT_V1" or receipt.get("status") != "PASS":
        raise OpsError("approved artifact Git promotion receipt schema/status mismatch")
    artifacts = receipt.get("artifacts")
    if type(artifacts) is not list:
        raise OpsError("approved artifact Git promotion receipt artifacts are missing")
    if artifact_descriptor not in [
        {k: row.get(k) for k in ("path", "bytes", "sha256")}
        for row in artifacts if type(row) is dict
    ]:
        raise OpsError(f"Git promotion receipt does not bind exact artifact bytes: {logical_id}")
    commit_sha = receipt.get("commit_sha")
    tag = receipt.get("tag")
    if type(commit_sha) is not str or re.fullmatch(r"[0-9a-f]{40,64}", commit_sha) is None:
        raise OpsError("Git promotion receipt commit SHA is invalid")
    if type(tag) is not str or not tag:
        raise OpsError("Git promotion receipt tag is missing")
    repo_probe = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if repo_probe.returncode != 0:
        raise OpsError("approved artifact requires a live Git repository for promotion verification")
    repo = Path(repo_probe.stdout.strip()).resolve()
    exists = subprocess.run(
        ["git", "cat-file", "-e", f"{commit_sha}^{{commit}}"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if exists.returncode != 0:
        raise OpsError("Git promotion receipt commit does not exist")
    tag_target = subprocess.run(
        ["git", "rev-list", "-n", "1", tag],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if tag_target.returncode != 0 or tag_target.stdout.strip() != commit_sha:
        raise OpsError("Git promotion receipt tag does not point to the recorded commit")
    blob = subprocess.run(
        ["git", "show", f"{commit_sha}:{artifact_descriptor['path']}"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if blob.returncode != 0:
        raise OpsError("approved artifact bytes are absent from Git promotion commit")
    if len(blob.stdout) != artifact_descriptor["bytes"] or sha256_bytes(blob.stdout) != artifact_descriptor["sha256"]:
        raise OpsError("approved artifact bytes in Git promotion commit differ from live artifact")
    return {
        "path": receipt_path.replace("\\", "/"),
        "commit_sha": commit_sha,
        "tag": tag,
        "promotion_id": receipt.get("promotion_id"),
        "promotion_class": receipt.get("promotion_class"),
    }


def register_artifact(
    project_root: Path,
    *,
    logical_id: str,
    path: str,
    status: str,
    approved_by: str,
    approval_basis: str,
    allowed_uses: list[str],
    supersedes: str | None,
    git_promotion_receipt: str | None = None,
) -> dict[str, Any]:
    if status not in {"APPROVED", "SUPERSEDED", "QUARANTINED"}:
        raise OpsError("invalid artifact status")
    if status == "APPROVED" and (not approved_by.strip() or not approval_basis.strip()):
        raise OpsError("approved artifact requires approver and approval basis")
    artifact_descriptor = descriptor(project_root, path)
    policy = load_policy(project_root)
    git_binding = None
    if status == "APPROVED" and policy.get("hard_rules", {}).get("approved_artifact_requires_git_promotion_checkpoint", False):
        if not git_promotion_receipt:
            raise OpsError("APPROVED artifact requires a Git promotion receipt under current policy")
        git_binding = _verify_git_promotion_receipt(
            project_root,
            receipt_path=git_promotion_receipt,
            artifact_descriptor=artifact_descriptor,
            logical_id=logical_id,
        )
    row = {
        "schema": "APPROVED_ARTIFACT_EVENT_V2" if git_binding else "APPROVED_ARTIFACT_EVENT_V1",
        "registry_event_id": f"ART-{uuid.uuid4().hex.upper()}",
        "timestamp": utc_now(),
        "logical_id": logical_id,
        "status": status,
        "artifact": artifact_descriptor,
        "approved_by": approved_by,
        "approval_basis": approval_basis,
        "allowed_uses": allowed_uses,
        "supersedes": supersedes,
        "git_promotion": git_binding,
    }
    append_jsonl(ops_root(project_root) / "approved_artifacts.jsonl", row)
    return row


def current_approved_artifacts(project_root: Path) -> dict[str, dict[str, Any]]:
    rows = read_jsonl(ops_root(project_root) / "approved_artifacts.jsonl")
    current: dict[str, dict[str, Any]] = {}
    for row in rows:
        current[row["logical_id"]] = row
    return current


def _verify_descriptor(project_root: Path, expected: dict[str, Any]) -> None:
    live = descriptor(project_root, expected["path"])
    if live != {"path": expected["path"], "bytes": expected["bytes"], "sha256": expected["sha256"]}:
        raise OpsError(f"live artifact differs from frozen descriptor: {expected['path']}")


def open_failures(project_root: Path) -> list[dict[str, Any]]:
    path = ops_root(project_root) / "failures" / "failure_registry.jsonl"
    rows = read_jsonl(path)
    resolved = {row["failure_id"] for row in rows if row.get("record_type") == "RESOLUTION"}
    return [row for row in rows if row.get("record_type") == "FAILURE" and row["failure_id"] not in resolved]


def preflight(project_root: Path, task_id: str, *, persist: bool = True) -> dict[str, Any]:
    packet = _task_packet(project_root, task_id)
    receipt = load_json(task_root(project_root, task_id) / "READ_RECEIPT.json")
    for row in receipt["files"]:
        _verify_descriptor(project_root, row)
    current = current_approved_artifacts(project_root)
    for pinned in packet["approved_artifacts"]:
        row = current.get(pinned["logical_id"])
        if not row or row["status"] != "APPROVED":
            raise OpsError(f"pinned artifact no longer approved: {pinned['logical_id']}")
        if row["artifact"] != {k: pinned[k] for k in ("path", "bytes", "sha256")}:
            raise OpsError(f"approved artifact substitution detected: {pinned['logical_id']}")
        if packet["scope"] not in row.get("allowed_uses", []) and "*" not in row.get("allowed_uses", []):
            raise OpsError(f"artifact use is outside its approved scope: {pinned['logical_id']}")
        _verify_descriptor(project_root, row["artifact"])
    configuration_sha = sha256_bytes(canonical_json_bytes({
        "scope": packet["scope"],
        "method_fingerprint": packet["method_fingerprint"],
        "approved_artifacts": packet["approved_artifacts"],
    }))
    blockers = []
    for failure in open_failures(project_root):
        same_scope = failure.get("scope") in {"*", packet["scope"]}
        same_config = failure.get("configuration_sha256") in {"*", configuration_sha}
        if same_scope and same_config and failure.get("recurrence_action") == "BLOCK_IDENTICAL_RETRY":
            blockers.append(failure["failure_id"])
    if blockers:
        raise OpsError(f"unresolved recurrence blockers: {blockers}")
    result = {
        "schema": "RESEARCH_PREFLIGHT_V1",
        "task_id": task_id,
        "created_at": utc_now(),
        "status": "PASS",
        "configuration_sha256": configuration_sha,
        "mandatory_read_count": len(receipt["files"]),
        "approved_artifact_count": len(packet["approved_artifacts"]),
        "unresolved_recurrence_blockers": [],
        "execution_authorized": packet["execution_authorized"],
        "destructive_actions_authorized": packet["destructive_actions_authorized"],
    }
    if persist:
        create_once_json(task_root(project_root, task_id) / "PREFLIGHT.json", result)
        append_jsonl(task_root(project_root, task_id) / "events.jsonl", _event(task_id, "EVIDENCE", "PREFLIGHT_PASS", []))
    else:
        original = load_json(task_root(project_root, task_id) / "PREFLIGHT.json")
        if any(original.get(key) != value for key, value in result.items() if key != 'created_at'):
            raise OpsError('Existing preflight no longer matches current task evidence')
    return result


def record_failure(
    project_root: Path,
    *,
    task_id: str,
    signature: str,
    summary: str,
    evidence_paths: list[str],
    correction_required: str,
    scope: str | None = None,
    configuration_sha256: str | None = None,
) -> dict[str, Any]:
    packet = _task_packet(project_root, task_id)
    preflight_path = task_root(project_root, task_id) / "PREFLIGHT.json"
    config = configuration_sha256 or (load_json(preflight_path)["configuration_sha256"] if preflight_path.exists() else "*")
    previous = [row for row in open_failures(project_root) if row.get("signature") == signature and row.get("configuration_sha256") == config]
    row = {
        "schema": "RESEARCH_FAILURE_EVENT_V1",
        "record_type": "FAILURE",
        "failure_id": f"FAIL-{uuid.uuid4().hex.upper()}",
        "timestamp": utc_now(),
        "task_id": task_id,
        "signature": signature,
        "summary": summary,
        "scope": scope or packet["scope"],
        "configuration_sha256": config,
        "evidence": [descriptor(project_root, path) for path in evidence_paths],
        "correction_required": correction_required,
        "recurrence_action": "BLOCK_IDENTICAL_RETRY",
        "repeated_of": previous[-1]["failure_id"] if previous else None,
        "status": "RECURRENCE_BLOCKED" if previous else "OPEN",
    }
    append_jsonl(ops_root(project_root) / "failures" / "failure_registry.jsonl", row)
    append_jsonl(task_root(project_root, task_id) / "events.jsonl", _event(task_id, "FAILURE", signature, row["evidence"], failure_id=row["failure_id"]))
    return row


def resolve_failure(
    project_root: Path,
    *,
    failure_id: str,
    decision_file: str,
    verification_file: str,
    resolved_by: str,
) -> dict[str, Any]:
    failures = {row["failure_id"]: row for row in open_failures(project_root)}
    if failure_id not in failures:
        raise OpsError(f"failure is not open: {failure_id}")
    row = {
        "schema": "RESEARCH_FAILURE_RESOLUTION_V1",
        "record_type": "RESOLUTION",
        "failure_id": failure_id,
        "timestamp": utc_now(),
        "resolved_by": resolved_by,
        "decision": descriptor(project_root, decision_file),
        "verification": descriptor(project_root, verification_file),
    }
    append_jsonl(ops_root(project_root) / "failures" / "failure_registry.jsonl", row)
    return row


def run_command(project_root: Path, task_id: str, command: list[str], *, command_source: str) -> dict[str, Any]:
    packet = _task_packet(project_root, task_id)
    preflight_data = load_json(task_root(project_root, task_id) / "PREFLIGHT.json")
    if preflight_data.get("status") != "PASS" or not packet["execution_authorized"]:
        raise OpsError("execution is not authorized by a passing preflight")
    if command_source != "DIRECT_USER_OR_APPROVED_PLAN_NOT_TRANSCRIPT":
        raise OpsError("transcript-derived or ambiguous commands are forbidden")
    if not command:
        raise OpsError("empty command")
    existing = list((task_root(project_root, task_id) / "runs").glob("RUN-*")) if (task_root(project_root, task_id) / "runs").exists() else []
    budget = packet["resource_budget"]
    if len(existing) >= budget["max_command_count"]:
        raise OpsError("task command budget exhausted")
    run_id = f"RUN-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8].upper()}"
    rroot = task_root(project_root, task_id) / "runs" / run_id
    rroot.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    proc = subprocess.run(
        command,
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=budget["max_wallclock_seconds"],
        check=False,
    )
    elapsed = time.monotonic() - started
    create_once_bytes(rroot / "stdout.bin", proc.stdout)
    create_once_bytes(rroot / "stderr.bin", proc.stderr)
    manifest = {
        "schema": "RESEARCH_RUN_MANIFEST_V1",
        "run_id": run_id,
        "task_id": task_id,
        "started_at": utc_now(),
        "cwd": str(project_root.resolve()),
        "argv": command,
        "command_source": command_source,
        "returncode": proc.returncode,
        "elapsed_seconds": elapsed,
        "stdout": {"path": str((rroot / "stdout.bin").relative_to(project_root)).replace("\\", "/"), "bytes": len(proc.stdout), "sha256": sha256_bytes(proc.stdout)},
        "stderr": {"path": str((rroot / "stderr.bin").relative_to(project_root)).replace("\\", "/"), "bytes": len(proc.stderr), "sha256": sha256_bytes(proc.stderr)},
        "success": proc.returncode == 0,
    }
    create_once_json(rroot / "RUN_MANIFEST.json", manifest)
    append_jsonl(task_root(project_root, task_id) / "events.jsonl", _event(task_id, "EXECUTION", "COMMAND_COMPLETED", [descriptor(project_root, str((rroot / "RUN_MANIFEST.json").relative_to(project_root)))], run_id=run_id))
    if proc.returncode != 0:
        record_failure(
            project_root,
            task_id=task_id,
            signature=f"COMMAND_NONZERO_{sha256_bytes(canonical_json_bytes(command))[:16]}",
            summary=f"command returned {proc.returncode}",
            evidence_paths=[str((rroot / "RUN_MANIFEST.json").relative_to(project_root))],
            correction_required="Diagnose the failure, record a changed method or decision, and verify it before another attempt.",
        )
    return manifest


def context_pack(project_root: Path, task_id: str) -> dict[str, Any]:
    troot = task_root(project_root, task_id)
    packet = _task_packet(project_root, task_id)
    handoffs = sorted(troot.glob("HANDOFF-*.json"))
    current_status = next(row for row in status(project_root)["tasks"] if row["task_id"] == task_id)
    profile = load_profile(project_root)
    continuation_paths = list(dict.fromkeys(profile["mandatory_project_instructions"] + [packet["user_instruction"]["path"]]))
    result = {
        "schema": "RESEARCH_CONTEXT_PACKET_V1",
        "created_at": utc_now(),
        "derived_state": current_status["derived_state"],
        "task": packet,
        "read_receipt": load_json(troot / "READ_RECEIPT.json") if (troot / "READ_RECEIPT.json").exists() else None,
        "preflight": load_json(troot / "PREFLIGHT.json") if (troot / "PREFLIGHT.json").exists() else None,
        "continuation_live_files": [descriptor(project_root, path) for path in continuation_paths],
        "final_report": load_json(troot / "FINAL_REPORT.json") if (troot / "FINAL_REPORT.json").exists() else None,
        "latest_handoff": load_json(handoffs[-1]) if handoffs else None,
        "open_failures": [row for row in open_failures(project_root) if row.get("task_id") == task_id or row.get("scope") in {"*", packet["scope"]}],
        "recent_public_events": read_jsonl(troot / "events.jsonl")[-25:],
        "startup_instruction": "Read AGENTS.md, invoke $research-operations-continuity, run doctor/status, verify this packet's hashes, then continue only the next safe task. Do not infer missing evidence.",
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = ops_root(project_root) / "contexts" / f"{task_id}_{stamp}.json"
    create_once_json(path, result)
    result["path"] = str(path.relative_to(project_root)).replace("\\", "/")
    result["sha256"] = sha256_file(path)
    return result


def status(project_root: Path) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []
    for troot in sorted((ops_root(project_root) / "tasks").glob("TASK-*")):
        if not troot.is_dir() or (troot / "QUARANTINE.json").exists():
            continue
        packet = load_json(troot / "TASK_PACKET.json")
        if (troot / "FINAL_REPORT.json").exists():
            state = "COMPLETE"
        elif [row for row in open_failures(project_root) if row.get("task_id") == troot.name]:
            state = "BLOCKED"
        elif (troot / "PREFLIGHT.json").exists():
            state = "PREFLIGHT_PASS"
        elif (troot / "READ_RECEIPT.json").exists():
            state = "READ_ACKNOWLEDGED"
        else:
            state = "PREREGISTERED"
        tasks.append({
            "task_id": troot.name,
            "objective": packet["objective"],
            "scope": packet["scope"],
            "role_id": packet["role_id"],
            "derived_state": state,
        })
    return {
        "schema": "RESEARCH_OPERATIONS_STATUS_V1",
        "created_at": utc_now(),
        "tasks": tasks,
        "open_failures": open_failures(project_root),
    }


def handoff(project_root: Path, task_id: str, *, next_action: str, blocker: str, evidence_paths: list[str]) -> dict[str, Any]:
    row = {
        "schema": "RESEARCH_HANDOFF_V1",
        "handoff_id": f"HANDOFF-{uuid.uuid4().hex.upper()}",
        "task_id": task_id,
        "created_at": utc_now(),
        "next_safe_action": next_action,
        "blocker": blocker,
        "evidence": [descriptor(project_root, path) for path in evidence_paths],
        "completion_claimed": False,
    }
    create_once_json(task_root(project_root, task_id) / f"{row['handoff_id']}.json", row)
    append_jsonl(task_root(project_root, task_id) / "events.jsonl", _event(task_id, "HANDOFF", "HANDOFF_CREATED", row["evidence"], handoff_id=row["handoff_id"]))
    return row


def close_task(
    project_root: Path,
    task_id: str,
    *,
    verification_file: str,
    independent_review_file: str,
    claims: list[str],
    evidence_paths: list[str],
) -> dict[str, Any]:
    packet = _task_packet(project_root, task_id)
    if [row for row in open_failures(project_root) if row.get("task_id") == task_id]:
        raise OpsError("task has unresolved failures")
    verification = descriptor(project_root, verification_file)
    independent = descriptor(project_root, independent_review_file)
    verification_payload = load_json(resolve_workspace_path(project_root, verification["path"]))
    independent_payload = load_json(resolve_workspace_path(project_root, independent["path"]))
    closing_contracts = (
        (
            verification,
            verification_payload,
            "RESEARCH_AUTOMATED_VERIFICATION_V1",
            "R04",
        ),
        (
            independent,
            independent_payload,
            "RESEARCH_INDEPENDENT_REVIEW_V1",
            "R06",
        ),
    )
    roles = load_json(ops_root(project_root) / "ROLE_REGISTRY.json")
    role_rows = {row["role_id"]: row for row in roles.get("roles", [])}
    for expected, payload, schema, role_id in closing_contracts:
        if payload.get("schema") != schema:
            raise OpsError(f"closing evidence schema differs: {expected['path']}")
        if payload.get("task_id") != task_id:
            raise OpsError(f"closing evidence task binding differs: {expected['path']}")
        if payload.get("role_id") != role_id:
            raise OpsError(f"closing evidence role differs: {expected['path']}")
        if role_id == packet.get("role_id"):
            raise OpsError(f"task author cannot approve own work: {expected['path']}")
        if role_rows.get(role_id, {}).get("may_approve_own_work") is not False:
            raise OpsError(f"closing evidence role is not fail-closed: {expected['path']}")
        if payload.get("status") not in {"PASS", "PASS_BLOCKER_0"}:
            raise OpsError(f"closing evidence is not PASS: {expected['path']}")
    evidence = [descriptor(project_root, path) for path in evidence_paths]
    if claims and not evidence:
        raise OpsError("claims require direct evidence")
    report = {
        "schema": "RESEARCH_FINAL_REPORT_V1",
        "task_id": task_id,
        "created_at": utc_now(),
        "status": "COMPLETE",
        "claims": claims,
        "evidence": evidence,
        "verification": verification,
        "independent_review": independent,
        "limitations": [],
    }
    create_once_json(task_root(project_root, task_id) / "FINAL_REPORT.json", report)
    append_jsonl(task_root(project_root, task_id) / "events.jsonl", _event(task_id, "RESULT", "TASK_COMPLETE", evidence))
    return report


def strict_audit(project_root: Path) -> dict[str, Any]:
    policy = load_policy(project_root)
    profile = load_profile(project_root)
    errors: list[str] = []
    task_count = 0
    quarantined_partial_task_count = 0
    for troot in sorted((ops_root(project_root) / "tasks").glob("TASK-*")):
        if not troot.is_dir():
            continue
        if (troot / "QUARANTINE.json").exists():
            quarantine = load_json(troot / "QUARANTINE.json")
            if quarantine.get("status") != "QUARANTINED_PARTIAL_PUBLICATION":
                errors.append(f"{troot.name}: invalid quarantine status")
            quarantined_partial_task_count += 1
            continue
        task_count += 1
        try:
            packet = load_json(troot / "TASK_PACKET.json")
            _reject_private_reasoning(packet)
            _verify_descriptor(project_root, packet["user_instruction"])
            events = read_jsonl(troot / "events.jsonl")
            if not events or events[0].get("action") != "TASK_PREREGISTERED":
                errors.append(f"{troot.name}: missing preregistration event")
            if (troot / "PREFLIGHT.json").exists() and not (troot / "READ_RECEIPT.json").exists():
                errors.append(f"{troot.name}: preflight exists without read receipt")
            if (troot / "FINAL_REPORT.json").exists():
                final = load_json(troot / "FINAL_REPORT.json")
                if final.get("claims") and not final.get("evidence"):
                    errors.append(f"{troot.name}: unsupported claims")
            for event in events:
                if event.get("category") not in PUBLIC_EVENT_CATEGORIES:
                    errors.append(f"{troot.name}: invalid event category")
                _reject_private_reasoning(event)
                for evidence in event.get("evidence", []):
                    if set(evidence) != {"path", "bytes", "sha256"}:
                        errors.append(f"{troot.name}: malformed historical evidence descriptor")
                    elif type(evidence["bytes"]) is not int or evidence["bytes"] < 0:
                        errors.append(f"{troot.name}: invalid historical evidence byte count")
                    elif not re.fullmatch(r"[0-9a-f]{64}", evidence["sha256"]):
                        errors.append(f"{troot.name}: invalid historical evidence SHA-256")
        except Exception as exc:  # audit reports all task-local failures
            errors.append(f"{troot.name}: {exc}")
    failure_rows = read_jsonl(ops_root(project_root) / "failures" / "failure_registry.jsonl")
    active_by_key: dict[tuple[str, str], set[str]] = {}
    failure_keys: dict[str, tuple[str, str]] = {}
    for row in failure_rows:
        if row.get("record_type") == "FAILURE":
            key = (row.get("signature", ""), row.get("configuration_sha256", ""))
            active_ids = active_by_key.setdefault(key, set())
            if active_ids and row.get("status") != "RECURRENCE_BLOCKED":
                errors.append(f"repeated failure was not recurrence-blocked: {key[0]}")
            failure_id = row.get("failure_id", "")
            active_ids.add(failure_id)
            failure_keys[failure_id] = key
        elif row.get("record_type") == "RESOLUTION":
            failure_id = row.get("failure_id", "")
            key = failure_keys.get(failure_id)
            if key is not None:
                active_by_key.get(key, set()).discard(failure_id)
    result = {
        "schema": "RESEARCH_OPERATIONS_STRICT_AUDIT_V1",
        "created_at": utc_now(),
        "status": "PASS" if not errors else "FAIL",
        "task_count": task_count,
        "quarantined_partial_task_count": quarantined_partial_task_count,
        "failure_event_count": sum(row.get("record_type") == "FAILURE" for row in failure_rows),
        "open_failure_count": len(open_failures(project_root)),
        "policy_rule_count": len(policy["hard_rules"]),
        "project_id": profile["project_id"],
        "error_count": len(errors),
        "errors": errors,
    }
    return result


def audit_zip_archive(archive_path: Path, *, expected_sha256: str | None = None) -> dict[str, Any]:
    archive_path = archive_path.resolve()
    errors: list[str] = []
    entries: list[dict[str, Any]] = []
    if not archive_path.exists() or not archive_path.is_file() or archive_path.is_symlink():
        raise OpsError("archive is missing or is not an ordinary file")
    archive_bytes = archive_path.stat().st_size
    archive_sha256 = sha256_file(archive_path)
    if expected_sha256 is not None and archive_sha256 != expected_sha256:
        errors.append("archive SHA-256 differs from the expected value")
    seen: set[str] = set()
    total_uncompressed = 0
    try:
        with zipfile.ZipFile(archive_path) as bundle:
            for info in bundle.infolist():
                name = info.filename
                parts = PurePosixPath(name).parts
                mode = info.external_attr >> 16
                is_symlink = stat.S_IFMT(mode) == stat.S_IFLNK
                unsafe = (
                    not name
                    or "\x00" in name
                    or name.startswith(("/", "\\"))
                    or "\\" in name
                    or ":" in name
                    or ".." in parts
                    or is_symlink
                    or name in seen
                )
                if unsafe:
                    errors.append(f"unsafe or duplicate archive member: {name}")
                seen.add(name)
                total_uncompressed += info.file_size
                digest: str | None = None
                if not info.is_dir():
                    h = hashlib.sha256()
                    with bundle.open(info, "r") as source:
                        while chunk := source.read(1024 * 1024):
                            h.update(chunk)
                    digest = h.hexdigest()
                entries.append(
                    {
                        "path": name,
                        "bytes": info.file_size,
                        "compressed_bytes": info.compress_size,
                        "sha256": digest,
                        "directory": info.is_dir(),
                        "symlink": is_symlink,
                    }
                )
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        errors.append(f"invalid ZIP archive: {exc}")
    if archive_bytes > 50 * 1024 * 1024:
        errors.append("archive exceeds the 50 MiB review limit")
    if total_uncompressed > 200 * 1024 * 1024:
        errors.append("archive exceeds the 200 MiB uncompressed review limit")
    return {
        "schema": "RESEARCH_ARCHIVE_SAFETY_AUDIT_V1",
        "created_at": utc_now(),
        "status": "PASS" if not errors else "FAIL",
        "archive": {
            "path": str(archive_path),
            "bytes": archive_bytes,
            "sha256": archive_sha256,
        },
        "entry_count": len(entries),
        "file_count": sum(not row["directory"] for row in entries),
        "total_uncompressed_bytes": total_uncompressed,
        "error_count": len(errors),
        "errors": errors,
        "entries": entries,
        "archive_extracted": False,
        "archive_code_executed": False,
    }


def research_system_audit(project_root: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(check_id: str, condition: bool, detail: str) -> None:
        checks.append({"check_id": check_id, "status": "PASS" if condition else "FAIL", "detail": detail})

    try:
        profile = load_profile(project_root)
    except Exception:
        profile = {}
    new_project_empty = profile.get("record_system_mode") in {"NEW_PROJECT_EMPTY", "NEW_PROJECT_EMPTY_V3"}

    binding_path = next((project_root / rel for rel in RESEARCH_SYSTEM_BINDING_PATHS if (project_root / rel).is_file()), None)
    try:
        if binding_path is None:
            raise OpsError("no record binding V2/V1 file found")
        binding = load_json(binding_path)
    except Exception as exc:
        binding = {}
        check("SYS-001", False, f"record binding unavailable: {exc}")
    else:
        check(
            "SYS-001",
            binding.get("schema") in {"RESEARCH_OPERATING_SYSTEM_RECORD_BINDING_V1", "RESEARCH_OPERATING_SYSTEM_RECORD_BINDING_V2"},
            f"record binding schema; path={binding_path.relative_to(project_root).as_posix()}",
        )

    try:
        gate_catalog = load_json(project_root / V7_GATE_CATALOG_PATH)
    except Exception as exc:
        gate_catalog = {}
        check("SYS-002", False, f"gate catalog unavailable: {exc}")
    else:
        gate_order = gate_catalog.get("gate_order")
        gate_ids = [row.get("gate_id") for row in gate_catalog.get("gates", [])]
        check("SYS-002", gate_order == list(V7_GATE_ORDER) and gate_ids == list(V7_GATE_ORDER), "G00-G11 exact ordered gate catalog")
        check("SYS-003", gate_catalog.get("generic_gate_cannot_supply_domain_thresholds") is True, "generic gates cannot self-author scientific thresholds")
        check("SYS-004", gate_catalog.get("domain_profile_required_for_scientific_run") is True, "scientific runs require a separately approved domain profile")

    required_paths = binding.get("required_record_paths", []) if isinstance(binding, dict) else []
    if new_project_empty:
        required_paths = [
            row
            for row in required_paths
            if not (
                isinstance(row, dict)
                and row.get("path") == "08_검증/reports/연구기록복구/연구기록_복구감사.json"
            )
        ]
    missing_paths: list[str] = []
    for row in required_paths:
        rel = row.get("path") if isinstance(row, dict) else None
        kind = row.get("kind") if isinstance(row, dict) else None
        if type(rel) is not str:
            missing_paths.append(str(rel))
            continue
        target = project_root / rel
        okay = target.is_dir() if kind == "directory" else target.is_file() and not target.is_symlink()
        if not okay:
            missing_paths.append(rel)
    check("SYS-005", bool(required_paths) and not missing_paths, f"record structure paths; missing={missing_paths}")

    if new_project_empty:
        initialization_path = profile.get("new_project_initialization_evidence", "")
        try:
            initialization = load_json(project_root / initialization_path)
        except Exception as exc:
            initialization = {}
            check("SYS-006", False, f"new-project initialization evidence unavailable: {exc}")
        else:
            initialization_ok = (
                initialization.get("schema") == "RESEARCH_NEW_PROJECT_INITIALIZATION_V1"
                and initialization.get("status") == "PASS"
                and initialization.get("record_system_mode") in {"NEW_PROJECT_EMPTY", "NEW_PROJECT_EMPTY_V3"}
                and initialization.get("historical_recovery_claimed") is False
                and initialization.get("scientific_validation_claimed") is False
                and initialization.get("record_store_initialized") is True
            )
            check("SYS-006", initialization_ok, "new-project empty record store initialized without recovery or scientific claims")
        recovery = {"status": "NOT_APPLICABLE_NEW_PROJECT", "counts": {}}

        lineage_path = profile.get("portable_package_lineage_evidence", "")
        try:
            archive_review = load_json(project_root / lineage_path)
        except Exception as exc:
            archive_review = {}
            check("SYS-007", False, f"portable package lineage unavailable: {exc}")
        else:
            review_ok = (
                archive_review.get("schema") == "RESEARCH_PORTABLE_PACKAGE_LINEAGE_V1"
                and archive_review.get("status") == "PASS"
                and bool(archive_review.get("package_id"))
                and archive_review.get("project_specific_data_included") is False
                and archive_review.get("historical_run_data_included") is False
            )
            check("SYS-007", review_ok, "portable package lineage excludes project-specific and historical RUN data")
    else:
        recovery_report_path = project_root / "08_검증/reports/연구기록복구/연구기록_복구감사.json"
        try:
            recovery = load_json(recovery_report_path)
        except Exception as exc:
            recovery = {}
            check("SYS-006", False, f"strict recovery report unavailable: {exc}")
        else:
            counts = recovery.get("counts", {})
            coverage = recovery.get("coverage", {})
            recovery_ok = (
                recovery.get("status") == "PASS"
                and recovery.get("strict") is True
                and recovery.get("errors") == []
                and counts.get("parse_failures") == 0
                and counts.get("unresolved_conflicts") == 0
                and counts.get("items_excluded_without_reason") == 0
                and counts.get("missing_documents") == 0
                and coverage
                and all(value == 1.0 for value in coverage.values())
            )
            check("SYS-006", recovery_ok, "V6 recovery strict audit and all coverage lanes are exact PASS")

        try:
            archive_review = load_json(project_root / V7_ARCHIVE_REVIEW_PATH)
        except Exception as exc:
            archive_review = {}
            check("SYS-007", False, f"V7 archive review unavailable: {exc}")
        else:
            review_ok = (
                archive_review.get("status") == "ACCEPTED_WITH_HARDENING_NOT_BLINDLY_INSTALLED"
                and archive_review.get("blind_extraction_performed") is False
                and archive_review.get("archive_code_executed") is False
                and archive_review.get("archive", {}).get("sha256") == "4331721fccfa8170d024c939fcdf1dd971f3786d25064c8db84e7da4da826c25"
                and bool(archive_review.get("accepted_concepts"))
                and bool(archive_review.get("rejected_direct_install_reasons"))
            )
            check("SYS-007", review_ok, "V7 was reviewed and selectively integrated without blind extraction")

    operations = strict_audit(project_root)
    check("SYS-008", operations.get("status") == "PASS", "research operations strict audit")
    authority = binding.get("authority_hierarchy")
    authority_ok = (
        authority == ["00_research_ops", "V6_RECORD_STRUCTURE"]
        or authority == ["00_research_ops", "V6_RECORD_STRUCTURE", "EXPLANATION_PUBLICATION_LAYER"]
    )
    check("SYS-009", authority_ok, "operating authority is above the record structure; explanation publication layer is read-only when present")
    check("SYS-010", binding.get("split_brain_record_store_forbidden") is True, "no duplicate V7 record store may compete with V6")
    role_policy = binding.get("role_policy", {}) if isinstance(binding, dict) else {}
    check(
        "SYS-011",
        role_policy.get("self_approval_forbidden") is True
        and role_policy.get("verification_role") == "R04"
        and role_policy.get("independent_review_role") == "R06"
        and role_policy.get("closing_evidence_must_bind_exact_task_id") is True,
        "task closure requires exact task-bound R04 verification and R06 independent review",
    )

    active_recovery_blockers: list[str] = []
    blockers_path = project_root / "02_상태/blockers.json"
    if blockers_path.exists():
        blocker_payload = load_json(blockers_path)
        active_recovery_blockers = [row.get("id", "UNKNOWN") for row in blocker_payload.get("blockers", []) if row.get("status") == "active"]
    current_open_failures = open_failures(project_root)
    active_chat_incremental_sync_complete = not any(
        row.get("failure_id") == "FAIL-RECOVERY-INCREMENTAL-BASE-MISSING"
        for row in current_open_failures
    )
    errors = [row for row in checks if row["status"] == "FAIL"]
    return {
        "schema": "RESEARCH_OPERATING_SYSTEM_FULL_AUDIT_V1",
        "created_at": utc_now(),
        "status": "PASS" if not errors else "FAIL",
        "structure_ready": not errors,
        "authority_hierarchy": "RESEARCH_OPERATING_SYSTEM_OVER_RECORD_STRUCTURE",
        "check_count": len(checks),
        "passed_check_count": len(checks) - len(errors),
        "failed_check_count": len(errors),
        "checks": checks,
        "operations_audit": operations,
        "record_recovery": {
            "status": recovery.get("status"),
            "selected_source_count": recovery.get("counts", {}).get("sources_selected"),
            "classifiable_event_count": recovery.get("counts", {}).get("classifiable_events"),
            "active_recovery_blockers": active_recovery_blockers,
            "active_chat_incremental_sync_complete": active_chat_incremental_sync_complete,
        },
        "open_scope_specific_failures": [row.get("failure_id") for row in current_open_failures],
        "new_task_requires_scope_preflight": True,
        "optimizer_authorized_by_this_audit": False,
        "model_or_gate_change_authorized_by_this_audit": False,
        "hooks_are_defense_in_depth_not_authority": True,
    }


def doctor(project_root: Path) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "project_root_exists": project_root.exists(),
        "ops_root_exists": ops_root(project_root).exists(),
        "policy_valid": False,
        "profile_valid": False,
        "python": sys.version,
    }
    try:
        load_policy(project_root)
        checks["policy_valid"] = True
        load_profile(project_root)
        checks["profile_valid"] = True
    except Exception as exc:
        checks["error"] = str(exc)
    return {"schema": "RESEARCH_OPERATIONS_DOCTOR_V1", "status": "PASS" if all(checks[k] for k in ("project_root_exists", "ops_root_exists", "policy_valid", "profile_valid")) else "FAIL", "checks": checks}
