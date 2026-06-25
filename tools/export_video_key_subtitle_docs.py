from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import deque
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRAPH = PROJECT_ROOT / "data" / "game" / "storyline_graph" / "storyline_graph_data.json"
SRT_ROOT = PROJECT_ROOT / "data" / "game" / "storyline_graph" / "srt"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "knowledge" / "video_subtitles"

KEYLIKE_RE = re.compile(r"^[A-Za-z0-9_]+$")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def useful_text(value: Any, *invalid_values: str) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    invalid = {normalize_text(item) for item in invalid_values if normalize_text(item)}
    if text in invalid or KEYLIKE_RE.fullmatch(text):
        return ""
    return text


def node_display_id(node: dict[str, Any]) -> str:
    return normalize_text(
        node.get("videoKey")
        or node.get("targetVideoKey")
        or node.get("annotation")
        or node.get("title")
        or node.get("hash")
        or node.get("id")
    )


def node_description(node: dict[str, Any]) -> str:
    video_key = normalize_text(node.get("videoKey"))
    parts: list[str] = []
    keys = ("storylineTitle", "title") if video_key else ("title", "annotation", "storylineTitle")
    for key in keys:
        text = useful_text(node.get(key), video_key, *parts)
        if text:
            parts.append(text)
    return parts[0] if parts else ""


def node_ref(node: dict[str, Any]) -> str:
    ident = node_display_id(node)
    desc = node_description(node)
    if ident and desc:
        return f"{ident}（{desc}）"
    return ident or desc


def choice_letter(index: Any) -> str:
    if isinstance(index, int) and 0 <= index < 26:
        return chr(ord("A") + index)
    return ""


def parse_srt(text: str) -> list[dict[str, str]]:
    if not text:
        return []
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    rows: list[dict[str, str]] = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in block.strip().split("\n") if line.strip()]
        if len(lines) < 3:
            continue
        raw_body = " ".join(lines[2:]).strip()
        match = re.match(r"^([^：:]{1,18})[：:](.*)$", raw_body)
        rows.append(
            {
                "index": lines[0],
                "time": re.sub(r"\s*-->\s*", " - ", lines[1]),
                "speaker": match.group(1).strip() if match else "",
                "body": match.group(2).strip() if match else raw_body,
            }
        )
    return rows


def load_srt_rows(node: dict[str, Any]) -> list[dict[str, str]]:
    srt = node.get("srt") or {}
    relative = srt.get("relative") or srt.get("name")
    if not relative:
        return []
    path = SRT_ROOT / relative
    if not path.exists():
        return []
    return parse_srt(path.read_text(encoding="utf-8-sig"))


def edge_target_id(edge: dict[str, Any]) -> str:
    return normalize_text(edge.get("resolvedTargetId") or edge.get("targetId"))


def load_graph() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    data = read_json(GRAPH)
    nodes: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    incoming: dict[str, list[dict[str, Any]]] = {}
    for chapter_index, chapter in enumerate(data.get("chapters", [])):
        for order, raw in enumerate(chapter.get("nodes", [])):
            node = dict(raw)
            node["_chapterIndex"] = chapter_index
            node["_order"] = order
            nodes.append(node)
            by_id[node["id"]] = node
    for node in nodes:
        for edge in node.get("edges") or []:
            target_id = edge_target_id(edge)
            if target_id:
                incoming.setdefault(target_id, []).append({"source": node["id"], "edge": edge})
    return nodes, by_id, incoming


def nearest_upstream_choice(
    target: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    incoming: dict[str, list[dict[str, Any]]],
    max_depth: int = 24,
) -> tuple[dict[str, Any], dict[str, Any], int] | None:
    seen = {target["id"]}
    queue = deque([(target["id"], 0)])
    while queue:
        current_id, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for item in incoming.get(current_id, []):
            source = by_id.get(item["source"])
            if not source:
                continue
            edge = item["edge"]
            if source.get("kind") == "ShowChoice":
                return source, edge, depth + 1
            source_id = source["id"]
            if source_id not in seen:
                seen.add(source_id)
                queue.append((source_id, depth + 1))
    return None


