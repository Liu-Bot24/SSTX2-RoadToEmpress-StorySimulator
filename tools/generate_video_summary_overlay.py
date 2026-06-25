from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRAPH_DIR = PROJECT_ROOT / "data" / "game" / "storyline_graph"
GRAPH_DATA = GRAPH_DIR / "storyline_graph_data.json"
SUBTITLE_DOC_DIR = PROJECT_ROOT / "data" / "knowledge" / "video_subtitles" / "docs"
OVERLAY_DIR = PROJECT_ROOT / "data" / "runtime" / "summary_generation"
PACK_DIR = OVERLAY_DIR / "evidence_packs"
RUN_DIR = OVERLAY_DIR / "runs"
SUMMARY_JSONL = PROJECT_ROOT / "data" / "knowledge" / "video_summaries" / "video_summaries.jsonl"
SUMMARY_APPEND_LOCK = threading.Lock()
KNOWLEDGE_GUIDE = PROJECT_ROOT / "data" / "knowledge" / "AGENT_GUIDE.md"
SUMMARY_TASK_GUIDE = PROJECT_ROOT / "data" / "knowledge" / "task_guides" / "summary_generation.md"
STORYLINE_GUIDE = PROJECT_ROOT / "data" / "knowledge" / "storyline_guide.md"
SUMMARY_INDEX = PROJECT_ROOT / "data" / "knowledge" / "video_summaries" / "INDEX.md"
KNOWLEDGE_ROOT = PROJECT_ROOT / "data" / "knowledge" / "dossiers"
KNOWLEDGE_DOC_DIRS = (
    (KNOWLEDGE_ROOT / "characters", "character"),
    (KNOWLEDGE_ROOT / "items", "item"),
    (KNOWLEDGE_ROOT / "aliases" / "characters", "character_alias"),
)

TEST_MODEL = "gemini-3.5-flash"
FORMAL_PRIMARY_MODEL = "gemini-3.1-pro-preview"
FORMAL_FALLBACK_MODEL = "gemini-3.5-flash"
CLAUDE_TEST_MODEL = "deepseek-v4-flash"
CLAUDE_TIMEOUT_SEC = int(os.environ.get("SSTX2_CLAUDE_TIMEOUT_SEC", "600"))

