from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import sync_video_summaries_from_md


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_ROOT = PROJECT_ROOT / "data" / "knowledge"
SUBTITLE_ROOT = KNOWLEDGE_ROOT / "video_subtitles"
SUBTITLE_DOC_DIR = SUBTITLE_ROOT / "docs"
SUMMARY_ROOT = KNOWLEDGE_ROOT / "video_summaries"
SUMMARY_JSONL = SUMMARY_ROOT / "video_summaries.jsonl"
SUMMARY_DOC_DIR = SUMMARY_ROOT / "docs"


def project_rel(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def existing_subtitle_order() -> dict[str, int]:
    index_path = SUBTITLE_ROOT / "INDEX.md"
    if not index_path.exists():
        return {}
    order: dict[str, int] = {}
    for idx, line in enumerate(read_text(index_path).splitlines()):
        match = re.match(r"- \[([^\]]+)\]\(docs/[^)]+\.subtitles\.md\)", line)
        if match:
            order[match.group(1)] = idx
    return order


def parse_location(value: str) -> tuple[str, str, str]:
    parts = [part.strip() for part in value.split(" / ") if part.strip()]
    if not parts:
        return "未标注线路", "未标注章节", "unknown"
    chapter = parts[-1] if parts[-1].startswith("chapter") else "unknown"
    if chapter != "unknown":
        parts = parts[:-1]
    line_title = parts[0] if parts else "未标注线路"
    chapter_title = " / ".join(parts[1:]) if len(parts) > 1 else line_title
    return line_title, chapter_title, chapter


def parse_subtitle_doc(path: Path, order: dict[str, int]) -> dict[str, Any]:
    text = read_text(path)
    video_key = path.name.removesuffix(".subtitles.md")
    meta: dict[str, str] = {}
    cue_count = 0
    has_subtitles = False
    for line in text.splitlines():
        if line.startswith("当前视频："):
            meta["current"] = line.split("：", 1)[1].strip()
        elif line.startswith("位置："):
            meta["location"] = line.split("：", 1)[1].strip()
        elif line.startswith("卡片摘要："):
            meta["annotation"] = line.split("：", 1)[1].strip()
        elif line.startswith("前置选择："):
            meta["upstream_choice"] = line.split("：", 1)[1].strip()
        elif line.startswith("前一视频："):
            meta["previous_video"] = line.split("：", 1)[1].strip()
        elif line.startswith("后续节点："):
            meta["next_node"] = line.split("：", 1)[1].strip()
        elif re.match(r"^\d+\.\s+`", line):
            cue_count += 1
            has_subtitles = True
    line_title, chapter_title, chapter = parse_location(meta.get("location", ""))
    return {
        "video_key": video_key,
        "path": project_rel(path),
        "doc_link": f"docs/{path.name}",
        "line_title": line_title,
        "chapter_title": chapter_title,
        "chapter": chapter,
        "location": meta.get("location", ""),
        "annotation": meta.get("annotation", ""),
        "upstream_choice": meta.get("upstream_choice", ""),
        "previous_video": meta.get("previous_video", ""),
        "next_node": meta.get("next_node", ""),
        "cue_count": cue_count,
        "has_subtitles": has_subtitles,
        "order": order.get(video_key, 10_000_000),
    }


def subtitle_docs() -> list[dict[str, Any]]:
    order = existing_subtitle_order()
    docs = [parse_subtitle_doc(path, order) for path in sorted(SUBTITLE_DOC_DIR.glob("*.subtitles.md"))]
    return sorted(docs, key=lambda row: (row["order"], row["video_key"]))


def entry_line(row: dict[str, Any]) -> str:
    cue_note = f"{row['cue_count']} 条字幕" if row["has_subtitles"] else "无字幕"
    extra: list[str] = [cue_note]
    if row["upstream_choice"]:
        extra.append(f"前置：{row['upstream_choice']}")
    if row["next_node"]:
        extra.append(f"后续：{row['next_node']}")
    return f"- [{row['video_key']}]({row['doc_link']})：{'；'.join(extra)}"


def write_subtitle_indexes(rows: list[dict[str, Any]]) -> None:
    by_chapter: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_chapter[row["chapter"]].append(row)

    chapter_lines = [
        "# Video Key 字幕文档 - 按章节索引",
        "",
        "本索引由 `tools/build_knowledge_navigation.py` 生成。具体视频事实仍以 `docs/<videoKey>.subtitles.md` 为准。",
        "",
        f"- 文档数：{len(rows)}",
        f"- 有字幕：{sum(1 for row in rows if row['has_subtitles'])}",
        f"- 无字幕：{sum(1 for row in rows if not row['has_subtitles'])}",
        "",
    ]
    for chapter, chapter_rows in sorted(by_chapter.items(), key=lambda item: min(row["order"] for row in item[1])):
        first = chapter_rows[0]
        title = first["chapter_title"]
        line_title = first["line_title"]
        chapter_lines.extend(
            [
                f"## {chapter} - {line_title} / {title}",
                "",
                f"- 视频文档：{len(chapter_rows)}",
                "",
            ]
        )
        chapter_lines.extend(entry_line(row) for row in chapter_rows)
        chapter_lines.append("")
    write_text(SUBTITLE_ROOT / "INDEX_BY_CHAPTER.md", "\n".join(chapter_lines))

    by_route: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_route[row["line_title"]].append(row)
    route_lines = [
        "# Video Key 字幕文档 - 按线路索引",
        "",
        "本索引由 `tools/build_knowledge_navigation.py` 生成。用于按线路进入字幕片段；具体视频事实仍以对应 `.subtitles.md` 为准。",
        "",
    ]
    for route, route_rows in sorted(by_route.items(), key=lambda item: min(row["order"] for row in item[1])):
        route_lines.extend([f"## {route}", "", f"- 视频文档：{len(route_rows)}", ""])
        route_chapters: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in route_rows:
            route_chapters[row["chapter"]].append(row)
        for chapter, chapter_rows in sorted(route_chapters.items(), key=lambda item: min(row["order"] for row in item[1])):
            title = chapter_rows[0]["chapter_title"]
            route_lines.extend([f"### {chapter} - {title}", ""])
            route_lines.extend(entry_line(row) for row in chapter_rows)
            route_lines.append("")
    write_text(SUBTITLE_ROOT / "INDEX_BY_ROUTE.md", "\n".join(route_lines))


def infer_video_key(row: dict[str, Any]) -> str:
    explicit = str(row.get("video_key") or "").strip()
    if explicit:
        return explicit
    return "unknown"


def safe_summary_filename(video_key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", video_key) + ".summary.md"


def summary_status(row: dict[str, Any]) -> str:
    raw = str(row.get("status") or "final").strip()
    return raw or "final"


def read_summary_rows() -> list[dict[str, Any]]:
    if not SUMMARY_JSONL.exists():
        return []
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(read_text(SUMMARY_JSONL).splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            rows.append(
                {
                    "line_number": index,
                    "video_key": "invalid_json",
                    "status": "invalid",
                    "summary": {"display_summary": "JSON 解析失败"},
                }
            )
            continue
        row["line_number"] = index
        row["video_key"] = infer_video_key(row)
        row["status"] = summary_status(row)
        rows.append(row)
    return rows


def markdown_list(value: Any) -> list[str]:
    if not value:
        return ["- 无"]
    if isinstance(value, list):
        return [f"- {item}" for item in value]
    return [f"- {value}"]


def summary_source_label(row: dict[str, Any]) -> str:
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    kind = str(source.get("kind") or "").strip()
    model = str(source.get("model") or "").strip()
    if kind == "ai_generated_summary" and model:
        return f"{model} 生成"
    if kind == "metadata_context_summary":
        basis = source.get("basis")
        if isinstance(basis, list) and basis:
            labels = {
                "official_annotation": "官方摘要",
                "storyline_title": "剧情标题",
                "neighboring_nodes": "相邻节点",
            }
            return "无字幕节点整理（" + "、".join(labels.get(str(item), str(item)) for item in basis) + "）"
        return "无字幕节点整理"
    if model:
        return model
    return "未标注"


def write_summary_doc(video_key: str, records: list[dict[str, Any]]) -> None:
    lines = [
        f"# {video_key} 摘要",
        "",
        "本文件保存该 video key 的 Markdown 摘要；前端剧情摘要直接读取本文件的 `### display_summary` 段。人工修正展示内容时，优先修改本 MD。",
        "",
        f"- video key：`{video_key}`",
        f"- 记录数：{len(records)}",
        "- 使用边界：本摘要层可作为剧情上下文和长距离回顾；生成或重写目标视频摘要时，不读取目标视频自己的既有摘要；事实核验仍回到目标字幕、路线图和档案正文。",
        "",
    ]
    for idx, row in enumerate(records, start=1):
        summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
        lines.extend(
            [
                f"## 记录 {idx}",
                "",
                f"- 来源：{summary_source_label(row)}",
                f"- confidence：`{summary.get('confidence', '')}`",
                "",
                "### display_summary",
                "",
                str(summary.get("display_summary") or "无"),
                "",
                "### detailed_summary",
                "",
            ]
        )
        lines.extend(markdown_list(summary.get("detailed_summary")))
        lines.extend(["", "### event_facts", ""])
        event_facts = summary.get("event_facts") or []
        if event_facts:
            for fact in event_facts:
                if not isinstance(fact, dict):
                    lines.append(f"- {fact}")
                    continue
                evidence = fact.get("evidence") or []
                evidence_text = "；".join(str(item) for item in evidence) if evidence else "无 evidence"
                lines.append(f"- {fact.get('fact', '')}（证据：{evidence_text}）")
        else:
            lines.append("- 无")
        lines.extend(["", "### context_refs", ""])
        lines.extend(markdown_list(summary.get("context_refs")))
        lines.extend(["", "### risk_flags", ""])
        lines.extend(markdown_list(summary.get("risk_flags")))
        lines.append("")
    write_text(SUMMARY_DOC_DIR / safe_summary_filename(video_key), "\n".join(lines))


def write_summary_indexes(rows: list[dict[str, Any]]) -> None:
    by_video: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_video[str(row.get("video_key") or "unknown")].append(row)

    index_lines = [
        "# 视频摘要索引",
        "",
        "本索引按 video key 指向独立剧情摘要文档，便于检索上下文和长距离剧情回顾。",
        "",
        "## 使用边界",
        "",
        "- 生成或重写某个目标视频摘要时，不读取目标视频自己的既有摘要。",
        "- 同路线、图顺序早于目标节点的摘要可作为辅助上下文；兄弟分支和后文摘要只用于判断路线位置与差异。",
        "- 摘要层不是一手事实源；事实核验仍回到目标字幕、路线图、官方字段和档案正文。",
        "",
        "## 统计",
        "",
        f"- 总记录数：{len(rows)}",
        f"- video key 数：{len(by_video)}",
    ]
    source_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        source_counts[summary_source_label(row)] += 1
    for source, count in sorted(source_counts.items()):
        index_lines.append(f"- {source}：{count}")
    index_lines.extend(["", "## 文档", ""])
    for video_key, records in sorted(by_video.items()):
        confidences = sorted(
            {
                str((row.get("summary") or {}).get("confidence") or "unknown")
                for row in records
                if isinstance(row.get("summary"), dict)
            }
        )
        confidence_text = "、".join(confidences) if confidences else "unknown"
        index_lines.append(
            f"- [{video_key}](docs/{safe_summary_filename(video_key)})：记录 {len(records)}；confidence {confidence_text}"
        )
    write_text(SUMMARY_ROOT / "INDEX.md", "\n".join(index_lines))

    readme_lines = [
        "# 视频摘要",
        "",
        "本目录保存按 video key 组织的剧情摘要层，用于补充上下文、回顾长距离前因后果和辅助路线理解。",
        "",
        "## 文件",
        "",
        "- `docs/<videoKey>.summary.md`：每个 video key 的 Markdown 摘要文档；人工修正和前端展示以这里的 `display_summary` 段为准。",
        "- `video_summaries.jsonl`：由 Markdown 摘要同步出的结构化摘要记录，保留批量生成结果和来源信息。",
        "- `INDEX.md`：按 video key 进入摘要文档的检索索引。",
        "",
        "## 来源标记",
        "",
        "- `source.kind = ai_generated_summary` 且 `source.model = DeepSeek V4 Flash`：由 DeepSeek V4 Flash 生成的有字幕剧情摘要。",
        "- `source.kind = metadata_context_summary`：无字幕节点摘要，依据官方摘要、剧情标题、节点元数据和相邻节点整理。",
        "",
        "## 使用边界",
        "",
        "- 目标视频自己的既有摘要不能作为生成或重写该目标摘要的输入。",
        "- 可读取同路线、图顺序早于目标节点的摘要来补充前文；后文和兄弟分支只用于判断路线位置与差异。",
        "- 具体事实仍以目标字幕片段、路线图、官方字段和档案正文为准。",
    ]
    write_text(SUMMARY_ROOT / "README.md", "\n".join(readme_lines))


def main() -> int:
    rows = subtitle_docs()
    write_subtitle_indexes(rows)
    summary_rows = sync_video_summaries_from_md.parse_summary_docs()
    if not summary_rows:
        summary_rows = read_summary_rows()
    write_summary_indexes(summary_rows)
    print(f"subtitle_docs={len(rows)}")
    print(f"summary_records={len(summary_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
