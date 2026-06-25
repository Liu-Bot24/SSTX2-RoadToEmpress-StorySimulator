from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

import build_value_table
import sync_srt_from_subtitle_md
import sync_video_summaries_from_md
from build_storyline_lines_html import GRAPH_DIR, build_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_HTML = GRAPH_DIR / "storyline_graph.html"
OUTPUT_JSON = GRAPH_DIR / "storyline_lines_manifest.json"
OUTPUT_DATA_JSON = GRAPH_DIR / "storyline_graph_data.json"
TEMPLATE_HTML = Path(__file__).with_name("storyline_graph_template.html")
RAW_STORYLINE_DIR = Path(__file__).with_name("recovered_storyline_json_live_26692")
TEXT_INDEX = PROJECT_ROOT / "data" / "index" / "roadtoempress2" / "textclient_zh.jsonl"
CHOICE_GROUPS = PROJECT_ROOT / "data" / "index" / "roadtoempress2" / "choice_groups.jsonl"
MECHANICS_DIR = GRAPH_DIR.parent / "storyline_mechanics"
SRT_OUTPUT_ROOT = GRAPH_DIR / "srt"
EPISODE_TITLE_RE = re.compile(r"^(第[一二三四五六七八九十百零〇两]+集)(?:\s+(.+))?$")
LINE_TITLES = {
    "entry": "前情提要",
    "empress": "女帝线",
    "new_world": "新世界线",
}
EPISODE_NAV_TITLES = {
    "chapter101": ["第十七集 盛世新篇章"],
    "chapter102": [
        "第十八集 · 吃人的后宫2.0 · 上",
        "第十九集 · 吃人的后宫2.0 · 中",
        "第二十集 · 吃人的后宫2.0 · 下",
    ],
    "chapter103": ["第二十一集 · 多余的母妃 · 上", "第二十二集 · 多余的母妃 · 下"],
    "chapter104": ["第二十三集 · 九嫔之首 · 上", "第二十四集 · 九嫔之首 · 下"],
    "chapter105": ["第二十五集 · 步入朝堂 · 上", "第二十六集 · 步入朝堂 · 下"],
    "chapter106": ["第二十七集 · 后位争夺战 · 上", "第二十八集 · 后位争夺战 · 下"],
    "chapter107": ["第二十九集 · 母仪天下 · 上", "第三十集 · 母仪天下 · 下"],
    "chapter108": ["第三十一集 · 权力的盛宴 · 上", "第三十二集 · 权力的盛宴 · 下"],
    "chapter109": ["第三十三集 · 二圣临朝 · 上", "第三十四集 · 二圣临朝 · 下"],
    "chapter110": ["第三十五集 · 帝后之间 · 上", "第三十六集 · 帝后之间 · 下"],
    "chapter111": ["第三十七集 · 日月同辉 · 上", "第三十八集 · 日月同辉 · 下"],
    "chapter112": [
        "第三十九集 · 盛世天下 · 上",
        "第四十集 · 盛世天下 · 中",
        "第四十一集 · 盛世天下 · 下",
    ],
}


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_text_map(path: Path) -> dict[str, str]:
    text_map: dict[str, str] = {}
    if not path.exists():
        return text_map
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        key = obj.get("raw_key") or (f"Key:{obj.get('key')}" if obj.get("key") else None) or obj.get("id")
        value = obj.get("zh_CN") or obj.get("zh_GL") or obj.get("zh") or obj.get("zh_TW") or obj.get("text")
        if key and isinstance(value, str):
            text_map[str(key)] = value
    return text_map


def tr(value: Any, text_map: dict[str, str]) -> Any:
    if isinstance(value, str):
        return text_map.get(value) or text_map.get(f"Deprecated@{value}") or value
    return value


def load_choice_groups(path: Path) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return groups
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        raw_id = str(obj.get("id") or "")
        match = re.search(r"ShowChoice-(.+)$", raw_id)
        if not match:
            continue
        groups[match.group(1)] = {
            "videoKey": match.group(1),
            "prompt": obj.get("prompt"),
            "storylineTitle": obj.get("storyline_title"),
            "choices": obj.get("choices") or [],
        }
    return groups


def node_key(node: dict[str, Any]) -> str:
    return node.get("baseInfo", {}).get("key") or ""


def node_pv(node: dict[str, Any]) -> dict[str, Any]:
    return node.get("dataInfo", {}).get("parameterValue") or {}


