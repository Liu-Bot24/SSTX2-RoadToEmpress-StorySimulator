from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


DEFAULT_MAPPING_PATH = Path("data") / "runtime" / "confirmed_mappings.json"


PROFILE_PREFIXES = {
    "TID_CharacterConfig",
    "TID_CharacterCardConfig",
    "TID_CharacterVideoConfig",
    "TID_VoteVideoConfig",
    "TID_ToastConfig",
    "TID_ItemConfig",
}


def strip_rich_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            rows.append(json.loads(line))
    return rows


def load_mappings(path: Path | None = None) -> dict[str, Any]:
    mapping_path = path or DEFAULT_MAPPING_PATH
    if not mapping_path.exists():
        return {"characters": {}, "items": {}, "candidates": {"characters": {}, "items": {}}}
    return json.loads(mapping_path.read_text(encoding="utf-8"))


def resolve_query(query: str, mappings: dict[str, Any]) -> dict[str, Any]:
    query = query.strip()
    resolved: dict[str, Any] = {"input": query, "search_text": query, "mapping": None}
    if not query:
        return resolved

    characters = mappings.get("characters", {})
    items = mappings.get("items", {})
    character_candidates = mappings.get("candidates", {}).get("characters", {})
    item_candidates = mappings.get("candidates", {}).get("items", {})

    if query in characters:
        mapping = characters[query]
        resolved["search_text"] = mapping.get("name", query)
        resolved["mapping"] = {"scope": "profile_unlocked", "entity_type": "character", "entity_id": query, **mapping}
    elif query in items:
        mapping = items[query]
        resolved["search_text"] = mapping.get("name", query)
        resolved["mapping"] = {"scope": "profile_unlocked", "entity_type": "item", "entity_id": query, **mapping}
    elif query in character_candidates:
        mapping = character_candidates[query]
        resolved["search_text"] = mapping.get("candidate_name", query)
        resolved["mapping"] = {"scope": "candidate_mapping", "entity_type": "character", "entity_id": query, **mapping}
    elif query in item_candidates:
        mapping = item_candidates[query]
        resolved["search_text"] = mapping.get("candidate_name", query)
        resolved["mapping"] = {"scope": "candidate_mapping", "entity_type": "item", "entity_id": query, **mapping}

    return resolved


def classify_row(row: dict[str, Any]) -> str:
    prefix = row.get("prefix", "")
    key = row.get("key", "")
    zh = row.get("zh", "")
    if prefix == "TID_ToastConfig":
        if "已解锁" in zh or "Unlocked" in row.get("en_US", ""):
            return "unlock_toast_candidate"
        if "已更新" in zh or "Updated" in row.get("en_US", ""):
            return "update_toast_candidate"
    if prefix == "TID_CharacterCardConfig":
        return "character_card_candidate"
    if prefix == "TID_CharacterConfig":
        return "character_profile_text_candidate"
    if prefix == "TID_CharacterVideoConfig":
        return "character_video_candidate"
    if prefix == "TID_VoteVideoConfig":
        return "vote_video_candidate"
    if prefix == "TID_ItemConfig":
        return "wiki_item_candidate"
    if key.startswith("EndPoint_"):
        return "endpoint_text_candidate"
    return "static_text_candidate"


def row_matches(row: dict[str, Any], query: str) -> bool:
    haystack = "\n".join(
        str(row.get(field, ""))
        for field in ("key", "zh", "zh_CN", "zh_GL", "zh_TW", "en_US")
    )
    return query in haystack


def build_dossier(index_dir: Path, query: str, limit: int = 40, mapping_path: Path | None = None) -> dict[str, Any]:
    mappings = load_mappings(mapping_path)
    resolved = resolve_query(query, mappings)
    search_text = resolved["search_text"]

    rows = load_jsonl(index_dir / "tid_text_index.jsonl")
    rows.extend(load_jsonl(index_dir / "textclient_zh.jsonl"))

    evidence: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for row in rows:
        if not row_matches(row, search_text):
            continue
        key = row.get("key") or row.get("id") or json.dumps(row, ensure_ascii=False, sort_keys=True)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        prefix = row.get("prefix")
        if prefix and prefix not in PROFILE_PREFIXES:
            continue
        zh = strip_rich_text(row.get("zh", ""))
        en_us = strip_rich_text(row.get("en_US", ""))
        evidence.append(
            {
                "scope": "static_candidate",
                "category": classify_row(row),
                "key": row.get("key"),
                "prefix": prefix,
                "zh": zh,
                "en_US": en_us,
                "source_file": row.get("source_file"),
            }
        )
        if len(evidence) >= limit:
            break

    return {
        "query": query,
        "resolved": resolved,
        "evidence_count": len(evidence),
        "evidence": evidence,
        "rules": [
            "confirmed mapping can identify an unlocked entity id, but static candidates still need field-level config before they become exact profile slots",
            "static candidates are reference material, not current story context",
            "unknown ids should stay in the resolver queue until direct UI, dossier, runtime metadata, or decoded config evidence appears",
        ],
    }