def nearest_upstream_video(
    target: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    incoming: dict[str, list[dict[str, Any]]],
    max_depth: int = 8,
) -> dict[str, Any] | None:
    seen = {target["id"]}
    queue = deque([(target["id"], 0)])
    while queue:
        current_id, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for item in incoming.get(current_id, []):
            source = by_id.get(item["source"])
            if not source:
                continue
            if source.get("videoKey") and source.get("kind") != "ShowChoice":
                return source
            source_id = source["id"]
            if source_id not in seen:
                seen.add(source_id)
                queue.append((source_id, depth + 1))
    return None


def downstream_refs(node: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for edge in node.get("edges") or []:
        target = by_id.get(edge_target_id(edge))
        if not target:
            label = normalize_text(edge.get("resolvedTargetLabel") or edge.get("targetLabel"))
            if label:
                refs.append(label)
            continue

        target_ref = node_ref(target)
        if target.get("kind") == "ShowChoice":
            target_ref = f"选择 {target_ref}"
        edge_hint = useful_text(edge.get("choiceText"))
        source_port = normalize_text(edge.get("sourcePort"))
        if not edge_hint and source_port == "endPointSuccess":
            edge_hint = "操作成功"
        elif not edge_hint and source_port == "endPointFail":
            edge_hint = "操作失败"
        refs.append(f"{edge_hint} → {target_ref}" if edge_hint else target_ref)
    return refs


def location_line(node: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("lineTitle", "chapterTitle", "chapter"):
        text = normalize_text(node.get(key))
        if text and text not in parts:
            parts.append(text)
    return " / ".join(parts)


def append_title_lines(lines: list[str], node: dict[str, Any], video_key: str) -> None:
    title = useful_text(node.get("title"), video_key)
    annotation = useful_text(node.get("annotation"), video_key, title)
    storyline_title = useful_text(node.get("storylineTitle"), video_key, title, annotation)
    if title:
        lines.append(f"卡片标题：{title}")
    if annotation:
        lines.append(f"卡片摘要：{annotation}")
    if storyline_title:
        lines.append(f"剧情标题：{storyline_title}")


def append_choice_context(
    lines: list[str],
    node: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    incoming: dict[str, list[dict[str, Any]]],
) -> None:
    upstream_choice = nearest_upstream_choice(node, by_id, incoming)
    if not upstream_choice:
        return

    choice_node, edge, _distance = upstream_choice
    option = choice_letter(edge.get("choiceIndex"))
    option_label = f"选项 {option}" if option else "选项"
    if edge.get("choiceHidden"):
        option_label = f"隐藏{option_label}"
    choice_text = useful_text(edge.get("choiceText")) or useful_text(edge.get("resolvedTargetLabel") or edge.get("targetLabel"))
    choice_key = node_display_id(choice_node)
    choice_desc = node_description(choice_node)
    target_key = normalize_text(edge.get("resolvedTargetLabel") or edge.get("targetLabel") or node.get("videoKey"))

    line = f"前置选择：{choice_key}"
    if choice_desc:
        line += f"（{choice_desc}）"
    line += f" / {option_label}"
    if choice_text:
        line += f" → {choice_text}"
    if target_key:
        line += f" / 流向 {target_key}"
    lines.append(line)


def video_doc(node: dict[str, Any], by_id: dict[str, dict[str, Any]], incoming: dict[str, list[dict[str, Any]]]) -> str:
    video_key = normalize_text(node.get("videoKey"))
    lines = [f"# {video_key}", "", f"当前视频：{video_key}"]

    loc = location_line(node)
    if loc:
        lines.append(f"位置：{loc}")
    append_title_lines(lines, node, video_key)
    append_choice_context(lines, node, by_id, incoming)

    previous_video = nearest_upstream_video(node, by_id, incoming)
    if previous_video:
        lines.append(f"前一视频：{node_ref(previous_video)}")

    next_refs = downstream_refs(node, by_id)
    if next_refs:
        lines.append("后续节点：" + "；".join(next_refs))

    lines.extend(["", "## 字幕", ""])
    rows = load_srt_rows(node)
    if rows:
        for row in rows:
            if row["speaker"]:
                lines.append(f'{row["index"]}. `{row["time"]}` **{row["speaker"]}**：{row["body"]}')
            else:
                lines.append(f'{row["index"]}. `{row["time"]}` {row["body"]}')
    else:
        lines.append("无字幕。")
    lines.append("")
    return "\n".join(lines)


def make_indexes(
    output: Path,
    exported: list[dict[str, Any]],
    missing: list[dict[str, Any]],
    skipped_choices: list[dict[str, Any]],
) -> None:
    lines = [
        "# Video Key Subtitle Docs",
        "",
        "每个非选择视频节点对应一个 `.subtitles.md` 文档。文档内容保留游戏日志和剧情串联所需的信息：当前视频 key、位置、可读标题/摘要、前置选择 key、选项字母、前一视频、后续节点、带时间码字幕。",
        "",
        f"- 文档数：{len(exported)}",
        f"- 有字幕：{len(exported) - len(missing)}",
        f"- 无字幕：{len(missing)}",
        f"- 选择节点未导出：{len(skipped_choices)}",
        "",
        "## 文档",
        "",
    ]
    for item in exported:
        rel = item["path"].relative_to(output).as_posix()
        lines.append(f'- [{item["videoKey"]}]({rel})：{location_line(item["node"])}')
    write_text(output / "INDEX.md", "\n".join(lines) + "\n")

    missing_lines = ["# Missing Subtitle Video Keys", ""]
    for item in missing:
        missing_lines.append(f'- {item["videoKey"]}：{location_line(item["node"])}')
    write_text(output / "MISSING_SUBTITLES.md", "\n".join(missing_lines) + "\n")

    choice_lines = [
        "# ShowChoice Video Keys Not Exported",
        "",
        "这些节点是选择卡，不是视频字幕卡；它们会作为视频文档里的前置选择上下文出现。",
        "",
    ]
    for node in skipped_choices:
        choice_lines.append(f"- {node_ref(node)}：{location_line(node)}")
    write_text(output / "SHOWCHOICE_VIDEO_KEYS_NOT_EXPORTED.md", "\n".join(choice_lines) + "\n")


def export_docs(output: Path) -> dict[str, Any]:
    print(
        "warning: export_video_key_subtitle_docs rewrites subtitle Markdown from page SRT. "
        "For human speaker corrections, edit data/knowledge/video_subtitles/docs/*.subtitles.md "
        "and run tools/sync_srt_from_subtitle_md.py instead."
    )
    nodes, by_id, incoming = load_graph()
    docs_dir = output / "docs"
    if docs_dir.exists():
        shutil.rmtree(docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)

    exported: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    skipped_choices: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for node in nodes:
        video_key = normalize_text(node.get("videoKey"))
        if not video_key:
            continue
        if node.get("kind") == "ShowChoice":
            skipped_choices.append(node)
            continue

        file_stem = video_key
        if file_stem in seen_names:
            file_stem = f'{video_key}.{normalize_text(node.get("hash")) or "duplicate"}'
        seen_names.add(file_stem)

        path = docs_dir / f"{file_stem}.subtitles.md"
        text = video_doc(node, by_id, incoming)
        write_text(path, text)
        item = {"videoKey": video_key, "path": path, "node": node}
        exported.append(item)
        if "无字幕。" in text:
            missing.append(item)

    make_indexes(output, exported, missing, skipped_choices)
    return {
        "docs": len(exported),
        "with_subtitles": len(exported) - len(missing),
        "missing_subtitles": len(missing),
        "showchoice_not_exported": len(skipped_choices),
        "output": str(output),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export one Markdown subtitle-context document per video key.")
    parser.add_argument("output", nargs="?", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(export_docs(args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
