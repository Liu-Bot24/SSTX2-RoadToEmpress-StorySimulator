from __future__ import annotations

from typing import Any

from .context_boundary import build_context_boundary, redact_story_text
from .runtime_state import RuntimeEvent


PROMPT_EVENT_KEYS = {
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
    "hash",
    "condition",
    "raw_text",
    "title",
    "prompt",
}

DOSSIER_EVENT_TYPES = {
    "unlock_toast_requested",
    "unlock_toast_confirmed",
    "character_unlocked",
    "character_description_unlocked",
    "item_content_unlocked",
    "item_description_unlocked",
}

DOSSIER_KEYS = {
    "line_no",
    "event_type",
    "classification",
    "context_reason",
    "context_session_id",
    "entity_type",
    "character_id",
    "item_id",
    "toast_id",
    "content_key",
    "description_key",
    "ret",
    "current_video_key",
    "current_folder_name",
}


def build_prompt_allowlist(events: list[RuntimeEvent], *, redact: bool = True) -> dict[str, Any]:
    boundary = build_context_boundary(events)
    packet = {
        "version": 1,
        "policy": {
            "main_context": "Only current context_session known events may enter the main AI prompt.",
            "candidate_targets": "Candidate targets are option keys only; their future subtitles remain excluded.",
            "risk_memory": "BadEnd history is compressed risk evidence, not current story context.",
            "optional_dossiers": "Unlock evidence is optional background and never advances story position.",
        },
        "context_session_id": boundary.context_session_id,
        "current_scope_start_line": boundary.current_scope_start_line,
        "current_scope_reason": boundary.current_scope_reason,
        "main_context": {
            "current_choice": _prompt_event(boundary.current_choice),
            "selected_target": boundary.selected_target,
            "candidate_targets": [_candidate_target(candidate) for candidate in boundary.candidate_targets],
            "known_events": [_prompt_event(event) for event in boundary.known_events],
        },
        "risk_memory": [_risk_hint(hint) for hint in boundary.risk_hints],
        "optional_dossiers": [_dossier_event(event) for event in boundary.auxiliary_events if _usable_dossier_event(event)],
        "excluded_summary": {
            "excluded_event_count": len(boundary.excluded_events),
            "candidate_target_count": len(boundary.candidate_targets),
            "auxiliary_event_count": len(boundary.auxiliary_events),
            "risk_hint_count": len(boundary.risk_hints),
        },
    }
    return redact_story_text(packet) if redact else packet


def _prompt_event(event: dict[str, Any] | None) -> dict[str, Any] | None:
    if event is None:
        return None
    return {key: value for key, value in event.items() if key in PROMPT_EVENT_KEYS}


def _candidate_target(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "line_no": event.get("line_no"),
        "video_key": event.get("video_key"),
        "folder_name": event.get("folder_name"),
        "context_session_id": event.get("context_session_id"),
        "choice_window_id": event.get("choice_window_id"),
        "policy": "option key only; do not resolve target subtitles before selection",
    }


def _risk_hint(hint: dict[str, Any]) -> dict[str, Any]:
    evidence = hint.get("evidence") or {}
    return {
        "line_no": hint.get("line_no"),
        "endpoint_id": hint.get("endpoint_id"),
        "endpoint_kind": evidence.get("kind"),
        "reset_anchor": hint.get("reset_anchor"),
        "policy": hint.get("policy"),
    }


def _usable_dossier_event(event: dict[str, Any]) -> bool:
    if event.get("event_type") not in DOSSIER_EVENT_TYPES:
        return False
    ret = event.get("ret")
    return ret is None or ret == 0


def _dossier_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = {key: value for key, value in event.items() if key in DOSSIER_KEYS}
    if "character_id" in payload:
        payload["entity_type"] = "character"
        payload["entity_id"] = str(payload["character_id"])
    elif "item_id" in payload:
        payload["entity_type"] = "item"
        payload["entity_id"] = str(payload["item_id"])
    payload["policy"] = "optional dossier evidence only; do not use as current story progress"
    return payload
