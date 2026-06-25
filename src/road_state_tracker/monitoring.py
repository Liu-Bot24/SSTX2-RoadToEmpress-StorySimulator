from __future__ import annotations

from typing import Any

from .context_boundary import build_context_boundary, redact_story_text
from .dossier import load_mappings
from .runtime_state import RuntimeEvent


MECHANISM_KEYS = {
    "line_no",
    "event_type",
    "known_to_context",
    "classification",
    "context_reason",
    "context_session_id",
    "choice_window_id",
    "runtime_key",
    "static_key",
    "video_key",
    "folder_name",
    "sequence_id",
    "play_state",
    "wall_time",
    "source",
    "matched_current_video_key",
    "matched_current_folder_name",
    "admission_reason",
    "kind",
    "endpoint_role",
    "endpoint_id",
    "source_ref",
    "toast_id",
    "character_id",
    "item_id",
    "content_key",
    "description_key",
    "ret",
    "current_video_key",
    "current_folder_name",
    "evidence_strength",
    "state",
    "from_state",
    "to_state",
}

EVIDENCE_STRENGTH_BY_TYPE = {
    "video_prepared": "prefetch_only",
    "choice_candidate_prepared": "candidate_only",
    "choice_shown": "visible_choice",
    "select_enter": "selection_ui",
    "select_exit": "selection_boundary",
    "ordinary_video_execute": "executed_command",
    "traceback_video_execute": "executed_command",
    "video_play_started": "played_video",
    "video_play_timing": "played_video_timing",
    "subtitle_loaded": "loaded_subtitle_for_current_video",
    "endpoint": "endpoint_boundary",
    "unlock_toast_requested": "auxiliary_unlock",
    "unlock_toast_confirmed": "auxiliary_unlock",
    "character_unlocked": "auxiliary_unlock",
    "character_description_unlocked": "auxiliary_unlock",
    "item_content_unlocked": "auxiliary_unlock",
    "item_description_unlocked": "auxiliary_unlock",
    "fail_panel_transition": "session_boundary",
    "fail_state_enter": "session_boundary",
    "chapter_result_enter": "session_boundary",
    "chapter_start_entry": "session_boundary",
    "story_line_enter": "session_boundary",
    "story_line_temp_enter": "session_boundary",
    "story_state_enter": "session_boundary",
    "story_state_exit_to_line": "session_boundary",
    "story_line_exit_to_state": "session_boundary",
}


def build_monitor_payload(
    snapshot: dict[str, Any],
    events: list[RuntimeEvent],
    tail_limit: int = 20,
    recent_events: list[RuntimeEvent] | None = None,
) -> dict[str, Any]:
    boundary = build_context_boundary(events)
    boundary_payload = redact_story_text(boundary.as_dict())
    process_payload = snapshot.get("process") or {}
    open_files_payload = snapshot.get("open_files") or {}
    recent_scope = recent_events if recent_events is not None else events
    current_choice_in_scope = boundary.current_choice is not None

    return {
        "source": snapshot.get("source"),
        "player_log": snapshot.get("player_log"),
        "process": _summarize_process(process_payload),
        "open_files": _summarize_open_files(open_files_payload),
        "snapshot": snapshot.get("snapshot"),
        "phase": _infer_phase(snapshot, current_choice_in_scope, boundary_payload),
        "latest_choice_state": _latest_choice_state(snapshot, current_choice_in_scope),
        "current_video": snapshot.get("current_video"),
        "latest_endpoint": redact_story_text(snapshot.get("latest_endpoint")),
        "prepared_after_current_video": snapshot.get("prepared_after_current_video", []),
        "unresolved_unlocks": _unresolved_unlocks(events),
        "new_unresolved_unlocks": _unresolved_unlocks(recent_scope),
        "context_boundary": {
            "current_scope_start_line": boundary_payload["current_scope_start_line"],
            "current_scope_reason": boundary_payload["current_scope_reason"],
            "context_session_id": boundary_payload["context_session_id"],
            "current_choice": boundary_payload["current_choice"],
            "selected_target": boundary_payload["selected_target"],
            "candidate_targets": boundary_payload["candidate_targets"],
            "counts": {
                "known_events": len(boundary.known_events),
                "candidate_targets": len(boundary.candidate_targets),
                "auxiliary_events": len(boundary.auxiliary_events),
                "excluded_events": len(boundary.excluded_events),
                "risk_hints": len(boundary.risk_hints),
            },
            "risk_hints": boundary_payload["risk_hints"],
            "rules": boundary_payload["rules"],
        },
        "recent_mechanism_events": [_mechanism_event(event.as_dict()) for event in recent_scope[-tail_limit:]],
    }


def _summarize_process(process_payload: dict[str, Any]) -> dict[str, Any]:
    processes = process_payload.get("processes") or []
    return {
        "available": process_payload.get("available"),
        "matched": process_payload.get("matched"),
        "process_name": process_payload.get("process_name"),
        "matched_processes": [
            {
                "pid": process.get("pid"),
                "name": process.get("name"),
                "exe": process.get("exe"),
                "cwd": process.get("cwd"),
                "create_time": process.get("create_time"),
                "window_titles": process.get("window_titles", []),
                "matches_game_root": process.get("matches_game_root"),
                "matches_window_title": process.get("matches_window_title"),
                "errors": process.get("errors", []),
            }
            for process in processes
            if process.get("matches_game_root") or process.get("matches_window_title")
        ],
    }


def _summarize_open_files(open_files_payload: dict[str, Any]) -> dict[str, Any]:
    files = open_files_payload.get("files") or []
    return {
        "available": open_files_payload.get("available"),
        "pids": open_files_payload.get("pids", []),
        "count": len(files),
        "story_resource_files": [
            path for path in files if "\\video\\" in path.lower() or "\\audio_s2\\" in path.lower()
        ],
        "diagnostic_files": [
            path for path in files if "\\doc\\log\\" in path.lower() or "crashsight" in path.lower()
        ],
        "errors": open_files_payload.get("errors", []),
    }