KEYLIKE_RE = re.compile(r"^[A-Za-z0-9_]+$")
UNSAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
SUBTITLE_EVIDENCE_RE = re.compile(r"^subtitle:(?P<source>[^:]+):(?P<start>\d+)(?:-(?P<end>\d+))?$")
OFFICIAL_EVIDENCE_RE = re.compile(r"^official_annotation:target$")
METADATA_EVIDENCE_RE = re.compile(r"^metadata:target(?::(?P<field>[A-Za-z0-9_.-]+))?$")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def project_path(path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (PROJECT_ROOT / path).resolve()


def project_rel(path: Path) -> str:
    return str(project_path(path).relative_to(PROJECT_ROOT)).replace("\\", "/")


def safe_filename_part(value: str) -> str:
    return UNSAFE_FILENAME_RE.sub("-", value).strip("-") or "model"


def safe_summary_filename(video_key: str) -> str:
    return f"{safe_filename_part(video_key)}.summary.md"


def cli_command(name: str) -> list[str]:
    binary = shutil.which(name)
    if not binary:
        raise SystemExit(f"{name} CLI was not found on PATH.")
    if binary.lower().endswith(".ps1"):
        return ["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", binary]
    return [binary]


def valid_official_annotation(node: dict[str, Any]) -> str:
    annotation = str(node.get("annotation") or "").strip()
    video_key = str(node.get("videoKey") or "").strip()
    if not annotation or annotation == video_key or KEYLIKE_RE.fullmatch(annotation):
        return ""
    return annotation


def effective_metadata_title(node: dict[str, Any]) -> str:
    video_key = str(node.get("videoKey") or "").strip()
    for key in ("storylineTitle", "title"):
        value = str(node.get(key) or "").strip()
        if value and value != video_key and not KEYLIKE_RE.fullmatch(value):
            return value
    return ""


def load_graph() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    data = read_json(GRAPH_DATA)
    nodes: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    incoming: dict[str, list[dict[str, Any]]] = {}
    for chapter_index, chapter in enumerate(data.get("chapters", [])):
        for order, node in enumerate(chapter.get("nodes", [])):
            node = dict(node)
            node["_chapterIndex"] = chapter_index
            node["_order"] = order
            node["_graphChapterTitle"] = chapter.get("title")
            nodes.append(node)
            by_id[node["id"]] = node
    for node in nodes:
        for edge in node.get("edges") or []:
            target_id = edge.get("resolvedTargetId") or edge.get("targetId")
            if not target_id:
                continue
            incoming.setdefault(target_id, []).append({"source": node["id"], "edge": edge})
    return nodes, by_id, incoming


def find_target(nodes: list[dict[str, Any]], chapter: str, video_key: str, node_id: str | None = None) -> dict[str, Any]:
    if node_id:
        matches = [node for node in nodes if node.get("id") == node_id]
    else:
        matches = [
            node
            for node in nodes
            if node.get("chapter") == chapter and node.get("videoKey") == video_key and node.get("kind") != "ShowChoice"
        ]
    if not matches:
        raise SystemExit(f"No video node found for {chapter}/{video_key}" + (f" node={node_id}" if node_id else ""))
    if len(matches) > 1 and not node_id:
        choices = "\n".join(f"- {item['id']} {item.get('lineTitle')} {item.get('chapterTitle')}" for item in matches[:20])
        raise SystemExit(f"Multiple nodes found for {chapter}/{video_key}; pass --node-id.\n{choices}")
    return matches[0]


def subtitle_doc_path(node: dict[str, Any]) -> Path:
    video_key = str(node.get("videoKey") or "").strip()
    if not video_key:
        raise SystemExit(f"Node has no videoKey: {node.get('id')}")
    direct = SUBTITLE_DOC_DIR / f"{video_key}.subtitles.md"
    if direct.exists():
        return direct
    matches = sorted(SUBTITLE_DOC_DIR.glob(f"{video_key}.*.subtitles.md"))
    if matches:
        return matches[0]
    raise SystemExit(
        f"Subtitle doc not found for {video_key}. Run `python tools\\export_video_key_subtitle_docs.py` first."
    )


def read_subtitle_doc(node: dict[str, Any]) -> tuple[Path, str]:
    path = subtitle_doc_path(node)
    return path, path.read_text(encoding="utf-8")


def subtitle_cue_count_from_text(text: str) -> int:
    return len(re.findall(r"^\s*\d+\.\s+`", text, flags=re.MULTILINE))


def node_label(node: dict[str, Any]) -> str:
    return str(
        node.get("storylineTitle")
        or node.get("title")
        or valid_official_annotation(node)
        or node.get("annotation")
        or node.get("videoKey")
        or node.get("kind")
        or ""
    ).strip()


def compact_node(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": node.get("id"),
        "kind": node.get("kind"),
        "chapter": node.get("chapter"),
        "chapterTitle": node.get("chapterTitle"),
        "lineTitle": node.get("lineTitle"),
        "videoKey": node.get("videoKey"),
        "title": node.get("title"),
        "storylineTitle": node.get("storylineTitle"),
        "annotation": node.get("annotation"),
        "officialSummary": valid_official_annotation(node),
        "label": node_label(node),
    }


def nearest_upstream_choice(
    target_id: str,
    by_id: dict[str, dict[str, Any]],
    incoming: dict[str, list[dict[str, Any]]],
    max_depth: int = 24,
) -> dict[str, Any] | None:
    queue: deque[tuple[str, list[dict[str, Any]]]] = deque([(target_id, [])])
    seen = {target_id}
    while queue:
        node_id, path = queue.popleft()
        if len(path) >= max_depth:
            continue
        for item in incoming.get(node_id, []):
            source_id = item["source"]
            if source_id in seen:
                continue
            seen.add(source_id)
            source = by_id.get(source_id)
            if not source:
                continue
            next_path = [{"node": source_id, "edge": item["edge"]}, *path]
            if source.get("kind") == "ShowChoice":
                return {"node": source, "edge": item["edge"], "path": next_path}
            queue.append((source_id, next_path))
    return None


def upstream_videos(
    start_id: str,
    by_id: dict[str, dict[str, Any]],
    incoming: dict[str, list[dict[str, Any]]],
    limit: int = 4,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    current = start_id
    seen = {current}
    while len(result) < limit:
        parents = incoming.get(current) or []
        if not parents:
            break
        source_id = parents[0]["source"]
        if source_id in seen:
            break
        seen.add(source_id)
        node = by_id.get(source_id)
        if not node:
            break
        if node.get("videoKey") and node.get("kind") != "ShowChoice":
            result.append(node)
        current = source_id
    result.reverse()
    return result


def downstream_nodes(
    node: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    summaries: dict[str, dict[str, Any]],
    limit: int = 3,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for edge in node.get("edges") or []:
        target_id = edge.get("resolvedTargetId") or edge.get("targetId")
        target = by_id.get(target_id or "")
        if target:
            item = context_node(target, summaries)
            item["viaEdge"] = {
                "choiceIndex": edge.get("choiceIndex"),
                "choiceText": edge.get("choiceText"),
                "targetLabel": edge.get("targetLabel"),
            }
            result.append(item)
        if len(result) >= limit:
            break
    return result


def sibling_branches(
    choice: dict[str, Any] | None,
    by_id: dict[str, dict[str, Any]],
    summaries: dict[str, dict[str, Any]],
    target_id: str,
) -> list[dict[str, Any]]:
    if not choice:
        return []
    result: list[dict[str, Any]] = []
    for edge in choice.get("edges") or []:
        sibling_id = edge.get("resolvedTargetId") or edge.get("targetId")
        sibling = by_id.get(sibling_id or "")
        if not sibling:
            continue
        result.append(
            {
                "isTarget": sibling_id == target_id,
                "choiceIndex": edge.get("choiceIndex"),
                "choiceText": edge.get("choiceText"),
                "target": context_node(sibling, summaries),
            }
        )
    return result


def knowledge_card_label(doc_type: str) -> str:
    if doc_type == "character":
        return "人物档案"
    if doc_type == "character_alias":
        return "人物导航"
    if doc_type == "item":
        return "词条档案"
    return "知识库文档"


def knowledge_card_label_for_path(path: Path, fallback: str = "知识库文档") -> str:
    rel = project_rel(path)
    if "/characters/" in rel.replace("\\", "/"):
        if "/reference/" in rel.replace("\\", "/"):
            return "前作/旧作参考人物资料"
        return "人物档案"
    if "/items/" in rel.replace("\\", "/"):
        return "词条档案"
    return fallback


def knowledge_doc_aliases(body: str) -> list[str]:
    aliases = re.findall(
        r"^\s*-\s*([^：`\n]+)：`Character_[^`]+`\s*/\s*`tag_[^`]+`",
        body,
        re.MULTILINE,
    )
    return sorted({alias.strip() for alias in aliases if alias.strip()})


def title_from_markdown(body: str, path: Path) -> str:
    title_match = re.search(r"^#\s+(.+?)\s*$", body, re.MULTILINE)
    return title_match.group(1).strip() if title_match else path.stem.split("__", 1)[0]


def alias_target_path(alias_path: Path, body: str) -> Path | None:
    match = re.search(r"^\s*-\s*指向人物：\[[^\]]+\]\(([^)]+)\)", body, re.MULTILINE)
    if not match:
        return None
    target = (alias_path.parent / match.group(1)).resolve()
    try:
        target.relative_to(PROJECT_ROOT)
    except ValueError:
        return None
    if not target.exists() or target.suffix.lower() != ".md":
        return None
    return target


@lru_cache(maxsize=1)
def load_knowledge_documents() -> tuple[dict[str, Any], ...]:
    docs: list[dict[str, Any]] = []
    for directory, doc_type in KNOWLEDGE_DOC_DIRS:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            if path.name == "README.md":
                continue
            body = path.read_text(encoding="utf-8")
            name = title_from_markdown(body, path)
            if not name or name == "README":
                continue
            target_path = alias_target_path(path, body) if doc_type == "character_alias" else None
            docs.append(
                {
                    "type": doc_type,
                    "name": name,
                    "path": project_rel(path),
                    "absolutePath": path,
                    "cardLabel": knowledge_card_label(doc_type),
                    "aliases": knowledge_doc_aliases(body),
                    "body": body,
                    "targetPath": target_path,
                }
            )
    return tuple(docs)


def knowledge_document_content(body: str) -> str:
    return body.strip()


def make_knowledge_card(
    *,
    row_type: str,
    name: str,
    card_label: str,
    path: Path | str,
    body: str,
    matched_terms: list[str],
    source_note: str,
) -> dict[str, Any]:
    content = knowledge_document_content(body)
    return {
        "type": row_type,
        "name": name,
        "cardLabel": card_label,
        "path": project_rel(Path(path)) if isinstance(path, Path) else path,
        "matchedTerms": matched_terms,
        "sourceNote": source_note,
        "content": content,
    }


def knowledge_cards(text: str) -> list[dict[str, Any]]:
    docs = load_knowledge_documents()
    matched_docs: list[tuple[int, int, dict[str, Any], str, str, str, list[str]]] = []
    for doc in docs:
        name = doc["name"]
        terms = [name, *doc.get("aliases", [])]
        matched_terms = [term for term in terms if len(term) >= 2 and term in text]
        if not matched_terms:
            continue
        row_type = doc["type"]
        card_label = doc["cardLabel"]
        matched_docs.append(
            (
                min(text.find(term) for term in matched_terms),
                -max(len(term) for term in matched_terms),
                doc,
                name,
                row_type,
                card_label,
                matched_terms,
            )
        )
    matched_docs.sort(key=lambda item: (item[0], item[1]))

    hits: list[dict[str, Any]] = []
    used_paths: set[str] = set()
    for _, _, doc, name, row_type, card_label, matched_terms in matched_docs:
        path_key = str(doc["path"])
        if path_key not in used_paths:
            used_paths.add(path_key)
            hits.append(
                make_knowledge_card(
                    row_type=row_type,
                    name=name,
                    card_label=card_label,
                    path=doc["path"],
                    body=doc["body"],
                    matched_terms=matched_terms,
                    source_note="完整 Markdown 文档；脚本只负责召回，不裁剪正文、不解释关系。",
                )
            )
        target_path = doc.get("targetPath")
        if row_type == "character_alias" and target_path:
            target_body = target_path.read_text(encoding="utf-8")
            target_name = title_from_markdown(target_body, target_path)
            target_key = project_rel(target_path)
            if target_key not in used_paths:
                used_paths.add(target_key)
                hits.append(
                    make_knowledge_card(
                        row_type="character",
                        name=target_name,
                        card_label=knowledge_card_label_for_path(target_path, "人物档案"),
                        path=target_path,
                        body=target_body,
                        matched_terms=matched_terms,
                        source_note=f"由别名/称号导航 `{name}` 指向；这是被导航到的完整人物档案。",
                    )
                )
    return hits


def video_key_from_run_path(value: str) -> str:
    name = Path(value).name
    for marker in (".claude-", ".gemini-", ".metadata-only-"):
        if marker in name:
            return name.split(marker, 1)[0]
    if "." in name:
        return name.split(".", 1)[0]
    return name


def load_existing_summaries() -> dict[str, dict[str, Any]]:
    if not SUMMARY_JSONL.exists():
        return {}
    summaries: dict[str, dict[str, Any]] = {}
    for line in SUMMARY_JSONL.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        status = str(row.get("status") or "final").strip()
        if status and status != "final":
            continue
        video_key = str(row.get("video_key") or "").strip()
        if not video_key:
            continue
        summary = row.get("summary")
        if video_key and isinstance(summary, dict):
            summaries[video_key] = {
                "videoKey": video_key,
                "source": project_rel(SUMMARY_JSONL),
                "summaryDoc": project_rel(PROJECT_ROOT / "data" / "knowledge" / "video_summaries" / "docs" / safe_summary_filename(video_key)),
                "status": "final",
                "sourceType": "ai_generated_summary",
                "usage": (
                    "辅助背景；不能替代目标字幕、路线图、人物/物品档案等一手来源。"
                    "生成目标视频摘要时不得读取目标视频自身摘要。"
                ),
            }
    return summaries


def context_node(node: dict[str, Any], summaries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    item = compact_node(node)
    video_key = str(node.get("videoKey") or "").strip()
    if video_key and video_key in summaries:
        item["existingOverlaySummaryRef"] = summaries[video_key]
    return item


def line_chapter_context(target: dict[str, Any], nodes: list[dict[str, Any]]) -> dict[str, Any]:
    line_title = str(target.get("lineTitle") or "")
    chapter = str(target.get("chapter") or "")
    line_nodes = [node for node in nodes if str(node.get("lineTitle") or "") == line_title]

    line_chapters: list[dict[str, Any]] = []
    seen_chapters: set[str] = set()
    for node in line_nodes:
        node_chapter = str(node.get("chapter") or "")
        if not node_chapter or node_chapter in seen_chapters:
            continue
        seen_chapters.add(node_chapter)
        line_chapters.append(
            {
                "chapter": node_chapter,
                "title": node.get("_graphChapterTitle") or node.get("chapterTitle"),
            }
        )

    chapter_nodes = [node for node in line_nodes if str(node.get("chapter") or "") == chapter]
    episode_sequence: list[dict[str, Any]] = []
    seen_episodes: set[str] = set()
    for node in chapter_nodes:
        key = str(node.get("navKey") or node.get("episodeLabel") or node.get("chapterTitle") or "")
        if not key or key in seen_episodes:
            continue
        seen_episodes.add(key)
        episode_sequence.append(
            {
                "navKey": node.get("navKey"),
                "episode": node.get("episode"),
                "episodeSuffix": node.get("episodeSuffix"),
                "episodeLabel": node.get("episodeLabel") or node.get("chapterTitle"),
            }
        )

    return {
        "lineTitle": line_title,
        "lineChaptersInGraphOrder": line_chapters,
        "currentChapter": {
            "chapter": chapter,
            "title": target.get("_graphChapterTitle") or target.get("chapterTitle"),
            "episodeSequenceInChapter": episode_sequence,
        },
        "targetPosition": {
            "chapterIndex": target.get("_chapterIndex"),
            "nodeOrderInChapter": target.get("_order"),
            "episodeLabel": target.get("episodeLabel") or target.get("chapterTitle"),
            "navKey": target.get("navKey"),
        },
        "guardrail": "只允许使用同一 lineTitle 的前文作为路线背景；女帝线、新世界线、前情提要不能互相补剧情。",
    }


def choice_context(
    choice: dict[str, Any] | None,
    edge_to_target: dict[str, Any] | None,
    by_id: dict[str, dict[str, Any]],
    summaries: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if not choice:
        return None
    selected_target_id = ""
    if edge_to_target:
        selected_target_id = str(edge_to_target.get("resolvedTargetId") or edge_to_target.get("targetId") or "")
    options: list[dict[str, Any]] = []
    for edge in choice.get("edges") or []:
        target_id = str(edge.get("resolvedTargetId") or edge.get("targetId") or "")
        target = by_id.get(target_id)
        options.append(
            {
                "choiceIndex": edge.get("choiceIndex"),
                "choiceText": edge.get("choiceText"),
                "isTargetChoice": bool(selected_target_id and target_id == selected_target_id),
                "targetLabel": edge.get("targetLabel") or edge.get("resolvedTargetLabel"),
                "targetKind": edge.get("targetKind"),
                "targetVideoKey": edge.get("targetVideoKey"),
                "target": context_node(target, summaries) if target else None,
            }
        )
    return {
        "choiceNode": compact_node(choice),
        "question": choice.get("title"),
        "storylineTitle": choice.get("storylineTitle"),
        "selectedChoice": next((item for item in options if item["isTargetChoice"]), None),
        "allOptions": options,
    }


def prior_generated_summaries(
    target: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    incoming: dict[str, list[dict[str, Any]]],
    summaries: dict[str, dict[str, Any]],
    limit: int = 4,
) -> list[dict[str, Any]]:
    target_id = str(target.get("id") or "")
    previous = upstream_videos(target_id, by_id, incoming, limit=limit)
    result: list[dict[str, Any]] = []
    for node in reversed(previous):
        video_key = str(node.get("videoKey") or "").strip()
        if video_key and video_key in summaries:
            result.append(context_node(node, summaries))
    for item in result:
        item["routeContext"] = "从目标节点沿剧情图逐级向上追溯的最近视频链；同一选择的兄弟分支不是本路径前文。"
    return result


def build_pack(chapter: str, video_key: str, node_id: str | None = None) -> Path:
    nodes, by_id, incoming = load_graph()
    target = find_target(nodes, chapter, video_key, node_id)
    summaries = load_existing_summaries()
    context_summaries = dict(summaries)
    target_video_key = str(target.get("videoKey") or "").strip()
    if target_video_key:
        context_summaries.pop(target_video_key, None)
    upstream_choice_info = nearest_upstream_choice(target["id"], by_id, incoming)
    choice_node = upstream_choice_info["node"] if upstream_choice_info else None
    previous = upstream_videos(target["id"], by_id, incoming)
    downstream = downstream_nodes(target, by_id, context_summaries)
    siblings = sibling_branches(choice_node, by_id, context_summaries, target["id"])
    subtitle_doc_path_value, subtitle_doc_text = read_subtitle_doc(target)
    subtitle_cue_count = subtitle_cue_count_from_text(subtitle_doc_text)
    line_context = line_chapter_context(target, nodes)
    full_choice_context = choice_context(
        choice_node,
        upstream_choice_info.get("edge") if upstream_choice_info else None,
        by_id,
        context_summaries,
    )
    prior_summaries = prior_generated_summaries(target, by_id, incoming, context_summaries)

    previous_context = [context_node(node, context_summaries) for node in previous]

    official = valid_official_annotation(target)
    official_status = "available" if official else "missing"
    pack = {
        "target": compact_node(target),
        "lineContext": line_context,
        "subtitleDoc": {
            "source": "video_key_subtitle_doc",
            "videoKey": target.get("videoKey"),
            "name": subtitle_doc_path_value.name,
            "path": project_rel(subtitle_doc_path_value),
            "cueCount": subtitle_cue_count,
        },
        "agentGuide": {
            "source": "knowledge_agent_guide",
            "path": project_rel(KNOWLEDGE_GUIDE),
        },
        "summaryTaskGuide": {
            "source": "summary_generation_task_guide",
            "path": project_rel(SUMMARY_TASK_GUIDE),
        },
        "storylineGuide": {
            "source": "storyline_query_guide",
            "path": project_rel(STORYLINE_GUIDE),
        },
        "storylineGraph": {
            "source": "storyline_graph_data",
            "path": project_rel(GRAPH_DATA),
        },
        "summaryIndex": {
            "source": "video_summary_index",
            "path": project_rel(SUMMARY_INDEX),
        },
        "knowledgeRoots": [
            {"type": "characters", "path": project_rel(KNOWLEDGE_ROOT / "characters")},
            {"type": "items", "path": project_rel(KNOWLEDGE_ROOT / "items")},
            {"type": "character_aliases", "path": project_rel(KNOWLEDGE_ROOT / "aliases" / "characters")},
            {"type": "reference", "path": project_rel(KNOWLEDGE_ROOT / "reference")},
        ],
        "officialAnnotationStatus": official_status,
        "officialAnnotation": official or str(target.get("annotation") or ""),
        "readStrategy": {
            "subtitleCueCount": subtitle_cue_count,
            "minimalPathForEmptySubtitle": (
                "若目标字幕文档无字幕且官方摘要/目标元数据已足够说明本节点，只需读取知识库导览、摘要生成导引、路线图导引和目标字幕文档；"
                "不要为泛称、短句或无具体人物/物品的官方摘要额外检索档案。"
            ),
            "whenToSearchDossiers": (
                "只有当目标字幕、官方摘要、上游选择或相邻节点出现需要消歧的人物、物品、地名、称谓时，才使用 Grep/Glob/Read 查找并读取对应 Markdown。"
            ),
        },
        "upstreamChoice": compact_node(choice_node) if choice_node else None,
        "upstreamChoiceEdgeToTarget": upstream_choice_info.get("edge") if upstream_choice_info else None,
        "upstreamChoiceContext": full_choice_context,
        "priorGeneratedSummariesInSameLine": prior_summaries,
        "previousVideosInGraphOrder": previous_context,
        "downstreamNodes": downstream,
        "siblingBranchesFromSameChoice": siblings,
    }

    text = render_pack(pack)
    out = PACK_DIR / chapter / f"{video_key}.md"
    write_text(out, text)
    return out


def render_pack(pack: dict[str, Any]) -> str:
    lines: list[str] = []
    target = pack["target"]
    lines.append(f"# Agentic 摘要任务: {target['chapter']} / {target['videoKey']}")
    lines.append("")
    lines.append("## 硬规则")
    lines.append("")
    lines.append("- 本文件是任务简报，不是完整证据包；必须使用 Claude Code 的 Read/Grep/Glob 等工具主动读取下列项目文件。")
    lines.append("- 本任务只允许读取资料；禁止使用 Write/Edit/MultiEdit/NotebookEdit/TaskUpdate，禁止创建或修改摘要文件。最终只在本次回答中输出 JSON。")
    lines.append("- 禁止读取 Claude Code 的长期记忆、会话导出或自动 memory 文件；资料只来自任务简报列出的项目路径。")
    lines.append("- 不要重复 Read 已读文件；如果已经读到目标字幕、必要导览和必要上下文，立即调用 StructuredOutput 输出结果。")
    lines.append("- 若目标字幕文档无字幕且官方摘要/目标元数据已足够说明本节点，只读必要导览和目标字幕文档即可；不要为泛称、短句或无具体人物/物品的官方摘要额外检索档案。")
    lines.append("- 用户不会提供 choice key、video key 或人物/词条 key；本任务中的 key 来自运行状态、路线图或批处理调度。")
    lines.append("- 需要当前游戏状态时，当前节点和当前选择必须来自后台日志、存档、HTML state、模拟器 state 或外层运行器传入的结构化状态。")
    lines.append("- 不要要求用户提供 key，也不要把截图、人工口述或猜测当成常规定位方式。")
    lines.append("- 先读取知识库导览、摘要生成导引、路线图导引，再读取目标视频片段文档；全量路线 JSON 只在任务简报不足以判断路线位置、合流或条件节点时精准复核，不要反复整文件读取。")
    lines.append("- 目标视频事实只能来自目标视频片段文档里的字幕和目标官方摘要。")
    lines.append("- 前置选择的问题、选项文本和流向用于理解本视频缘起，可以写入 context_refs。")
    lines.append("- 同线路已生成前文摘要可作为 AI 辅助背景；必须视为次级材料，不能替代目标字幕、路线图和档案正文。")
    lines.append("- 前文摘要只指剧情图真实上游路径中的视频摘要；同一选择的兄弟分支不是前一个视频，不能当作本路径前文。")
    lines.append("- 目标视频自己的既有摘要禁止读取；后文、兄弟分支只能用于理解位置和差异，不能写成目标视频已发生事实。")
    lines.append("- 人物/词条资料必须按需主动读取完整 Markdown 档案；它们只用于辨识身份、称谓和名词，不能写成目标视频已发生事实。")
    lines.append("- 人物档案文件名通常带有配置 id 和 tag，不要按人名直接拼 `<人名>.md`；先读 `data/knowledge/dossiers/characters/README.md`、`data/knowledge/dossiers/aliases/README.md`、`data/knowledge/dossiers/aliases/characters/README.md` 或具体别名 `.md`，拿到真实文件名后再 Read；不要把目录路径直接交给 Read。")
    lines.append("- event_facts 只写目标视频字幕或目标官方摘要明示的事实；前置选择、上游节点、后文节点和人物档案只能进入 context_refs 或 risk_flags。")
    lines.append("- display_summary 和 detailed_summary 要写成自然、连贯的剧情复述，说明人物动机、冲突和转折；不要机械改写字幕清单，也不要为了顺口牺牲证据边界。")
    lines.append("- 代词、称谓或省略主语能由当前节点、紧邻选择、目标字幕和命中档案明确消歧时，摘要应写出对应人物；不确定时才保留不确定表达，并写入 risk_flags。")
    lines.append("- `主子`、`陛下`、`皇后`、`殿下` 等关系/职位称谓不能按全局默认硬套；必须结合说话人、前后回应者、场景切换、当前路线和目标字幕判断。")
    lines.append("- 新世界线中，目标字幕或目标元数据只写“你”“主角”时，主角优先按该线身份写作“伍元照”；不要把女帝线的“伍媚娘”称呼带入新世界线。若目标字幕明确使用其他称呼，以目标字幕为准。")
    lines.append("- 不要用斜杠拼接含混称谓；不确定身份时使用自然中文，如“宫人或侍从”。")
    lines.append("- context_refs 使用自然语言说明引用到的前置选择、相邻视频、人物档案或词条，不写 `profile:`、`choice:`、`alias:` 等机读前缀。")
    lines.append("- 命中别名/称号导航时，别名文件只说明指向关系；真正的人物背景必须继续读取被导航到的完整档案。")
    lines.append("- 使用游戏内名称，不引入历史原名、史实或外部解释。")
    lines.append("- 官方摘要若残留历史原名，输出时必须改回游戏内名称，例如李治→礼治、李泰→礼泰、李弘→礼弘、武媚娘→伍媚娘。")
    lines.append("- 输出使用中文，不使用资料卡里的英文译名、英文标签或翻译说明。")
    lines.append("- 输出 JSON 字符串内不要使用英文双引号；引用称呼、标题或概念时使用中文书名号、中文引号或单引号，避免破坏 JSON。")
    lines.append("- 必须严格区分 lineTitle；女帝线、新世界线、前情提要不能串线。")
    lines.append("- evidence 只能引用目标视频片段文档 `## 字幕` 中真实存在的编号；引用末尾事实前必须核对最后一条字幕编号。")
    lines.append("- 禁止把“无字幕”写成 `subtitle:<videoKey>.subtitles.md:无字幕`；无字幕只能作为 risk_flags 或 context_refs 说明。")
    lines.append("- 输出必须是严格 JSON，不要 Markdown 代码围栏。")
    lines.append("")
    lines.append("## 知识库使用导览")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(pack["agentGuide"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("必须用 Read 工具打开该文档，不要只依赖本任务简报。")
    lines.append("")
    lines.append("## 摘要生成导引")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(pack["summaryTaskGuide"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## 路线图导引与按需原始路线图")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps({"guide": pack["storylineGuide"], "graph": pack["storylineGraph"]}, ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("必须用 Read 工具打开路线图导引。任务简报已经包含目标节点、上游选择、同线路前文、后文直接节点和兄弟分支；原始全量路线图只在这些字段不足以判断路线位置、合流或条件节点时，用 Grep 或定向 Read 精准复核，不要反复读取整份 JSON。")
    lines.append("")
    lines.append("## 目标节点")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(pack["target"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## 路线与章节导览（防止串线）")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(pack["lineContext"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## 目标视频片段文档来源")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(pack["subtitleDoc"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("必须用 Read 工具打开该字幕片段文档，并以其中 `## 字幕` 的编号作为 evidence 行号。")
    lines.append("")
    lines.append("## 读取策略")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(pack["readStrategy"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("读取策略用于控制检索范围。资料不足时可以继续查找；资料已经足够时应立即输出，不要用无意义检索延长工具轮次。")
    lines.append("")
    subtitle_doc_name = str(pack["subtitleDoc"].get("name") or "")
    lines.append("## 证据引用格式")
    lines.append("")
    lines.append(f"- event_facts[].evidence 优先使用 `subtitle:{subtitle_doc_name}:<字幕序号或范围>`。")
    lines.append("- 字幕序号指“目标视频片段文档”里 `## 字幕` 下的编号，不是原始 SRT 文件行号。")
    lines.append("- 不连续的字幕证据必须拆成多个 evidence 字符串；不要写 `1-3,7-9` 这种合并范围。")
    lines.append("- 如果某条事实只能来自目标官方摘要，使用 `official_annotation:target`。")
    lines.append("- 如果目标视频片段文档明确写着“无字幕”，只能用目标卡片摘要、剧情标题、节点类型等目标元数据生成极简摘要。")
    lines.append("- metadata evidence 只能用于目标视频无字幕时的元数据事实，固定字段为：`metadata:target:storylineTitle`、`metadata:target:title`、`metadata:target:kind`、`metadata:target:chapterTitle`、`metadata:target:lineTitle`、`metadata:target:videoKey`；目标官方摘要必须写 `official_annotation:target`，不要写 `metadata:target:annotation`。")
    lines.append("- 禁止把“无字幕”写成 `subtitle:<videoKey>.subtitles.md:无字幕`；无字幕只能作为 risk_flags 或 context_refs 说明。")
    lines.append("- 前置选择、上游视频、后文节点、合流关系和兄弟分支只能放在 context_refs 或 risk_flags，不能作为 event_facts 的 metadata evidence。")
    lines.append("- 不能引用前文、后文或兄弟分支字幕作为目标视频事实证据。")
    lines.append("")
    lines.append("## 知识库资料入口")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(pack["knowledgeRoots"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("根据目标字幕、前置选择、前后节点和摘要索引中出现且需要消歧的人物、物品、地名、称谓，主动使用 Glob/Grep/Read 查找并读取相关 Markdown。不要等待用户告诉 key；也不要在没有消歧需求时做泛化检索。")
    lines.append("")
    lines.append("## 已生成摘要索引")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(pack["summaryIndex"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("需要更远前文时，先读该索引，再读取同线路、目标之前的摘要文档。已生成摘要可以参考，但不能作为事实优先来源。")
    lines.append("")
    lines.append("## 官方摘要")
    lines.append("")
    lines.append(f"- status: `{pack['officialAnnotationStatus']}`")
    lines.append(f"- annotation: {pack['officialAnnotation']}")
    lines.append("")
    lines.append("## 上游选择全貌（问题、所有选项、当前选项）")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(pack["upstreamChoiceContext"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## 上游最近选择")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(pack["upstreamChoice"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("### 当前目标对应的选择边")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(pack["upstreamChoiceEdgeToTarget"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## 同线路已生成前文摘要索引（只作辅助上下文）")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(pack["priorGeneratedSummariesInSameLine"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## 前文视频与已生成摘要（真实图路径顺序，只作上下文）")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(pack["previousVideosInGraphOrder"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## 后文直接节点（只作为去向提示）")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(pack["downstreamNodes"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## 同选择兄弟分支（只作为差异参照）")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(pack["siblingBranchesFromSameChoice"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## 输出 JSON schema")
    lines.append("")
    lines.append(
        json.dumps(
            {
                "display_summary": "1-3 句自然剧情复述，适合显示在视频卡片上，不机械复述字幕",
                "detailed_summary": ["3-6 条自然剧情要点，说明因果、转折和人物意图"],
                "event_facts": [
                    {"fact": "关键事实", "evidence": [f"subtitle:{subtitle_doc_name}:<cue-range>"]}
                ],
                "context_refs": ["使用到的上游选择/官方摘要/资料卡引用"],
                "risk_flags": ["如果有不确定、合流、多上游、兄弟分支污染风险，在这里列出"],
                "confidence": "high|medium|low",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return "\n".join(lines) + "\n"


def prompt_text() -> str:
    return (
        "你是《盛世天下：女帝篇》剧情摘要助手。"
        "请根据输入的任务简报，主动使用 Claude Code 的 Read/Grep/Glob 等工具读取项目内知识库文件，然后生成 JSON。"
        "本任务只允许读取资料；禁止使用 Write/Edit/MultiEdit/NotebookEdit/TaskUpdate，禁止创建或修改摘要文件。最终只在本次回答中输出 JSON。"
        "禁止读取 Claude Code 的长期记忆、会话导出或自动 memory 文件；资料只来自任务简报列出的项目路径。"
        "不要重复 Read 已读文件；如果已经读到目标字幕、必要导览和必要上下文，立即调用 StructuredOutput 输出结果。"
        "若目标字幕文档无字幕且官方摘要/目标元数据已足够说明本节点，只读必要导览和目标字幕文档即可；不要为泛称、短句或无具体人物/物品的官方摘要额外检索档案。"
        "用户不会提供 choice key、video key 或人物/词条 key；这些定位信息只能来自运行状态、路线图或外层调度。"
        "如果缺少当前运行状态，应报告缺少结构化状态，不要向用户索要 key。"
        "不要使用外部历史知识，不要补写项目知识库和路线图之外的剧情，不要把后文或兄弟分支写成本视频已发生事实。"
        "必须先用工具阅读知识库使用导览、摘要生成导引和路线图导引，理解目录职责、来源优先级和禁止事项；全量路线 JSON 只在任务简报不足以判断路线位置、合流或条件节点时精准复核，不要反复整文件读取。"
        "必须用工具阅读目标视频片段文档；需要人物、物品、称谓、前文时，再用工具检索并读取对应 Markdown；没有消歧需求时不要泛化检索。"
        "目标视频事实只能来自目标视频片段文档里的字幕和目标官方摘要。"
        "前置选择、同线路前文摘要、后文节点、兄弟分支只能用于理解上下文、分支差异和路线位置。"
        "同线路已生成前文摘要可作为 AI 辅助背景参考；但它们不能替代目标字幕、路线图和档案正文。"
        "前文摘要只指剧情图真实上游路径中的视频摘要；同一选择的兄弟分支不是前一个视频，不能当作本路径前文。"
        "禁止读取或引用目标视频自己的既有摘要。"
        "人物/词条资料只能用于辨识身份、称谓和名词，不能写成目标视频已发生事实。"
        "人物档案文件名通常带有配置 id 和 tag，不要按人名直接拼 `<人名>.md`；先读 data/knowledge/dossiers/characters/README.md、data/knowledge/dossiers/aliases/README.md、data/knowledge/dossiers/aliases/characters/README.md 或具体别名 .md，拿到真实文件名后再 Read；不要把目录路径直接交给 Read。"
        "event_facts 只写目标视频字幕或目标官方摘要明示的事实；前置选择、上游节点、后文节点和人物档案只能进入 context_refs 或 risk_flags。"
        "display_summary 和 detailed_summary 要写成自然、连贯的剧情复述，说明人物动机、冲突和转折；不要机械改写字幕清单，也不要为了顺口牺牲证据边界。"
        "代词、称谓或省略主语能由当前节点、紧邻选择、目标字幕和命中档案明确消歧时，摘要应写出对应人物；不确定时才保留不确定表达，并写入 risk_flags。"
        "主子、陛下、皇后、殿下等关系/职位称谓不能按全局默认硬套；必须结合说话人、前后回应者、场景切换、当前路线和目标字幕判断。"
        "新世界线中，目标字幕或目标元数据只写“你”“主角”时，主角优先按该线身份写作“伍元照”；不要把女帝线的“伍媚娘”称呼带入新世界线。若目标字幕明确使用其他称呼，以目标字幕为准。"
        "不要用斜杠拼接含混称谓；不确定身份时使用自然中文，例如“宫人或侍从”。"
        "context_refs 使用自然语言说明引用到的前置选择、相邻视频、人物档案或词条，不写 profile、choice、alias 等机读前缀。"
        "涉及称呼、发话、动作时必须保留字幕说话人边界，不要把被称呼对象误写成说话人。"
        "必须使用游戏内名称；官方摘要若残留历史原名，输出时改回游戏内名称，例如李治→礼治、李泰→礼泰、李弘→礼弘、武媚娘→伍媚娘。"
        "event_facts 的 evidence 必须引用目标视频片段文档和字幕序号，格式为 subtitle:<videoKey>.subtitles.md:<字幕序号或范围>；"
        "不连续的字幕证据必须拆成多个 evidence 字符串，禁止写 1-3,7-9 这种合并范围。"
        "如果事实只能来自目标官方摘要，使用 official_annotation:target。"
        "如果目标视频片段文档明确写着无字幕，只能使用目标卡片摘要、剧情标题、节点类型等目标元数据生成极简摘要。"
        "metadata evidence 只能用于目标视频无字幕时的元数据事实，固定字段为：metadata:target:storylineTitle、metadata:target:title、metadata:target:kind、metadata:target:chapterTitle、metadata:target:lineTitle、metadata:target:videoKey；目标官方摘要必须写 official_annotation:target，禁止写 metadata:target:annotation。"
        "禁止把“无字幕”写成 subtitle:<videoKey>.subtitles.md:无字幕；无字幕只能作为 risk_flags 或 context_refs 说明。"
        "前置选择、上游视频、后文节点、合流关系和兄弟分支只能放在 context_refs 或 risk_flags，不能作为 event_facts 的 metadata evidence。"
        "evidence 只能引用目标视频片段文档 ## 字幕 中真实存在的编号；引用末尾事实前必须核对最后一条字幕编号。"
        "必须严格区分女帝线、新世界线和前情提要，不得串线。"
        "输出使用中文，不使用资料卡里的英文译名、英文标签或翻译说明。"
        "输出 JSON 字符串内不要使用英文双引号；引用称呼、标题或概念时使用中文书名号、中文引号或单引号，避免破坏 JSON。"
        "输出只允许一个 JSON 对象，不要 Markdown 代码围栏。"
    )


def summary_json_schema() -> str:
    return json.dumps(
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "display_summary": {"type": "string"},
                "detailed_summary": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "event_facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "fact": {"type": "string"},
                            "evidence": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                        },
                        "required": ["fact", "evidence"],
                    },
                },
                "context_refs": {"type": "array", "items": {"type": "string"}},
                "risk_flags": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            },
            "required": [
                "display_summary",
                "detailed_summary",
                "event_facts",
                "context_refs",
                "risk_flags",
                "confidence",
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def run_gemini(pack_path: Path, model: str) -> Path:
    if model.lower() in {"auto", "router", "smart", "model-router"}:
        raise SystemExit("Refusing to use model router/auto model. Pass an explicit Gemini model id.")
    pack_path = project_path(pack_path)
    text = pack_path.read_text(encoding="utf-8")
    prompt = prompt_text()
    digest = hashlib.sha256((prompt + "\n\n" + text).encode("utf-8")).hexdigest()[:12]
    out_dir = RUN_DIR / pack_path.parent.name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{pack_path.stem}.{safe_filename_part(model)}.{digest}.raw.txt"
    cmd = cli_command("gemini")
    cmd.extend(["--skip-trust", "-m", model, "-p", prompt_text(), "--output-format", "text"])
    completed = subprocess.run(
        cmd,
        input=text,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=PROJECT_ROOT,
        timeout=CLAUDE_TIMEOUT_SEC,
    )
    write_text(out_path, completed.stdout)
    err_path = out_path.with_suffix(".stderr.txt")
    write_text(err_path, completed.stderr)
    meta_path = out_path.with_suffix(".meta.json")
    write_text(
        meta_path,
        json.dumps(
            {
                "model": model,
                "command": cmd,
                "returncode": completed.returncode,
                "pack": project_rel(pack_path),
                "stdout": project_rel(out_path),
                "stderr": project_rel(err_path),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    if completed.returncode != 0:
        raise SystemExit(f"Gemini CLI failed with code {completed.returncode}. See {err_path}")
    return out_path


def walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def run_claude(pack_path: Path, model: str, max_budget_usd: str | None = None, env: dict[str, str] | None = None) -> Path:
    if model.lower() in {"auto", "router", "smart", "model-router"}:
        raise SystemExit("Refusing to use model router/auto model. Pass an explicit Claude Code model id.")
    pack_path = project_path(pack_path)
    text = pack_path.read_text(encoding="utf-8")
    prompt = prompt_text()
    digest = hashlib.sha256((prompt + "\n\n" + text).encode("utf-8")).hexdigest()[:12]
    out_dir = RUN_DIR / pack_path.parent.name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{pack_path.stem}.claude-{safe_filename_part(model)}.{digest}.raw.txt"
    response_path = out_path.with_suffix(".response.txt")
    envelope_path = out_path.with_suffix(".envelope.json")
    cmd = cli_command("claude")
    cmd.extend(
        [
            "-p",
            prompt,
            "--model",
            model,
            "--output-format",
            "stream-json",
            "--verbose",
            "--json-schema",
            summary_json_schema(),
            "--bare",
            "--tools",
            "Read,Grep,Glob",
            "--allowedTools",
            "Read,Grep,Glob",
            "--disallowedTools",
            "Write",
            "--permission-mode",
            "dontAsk",
            "--no-session-persistence",
        ]
    )
    if max_budget_usd:
        cmd.extend(["--max-budget-usd", max_budget_usd])
    run_env = os.environ.copy()
    run_env.pop("DISABLE_INTERLEAVED_THINKING", None)
    run_env.pop("CLAUDE_CODE_DISABLE_INTERLEAVED_THINKING", None)
    if env:
        run_env.update(env)
        run_env.pop("DISABLE_INTERLEAVED_THINKING", None)
        run_env.pop("CLAUDE_CODE_DISABLE_INTERLEAVED_THINKING", None)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            cmd,
            input=text,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=PROJECT_ROOT,
            timeout=CLAUDE_TIMEOUT_SEC,
            env=run_env,
        )
    except subprocess.TimeoutExpired as exc:
        duration_sec = round(time.monotonic() - started, 3)
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        write_text(response_path, stdout)
        write_text(out_path, stdout)
        err_path = out_path.with_suffix(".stderr.txt")
        write_text(err_path, stderr)
        write_text(envelope_path, "{}")
        meta_path = out_path.with_suffix(".meta.json")
        write_text(
            meta_path,
            json.dumps(
                {
                    "model": model,
                    "command": cmd,
                    "returncode": "timeout",
                    "timeoutSec": CLAUDE_TIMEOUT_SEC,
                    "durationSec": duration_sec,
                    "pack": project_rel(pack_path),
                    "stdout": project_rel(out_path),
                    "response": project_rel(response_path),
                    "envelope": project_rel(envelope_path),
                    "stderr": project_rel(err_path),
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        raise SystemExit(f"Claude Code timed out after {CLAUDE_TIMEOUT_SEC}s. See {response_path}")
    duration_sec = round(time.monotonic() - started, 3)
    write_text(response_path, completed.stdout)
    err_path = out_path.with_suffix(".stderr.txt")
    write_text(err_path, completed.stderr)
    structured: Any = None
    parse_error: str | None = None
    envelope: dict[str, Any] | None = None
    session_id: str | None = None
    stream_parse_errors: list[str] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except Exception as exc:
            stream_parse_errors.append(str(exc))
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            envelope = event
            session_id = event.get("session_id") or session_id
        for block in walk_dicts(event):
            if block.get("type") == "tool_use" and block.get("name") == "StructuredOutput":
                tool_input = block.get("input")
                if isinstance(tool_input, dict):
                    if "__unparsedToolInput" in tool_input:
                        raw_input = tool_input.get("__unparsedToolInput", {}).get("raw")
                        if isinstance(raw_input, str):
                            try:
                                parsed_input = extract_json(raw_input)
                                if isinstance(parsed_input, dict):
                                    structured = parsed_input
                            except Exception as exc:
                                stream_parse_errors.append(str(exc))
                    elif {"display_summary", "detailed_summary", "event_facts"}.issubset(tool_input):
                        structured = tool_input
            elif block.get("session_id") and not session_id:
                session_id = block.get("session_id")
    write_text(envelope_path, json.dumps(envelope or {}, ensure_ascii=False, indent=2))
    if structured is None and completed.returncode == 0:
        parse_error = "Claude Code stream returned no StructuredOutput"
    elif structured is None and stream_parse_errors:
        parse_error = "; ".join(stream_parse_errors[-3:])
    if structured is not None:
        write_text(out_path, json.dumps(structured, ensure_ascii=False, indent=2))
    else:
        write_text(out_path, completed.stdout)
        if parse_error is None and completed.returncode == 0:
            parse_error = "Claude Code returned no structured_output"
    meta: dict[str, Any] = {
        "model": model,
        "command": cmd,
        "returncode": completed.returncode,
        "timeoutSec": CLAUDE_TIMEOUT_SEC,
        "durationSec": duration_sec,
        "pack": project_rel(pack_path),
        "stdout": project_rel(out_path),
        "response": project_rel(response_path),
        "envelope": project_rel(envelope_path),
        "stderr": project_rel(err_path),
        "session_id": session_id,
    }
    meta_path = out_path.with_suffix(".meta.json")
    write_text(
        meta_path,
        json.dumps(meta, ensure_ascii=False, indent=2),
    )
    if completed.returncode != 0 and structured is None:
        raise SystemExit(f"Claude Code failed with code {completed.returncode}. See {err_path}")
    if parse_error:
        raise SystemExit(f"Claude Code output JSON parse failed: {parse_error}. See {response_path}")
    return out_path


def extract_json(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            return json.loads(stripped[start : end + 1])
        raise


def verify_output(raw_path: Path) -> Path:
    raw_path = project_path(raw_path)
    raw = raw_path.read_text(encoding="utf-8")
    data = extract_json(raw)
    required = ["display_summary", "detailed_summary", "event_facts", "context_refs", "risk_flags", "confidence"]
    issues: list[str] = []
    for key in required:
        if key not in data:
            issues.append(f"missing field: {key}")
    if not isinstance(data.get("display_summary"), str) or not data.get("display_summary", "").strip():
        issues.append("display_summary must be a non-empty string")
    if not isinstance(data.get("detailed_summary"), list) or not data.get("detailed_summary"):
        issues.append("detailed_summary must be a non-empty list")
    if not isinstance(data.get("event_facts"), list):
        issues.append("event_facts must be a list")
    else:
        for index, fact in enumerate(data["event_facts"]):
            if not isinstance(fact, dict) or not fact.get("fact") or not fact.get("evidence"):
                issues.append(f"event_facts[{index}] must include fact and evidence")
    if data.get("confidence") not in {"high", "medium", "low"}:
        issues.append("confidence must be high|medium|low")

    verified_path = raw_path.with_suffix(".verified.json")
    write_text(
        verified_path,
        json.dumps({"ok": not issues, "issues": issues, "summary": data}, ensure_ascii=False, indent=2),
    )
    if issues:
        raise SystemExit(f"Verification failed: {issues}. See {verified_path}")
    append_summary(data, raw_path)
    return verified_path


def metadata_only_summary_for_pack(pack_path: Path) -> dict[str, Any]:
    pack_path = project_path(pack_path)
    pack_text = pack_path.read_text(encoding="utf-8")
    target = json.loads(fenced_block_after_heading(pack_text, "## 目标节点", "json"))
    subtitle_doc = json.loads(fenced_block_after_heading(pack_text, "## 目标视频片段文档来源", "json"))
    cue_count = int(subtitle_doc.get("cueCount") or 0)
    official = section_between(pack_text, "## 官方摘要", "## 上游选择全貌").strip()
    official_available = "- status: `available`" in official
    title = effective_metadata_title(target)
    video_key = str(target.get("videoKey") or "").strip()
    line_title = str(target.get("lineTitle") or "").strip()
    chapter_title = str(target.get("chapterTitle") or target.get("_graphChapterTitle") or "").strip()
    kind = str(target.get("kind") or "").strip()
    if cue_count > 0 or official_available:
        raise ValueError("metadata-only summary is only for no-subtitle nodes without official annotation")
    if title:
        display = f"无字幕节点：{line_title} / {chapter_title} 中的「{title}」。"
        title_fact = f"本节点无字幕、无官方摘要，路线图标题为「{title}」。"
        title_evidence = ["metadata:target:storylineTitle"]
    else:
        display = f"无字幕节点：{line_title} / {chapter_title} 的 {video_key}，无可用剧情摘要。"
        title_fact = "本节点无字幕、无官方摘要，也没有可用的剧情标题。"
        title_evidence = ["metadata:target:videoKey"]
    return {
        "display_summary": display,
        "detailed_summary": [
            "目标视频片段文档明确标记为无字幕。",
            title_fact,
            "现有资料不足以确认画面中的具体动作、人物表现或对白内容；该记录只作为路线图节点说明，不扩写剧情。",
        ],
        "event_facts": [
            {
                "fact": f"本节点位于{line_title} / {chapter_title}，video key 为 {video_key}。",
                "evidence": [
                    "metadata:target:lineTitle",
                    "metadata:target:chapterTitle",
                    "metadata:target:videoKey",
                ],
            },
            {
                "fact": f"本节点类型为 {kind}。",
                "evidence": ["metadata:target:kind"],
            },
            {
                "fact": title_fact,
                "evidence": title_evidence,
            },
        ],
        "context_refs": [
            "该记录由本地生成器根据路线图元数据生成；未调用模型扩写剧情。",
            "上游选择、前后节点和兄弟分支只能用于定位路线，不构成本节点画面事实。",
        ],
        "risk_flags": [
            "目标视频无字幕且无官方摘要，不能确认具体画面内容。",
            "本记录是 metadata_only 节点说明，不等同于对白/画面级剧情摘要。",
        ],
        "confidence": "low",
        "metadataOnly": True,
    }


def write_metadata_only_run(pack_path: Path, model: str) -> Path:
    pack_path = project_path(pack_path)
    summary = metadata_only_summary_for_pack(pack_path)
    text = pack_path.read_text(encoding="utf-8")
    digest = hashlib.sha256(("metadata-only\n\n" + text).encode("utf-8")).hexdigest()[:12]
    out_dir = RUN_DIR / pack_path.parent.name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{pack_path.stem}.metadata-only-{safe_filename_part(model)}.{digest}.raw.txt"
    response_path = out_path.with_suffix(".response.txt")
    envelope_path = out_path.with_suffix(".envelope.json")
    err_path = out_path.with_suffix(".stderr.txt")
    write_text(out_path, json.dumps(summary, ensure_ascii=False, indent=2))
    write_text(response_path, json.dumps({"type": "metadata_only", "summary": summary}, ensure_ascii=False, indent=2))
    write_text(envelope_path, json.dumps({"type": "metadata_only", "reason": "no subtitles and no official annotation"}, ensure_ascii=False, indent=2))
    write_text(err_path, "")
    meta_path = out_path.with_suffix(".meta.json")
    write_text(
        meta_path,
        json.dumps(
            {
                "model": model,
                "command": ["metadata-only"],
                "returncode": 0,
                "pack": project_rel(pack_path),
                "stdout": project_rel(out_path),
                "response": project_rel(response_path),
                "envelope": project_rel(envelope_path),
                "stderr": project_rel(err_path),
                "session_id": None,
                "metadataOnly": True,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    return out_path


def write_metadata_only_audit(meta_path: Path) -> Path:
    meta_path = project_path(meta_path)
    meta = read_json(meta_path)
    raw_path = project_path(Path(meta["stdout"]))
    pack_path = project_path(Path(meta["pack"]))
    raw_data = extract_json(raw_path.read_text(encoding="utf-8"))
    checks = [
        {"name": "metadata-only-run", "ok": bool(meta.get("metadataOnly")), "detail": "no Claude call"},
        {"name": "metadata-only-no-subtitle", "ok": True, "detail": "generated only for no-subtitle/no-official nodes"},
        {"name": "metadata-only-summary-flag", "ok": bool(raw_data.get("metadataOnly")), "detail": "summary.metadataOnly"},
        {"name": "pack-exists", "ok": pack_path.exists(), "detail": project_rel(pack_path)},
        {"name": "raw-exists", "ok": raw_path.exists(), "detail": project_rel(raw_path)},
    ]
    issues = [f"{item['name']}: {item['detail']}" for item in checks if not item["ok"]]
    audit_path = meta_path.with_suffix(".audit.json")
    write_text(
        audit_path,
        json.dumps(
            {
                "ok": not issues,
                "issues": issues,
                "meta": project_rel(meta_path),
                "pack": project_rel(pack_path),
                "raw": project_rel(raw_path),
                "session": None,
                "trace": project_rel(Path(meta["response"])) if meta.get("response") else None,
                "checks": checks,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    if issues:
        raise SystemExit(f"Metadata-only audit failed: {issues}. See {audit_path}")
    return audit_path


def fenced_block_after_heading(text: str, heading: str, language: str) -> str:
    heading_match = re.search(r"(?m)^" + re.escape(heading) + r"\s*$", text)
    if not heading_match:
        return ""
    start = heading_match.end()
    pattern = re.compile(r"```" + re.escape(language) + r"\s*(.*?)\s*```", re.DOTALL)
    match = pattern.search(text, start)
    return match.group(1).strip() if match else ""


def section_between(text: str, start_heading: str, end_heading: str) -> str:
    start = text.find(start_heading)
    if start < 0:
        return ""
    start += len(start_heading)
    end = text.find(end_heading, start)
    if end < 0:
        end = len(text)
    return text[start:end]


def session_contains(session_text: str, value: str) -> bool:
    escaped = json.dumps(value, ensure_ascii=False)[1:-1]
    return value in session_text or escaped in session_text


def session_occurrences(session_text: str, value: str) -> int:
    escaped = json.dumps(value, ensure_ascii=False)[1:-1]
    return session_text.count(value) + (session_text.count(escaped) if escaped != value else 0)


def find_claude_session(session_id: str | None) -> Path | None:
    if not session_id:
        return None
    root = Path.home() / ".claude" / "projects"
    if not root.exists():
        return None
    matches = list(root.rglob(f"{session_id}.jsonl"))
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def trace_tool_uses(trace_text: str) -> list[dict[str, Any]]:
    tool_uses: list[dict[str, Any]] = []
    for line in trace_text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        for block in walk_dicts(event):
            if block.get("type") == "tool_use" and block.get("name"):
                tool_uses.append({"name": block.get("name"), "input": block.get("input") or {}})
    return tool_uses


def normalize_trace_path(value: str) -> str:
    return value.replace("\\", "/")


def target_subtitle_cue_count(pack_text: str) -> int:
    try:
        subtitle_doc_info = json.loads(fenced_block_after_heading(pack_text, "## 目标视频片段文档来源", "json"))
    except json.JSONDecodeError:
        return 0
    path_value = subtitle_doc_info.get("path")
    if not path_value:
        return 0
    subtitle_doc = project_path(Path(str(path_value)))
    if not subtitle_doc.exists():
        return 0
    block = subtitle_doc.read_text(encoding="utf-8")
    cue_numbers: list[int] = []
    for line in block.splitlines():
        match = re.match(r"^\s*(\d+)\.\s+`", line)
        if match:
            cue_numbers.append(int(match.group(1)))
    return max(cue_numbers) if cue_numbers else 0


def audit_claude_run(meta_path: Path) -> Path:
    meta_path = project_path(meta_path)
    meta = read_json(meta_path)
    pack_path = project_path(Path(meta["pack"]))
    raw_path = project_path(Path(meta["stdout"]))
    pack_text = pack_path.read_text(encoding="utf-8")
    raw_data = extract_json(raw_path.read_text(encoding="utf-8"))
    issues: list[str] = []
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            issues.append(f"{name}: {detail}")

    model = str(meta.get("model") or "")
    check("explicit-model", model.lower() not in {"auto", "router", "smart", "model-router"}, model)

    session_path = find_claude_session(meta.get("session_id"))
    response_path = project_path(Path(meta["response"])) if meta.get("response") else None
    trace_path = session_path or (response_path if response_path and response_path.exists() else None)
    check("run-trace-exists", trace_path is not None, str(meta.get("session_id") or ""))
    session_text = trace_path.read_text(encoding="utf-8", errors="replace") if trace_path else ""
    tool_uses = trace_tool_uses(session_text)
    read_paths = [
        normalize_trace_path(str((tool.get("input") or {}).get("file_path") or ""))
        for tool in tool_uses
        if tool.get("name") == "Read" and isinstance(tool.get("input"), dict)
    ]

    def trace_read_path(path_value: str) -> bool:
        expected = normalize_trace_path(path_value)
        return any(expected in path or path.endswith(expected) for path in read_paths)

    heading_match = re.search(r"^# Agentic 摘要任务:\s*(?P<chapter>[^/]+?)\s*/\s*(?P<video>\S+)\s*$", pack_text, re.MULTILINE)
    heading = heading_match.group(0).strip() if heading_match else ""
    check("pack-heading-parsed", bool(heading), pack_path.name)
    trace_has_pack_text = bool(session_path) or (bool(heading) and session_contains(session_text, heading))
    if heading and trace_has_pack_text:
        check("session-has-pack-heading", session_contains(session_text, heading), heading)
    elif heading:
        check("trace-response-stream-without-pack-echo", True, heading)

    target_video_key = heading_match.group("video") if heading_match else ""
    if target_video_key:
        target_summary_leak = re.search(
            r'"existingOverlaySummaryRef"\s*:\s*\{(?:(?!\n\s*\}).)*"videoKey"\s*:\s*"'
            + re.escape(target_video_key)
            + r'"',
            pack_text,
            re.DOTALL,
        )
        check("pack-no-target-existing-summary-leak", target_summary_leak is None, target_video_key)

    forbidden_markers = [
        "sourceRaw",
        "data/runtime/video_summary_overlay",
        "data\\runtime\\video_summary_overlay",
        "storyline_graph/srt",
        "storyline_graph\\srt",
        str(Path.home() / ".claude"),
        (Path.home() / ".claude").as_posix(),
        "en_US:",
        "TextClientExcel.pbin",
        "TextClientExamplezh_CN.pbin",
    ]
    for marker in forbidden_markers:
        check(f"pack-absent-forbidden-marker:{marker}", marker not in pack_text, marker)
        if marker not in {"storyline_graph/srt", "storyline_graph\\srt"}:
            check(f"session-absent-forbidden-marker:{marker}", marker not in session_text, marker)
    raw_srt_access = re.search(
        r"data[/\\]game[/\\]storyline_graph[/\\]srt[/\\][^\"'\s]+\.srt",
        session_text,
        re.IGNORECASE,
    )
    check(
        "session-did-not-read-raw-srt-file",
        raw_srt_access is None,
        raw_srt_access.group(0) if raw_srt_access else "",
    )

    required_sections = [
        "## 硬规则",
        "## 知识库使用导览",
        "## 摘要生成导引",
        "## 路线图导引与按需原始路线图",
        "## 路线与章节导览（防止串线）",
        "## 目标视频片段文档来源",
        "## 知识库资料入口",
        "## 已生成摘要索引",
        "## 上游选择全貌（问题、所有选项、当前选项）",
        "## 上游最近选择",
        "## 同线路已生成前文摘要索引（只作辅助上下文）",
        "## 前文视频与已生成摘要（真实图路径顺序，只作上下文）",
        "## 后文直接节点（只作为去向提示）",
        "## 同选择兄弟分支（只作为差异参照）",
    ]
    if trace_has_pack_text:
        for section in required_sections:
            check(f"session-has-section:{section}", session_contains(session_text, section), section)
    else:
        check("trace-read-knowledge-guide", trace_read_path(project_rel(KNOWLEDGE_GUIDE)), project_rel(KNOWLEDGE_GUIDE))
        check("trace-read-summary-guide", trace_read_path(project_rel(SUMMARY_TASK_GUIDE)), project_rel(SUMMARY_TASK_GUIDE))
        check("trace-read-storyline-guide", trace_read_path(project_rel(STORYLINE_GUIDE)), project_rel(STORYLINE_GUIDE))

    subtitle_doc_info: dict[str, Any] = {}
    try:
        subtitle_doc_info = json.loads(fenced_block_after_heading(pack_text, "## 目标视频片段文档来源", "json"))
    except json.JSONDecodeError as exc:
        check("pack-subtitle-doc-json-parse", False, str(exc))
    target_subtitle_doc_name = str(subtitle_doc_info.get("name") or Path(str(subtitle_doc_info.get("path") or "")).name)
    check(
        "pack-uses-video-key-subtitle-doc",
        subtitle_doc_info.get("source") == "video_key_subtitle_doc",
        str(subtitle_doc_info.get("source") or ""),
    )
    if trace_has_pack_text:
        check("session-has-subtitle-doc-source", session_contains(session_text, "video_key_subtitle_doc"), target_subtitle_doc_name)
    if subtitle_doc_info.get("path"):
        check(
            "session-has-subtitle-doc-path",
            (trace_has_pack_text and session_contains(session_text, str(subtitle_doc_info["path"])))
            or trace_read_path(str(subtitle_doc_info["path"])),
            str(subtitle_doc_info["path"]),
        )
        check(
            "session-read-target-subtitle-doc",
            trace_read_path(str(subtitle_doc_info["path"])),
            str(subtitle_doc_info["path"]),
        )

    tool_use_detected = any(tool.get("name") in {"Read", "Grep", "Glob"} for tool in tool_uses)
    check("session-has-file-query-tool-use", tool_use_detected, "Read/Grep/Glob")

    if model:
        check("session-model-matches-meta", session_contains(session_text, f'"model":"{model}') or session_contains(session_text, f'"model": "{model}"'), model)
    allowed_tool_names = {"Read", "Grep", "Glob", "StructuredOutput"}
    unexpected_tool_names = sorted({str(tool.get("name")) for tool in tool_uses if tool.get("name") not in allowed_tool_names})
    check(
        "session-tool-use-allowlist",
        not unexpected_tool_names,
        ",".join(unexpected_tool_names),
    )
    write_tool_detected = any(tool.get("name") in {"Write", "Edit", "MultiEdit", "NotebookEdit", "TaskUpdate"} for tool in tool_uses)
    check("session-has-no-write-tool-use", not write_tool_detected, "Write/Edit/MultiEdit/NotebookEdit/TaskUpdate")
    check(
        "session-has-final-json-output",
        session_contains(session_text, '"display_summary"')
        or session_contains(session_text, "display_summary")
        or isinstance(raw_data.get("display_summary"), str),
        "",
    )

    check("pack-has-no-static-knowledge-card-section", "## 按需游戏内人物/词条资料" not in pack_text, "")
    check("pack-does-not-inline-target-subtitles", "## 目标视频片段文档\n\n```md" not in pack_text, "")

    max_line = target_subtitle_cue_count(pack_text)
    target_subtitle_block = ""
    if subtitle_doc_info.get("path"):
        subtitle_path = project_path(Path(str(subtitle_doc_info["path"])))
        if subtitle_path.exists():
            target_subtitle_block = subtitle_path.read_text(encoding="utf-8")
    metadata_evidence_allowed = max_line == 0 and "无字幕" in target_subtitle_block
    check("target-subtitle-cue-count-or-empty-marker", max_line > 0 or metadata_evidence_allowed, str(max_line))
    for fact_index, fact in enumerate(raw_data.get("event_facts") or []):
        evidence_list = fact.get("evidence") if isinstance(fact, dict) else None
        if not isinstance(evidence_list, list):
            check(f"event-fact-{fact_index}-evidence-list", False, str(fact))
            continue
        for evidence_index, evidence in enumerate(evidence_list):
            if not isinstance(evidence, str):
                check(f"event-fact-{fact_index}-evidence-{evidence_index}-string", False, repr(evidence))
                continue
            if OFFICIAL_EVIDENCE_RE.fullmatch(evidence.strip()):
                check(f"event-fact-{fact_index}-evidence-{evidence_index}-official", True, evidence)
                continue
            metadata_match = METADATA_EVIDENCE_RE.fullmatch(evidence.strip())
            if metadata_match:
                check(
                    f"event-fact-{fact_index}-evidence-{evidence_index}-metadata-allowed",
                    metadata_evidence_allowed,
                    evidence,
                )
                continue
            match = SUBTITLE_EVIDENCE_RE.fullmatch(evidence.strip())
            check(f"event-fact-{fact_index}-evidence-{evidence_index}-format", match is not None, evidence)
            if not match:
                continue
            source_name = match.group("source")
            check(
                f"event-fact-{fact_index}-evidence-{evidence_index}-target-source",
                source_name == target_subtitle_doc_name,
                source_name if source_name == target_subtitle_doc_name else f"{source_name} != {target_subtitle_doc_name}",
            )
            start = int(match.group("start"))
            end = int(match.group("end") or start)
            check(
                f"event-fact-{fact_index}-evidence-{evidence_index}-line-range",
                1 <= start <= end <= max_line,
                f"{start}-{end}, max={max_line}",
            )

    audit_path = meta_path.with_suffix(".audit.json")
    write_text(
        audit_path,
        json.dumps(
            {
                "ok": not issues,
                "issues": issues,
                "meta": project_rel(meta_path),
                "pack": project_rel(pack_path),
                "raw": project_rel(raw_path),
                "session": str(session_path) if session_path else None,
                "trace": str(trace_path) if trace_path else None,
                "checks": checks,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    if issues:
        raise SystemExit(f"Claude run audit failed: {issues}. See {audit_path}")
    return audit_path


def append_summary(data: dict[str, Any], raw_path: Path) -> None:
    SUMMARY_JSONL.parent.mkdir(parents=True, exist_ok=True)
    video_key = video_key_from_run_path(project_rel(raw_path))
    raw_name = raw_path.name.lower()
    if "deepseek-v4-flash" in raw_name:
        source = {"kind": "ai_generated_summary", "model": "DeepSeek V4 Flash"}
    else:
        source = {"kind": "ai_generated_summary"}
    record = {
        "video_key": video_key,
        "status": "final",
        "source": source,
        "summary": data,
    }
    with SUMMARY_APPEND_LOCK:
        with SUMMARY_JSONL.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and test AI video summary input packages.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    build = sub.add_parser("build-pack")
    build.add_argument("chapter")
    build.add_argument("video_key")
    build.add_argument("--node-id", default=None)

    run = sub.add_parser("run-gemini")
    run.add_argument("pack")
    run.add_argument("--model", default=TEST_MODEL)

    run_claude_parser = sub.add_parser("run-claude")
    run_claude_parser.add_argument("pack")
    run_claude_parser.add_argument("--model", default=CLAUDE_TEST_MODEL)
    run_claude_parser.add_argument("--max-budget-usd", default=None)

    verify = sub.add_parser("verify")
    verify.add_argument("raw_output")

    audit = sub.add_parser("audit-claude-run")
    audit.add_argument("meta")

    args = parser.parse_args()
    if args.cmd == "build-pack":
        path = build_pack(args.chapter, args.video_key, args.node_id)
        print(path)
    elif args.cmd == "run-gemini":
        path = run_gemini(Path(args.pack), args.model)
        print(path)
    elif args.cmd == "run-claude":
        path = run_claude(Path(args.pack), args.model, args.max_budget_usd)
        print(path)
    elif args.cmd == "verify":
        path = verify_output(Path(args.raw_output))
        print(path)
    elif args.cmd == "audit-claude-run":
        path = audit_claude_run(Path(args.meta))
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
