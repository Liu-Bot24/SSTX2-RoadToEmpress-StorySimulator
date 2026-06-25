from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha1
from typing import Any

from .runtime_state import RuntimeEvent, UNLOCK_EVENT_TYPES


CONTEXT_RESET_ENDPOINT_KINDS = ("BadEnd", "ChapterReport", "SubChapterReport")
REENTRY_EVENT_TYPES = {
    "chapter_start_entry",
    "choice_shown",
    "ordinary_video_execute",
    "traceback_video_execute",
    "video_play_started",
}
CHAPTER_REENTRY_EVENT_TYPES = {
    "chapter_result_enter",
    "chapter_start_entry",
}
SESSION_BOUNDARY_EVENT_TYPES = {
    "chapter_result_enter",
    "chapter_start_entry",
    "fail_panel_transition",
    "fail_state_enter",
    "story_line_enter",
    "story_line_temp_enter",
    "story_state_enter",
    "story_state_exit_to_line",
    "story_line_exit_to_state",
}


@dataclass
class ContextBoundaryPacket:
    current_scope_start_line: int | None
    current_scope_reason: str
    context_session_id: str | None = None
    known_events: list[dict[str, Any]] = field(default_factory=list)
    current_choice: dict[str, Any] | None = None
    selected_target: dict[str, Any] | None = None
    candidate_targets: list[dict[str, Any]] = field(default_factory=list)
    auxiliary_events: list[dict[str, Any]] = field(default_factory=list)
    excluded_events: list[dict[str, Any]] = field(default_factory=list)
    risk_hints: list[dict[str, Any]] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "current_scope_start_line": self.current_scope_start_line,
            "current_scope_reason": self.current_scope_reason,
            "context_session_id": self.context_session_id,
            "known_events": self.known_events,
            "current_choice": self.current_choice,
            "selected_target": self.selected_target,
            "candidate_targets": self.candidate_targets,
            "auxiliary_events": self.auxiliary_events,
            "excluded_events": self.excluded_events,
            "risk_hints": self.risk_hints,
            "rules": self.rules,
        }


