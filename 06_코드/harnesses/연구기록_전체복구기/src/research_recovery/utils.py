from __future__ import annotations

import hashlib
import json
import gzip
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

BASE64_RE = re.compile(r"^data:[^;]+;base64,", re.IGNORECASE)
TOKEN_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|authorization)\s*[:=]\s*['\"]?[^\s'\"]+"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8", errors="replace"))


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def json_dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def json_load(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    return count


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def iter_jsonl(path: Path) -> Iterator[tuple[int, str, Any | None, str | None]]:
    manifest_path = path.with_name(path.name + ".parts.json")
    parts = [path]
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        declared = manifest.get("parts") if isinstance(manifest, dict) else None
        if not isinstance(declared, list) or not declared:
            raise RuntimeError(f"invalid JSONL parts manifest: {manifest_path}")
        parts = []
        for item in declared:
            candidate = path.parent / str(item)
            if not candidate.is_file():
                raise RuntimeError(f"JSONL part missing: {candidate}")
            parts.append(candidate)
    logical_line_no = 0
    for part in parts:
        opener = gzip.open if part.suffix.lower() == ".gz" else part.open
        with opener(part, "rt", encoding="utf-8-sig", errors="replace") if part.suffix.lower() == ".gz" else opener("r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                logical_line_no += 1
                line_no = logical_line_no
                raw = line.rstrip("\r\n")
                if not raw.strip():
                    yield line_no, raw, None, None
                    continue
                try:
                    yield line_no, raw, json.loads(raw), None
                except Exception as exc:  # malformed transcript must be recorded, never silently skipped
                    yield line_no, raw, None, f"{type(exc).__name__}: {exc}"


def redact_text(text: str, max_chars: int = 120_000) -> tuple[str, bool, list[str]]:
    notes: list[str] = []
    redacted = text
    if BASE64_RE.match(redacted.strip()):
        notes.append("inline_binary_payload_redacted")
        redacted = f"[인라인 바이너리 생략: sha256={sha256_text(text)}, chars={len(text)}]"
    for pattern in TOKEN_PATTERNS:
        new = pattern.sub("[비밀값_삭제]", redacted)
        if new != redacted:
            notes.append("secret_like_value_redacted")
            redacted = new
    truncated = False
    if len(redacted) > max_chars:
        digest = sha256_text(redacted)
        redacted = redacted[:max_chars] + f"\n[이후 내용 생략: 원문 chars={len(text)}, sha256={digest}]"
        truncated = True
        notes.append("oversize_text_truncated")
    return redacted, truncated, sorted(set(notes))


def flatten_text(value: Any, *, max_chars: int = 120_000) -> str:
    """JSON payload에서 사람이 읽을 수 있는 텍스트를 보수적으로 추출한다."""
    parts: list[str] = []
    seen: set[int] = set()

    def walk(obj: Any, key: str = "") -> None:
        if len("\n".join(parts)) > max_chars:
            return
        if isinstance(obj, (dict, list)):
            ident = id(obj)
            if ident in seen:
                return
            seen.add(ident)
        if isinstance(obj, str):
            lowered = key.lower()
            if lowered in {"reasoning", "chain_of_thought", "encrypted_content"}:
                parts.append(f"[{key or 'internal_reasoning'} 비공개; sha256={sha256_text(obj)} chars={len(obj)}]")
            elif lowered in {"image_url", "image", "images", "result"} and BASE64_RE.match(obj.strip()):
                parts.append(f"[{key or 'binary'} 생략 sha256={sha256_text(obj)} chars={len(obj)}]")
            elif lowered in {"text", "message", "output", "arguments", "input", "content", "summary", "command", "cmd"} or not key:
                clean, _, _ = redact_text(obj, max_chars=max_chars)
                parts.append(clean)
        elif isinstance(obj, list):
            for item in obj:
                walk(item, key)
        elif isinstance(obj, dict):
            preferred = ["text", "message", "output", "arguments", "command", "cmd", "content", "summary"]
            used: set[str] = set()
            for k in preferred:
                if k in obj:
                    walk(obj[k], k)
                    used.add(k)
            if not parts:
                for k, v in obj.items():
                    if k in {"reasoning", "chain_of_thought", "encrypted_content"}:
                        if isinstance(v, str):
                            walk(v, k)
                        continue
                    if k not in used and isinstance(v, (str, list, dict)):
                        walk(v, k)

    walk(value)
    text = "\n".join(p for p in parts if p and p.strip())
    clean, _, _ = redact_text(text, max_chars=max_chars)
    return clean.strip()


def safe_relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(path.resolve())


def run_command(args: list[str], *, cwd: Path | None = None, input_text: str | None = None, timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def which(command: str) -> str | None:
    return shutil.which(command)


def codex_home(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("CODEX_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / ".codex").resolve()


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def recovery(self) -> Path:
        return self.root / "04_근거" / "복구증거"

    @property
    def source_index(self) -> Path:
        return self.recovery / "원본목록" / "원본자료목록.jsonl"

    @property
    def raw_line_index(self) -> Path:
        return self.recovery / "대화색인" / "원본레코드_전수색인.jsonl"

    @property
    def timeline(self) -> Path:
        return self.recovery / "정규화기록" / "전체대화_연속기록.jsonl"

    @property
    def project_files(self) -> Path:
        return self.recovery / "정규화기록" / "프로젝트파일_전수색인.jsonl"

    @property
    def git_history(self) -> Path:
        return self.recovery / "정규화기록" / "Git_변경이력.jsonl"

    @property
    def classification(self) -> Path:
        return self.recovery / "분류결과" / "대화항목_분류.jsonl"

    @property
    def coverage_map(self) -> Path:
        return self.recovery / "분류결과" / "대화항목_문서반영표.jsonl"

    @property
    def coverage_report(self) -> Path:
        return self.recovery / "감사결과" / "누락검사.json"

    @property
    def conflict_report(self) -> Path:
        return self.recovery / "감사결과" / "충돌목록.jsonl"

    @property
    def recovery_report(self) -> Path:
        return self.root / "08_검증" / "reports" / "연구기록복구" / "연구기록_복구감사.json"