def _mechanism_event(event: dict[str, Any]) -> dict[str, Any]:
    enriched = {
        **event,
        "evidence_strength": _evidence_strength(event),
    }
    return {
        key: value
        for key, value in redact_story_text(enriched).items()
        if key in MECHANISM_KEYS
    }


def _evidence_strength(event: dict[str, Any]) -> str:
    if event.get("event_type") == "subtitle_loaded" and not event.get("known_to_context"):
        return "loaded_subtitle_not_current_video"
    return EVIDENCE_STRENGTH_BY_TYPE.get(str(event.get("event_type")), "unknown")


def _infer_phase(snapshot: dict[str, Any], current_choice_in_scope: bool, boundary_payload: dict[str, Any]) -> dict[str, Any]:
    state = snapshot.get("state") or {}
    current_video = snapshot.get("current_video") or {}
    selected_target = state.get("selected_target") or {}
    prepared_after_current = snapshot.get("prepared_after_current_video") or []
    current_key = current_video.get("video_key")
    choice_key = state.get("runtime_key")
    selected_key = selected_target.get("video_key")
    if boundary_payload.get("current_scope_reason") == "terminal_pending_reentry":
        return {
            "name": "terminal_pending_reentry",
            "reason": "latest reset endpoint is still current; wait for story-line re-entry before giving choice advice",
            "current_video_key": current_key,
            "latest_choice_key": None,
            "selected_target_key": None,
            "latest_choice_in_current_scope": False,
            "prepared_after_current_count": len(prepared_after_current),
        }

    if state.get("active") and current_choice_in_scope:
        name = "choice_visible"
        reason = "latest choice is currently in EStoryExecState.Select"
    elif current_choice_in_scope and selected_key and current_key == selected_key:
        name = "selected_target_playing"
        reason = "selected target is the current played video"
    elif current_choice_in_scope and choice_key and current_key == choice_key:
        name = "choice_video_playing"
        reason = "choice prompt video is playing, but Select may not be active"
    elif current_key:
        name = "playing"
        reason = "runtime is outside a current choice window" if not current_choice_in_scope else "runtime has advanced beyond the latest tracked choice"
    else:
        name = "unknown"
        reason = "no current played video was parsed"

    return {
        "name": name,
        "reason": reason,
        "current_video_key": current_key,
        "latest_choice_key": choice_key if current_choice_in_scope else None,
        "selected_target_key": selected_key if current_choice_in_scope else None,
        "latest_choice_in_current_scope": current_choice_in_scope,
        "prepared_after_current_count": len(prepared_after_current),
    }


def _latest_choice_state(snapshot: dict[str, Any], current_choice_in_scope: bool) -> dict[str, Any] | None:
    state = snapshot.get("state")
    if not isinstance(state, dict) or state.get("type") != "choice":
        return None
    return redact_story_text(
        {
            "active": state.get("active"),
            "runtime_key": state.get("runtime_key"),
            "static_key": state.get("static_key"),
            "hash": state.get("hash"),
            "title": state.get("title"),
            "prompt": state.get("prompt"),
            "selected_target": state.get("selected_target"),
            "prepared_targets": state.get("prepared_targets", []),
            "in_current_scope": current_choice_in_scope,
        }
    )


def _unresolved_unlocks(events: list[RuntimeEvent]) -> list[dict[str, Any]]:
    mappings = load_mappings()
    unresolved: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str | None, str | None]] = set()

    for event in events:
        entity_type, entity_id = _unlock_entity(event)
        if entity_type is None or entity_id is None:
            continue
        if _failed_unlock(event):
            continue

        status = _mapping_status(mappings, entity_type, entity_id)
        if status != "unknown":
            continue

        content_key = event.data.get("content_key")
        description_key = event.data.get("description_key")
        key = (entity_type, entity_id, str(content_key) if content_key is not None else None, str(description_key) if description_key is not None else None)
        if key in seen:
            continue
        seen.add(key)
        unresolved.append(
            {
                "line_no": event.line_no,
                "event_type": event.event_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "mapping_status": status,
                "toast_id": event.data.get("toast_id"),
                "content_key": content_key,
                "description_key": description_key,
                "current_video_key": event.data.get("current_video_key"),
                "current_folder_name": event.data.get("current_folder_name"),
                "policy": "do not infer entity name from static search; wait for direct UI, dossier, runtime metadata, or decoded config evidence",
            }
        )

    return unresolved


def _unlock_entity(event: RuntimeEvent) -> tuple[str | None, str | None]:
    if event.event_type in {"character_unlocked", "character_description_unlocked"}:
        character_id = event.data.get("character_id")
        return "character", str(character_id) if character_id is not None else None
    if event.event_type in {"item_content_unlocked", "item_description_unlocked"}:
        item_id = event.data.get("item_id")
        return "item", str(item_id) if item_id is not None else None
    return None, None


def _failed_unlock(event: RuntimeEvent) -> bool:
    ret = event.data.get("ret")
    return ret is not None and ret != 0


def _mapping_status(mappings: dict[str, Any], entity_type: str, entity_id: str) -> str:
    if entity_type == "character":
        if entity_id in mappings.get("characters", {}):
            return "confirmed"
        if entity_id in mappings.get("candidates", {}).get("characters", {}):
            return "candidate"
    if entity_type == "item":
        if entity_id in mappings.get("items", {}):
            return "confirmed"
        if entity_id in mappings.get("candidates", {}).get("items", {}):
            return "candidate"
    return "unknown"
