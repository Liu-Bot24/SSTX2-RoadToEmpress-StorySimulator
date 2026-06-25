from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from collections import OrderedDict, deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import generate_video_summary_overlay as overlay


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BATCH_DIR = PROJECT_ROOT / "data" / "runtime" / "summary_generation" / "batches"
SECRET_CACHE: dict[str, str] = {}
SECRET_CACHE_LOCK = threading.Lock()
QUOTA_RE = re.compile(
    r"quota|credit|balance|billing|insufficient|resourceexhausted|rate.?limit|429|402|额度|余额|限额",
    re.IGNORECASE,
)
TRANSIENT_RE = re.compile(
    r"cloudflare|attention required|temporar|timeout|timed out|503|502|500|403",
    re.IGNORECASE,
)
THINKING_CONTINUATION_RE = re.compile(
    r"content\[\]\.thinking|thinking mode must be passed back",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Target:
    chapter: str
    video_key: str
    node_id: str
    order: int
    line_title: str
    chapter_title: str
    cue_count: int
    official_annotation_status: str


def now_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}_p{os.getpid()}"


def project_rel(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")


def read_existing_video_keys() -> set[str]:
    keys: set[str] = set()
    path = overlay.SUMMARY_JSONL
    if not path.exists():
        return keys
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        status = str(row.get("status") or "final").strip()
        if status and status != "final":
            continue
        key = str(row.get("video_key") or "").strip()
        if key:
            keys.add(key)
    return keys


def subtitle_cue_count_for_node(node: dict[str, Any]) -> int:
    try:
        path = overlay.subtitle_doc_path(node)
    except SystemExit:
        return 0
    text = path.read_text(encoding="utf-8")
    return len(re.findall(r"^\s*\d+\.\s+`", text, flags=re.MULTILINE))


def list_targets(
    include_official: bool,
    skip_existing: bool,
    include_empty_cues: bool,
    empty_cues_only: bool,
) -> list[Target]:
    existing = read_existing_video_keys() if skip_existing else set()
    nodes, _, _ = overlay.load_graph()
    targets: list[Target] = []
    seen_video_keys: set[str] = set()
    for index, node in enumerate(nodes):
        video_key = str(node.get("videoKey") or "").strip()
        chapter = str(node.get("chapter") or "").strip()
        if not video_key or not chapter or node.get("kind") == "ShowChoice":
            continue
        if video_key in seen_video_keys:
            continue
        seen_video_keys.add(video_key)
        if skip_existing and video_key in existing:
            continue
        official = overlay.valid_official_annotation(node)
        if official and not include_official:
            continue
        cue_count = subtitle_cue_count_for_node(node)
        if empty_cues_only and cue_count > 0:
            continue
        if cue_count <= 0 and not (include_empty_cues or empty_cues_only):
            continue
        targets.append(
            Target(
                chapter=chapter,
                video_key=video_key,
                node_id=str(node.get("id") or ""),
                order=index,
                line_title=str(node.get("lineTitle") or ""),
                chapter_title=str(node.get("chapterTitle") or node.get("_graphChapterTitle") or ""),
                cue_count=cue_count,
                official_annotation_status="available" if official else "missing",
            )
        )
    return targets


def trim_failure_text(text: str, limit: int = 1200) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def retryable_claude_failure(error: str, failure_text: str) -> bool:
    if "Claude Code failed" not in error:
        return False
    combined = error + "\n" + failure_text
    return bool(QUOTA_RE.search(combined) or TRANSIENT_RE.search(combined) or THINKING_CONTINUATION_RE.search(combined))


def expected_raw_path(pack_path: Path, model: str) -> Path:
    text = overlay.project_path(pack_path).read_text(encoding="utf-8")
    digest = overlay.hashlib.sha256((overlay.prompt_text() + "\n\n" + text).encode("utf-8")).hexdigest()[:12]
    return overlay.RUN_DIR / pack_path.parent.name / f"{pack_path.stem}.claude-{overlay.safe_filename_part(model)}.{digest}.raw.txt"


def failure_text_for_run(pack_path: Path, model: str) -> str:
    raw = expected_raw_path(pack_path, model)
    parts: list[str] = []
    for path in (raw.with_suffix(".stderr.txt"), raw, raw.with_suffix(".meta.json")):
        if path.exists():
            parts.append(f"## {project_rel(path)}\n{path.read_text(encoding='utf-8', errors='replace')}")
    return "\n\n".join(parts)


def preserve_failed_attempt(pack_path: Path, model: str, attempt_number: int) -> list[str]:
    raw = expected_raw_path(pack_path, model)
    saved: list[str] = []
    for path in (
        raw,
        raw.with_suffix(".response.txt"),
        raw.with_suffix(".envelope.json"),
        raw.with_suffix(".stderr.txt"),
        raw.with_suffix(".meta.json"),
    ):
        if not path.exists():
            continue
        preserved = path.with_name(f"{path.stem}.attempt{attempt_number:02d}.failed{path.suffix}")
        shutil.copy2(path, preserved)
        saved.append(project_rel(preserved))
    return saved


def max_budget_for_target(target: Target, args: argparse.Namespace) -> str | None:
    value = str(args.max_budget_usd or "").strip()
    if not value:
        return None
    if value.lower() != "auto":
        return value
    return "2.50" if target.cue_count >= 150 else "1.00"


def target_line_key(target: Target) -> str:
    return target.line_title or "(unknown-line)"


def select_targets(targets: list[Target], limit: int, workers: int) -> list[Target]:
    if workers <= 1:
        return targets[:limit]

    buckets: OrderedDict[str, deque[Target]] = OrderedDict()
    for target in targets:
        buckets.setdefault(target_line_key(target), deque()).append(target)

    selected: list[Target] = []
    while len(selected) < limit and any(buckets.values()):
        for queue in buckets.values():
            if not queue:
                continue
            selected.append(queue.popleft())
            if len(selected) >= limit:
                break
    return selected


def get_secret(service: str) -> str:
    with SECRET_CACHE_LOCK:
        cached = SECRET_CACHE.get(service)
    if cached:
        return cached

    secret_cli = shutil.which("liuqi-secret") or shutil.which("liuqi-secret.cmd")
    if not secret_cli:
        fallback = Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin" / "liuqi-secret.cmd"
        if fallback.exists():
            secret_cli = str(fallback)
    if not secret_cli:
        raise RuntimeError("liuqi-secret command could not be found")
    completed = subprocess.run(
        [secret_cli, "store-get", service],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=PROJECT_ROOT,
        timeout=20,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"secret service `{service}` could not be read")
    secret = completed.stdout.strip()
    if not secret:
        raise RuntimeError(f"secret service `{service}` returned an empty value")
    with SECRET_CACHE_LOCK:
        SECRET_CACHE[service] = secret
    return secret


def run_claude_with_fallback(
    pack_path: Path,
    model: str,
    max_budget_usd: str | None,
    primary_secret_service: str | None,
    fallback_secret_service: str | None,
) -> tuple[Path, str, str | None]:
    if primary_secret_service:
        env = os.environ.copy()
        env["ANTHROPIC_AUTH_TOKEN"] = get_secret(primary_secret_service)
        return overlay.run_claude(pack_path, model, max_budget_usd, env=env), f"primary:{primary_secret_service}", None

    try:
        return overlay.run_claude(pack_path, model, max_budget_usd), "default", None
    except SystemExit as exc:
        first_failure = failure_text_for_run(pack_path, model)
        if not fallback_secret_service or not QUOTA_RE.search(first_failure + "\n" + str(exc)):
            raise
        env = os.environ.copy()
        env["ANTHROPIC_AUTH_TOKEN"] = get_secret(fallback_secret_service)
        raw = overlay.run_claude(pack_path, model, max_budget_usd, env=env)
        return raw, f"fallback:{fallback_secret_service}", trim_failure_text(first_failure)


def process_target(target: Target, args: argparse.Namespace) -> dict[str, Any]:
    entry: dict[str, Any] = target.__dict__.copy()
    max_budget_usd = max_budget_for_target(target, args)
    pack_path: Path | None = None
    failures: list[str] = []
    for attempt in range(args.retries + 1):
        try:
            pack_path = overlay.build_pack(target.chapter, target.video_key, target.node_id)
            raw_path, auth_profile, first_failure = run_claude_with_fallback(
                pack_path,
                args.model,
                max_budget_usd,
                args.primary_secret_service,
                args.fallback_secret_service,
            )
            meta_path = raw_path.with_suffix(".meta.json")
            audit_path = overlay.audit_claude_run(meta_path)
            verified_path = overlay.verify_output(raw_path)
            entry.update(
                {
                    "status": "ok",
                    "authProfile": auth_profile,
                    "pack": project_rel(pack_path),
                    "raw": project_rel(raw_path),
                    "meta": project_rel(meta_path),
                    "audit": project_rel(audit_path),
                    "verified": project_rel(verified_path),
                    "maxBudgetUsd": max_budget_usd,
                    "attempts": attempt + 1,
                }
            )
            if first_failure:
                entry["defaultAuthFailureBeforeFallback"] = first_failure
            return entry
        except Exception as exc:
            error = str(exc)
        except SystemExit as exc:
            error = str(exc)
        failure_text = failure_text_for_run(pack_path, args.model) if pack_path else ""
        preserved = preserve_failed_attempt(pack_path, args.model, attempt + 1) if pack_path else []
        failures.append(trim_failure_text(error + ("\n" + failure_text if failure_text else ""), 2000))
        if preserved:
            entry.setdefault("preservedFailedAttempts", []).append(
                {"attempt": attempt + 1, "files": preserved}
            )
        if attempt < args.retries and retryable_claude_failure(error, failure_text):
            continue
        break
    entry.update(
        {
            "status": "failed",
            "error": failures[-1] if failures else "unknown failure",
            "maxBudgetUsd": max_budget_usd,
            "attempts": len(failures) or 1,
        }
    )
    if len(failures) > 1:
        entry["previousFailures"] = failures[:-1]
    return entry


def run_targets_sequential(selected: list[Target], args: argparse.Namespace, on_entry: Any = None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for target in selected:
        entry = process_target(target, args)
        entries.append(entry)
        if on_entry:
            on_entry(entry)
        if entry.get("status") != "ok" and args.stop_on_error:
            raise SystemExit(entry.get("error") or "batch target failed")
    return entries


def run_targets_by_line(selected: list[Target], args: argparse.Namespace, on_entry: Any = None) -> list[dict[str, Any]]:
    queues: OrderedDict[str, deque[Target]] = OrderedDict()
    for target in selected:
        queues.setdefault(target_line_key(target), deque()).append(target)

    entries: list[dict[str, Any]] = []
    futures: dict[Any, str] = {}
    line_order = list(queues)

    def submit_next(executor: ThreadPoolExecutor, line_key: str) -> None:
        queue = queues.get(line_key)
        if queue:
            futures[executor.submit(process_target, queue.popleft(), args)] = line_key

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for line_key in line_order:
            if len(futures) >= args.workers:
                break
            submit_next(executor, line_key)

        stop_error: str | None = None
        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                line_key = futures.pop(future)
                entry = future.result()
                entries.append(entry)
                if on_entry:
                    on_entry(entry)
                if entry.get("status") != "ok" and args.stop_on_error:
                    stop_error = entry.get("error") or "batch target failed"
                    continue
                if not stop_error:
                    submit_next(executor, line_key)

            if stop_error:
                continue

            for line_key in line_order:
                if len(futures) >= args.workers:
                    break
                if line_key not in futures.values():
                    submit_next(executor, line_key)

        if stop_error:
            raise SystemExit(stop_error)

    return entries

def run_batch(args: argparse.Namespace) -> Path:
    targets = list_targets(
        args.include_official,
        not args.include_existing,
        args.include_empty_cues,
        args.empty_cues_only,
    )
    if args.line_title:
        allowed_lines = set(args.line_title)
        targets = [target for target in targets if target.line_title in allowed_lines]
    if args.start_after:
        marker = args.start_after.strip()
        filtered: list[Target] = []
        seen_marker = False
        for target in targets:
            if seen_marker:
                filtered.append(target)
                continue
            if marker in {target.video_key, f"{target.chapter}/{target.video_key}", target.node_id}:
                seen_marker = True
        targets = filtered
    selected = select_targets(targets, args.limit, args.workers)

    report: dict[str, Any] = {
        "createdAtUtc": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "maxBudgetUsd": args.max_budget_usd,
        "claudeTimeoutSec": args.claude_timeout_sec,
        "includeOfficial": args.include_official,
        "includeExisting": args.include_existing,
        "includeEmptyCues": args.include_empty_cues,
        "emptyCuesOnly": args.empty_cues_only,
        "workers": args.workers,
        "parallelism": "lineTitle-serial" if args.workers > 1 else "serial",
        "skipExistingPolicy": "status final video_key records",
        "lineTitleFilter": args.line_title,
        "startAfter": args.start_after,
        "limit": args.limit,
        "retries": args.retries,
        "remainingCandidateCountBeforeRun": len(targets),
        "selected": [target.__dict__ for target in selected],
        "entries": [],
    }
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    report_path = BATCH_DIR / f"batch_{now_id()}_{overlay.safe_filename_part(args.model)}.json"

    if args.dry_run:
        report["dryRun"] = True
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report_path

    def persist_entry(entry: dict[str, Any]) -> None:
        report["entries"].append(entry)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    overlay.CLAUDE_TIMEOUT_SEC = args.claude_timeout_sec
    if args.workers <= 1:
        run_targets_sequential(selected, args, persist_entry)
    else:
        run_targets_by_line(selected, args, persist_entry)

    if any(entry.get("status") == "ok" for entry in report["entries"]):
        subprocess.run(
            [sys.executable, "tools\\build_knowledge_navigation.py"],
            cwd=PROJECT_ROOT,
            check=True,
        )
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run resumable video-summary batches through Claude Code.")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--start-after", default="")
    parser.add_argument("--model", default=overlay.CLAUDE_TEST_MODEL)
    parser.add_argument("--max-budget-usd", default="")
    parser.add_argument("--primary-secret-service", default="")
    parser.add_argument("--fallback-secret-service", default="")
    official_group = parser.add_mutually_exclusive_group()
    official_group.add_argument("--include-official", dest="include_official", action="store_true", default=True)
    official_group.add_argument("--missing-official-only", dest="include_official", action="store_false")
    parser.add_argument("--include-existing", action="store_true")
    parser.add_argument("--include-empty-cues", action="store_true")
    parser.add_argument("--empty-cues-only", action="store_true")
    parser.add_argument("--line-title", action="append", default=[])
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--claude-timeout-sec", type=int, default=overlay.CLAUDE_TIMEOUT_SEC)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args()
    if args.model.lower() in {"auto", "router", "smart", "model-router"}:
        raise SystemExit("Refusing to use an auto/router model.")
    if args.limit <= 0:
        raise SystemExit("--limit must be positive.")
    if args.workers <= 0:
        raise SystemExit("--workers must be positive.")
    if args.retries < 0:
        raise SystemExit("--retries must be non-negative.")
    if args.claude_timeout_sec <= 0:
        raise SystemExit("--claude-timeout-sec must be positive.")
    if args.include_empty_cues and args.empty_cues_only:
        raise SystemExit("Use either --include-empty-cues or --empty-cues-only, not both.")
    report_path = run_batch(args)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