def build_context_boundary(events: list[RuntimeEvent]) -> ContextBoundaryPacket:
    packet = ContextBoundaryPacket(
        current_scope_start_line=None,
        current_scope_reason="session_start",
        rules=[
            "Only runtime-confirmed played videos and loaded subtitles may enter known_events.",
            "Prepared candidate targets are selectable options only; their future subtitles are excluded until actually played.",
            "BadEnd content is historical risk after re-entry, not current story context.",
            "Unlock events are auxiliary dossier evidence and never advance current story context.",
            "Static indexes are lookup material only; they are not proof that the player has seen the content.",
        ],
    )

    last_choice: RuntimeEvent | None = None
    candidate_targets: list[RuntimeEvent] = []
    awaiting_selected_target = False
    pending_ordinary_target: RuntimeEvent | None = None
    current_choice_window_id: str | None = None
    latest_bad_end_risk: dict[str, Any] | None = None
    latest_reset_endpoint_kind: str | None = None
    in_historical_endpoint_state = False

    for event in events:
        if event.event_type == "endpoint":
            endpoint = event.as_dict()
            if _is_reset_endpoint(event):
                latest_reset_endpoint_kind = str(event.data.get("kind", ""))
                if _is_bad_end_endpoint(event):
                    latest_bad_end_risk = {
                        "line_no": event.line_no,
                        "endpoint_id": event.data.get("endpoint_id"),
                        "endpoint_title": event.data.get("title"),
                        "reset_anchor": event.data.get("source_ref"),
                        "evidence": endpoint,
                    }
                in_historical_endpoint_state = True
                packet = _start_terminal_packet_from_endpoint(packet, event, latest_bad_end_risk)
            packet.auxiliary_events.append(_tag(endpoint, "endpoint_history", "endpoint is not current context after re-entry"))
            continue

        if in_historical_endpoint_state and _is_reentry_event_for_reset(event, latest_reset_endpoint_kind):
            packet = _start_new_packet_from_reentry(packet, event, latest_bad_end_risk, latest_reset_endpoint_kind)
            in_historical_endpoint_state = False
            latest_bad_end_risk = None
            latest_reset_endpoint_kind = None
            last_choice = None
            candidate_targets = []
            awaiting_selected_target = False
            pending_ordinary_target = None
            current_choice_window_id = None

        if in_historical_endpoint_state:
            if event.event_type in UNLOCK_EVENT_TYPES:
                packet.auxiliary_events.append(_tag(event.as_dict(), "dossier_unlock", "unlock evidence after endpoint is background material, not story progress"))
            elif event.event_type in SESSION_BOUNDARY_EVENT_TYPES:
                packet.auxiliary_events.append(_tag(event.as_dict(), "session_boundary", "state-machine boundary evidence after endpoint, not story content"))
            else:
                packet.auxiliary_events.append(
                    _tag(
                        event.as_dict(),
                        "post_endpoint_transition",
                        "event occurs after a reset endpoint and before confirmed re-entry, so it is not current main context",
                    )
                )
            continue

        if event.event_type == "choice_shown":
            choice = event.as_dict()
            if packet.current_scope_start_line is None:
                packet.current_scope_start_line = event.line_no
                packet.current_scope_reason = "first_runtime_choice"
                packet.context_session_id = _context_session_id(event.line_no, packet.current_scope_reason, event.data.get("runtime_key"))

            last_choice = event
            candidate_targets = []
            awaiting_selected_target = False
            pending_ordinary_target = None
            current_choice_window_id = _choice_window_id(packet.context_session_id, event)
            choice = _with_scope_ids(choice, packet.context_session_id, current_choice_window_id)
            packet.current_choice = choice
            packet.selected_target = None
            packet.candidate_targets = []
            packet.known_events.append(_tag(choice, "current_choice", "choice text is visible to the player"))
            continue

        if event.event_type == "choice_candidate_prepared":
            candidate_targets.append(event)
            candidate = _with_scope_ids(event.as_dict(), packet.context_session_id, current_choice_window_id)
            packet.candidate_targets.append(candidate)
            packet.excluded_events.append(
                _tag(candidate, "prepared_candidate_only", "candidate target is not known story content until selected and played")
            )
            continue

        if event.event_type == "ordinary_video_execute":
            pending_ordinary_target = event
            packet.known_events.append(_tag(_with_scope_ids(event.as_dict(), packet.context_session_id, current_choice_window_id), "executed_video_command", "runtime command executed in current scope"))
            if awaiting_selected_target:
                packet.selected_target = _selected_target(last_choice, candidate_targets, event, pending_ordinary_target, packet.context_session_id, current_choice_window_id)
                awaiting_selected_target = False
                pending_ordinary_target = None
            continue

        if event.event_type == "select_exit":
            awaiting_selected_target = True
            packet.known_events.append(_tag(_with_scope_ids(event.as_dict(), packet.context_session_id, current_choice_window_id), "selection_boundary", "selection UI exited"))
            continue

        if event.event_type == "video_play_started":
            played = _with_scope_ids(event.as_dict(), packet.context_session_id, current_choice_window_id)
            packet.known_events.append(_tag(played, "played_video", "video playback is runtime-confirmed"))
            if awaiting_selected_target:
                packet.selected_target = _selected_target(last_choice, candidate_targets, event, pending_ordinary_target, packet.context_session_id, current_choice_window_id)
                awaiting_selected_target = False
                pending_ordinary_target = None
            continue

        if event.event_type == "subtitle_loaded":
            subtitle = _with_scope_ids(event.as_dict(), packet.context_session_id, current_choice_window_id)
            if event.known_to_context:
                packet.known_events.append(_tag(subtitle, "loaded_subtitle_for_played_video", "subtitle belongs to the currently played video"))
            else:
                packet.excluded_events.append(_tag(subtitle, "subtitle_not_current_video", "subtitle is not tied to current played video"))
            continue

        if event.event_type in UNLOCK_EVENT_TYPES:
            packet.auxiliary_events.append(_tag(_with_scope_ids(event.as_dict(), packet.context_session_id, None), "dossier_unlock", "unlock evidence is background material, not story progress"))
            continue

        if event.event_type in SESSION_BOUNDARY_EVENT_TYPES:
            packet.auxiliary_events.append(_tag(_with_scope_ids(event.as_dict(), packet.context_session_id, None), "session_boundary", "state-machine boundary evidence, not story content"))
            continue

        if event.known_to_context:
            packet.known_events.append(_tag(_with_scope_ids(event.as_dict(), packet.context_session_id, None), "runtime_known", "runtime event is safe context evidence"))
        else:
            packet.excluded_events.append(_tag(_with_scope_ids(event.as_dict(), packet.context_session_id, None), "not_runtime_confirmed_context", "event is not safe context evidence"))

    return packet


