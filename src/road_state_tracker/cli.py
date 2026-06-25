from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import DEFAULT_GAME_ROOT, DEFAULT_INDEX_DIR, DEFAULT_LANGUAGE, resolve_game_root, resolve_index_dir
from .config_inventory import build_config_inventory
from .context_boundary import build_context_boundary, redact_story_text
from .dossier import build_dossier
from .dossier_unlocks import build_dossier_unlocks
from .monitoring import build_monitor_payload
from .prompt_allowlist import build_prompt_allowlist
from .runtime_state import DEFAULT_PLAYER_LOG, collect_process_state, collect_runtime_events, collect_runtime_snapshot, collect_runtime_snapshot_from_text, collect_runtime_state, collect_unlock_events, get_process_open_files, parse_runtime_events
from .text_index import build_index, search_index


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("game_root", nargs="?", default=None, help=f"Game root. Default: {DEFAULT_GAME_ROOT}")
    parser.add_argument("index_dir", nargs="?", default=None, help=f"Index output dir. Default: {DEFAULT_INDEX_DIR}")


def cmd_inspect(args: argparse.Namespace) -> int:
    game_root = resolve_game_root(args.game_root)
    checks = {
        "game_root": str(game_root),
        "exists": game_root.exists(),
        "exe": (game_root / "sstx2.exe").exists(),
        "textclient_dir": (game_root / "Data" / "StreamingAssets" / "res" / "main" / "cfg" / "data").exists(),
        "srt_zh_gl": (game_root / "Data" / "StreamingAssets" / "res" / "main" / "SSTX2" / "Global" / "srt" / "zh_GL").exists(),
        "player_prefs": (game_root / "doc" / "tbu" / "playerPrefs").exists(),
    }
    print(json.dumps(checks, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if checks["exists"] else 1


def cmd_index(args: argparse.Namespace) -> int:
    game_root = resolve_game_root(args.game_root)
    index_dir = resolve_index_dir(args.index_dir)
    summary = build_index(game_root, index_dir, args.language)
    print(json.dumps(summary.__dict__, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    index_dir = resolve_index_dir(args.index_dir)
    results = search_index(index_dir, args.query, args.limit)
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_dossier(args: argparse.Namespace) -> int:
    index_dir = resolve_index_dir(args.index_dir)
    dossier = build_dossier(index_dir, args.query, args.limit)
    print(json.dumps(dossier, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_config_inventory(args: argparse.Namespace) -> int:
    game_root = resolve_game_root(args.game_root)
    index_dir = resolve_index_dir(args.index_dir)
    inventory = build_config_inventory(game_root, index_dir)
    print(json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_state(args: argparse.Namespace) -> int:
    game_root = resolve_game_root(args.game_root)
    state = collect_runtime_state(game_root, args.player_log, include_handles=not args.no_handles)
    print(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_process(args: argparse.Namespace) -> int:
    game_root = resolve_game_root(args.game_root)
    process_state = collect_process_state(game_root)
    print(json.dumps(process_state, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_events(args: argparse.Namespace) -> int:
    events = collect_runtime_events(args.player_log, args.limit)
    print(json.dumps(events, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_unlocks(args: argparse.Namespace) -> int:
    unlocks = collect_unlock_events(args.player_log, args.limit, args.since_line)
    print(json.dumps(unlocks, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_dossier_unlocks(args: argparse.Namespace) -> int:
    log_path = Path(args.player_log).expanduser().resolve() if args.player_log else DEFAULT_PLAYER_LOG
    text = log_path.read_text(encoding="utf-8", errors="replace")
    events = parse_runtime_events(text, None)
    if args.since_line > 0:
        events = [event for event in events if event.line_no >= args.since_line]
    payload = {
        "source": "player_log",
        "player_log": str(log_path),
        "since_line": args.since_line,
        "dossier_unlocks": build_dossier_unlocks(events),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    log_path = Path(args.player_log).expanduser().resolve() if args.player_log else DEFAULT_PLAYER_LOG
    text = log_path.read_text(encoding="utf-8", errors="replace")
    events = parse_runtime_events(text, None)
    if args.since_line > 0:
        events = [event for event in events if event.line_no >= args.since_line]
    boundary = build_context_boundary(events)
    payload = {
        "source": "player_log",
        "player_log": str(log_path),
        "since_line": args.since_line,
        "context_boundary": redact_story_text(boundary.as_dict()),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    game_root = resolve_game_root(args.game_root)
    snapshot = collect_runtime_snapshot(game_root, args.player_log, args.limit, include_handles=not args.no_handles)
    print(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    game_root = resolve_game_root(args.game_root)
    log_path = Path(args.player_log).expanduser().resolve() if args.player_log else DEFAULT_PLAYER_LOG
    before_stat = log_path.stat()
    raw = log_path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    after_stat = log_path.stat()
    snapshot = collect_runtime_snapshot_from_text(text, raw, before_stat, after_stat, log_path, args.limit)
    snapshot["process"] = collect_process_state(game_root)
    if not args.no_handles:
        snapshot["open_files"] = get_process_open_files(game_root)
    events = parse_runtime_events(text, None)
    recent_events = events
    if args.since_line > 0:
        recent_events = [event for event in events if event.line_no >= args.since_line]
    payload = build_monitor_payload(snapshot, events, args.tail, recent_events=recent_events)
    payload["monitor_window"] = {
        "since_line": args.since_line,
        "recent_event_count": len(recent_events),
        "boundary_uses_full_log": True,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    log_path = Path(args.player_log).expanduser().resolve() if args.player_log else DEFAULT_PLAYER_LOG
    text = log_path.read_text(encoding="utf-8", errors="replace")
    events = parse_runtime_events(text, None)
    payload = {
        "source": "player_log",
        "player_log": str(log_path),
        "prompt_allowlist": build_prompt_allowlist(events, redact=not args.raw),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sstx2-story-simulator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect whether the configured game install is readable.")
    inspect_parser.add_argument("game_root", nargs="?", default=None)
    inspect_parser.set_defaults(func=cmd_inspect)

    index_parser = subparsers.add_parser("index", help="Build the local full-text lookup index.")
    add_common_args(index_parser)
    index_parser.add_argument("language", nargs="?", default=DEFAULT_LANGUAGE)
    index_parser.set_defaults(func=cmd_index)

    search_parser = subparsers.add_parser("search", help="Search the generated local index.")
    search_parser.add_argument("query")
    search_parser.add_argument("index_dir", nargs="?", default=None)
    search_parser.add_argument("limit", nargs="?", type=int, default=20)
    search_parser.set_defaults(func=cmd_search)

    dossier_parser = subparsers.add_parser("dossier", help="Build a source-labeled candidate dossier for a known or candidate entity.")
    dossier_parser.add_argument("query")
    dossier_parser.add_argument("index_dir", nargs="?", default=None)
    dossier_parser.add_argument("limit", nargs="?", type=int, default=40)
    dossier_parser.set_defaults(func=cmd_dossier)

    config_inventory_parser = subparsers.add_parser("config-inventory", help="Inspect encrypted/plain config pbin files without dumping story text.")
    add_common_args(config_inventory_parser)
    config_inventory_parser.set_defaults(func=cmd_config_inventory)

    state_parser = subparsers.add_parser("state", help="Read the current runtime choice state from safe game logs.")
    state_parser.add_argument("game_root", nargs="?", default=None)
    state_parser.add_argument("player_log", nargs="?", default=None, help=f"Player.log path. Default: {DEFAULT_PLAYER_LOG}")
    state_parser.add_argument("--no-handles", dest="no_handles", action="store_true", help="Skip OS open-file handle confirmation.")
    state_parser.set_defaults(func=cmd_state)

    process_parser = subparsers.add_parser("process", help="Confirm the running Road to Empress process identity.")
    process_parser.add_argument("game_root", nargs="?", default=None)
    process_parser.set_defaults(func=cmd_process)

    events_parser = subparsers.add_parser("events", help="Read recent runtime story events from Player.log.")
    events_parser.add_argument("limit", nargs="?", type=int, default=80)
    events_parser.add_argument("player_log", nargs="?", default=None, help=f"Player.log path. Default: {DEFAULT_PLAYER_LOG}")
    events_parser.set_defaults(func=cmd_events)

    unlocks_parser = subparsers.add_parser("unlocks", help="Read recent runtime unlock events from Player.log.")
    unlocks_parser.add_argument("limit", nargs="?", type=int, default=80)
    unlocks_parser.add_argument("since_line", nargs="?", type=int, default=0)
    unlocks_parser.add_argument("player_log", nargs="?", default=None, help=f"Player.log path. Default: {DEFAULT_PLAYER_LOG}")
    unlocks_parser.set_defaults(func=cmd_unlocks)

    dossier_unlocks_parser = subparsers.add_parser("dossier-unlocks", help="Aggregate runtime dossier/wiki unlocks by entity and mapping status.")
    dossier_unlocks_parser.add_argument("since_line", nargs="?", type=int, default=0)
    dossier_unlocks_parser.add_argument("player_log", nargs="?", default=None, help=f"Player.log path. Default: {DEFAULT_PLAYER_LOG}")
    dossier_unlocks_parser.set_defaults(func=cmd_dossier_unlocks)

    context_parser = subparsers.add_parser("context", help="Classify runtime events into AI context, auxiliary evidence, and excluded future/unsafe evidence.")
    context_parser.add_argument("since_line", nargs="?", type=int, default=0)
    context_parser.add_argument("player_log", nargs="?", default=None, help=f"Player.log path. Default: {DEFAULT_PLAYER_LOG}")
    context_parser.set_defaults(func=cmd_context)

    snapshot_parser = subparsers.add_parser("snapshot", help="Read state, events, process, and handles from one Player.log snapshot.")
    snapshot_parser.add_argument("limit", nargs="?", type=int, default=80)
    snapshot_parser.add_argument("game_root", nargs="?", default=None)
    snapshot_parser.add_argument("player_log", nargs="?", default=None, help=f"Player.log path. Default: {DEFAULT_PLAYER_LOG}")
    snapshot_parser.add_argument("--no-handles", dest="no_handles", action="store_true", help="Skip OS open-file handle confirmation.")
    snapshot_parser.set_defaults(func=cmd_snapshot)

    monitor_parser = subparsers.add_parser("monitor", help="Print a redacted mechanism-only runtime monitor payload.")
    monitor_parser.add_argument("since_line", nargs="?", type=int, default=0)
    monitor_parser.add_argument("limit", nargs="?", type=int, default=80)
    monitor_parser.add_argument("game_root", nargs="?", default=None)
    monitor_parser.add_argument("player_log", nargs="?", default=None, help=f"Player.log path. Default: {DEFAULT_PLAYER_LOG}")
    monitor_parser.add_argument("tail", nargs="?", type=int, default=20, help="Recent mechanism event count.")
    monitor_parser.add_argument("--no-handles", dest="no_handles", action="store_true", help="Skip OS open-file handle confirmation.")
    monitor_parser.set_defaults(func=cmd_monitor)

    prompt_parser = subparsers.add_parser("prompt", help="Build the prompt allowlist packet from current runtime context.")
    prompt_parser.add_argument("player_log", nargs="?", default=None, help=f"Player.log path. Default: {DEFAULT_PLAYER_LOG}")
    prompt_parser.add_argument("--raw", dest="raw", action="store_true", help="Include allowed visible story text instead of redacting it.")
    prompt_parser.set_defaults(func=cmd_prompt)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
