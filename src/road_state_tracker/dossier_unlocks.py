from __future__ import annotations

from typing import Any

from .dossier import load_mappings
from .runtime_state import RuntimeEvent


DOSSIER_UNLOCK_TYPES = {
    "character_unlocked",
    "character_description_unlocked",
    "item_content_unlocked",
    "item_description_unlocked",
}


def build_dossier_unlocks(
    events: list[RuntimeEvent],
    mappings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mappings = mappings or load_mappings()
    records_by_entity: dict[tuple[str, str], dict[str, Any]] = {}

    for event in events:
        if event.event_type not in DOSSIER_UNLOCK_TYPES:
            continue
        entity_type, entity_id = _unlock_entity(event)
        if entity_type is None or entity_id is None:
            continue

        key = (entity_type, entity_id)
        record = records_by_entity.get(key)
        if record is None:
            status, mapping = _mapping_status(mappings, entity_type, entity_id)
            record = {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "mapping_status": status,
                "name": _mapping_name(status, mapping),
                "confidence": mapping.get("confidence") if status == "candidate" else None,
                "usable": False,
                "unlock_kind": "description_update",
                "first_line_no": event.line_no,
                "last_line_no": event.line_no,
                "first_current_video_key": event.data.get("current_video_key"),
                "last_current_video_key": event.data.get("current_video_key"),
                "first_current_folder_name": event.data.get("current_folder_name"),
                "last_current_folder_name": event.data.get("current_folder_name"),
                "toast_ids": [],
                "content_keys": [],
                "description_keys": [],
                "event_types": [],
                "failed_events": [],
                "prompt_policy": _prompt_policy(status),
            }
            records_by_entity[key] = record

        _merge_event(record, event)

    records = list(records_by_entity.values())
    records.sort(key=lambda record: (record["first_line_no"], record["entity_type"], record["entity_id"]))

    return {
        "version": 1,
        "totals": {
            "records": len(records),
            "confirmed": sum(1 for record in records if record["mapping_status"] == "confirmed"),
            "candidate": sum(1 for record in records if record["mapping_status"] == "candidate"),
            "unknown": sum(1 for record in records if record["mapping_status"] == "unknown"),
            "usable": sum(1 for record in records if record["usable"]),
            "failed_only": sum(1 for record in records if not record["usable"] and record["failed_events"]),
        },
        "confirmed_profiles": [record for record in records if record["mapping_status"] == "confirmed" and record["usable"]],
        "candidate_queue": [record for record in records if record["mapping_status"] == "candidate" and record["usable"]],
        "unknown_queue": [record for record in records if record["mapping_status"] == "unknown" and record["usable"]],
        "failed_events": [
            failed_event
            for record in records
            for failed_event in record["failed_events"]
        ],
        "records": records,
        "rules": [
            "unlock records are cumulative dossier evidence and never advance current story context",
            "confirmed records may enter an optional unlocked dossier area",
            "candidate and unknown records require confirmation before their names or inferred content become model facts",
            "Ret != 0 is retained for audit but is not usable dossier evidence",
        ],
    }


def _merge_event(record: dict[str, Any], event: RuntimeEvent) -> None:
    record["last_line_no"] = event.line_no
    record["last_current_video_key"] = event.data.get("current_video_key")
    record["last_current_folder_name"] = event.data.get("current_folder_name")
    _append_unique(record["event_types"], event.event_type)

    toast_id = event.data.get("toast_id")
    if toast_id is not None:
        _append_unique(record["toast_ids"], str(toast_id))

    content_key = event.data.get("content_key")
    if content_key is not None:
        _append_unique(record["content_keys"], int(content_key))

    description_key = event.data.get("description_key")
    if description_key is not None:
        _append_unique(record["description_keys"], int(description_key))

    ret = event.data.get("ret")
    if ret is not None and ret != 0:
        record["failed_events"].append(
            {
                "line_no": event.line_no,
                "event_type": event.event_type,
                "ret": ret,
                "toast_id": toast_id,
                "content_key": content_key,
                "description_key": description_key,
                "policy": "failure response; keep for audit only",
            }
        )
        return

    record["usable"] = True
    if event.event_type in {"character_unlocked", "item_content_unlocked"}:
        record["unlock_kind"] = "entity_first_unlock"
    elif record["unlock_kind"] != "entity_first_unlock":
        record["unlock_kind"] = "description_update"


def _append_unique(values: list[Any], value: Any) -> None:
    if value not in values:
        values.append(value)


def _unlock_entity(event: RuntimeEvent) -> tuple[str | None, str | None]:
    if event.event_type in {"character_unlocked", "character_description_unlocked"}:
        character_id = event.data.get("character_id")
        return "character", str(character_id) if character_id is not None else None
    if event.event_type in {"item_content_unlocked", "item_description_unlocked"}:
        item_id = event.data.get("item_id")
        return "item", str(item_id) if item_id is not None else None
    return None, None


def _mapping_status(mappings: dict[str, Any], entity_type: str, entity_id: str) -> tuple[str, dict[str, Any]]:
    if entity_type == "character":
        confirmed = mappings.get("characters", {})
        candidates = mappings.get("candidates", {}).get("characters", {})
    else:
        confirmed = mappings.get("items", {})
        candidates = mappings.get("candidates", {}).get("items", {})

    if entity_id in confirmed:
        return "confirmed", confirmed[entity_id]
    if entity_id in candidates:
        return "candidate", candidates[entity_id]
    return "unknown", {}


def _mapping_name(status: str, mapping: dict[str, Any]) -> str | None:
    if status == "confirmed":
        return mapping.get("name")
    if status == "candidate":
        return mapping.get("candidate_name")
    return None


def _prompt_policy(status: str) -> str:
    if status == "confirmed":
        return "optional unlocked dossier only; do not use as current story progress"
    if status == "candidate":
        return "confirmation queue only; candidate name is not a prompt fact"
    return "confirmation queue only; do not infer entity name from static search"