def node_annotation(node: dict[str, Any]) -> str:
    return node.get("dataInfo", {}).get("annotation") or ""


def port_ref(ref: dict[str, Any]) -> tuple[str, str, str, int, str]:
    return (
        ref.get("hashNode") or "",
        ref.get("hashSubNode") or "",
        ref.get("searchKeyGroup") or "",
        int(ref.get("indexGroup", -1)),
        ref.get("searchKey") or "",
    )


def choice_key_for_video(video_key: str, index: int) -> str:
    return f"Key:ShowChoice-{video_key}.choice+{index}.choiceText"


def choice_title_for_video(video_key: str, text_map: dict[str, str], groups: dict[str, dict[str, Any]]) -> str:
    group = groups.get(video_key) or {}
    return str(
        group.get("prompt")
        or tr(f"Key:ShowChoice-{video_key}.title", text_map)
        or tr(f"Deprecated@Key:ShowChoice-{video_key}.title", text_map)
        or video_key
    )


def choices_for_video(video_key: str, text_map: dict[str, str], groups: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    group = groups.get(video_key)
    if group and group.get("choices"):
        return [
            {"index": item.get("index"), "choiceText": item.get("text")}
            for item in group.get("choices", [])
        ]
    choices: list[dict[str, Any]] = []
    for idx in range(10):
        text = tr(choice_key_for_video(video_key, idx), text_map)
        if text == choice_key_for_video(video_key, idx):
            text = tr(f"Deprecated@Key:ShowChoice-{video_key}.choice+{idx}.choiceText", text_map)
        if isinstance(text, str) and not text.startswith(("Key:", "Deprecated@Key:")):
            choices.append({"index": idx, "choiceText": text})
    return choices


def build_choice_runtime_metadata() -> dict[str, dict[str, dict[str, Any]]]:
    text_map = load_text_map(TEXT_INDEX)
    choice_groups = load_choice_groups(CHOICE_GROUPS)
    result: dict[str, dict[str, dict[str, Any]]] = {}
    if not RAW_STORYLINE_DIR.exists():
        return result

    for path in sorted(RAW_STORYLINE_DIR.glob("*.json")):
        storyline_id = path.stem
        raw = read_json(path)
        nodes = {node.get("hash"): node for node in raw.get("node", []) if node.get("hash")}
        param_in: dict[tuple[str, str, str, int, str], list[dict[str, Any]]] = {}
        for link in raw.get("parameterLink", []) or []:
            dst = (link.get("baseInfo", {}).get("to") or {})
            param_in.setdefault(port_ref(dst), []).append(link)

        choice_nodes_by_video: dict[str, list[dict[str, Any]]] = {}
        for node in nodes.values():
            if node_key(node) != "ShowChoice":
                continue
            video_key = node_pv(node).get("videoKey")
            if video_key:
                choice_nodes_by_video.setdefault(str(video_key), []).append(node)

        def linked_source(node_hash: str, search_key: str, sub_hash: str = "", group: str = "", index: int = -1) -> str | None:
            links = param_in.get((node_hash, sub_hash, group, index, search_key), [])
            if len(links) != 1:
                return None
            return (links[0].get("baseInfo", {}).get("from") or {}).get("hashNode")

        def expr_for_node(node_hash: str | None, seen: set[str] | None = None) -> str:
            if not node_hash:
                return ""
            seen = seen or set()
            if node_hash in seen:
                return f"<cycle:{node_hash}>"
            seen.add(node_hash)
            node = nodes.get(node_hash)
            if not node:
                return f"<missing:{node_hash}>"
            kind = node_key(node)
            pv = node_pv(node)
            if kind == "Getter_GetVideoKeyVariable_Boloean":
                key = pv.get("parameterKey")
                return f"已播放/选择过 {key}"
            if kind == "Getter_GetVideoKeyIndex":
                key = pv.get("connectVideoKey")
                index = pv.get("selectIndex")
                return f"已选择 {key}#{index}"
            if kind == "Logic_NOT":
                return f"NOT ({expr_for_node(linked_source(node_hash, 'inputValue'), seen)})"
            if kind in {"Logic_OR", "Logic_AND"}:
                op = "OR" if kind == "Logic_OR" else "AND"
                a = expr_for_node(linked_source(node_hash, "inputValueA"), seen) or str(pv.get("inputValueA"))
                b = expr_for_node(linked_source(node_hash, "inputValueB"), seen) or str(pv.get("inputValueB"))
                return f"({a}) {op} ({b})"
            return node_annotation(node) or kind or node_hash

        def choice_rule_from_node(node_hash: str | None) -> dict[str, Any] | None:
            if not node_hash:
                return None
            node = nodes.get(node_hash)
            if not node:
                return None
            kind = node_key(node)
            pv = node_pv(node)
            if kind == "Logic_NOT":
                inner = choice_rule_from_node(linked_source(node_hash, "inputValue"))
                if inner and inner.get("type") == "selectedChoice":
                    inner = dict(inner)
                    inner["type"] = "notSelectedChoice"
                    return inner
                if inner and inner.get("type") == "notSelectedChoice":
                    inner = dict(inner)
                    inner["type"] = "selectedChoice"
                    return inner
                expression = expr_for_node(node_hash)
                return {"type": "expression", "expression": expression} if expression else None
            if kind == "Getter_GetVideoKeyIndex":
                video_key = str(pv.get("connectVideoKey") or "")
                try:
                    choice_index = int(pv.get("selectIndex"))
                except (TypeError, ValueError):
                    return None
                choice_matches = choice_nodes_by_video.get(video_key) or []
                choice_node = choice_matches[0] if len(choice_matches) == 1 else None
                choices = node_pv(choice_node).get("choice") if choice_node else []
                choice_text = ""
                if isinstance(choices, list) and 0 <= choice_index < len(choices):
                    choice_text = str(tr(choices[choice_index].get("choiceText") or "", text_map) or "")
                if not choice_text:
                    choice_text = str(tr(choice_key_for_video(video_key, choice_index), text_map) or "")
                return {
                    "type": "selectedChoice",
                    "choiceVideoKey": video_key,
                    "choiceIndex": choice_index,
                    "choiceText": choice_text,
                    "choiceTitle": choice_title_for_video(video_key, text_map, choice_groups),
                }
            expression = expr_for_node(node_hash)
            return {"type": "expression", "expression": expression} if expression else None

        def dynamic_choice_video_for(show_hash: str) -> dict[str, Any] | None:
            src_hash = linked_source(show_hash, "videoKey")
            if not src_hash:
                return None
            src = nodes.get(src_hash)
            if not src or node_key(src) != "Getter_Storyline_DynamicChoiceVideo":
                return None
            pv = node_pv(src)
            video_slots = []
            for slot in ("customParams1", "customParams2", "customParams3"):
                video_key = pv.get(slot)
                if isinstance(video_key, str) and video_key:
                    video_slots.append(
                        {
                            "slot": slot,
                            "videoKey": video_key,
                            "choices": choices_for_video(video_key, text_map, choice_groups),
                        }
                    )
            condition_slots = []
            for slot in ("customParams4", "customParams5"):
                condition_slots.append(
                    {
                        "slot": slot,
                        "rule": choice_rule_from_node(linked_source(src_hash, slot)),
                    }
                )
            return {
                "sourceHash": src_hash,
                "videoSlots": video_slots,
                "conditionSlots": condition_slots,
            }

        by_hash: dict[str, dict[str, Any]] = {}
        for show_hash, show_node in nodes.items():
            if node_key(show_node) != "ShowChoice":
                continue
            controls = []
            for sub in show_node.get("dataInfo", {}).get("subNode", []) or []:
                if node_key(sub) != "ShowChoice_ChoiceControl":
                    continue
                sub_hash = sub.get("hash") or ""
                pv = node_pv(sub)
                target_choice = pv.get("targetChoice")
                if not isinstance(target_choice, int):
                    continue
                control: dict[str, Any] = {
                    "targetChoice": target_choice,
                    "display": bool(pv.get("display", True)),
                    "enable": bool(pv.get("enable", True)),
                    "isDelay": bool(pv.get("isDelay", False)),
                    "delayTime": pv.get("delayTime", 0),
                }
                display_rule = choice_rule_from_node(linked_source(show_hash, "display", sub_hash=sub_hash))
                enable_rule = choice_rule_from_node(linked_source(show_hash, "enable", sub_hash=sub_hash))
                if display_rule:
                    control["displayRule"] = display_rule
                if enable_rule:
                    control["enableRule"] = enable_rule
                controls.append(control)
            meta: dict[str, Any] = {}
            if controls:
                meta["choiceControls"] = controls
            dynamic = dynamic_choice_video_for(show_hash)
            if dynamic:
                meta["dynamicChoiceVideo"] = dynamic
            if meta:
                by_hash[show_hash] = meta
        if by_hash:
            result[storyline_id] = by_hash
    return result


def prefer_speaker_srt(srt: dict[str, Any] | None) -> dict[str, Any] | None:
    if not srt:
        return None
    relative = str(srt.get("relative") or "")
    prefix = "zh_GL/"
    if not relative.startswith(prefix):
        return {key: value for key, value in srt.items() if key != "text"}
    target_path = SRT_OUTPUT_ROOT / relative
    target_path.parent.mkdir(parents=True, exist_ok=True)
    merged = dict(srt)
    if target_path.exists():
        merged["srtSource"] = "project"
    elif srt.get("text"):
        target_path.write_text(
            str(srt.get("text") or "").replace("\r\n", "\n").replace("\r", "\n").strip() + "\n",
            encoding="utf-8",
        )
        merged["srtSource"] = "manifest"
    else:
        return {key: value for key, value in merged.items() if key != "text"}
    merged.pop("text", None)
    merged["srtUrl"] = "srt/" + relative.replace("\\", "/")
    return merged


def split_episode_title(title: str) -> tuple[str | None, str | None]:
    title = re.sub(r"\s+", " ", title.strip())
    if not title:
        return None, None
    match = EPISODE_TITLE_RE.match(title)
    if not match:
        return None, title
    episode = match.group(1)
    rest = (match.group(2) or "").strip()
    if rest == "完":
        rest = ""
    return episode, rest or None


def display_chapter_title(chapter: dict[str, Any]) -> str:
    if chapter.get("line_key") == "entry":
        return "前情提要"
    configured = EPISODE_NAV_TITLES.get(str(chapter.get("chapter") or ""))
    if configured:
        parts = [label.split(" · ") for label in configured]
        episodes = [part[0] for part in parts if part]
        names = [part[1] for part in parts if len(part) > 1 and part[1]]
        if episodes and names and len(set(names)) == 1:
            episode_label = episodes[0] if len(episodes) == 1 else f"{episodes[0]}-{episodes[-1]}"
            return f"{episode_label} {names[0]}"
        return " / ".join(configured)
    reports = sorted(chapter.get("reports", []), key=lambda report: report.get("endpoint_id") or 0)
    episodes: list[str] = []
    names: list[str] = []
    fallback_titles: list[str] = []
    for report in reports:
        title = report.get("title_zh") or report.get("storyline_title_zh") or report.get("annotation") or ""
        episode, name = split_episode_title(str(title))
        if episode and episode not in episodes:
            episodes.append(episode)
        if name and name not in names:
            names.append(name)
        if title:
            stripped = re.sub(r"\s+完$", "", str(title).strip())
            if stripped and stripped not in fallback_titles:
                fallback_titles.append(stripped)
    if episodes and names:
        episode_label = episodes[0] if len(episodes) == 1 else f"{episodes[0]}-{episodes[-1]}"
        return f"{episode_label} {names[-1]}"
    if episodes:
        return " / ".join(episodes)
    return " / ".join(fallback_titles) or str(chapter.get("title") or chapter.get("storyline_id") or "")


def display_line_title(line_key: str, fallback: str) -> str:
    return LINE_TITLES.get(line_key, fallback)


def episode_items(chapter: dict[str, Any]) -> list[dict[str, str]]:
    configured = EPISODE_NAV_TITLES.get(str(chapter.get("chapter") or ""))
    if configured:
        items: list[dict[str, str]] = []
        for label in configured:
            parts = label.split(" · ")
            items.append(
                {
                    "label": label,
                    "episode": parts[0] if parts else label,
                    "suffix": parts[-1] if len(parts) > 2 else "",
                }
            )
        return items
    reports = sorted(chapter.get("reports", []), key=lambda report: report.get("endpoint_id") or 0)
    episodes: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for report in reports:
        title = report.get("title_zh") or report.get("storyline_title_zh") or report.get("annotation") or ""
        episode, name = split_episode_title(str(title))
        if not episode or episode in seen:
            continue
        episodes.append({"episode": episode, "name": name})
        seen.add(episode)
    if not episodes:
        return []
    shared_name = next((str(item["name"]) for item in reversed(episodes) if item.get("name")), "")
    suffixes = {
        2: ["上", "下"],
        3: ["上", "中", "下"],
        4: ["上", "中上", "中下", "下"],
    }.get(len(episodes), [])
    items: list[dict[str, str]] = []
    for index, item in enumerate(episodes):
        episode = str(item["episode"])
        name = str(item.get("name") or shared_name or "").strip()
        suffix = suffixes[index] if index < len(suffixes) else ""
        if suffix and name:
            label = f"{episode} · {name} · {suffix}"
        elif name:
            label = f"{episode} {name}"
        else:
            label = episode
        items.append({"label": label, "episode": episode, "suffix": suffix})
    return items


def attach_episode_entries(episodes: list[dict[str, str]], nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not episodes:
        return episodes
    chapter_entries = [node for node in nodes if node.get("kind") == "EntryPoint_ChapterStart"]
    sub_entries = [node for node in nodes if node.get("kind") == "EntryPoint_SubChapterStart"]
    entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for node in chapter_entries[:1] + sub_entries + chapter_entries[1:]:
        node_id = str(node.get("id") or "")
        if not node_id or node_id in seen_ids:
            continue
        seen_ids.add(node_id)
        entries.append(node)
    entry_order = episode_entry_order_from_reports(entries, nodes)
    if entry_order:
        entries = entry_order
    result: list[dict[str, str]] = []
    for index, episode in enumerate(episodes):
        item = dict(episode)
        if index < len(entries):
            item["startId"] = entries[index]["id"]
        result.append(item)
    return result


def episode_entry_order_from_reports(
    entries: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    report_nodes = [
        node
        for node in nodes
        if node.get("kind") in {"EndPoint_ChapterReport", "EndPoint_SubChapterReport"}
        and node.get("endpointId") is not None
    ]
    if len(entries) < 2 or len(report_nodes) < 2:
        return []
    node_by_id = {str(node.get("id")): node for node in nodes if node.get("id")}
    report_rank = {
        str(node.get("id")): index
        for index, node in enumerate(sorted(report_nodes, key=lambda item: item.get("endpointId") or 0))
    }
    start_ids = {str(node.get("id")) for node in entries if node.get("id")}

    def reachable_report_rank(entry: dict[str, Any]) -> int:
        entry_id = str(entry.get("id") or "")
        queue = [entry_id]
        seen: set[str] = set()
        while queue:
            node_id = queue.pop(0)
            if node_id in seen or node_id not in node_by_id:
                continue
            if node_id in start_ids and node_id != entry_id:
                continue
            seen.add(node_id)
            if node_id in report_rank:
                return report_rank[node_id]
            for edge in node_by_id[node_id].get("edges", []) or []:
                target_id = edge.get("resolvedTargetId") or edge.get("targetId")
                if target_id and target_id in node_by_id:
                    queue.append(str(target_id))
        return 10_000

    ranked_entries = [(reachable_report_rank(entry), index, entry) for index, entry in enumerate(entries)]
    if all(rank == 10_000 for rank, _, _ in ranked_entries):
        return []
    return [entry for _, _, entry in sorted(ranked_entries, key=lambda item: (item[0], item[1]))]


def apply_episode_metadata_to_nodes(
    chapter_id: str,
    nodes: list[dict[str, Any]],
    episodes: list[dict[str, str]],
    fallback_title: str,
) -> None:
    if not nodes:
        return
    if not episodes:
        for node in nodes:
            node["chapterTitle"] = fallback_title
        return

    node_by_id = {str(node.get("id")): node for node in nodes if node.get("id")}
    node_index = {str(node.get("id")): index for index, node in enumerate(nodes) if node.get("id")}
    starts: list[tuple[int, int, str, dict[str, str]]] = []
    for episode_index, episode in enumerate(episodes):
        start_id = episode.get("startId")
        label = episode.get("label")
        if not start_id or start_id not in node_by_id or not label:
            continue
        starts.append((node_index[start_id], episode_index, start_id, episode))
    if not starts:
        return
    starts.sort(key=lambda item: item[0])

    start_ids = {start_id for _, _, start_id, _ in starts}
    assigned_episode: dict[str, int] = {}
    for _, episode_index, start_id, _ in starts:
        queue = [start_id]
        seen: set[str] = set()
        while queue:
            node_id = queue.pop(0)
            if node_id in seen or node_id not in node_by_id:
                continue
            if node_id in start_ids and node_id != start_id:
                continue
            seen.add(node_id)
            assigned_episode.setdefault(node_id, episode_index)
            for edge in node_by_id[node_id].get("edges", []) or []:
                target_id = edge.get("targetId")
                if not target_id or target_id not in node_by_id:
                    continue
                if target_id in start_ids and target_id != start_id:
                    continue
                queue.append(str(target_id))

    current_title = fallback_title
    current_episode_index: int | None = None
    cursor = 0
    for index, node in enumerate(nodes):
        while cursor < len(starts) and starts[cursor][0] <= index:
            current_episode_index = starts[cursor][1]
            current_title = starts[cursor][3].get("label") or fallback_title
            cursor += 1
        node_id = str(node.get("id") or "")
        episode_index = assigned_episode.get(node_id, current_episode_index)
        if episode_index is not None and 0 <= episode_index < len(episodes):
            episode = episodes[episode_index]
            node["episodeIndex"] = episode_index
            node["episodeLabel"] = episode.get("label")
            node["episode"] = episode.get("episode")
            node["episodeSuffix"] = episode.get("suffix")
            node["episodeStartId"] = episode.get("startId")
            node["navKey"] = f"episode:{chapter_id}:{episode_index}"
            current_title = episode.get("label") or current_title
        node["chapterTitle"] = current_title


def is_logic_kind(kind: Any) -> bool:
    value = str(kind or "")
    return value == "Link_Lead" or bool(re.match(r"^(Function|Logic|Getter|Global)_", value))


def is_condition_kind(kind: Any) -> bool:
    return str(kind or "") in {"Function_Storyline_If", "Function_If"}


def is_terminal_endpoint_kind(kind: Any) -> bool:
    value = str(kind or "")
    return value.startswith("EndPoint_") and value not in {"EndPoint_ChapterReport", "EndPoint_SubChapterReport"}


def manifest_node_label(node: dict[str, Any] | None) -> str:
    if not node:
        return ""
    return str(
        node.get("video_key")
        or node.get("title_zh")
        or node.get("storyline_title_zh")
        or node.get("annotation")
        or node.get("kind")
        or node.get("node_id")
        or ""
    )


def resolve_linear_target_node(
    target_id: str | None,
    nodes_by_id: dict[str, dict[str, Any]],
    outgoing_by_source: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    current = str(target_id or "")
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        node = nodes_by_id.get(current)
        if not node:
            return None
        edges = outgoing_by_source.get(current, [])
        kind = node.get("kind")
        if node.get("video_key"):
            return node
        if is_condition_kind(kind) or is_terminal_endpoint_kind(kind) or kind == "ShowChoice":
            return node
        if is_logic_kind(kind) and len(edges) == 1:
            next_id = str(edges[0].get("target_node_id") or "")
            if next_id:
                current = next_id
                continue
        return node
    return None


def compact_for_browser(manifest: dict[str, Any]) -> dict[str, Any]:
    choice_runtime_metadata = build_choice_runtime_metadata()
    chapters = []
    for chapter in manifest["chapters"]:
        display_title = display_chapter_title(chapter)
        display_line = display_line_title(chapter["line_key"], chapter["line_title"])
        episodes = episode_items(chapter)
        nodes_by_id = {node["node_id"]: node for node in chapter["nodes"] if node.get("node_id")}
        outgoing_by_source: dict[str, list[dict[str, Any]]] = {}
        for manifest_node in chapter["nodes"]:
            node_id = manifest_node.get("node_id")
            if node_id:
                outgoing_by_source[str(node_id)] = list(manifest_node.get("outgoing_edges", []) or [])
        nodes = []
        for node in chapter["nodes"]:
            source_edges = list(node.get("outgoing_edges", []))
            if node.get("kind") == "ShowChoice":
                raw_edges = sorted(
                    source_edges,
                    key=lambda edge: (
                        0 if isinstance(edge.get("choice_index"), int) else 1,
                        edge.get("choice_index") if isinstance(edge.get("choice_index"), int) else 999,
                        str(edge.get("source_port") or ""),
                    ),
                )
            else:
                raw_edges = source_edges
            choices_by_index = {
                choice.get("index"): choice
                for choice in node.get("choices", [])
                if isinstance(choice.get("index"), int)
            }
            def edge_record(edge: dict[str, Any]) -> dict[str, Any]:
                resolved_target = resolve_linear_target_node(edge.get("target_node_id"), nodes_by_id, outgoing_by_source)
                return {
                    "sourcePort": edge.get("source_port"),
                    "sourceGroup": edge.get("source_group"),
                    "sourceIndexGroup": edge.get("source_index_group"),
                    "choiceIndex": edge.get("choice_index"),
                    "choiceText": edge.get("choice_text_zh") or edge.get("choice_text_key"),
                    "choiceHidden": choices_by_index.get(edge.get("choice_index"), {}).get("hidden", False),
                    "targetId": edge.get("target_node_id"),
                    "targetLabel": edge.get("target_label"),
                    "targetKind": edge.get("target_kind"),
                    "targetVideoKey": resolved_target.get("video_key") if resolved_target else "",
                    "resolvedTargetId": resolved_target.get("node_id") if resolved_target else "",
                    "resolvedTargetLabel": manifest_node_label(resolved_target) or edge.get("target_label"),
                }

            node_record = {
                    "id": node["node_id"],
                    "storylineId": chapter["storyline_id"],
                    "chapter": chapter["chapter"],
                    "chapterTitle": display_title,
                    "lineTitle": display_line,
                    "kind": node.get("kind"),
                    "hash": node.get("hash"),
                    "annotation": node.get("annotation"),
                    "videoKey": node.get("video_key"),
                    "title": node.get("title_zh"),
                    "storylineTitle": node.get("storyline_title_zh"),
                    "endpointId": node.get("endpoint_id"),
                    "targetVideoKey": node.get("endpoint_target_video_key"),
                    "srt": prefer_speaker_srt(node.get("srt")),
                    "edges": [edge_record(edge) for edge in raw_edges],
                }
            node_record.update(choice_runtime_metadata.get(chapter["storyline_id"], {}).get(node.get("hash"), {}))
            nodes.append(node_record)
        attached_episodes = attach_episode_entries(episodes, nodes)
        apply_episode_metadata_to_nodes(chapter["chapter"], nodes, attached_episodes, display_title)
        entry = next((node["id"] for node in nodes if node.get("kind") == "EntryPoint_ChapterStart"), nodes[0]["id"])
        chapters.append(
            {
                "lineKey": chapter["line_key"],
                "lineTitle": display_line,
                "chapter": chapter["chapter"],
                "storylineId": chapter["storyline_id"],
                "title": display_title,
                "rawTitle": chapter["title"],
                "episodes": attached_episodes,
                "entryId": entry,
                "nodeCount": chapter["node_count"],
                "edgeCount": chapter["edge_count"],
                "choiceEdgeCount": chapter["choice_edge_count"],
                "nodes": nodes,
            }
        )
    addons = []
    for addon in manifest["addons"]:
        files = []
        for file in addon.get("files", []):
            files.append(prefer_speaker_srt(file) or file)
        addons.append({**addon, "files": files})
    return {
        "chapters": chapters,
        "addons": addons,
    }


def strip_embedded_srt_text(value: Any) -> Any:
    if isinstance(value, list):
        return [strip_embedded_srt_text(item) for item in value]
    if not isinstance(value, dict):
        return value
    cleaned = {}
    is_srt_record = "name" in value and "relative" in value and "text" in value
    for key, item in value.items():
        if is_srt_record and key == "text":
            continue
        cleaned[key] = strip_embedded_srt_text(item)
    return cleaned


def render_html() -> str:
    return TEMPLATE_HTML.read_text(encoding="utf-8")

def main() -> int:
    manifest = build_manifest()
    data = compact_for_browser(manifest)
    OUTPUT_JSON.write_text(
        json.dumps(strip_embedded_srt_text(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    OUTPUT_DATA_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_count = sync_video_summaries_from_md.sync_jsonl_from_md()
    subtitle_sync = sync_srt_from_subtitle_md.sync_srt_from_subtitle_md()
    build_value_table.main()
    OUTPUT_HTML.write_text(render_html(), encoding="utf-8")
    print(
        f"wrote {OUTPUT_HTML} chapters={len(data['chapters'])} "
        f"addons={len(data['addons'])} data={OUTPUT_DATA_JSON.name} summaries={summary_count} "
        f"subtitle_srt={subtitle_sync['written']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