def redact_story_text(value: Any) -> Any:
    if isinstance(value, list):
        return [redact_story_text(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _redacted_text_payload(item) if _is_story_text_key(key) else redact_story_text(item)
            for key, item in value.items()
        }
    return value


def _start_new_packet_from_reentry(
    previous_packet: ContextBoundaryPacket,
    event: RuntimeEvent,
    latest_bad_end_risk: dict[str, Any] | None,
    latest_reset_endpoint_kind: str | None,
) -> ContextBoundaryPacket:
    scope_reason = "reentry_after_chapter_boundary" if latest_reset_endpoint_kind and "ChapterReport" in latest_reset_endpoint_kind else "reentry_after_endpoint"
    packet = ContextBoundaryPacket(
        current_scope_start_line=event.line_no,
        current_scope_reason=scope_reason,
        context_session_id=_context_session_id(event.line_no, scope_reason, event.data.get("runtime_key") or event.data.get("video_key") or event.data.get("current_video_key")),
        rules=previous_packet.rules,
    )
    if latest_bad_end_risk is not None:
        packet.risk_hints.append(
            {
                **latest_bad_end_risk,
                "policy": "historical risk only; do not include endpoint story text in current narrative context",
            }
        )
    return packet


def _start_terminal_packet_from_endpoint(
    previous_packet: ContextBoundaryPacket,
    event: RuntimeEvent,
    latest_bad_end_risk: dict[str, Any] | None,
) -> ContextBoundaryPacket:
    scope_reason = "terminal_pending_reentry"
    packet = ContextBoundaryPacket(
        current_scope_start_line=event.line_no,
        current_scope_reason=scope_reason,
        context_session_id=_context_session_id(event.line_no, scope_reason, event.data.get("endpoint_id") or event.data.get("kind")),
        rules=previous_packet.rules,
    )
    if latest_bad_end_risk is not None:
        packet.risk_hints.append(
            {
                **latest_bad_end_risk,
                "policy": "current terminal boundary; wait for story-line re-entry before giving new choice advice",
            }
        )
    return packet


def _selected_target(
    choice_event: RuntimeEvent | None,
    candidates: list[RuntimeEvent],
    selected_event: RuntimeEvent,
    ordinary_event: RuntimeEvent | None,
    context_session_id: str | None,
    choice_window_id: str | None,
) -> dict[str, Any]:
    target_key = (
        ordinary_event.data.get("runtime_key")
        if ordinary_event is not None and ordinary_event.data.get("runtime_key")
        else selected_event.data.get("video_key") or selected_event.data.get("runtime_key")
    )
    return {
        "choice_key": choice_event.data.get("runtime_key") if choice_event else None,
        "choice_line_no": choice_event.line_no if choice_event else None,
        "target_video_key": target_key,
        "selected_line_no": selected_event.line_no,
        "candidate_video_keys": [candidate.data.get("video_key") for candidate in candidates],
        "context_session_id": context_session_id,
        "choice_window_id": choice_window_id,
        "policy": "selected target is known only after select exit and runtime playback/execute evidence",
    }


def _with_scope_ids(payload: dict[str, Any], context_session_id: str | None, choice_window_id: str | None) -> dict[str, Any]:
    enriched = {**payload}
    if context_session_id is not None:
        enriched["context_session_id"] = context_session_id
    if choice_window_id is not None:
        enriched["choice_window_id"] = choice_window_id
    return enriched


def _context_session_id(start_line: int, reason: str, anchor: Any) -> str:
    return f"ctx:{start_line}:{reason}:{_short_hash(anchor)}"


def _choice_window_id(context_session_id: str | None, choice_event: RuntimeEvent) -> str:
    return f"choice:{context_session_id or 'none'}:{choice_event.line_no}:{_short_hash(choice_event.data.get('runtime_key'))}"


def _short_hash(value: Any) -> str:
    encoded = str(value or "").encode("utf-8", errors="replace")
    return sha1(encoded).hexdigest()[:8]


def _is_reset_endpoint(event: RuntimeEvent) -> bool:
    kind = str(event.data.get("kind", ""))
    return any(marker in kind for marker in CONTEXT_RESET_ENDPOINT_KINDS)


def _is_bad_end_endpoint(event: RuntimeEvent) -> bool:
    return "BadEnd" in str(event.data.get("kind", ""))


def _is_reentry_event_for_reset(event: RuntimeEvent, latest_reset_endpoint_kind: str | None) -> bool:
    if latest_reset_endpoint_kind and "ChapterReport" in latest_reset_endpoint_kind:
        return event.event_type in CHAPTER_REENTRY_EVENT_TYPES
    return event.event_type in REENTRY_EVENT_TYPES


def _tag(payload: dict[str, Any], classification: str, reason: str) -> dict[str, Any]:
    return {**payload, "classification": classification, "context_reason": reason}


def _redacted_text_payload(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    encoded = value.encode("utf-8", errors="replace")
    return {
        "redacted": True,
        "char_count": len(value),
        "sha1_12": sha1(encoded).hexdigest()[:12],
    }


def _is_story_text_key(key: str) -> bool:
    normalized = key.lower()
    return normalized in {"raw_text", "prompt", "description", "title", "endpoint_title"} or normalized.endswith("_title")
