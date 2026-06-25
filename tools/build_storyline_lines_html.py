from __future__ import annotations

import html
import json
import os
import re
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRAPH_DIR = PROJECT_ROOT / "data" / "game" / "storyline_graph"
MECHANICS_DIR = GRAPH_DIR.parent / "storyline_mechanics"
GAME_SRT_ROOT = Path(os.environ.get("SSTX2_SRT_ROOT", str(GRAPH_DIR / "srt")))

OUTPUT_HTML = GRAPH_DIR / "storyline_graph.html"
OUTPUT_JSON = GRAPH_DIR / "storyline_lines_manifest.json"

ENTRY_KINDS = {"EntryPoint_ChapterStart", "EntryPoint_SubChapterStart"}
ADDON_EVENTS = [
    ("chapter_envoy_1", "乌檀国使者事件"),
    ("chapter_envoy_2", "茯苓国王子事件"),
    ("chapter_envoy_3", "金象国使者事件"),
    ("chapter_extra_nc", "男侍事件"),
]


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def source_path_label(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return "SSTX2_SRT_ROOT"


def compact_srt_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def chapter_from_storyline(item: dict[str, Any]) -> str:
    endpoint_ids = [
        report.get("endpoint_id")
        for report in item.get("chapter_reports", [])
        if isinstance(report.get("endpoint_id"), int)
    ]
    if not endpoint_ids:
        return "unknown"
    chapter_no = min(endpoint_ids) // 100
    return f"chapter{chapter_no}"


def line_key_for_chapter(chapter: str) -> str:
    if chapter == "chapter999":
        return "entry"
    if re.fullmatch(r"chapter1\d\d", chapter):
        return "empress"
    if re.fullmatch(r"chapter2\d\d", chapter):
        return "new_world"
    return "other"


def line_title(line_key: str) -> str:
    return {
        "entry": "分线入口",
        "empress": "女帝篇",
        "new_world": "新世界篇",
        "other": "其他主包",
    }.get(line_key, line_key)


def chapter_sort_key(chapter: str) -> tuple[int, int]:
    if chapter == "chapter999":
        return (0, 999)
    match = re.fullmatch(r"chapter(\d+)", chapter)
    if not match:
        return (9, 9999)
    number = int(match.group(1))
    if 101 <= number <= 112:
        return (1, number)
    if 201 <= number <= 204:
        return (2, number)
    return (8, number)


def chapter_title(item: dict[str, Any]) -> str:
    reports = sorted(
        item.get("chapter_reports", []),
        key=lambda report: (report.get("endpoint_id") or 0, report.get("kind") or ""),
    )
    titles = []
    for report in reports:
        title = report.get("title_zh") or report.get("storyline_title_zh") or report.get("annotation")
        if title and title not in titles:
            titles.append(title)
    return " / ".join(titles) or item["storyline_id"]


def node_title(node: dict[str, Any]) -> str:
    return (
        node.get("video_key")
        or node.get("title_zh")
        or node.get("storyline_title_zh")
        or node.get("annotation")
        or node.get("kind")
        or node.get("node_id")
        or ""
    )


def choice_letter(index: int | None) -> str:
    if index is None or index < 0:
        return ""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return alphabet[index] if index < len(alphabet) else str(index)


def srt_for_node(chapter: str, node: dict[str, Any]) -> dict[str, str] | None:
    video_key = node.get("video_key")
    if not video_key:
        return None
    path = GAME_SRT_ROOT / "zh_GL" / chapter / f"{video_key}.srt"
    if not path.exists():
        path = GAME_SRT_ROOT / chapter / f"{video_key}.srt"
    if not path.exists():
        return None
    return {
        "name": path.name,
        "relative": f"zh_GL/{chapter}/{path.name}",
        "text": compact_srt_text(path),
    }


def traversal_order(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {node["node_id"]: node for node in nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)
    incoming = Counter()
    for edge in edges:
        if edge["source_node_id"] in by_id and edge["target_node_id"] in by_id:
            outgoing[edge["source_node_id"]].append(edge["target_node_id"])
            incoming[edge["target_node_id"]] += 1

    starts = [
        node["node_id"]
        for node in nodes
        if node.get("kind") in ENTRY_KINDS or incoming[node["node_id"]] == 0
    ]
    starts.sort(key=lambda node_id: (0 if by_id[node_id].get("kind") == "EntryPoint_ChapterStart" else 1, node_title(by_id[node_id])))

    seen: set[str] = set()
    ordered: list[dict[str, Any]] = []
    queue: deque[str] = deque(starts)
    while queue:
        node_id = queue.popleft()
        if node_id in seen or node_id not in by_id:
            continue
        seen.add(node_id)
        ordered.append(by_id[node_id])
        targets = sorted(outgoing.get(node_id, []), key=lambda tid: node_title(by_id.get(tid, {})))
        for target in targets:
            if target not in seen:
                queue.append(target)

    leftovers = [node for node in nodes if node["node_id"] not in seen]
    leftovers.sort(key=lambda node: (node.get("video_prefix") or "", node_title(node), node.get("hash") or ""))
    return ordered + leftovers


def load_storyline_mechanics_scores() -> Counter[str]:
    scores: Counter[str] = Counter()
    for name in ("video_effects.jsonl", "conditions.jsonl", "global_variable_nodes.jsonl"):
        path = MECHANICS_DIR / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            storyline_id = obj.get("storyline_id")
            if storyline_id:
                scores[str(storyline_id)] += 1
    return scores


def equivalent_chapter_signature(chapter: dict[str, Any]) -> tuple[Any, ...]:
    node_signature = tuple(
        sorted(
            (
                node.get("hash"),
                node.get("kind"),
                node.get("video_key"),
                node.get("annotation"),
            )
            for node in chapter.get("nodes", [])
        )
    )
    edge_signature = tuple(
        sorted(
            (
                edge.get("source_hash") or edge.get("source_node_hash"),
                edge.get("target_hash") or edge.get("target_node_hash"),
                edge.get("source_port"),
                edge.get("choice_index"),
                edge.get("choice_text_zh") or edge.get("choice_text_key"),
            )
            for node in chapter.get("nodes", [])
            for edge in node.get("outgoing_edges", [])
        )
    )
    return (
        chapter.get("line_key"),
        chapter.get("chapter"),
        chapter.get("node_count"),
        chapter.get("edge_count"),
        chapter.get("choice_edge_count"),
        node_signature,
        edge_signature,
    )


def dedupe_equivalent_chapters(chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scores = load_storyline_mechanics_scores()
    grouped: dict[tuple[str, str, tuple[Any, ...]], list[dict[str, Any]]] = defaultdict(list)
    passthrough: list[dict[str, Any]] = []
    for chapter in chapters:
        key = (
            str(chapter.get("line_key") or ""),
            str(chapter.get("chapter") or ""),
            equivalent_chapter_signature(chapter),
        )
        grouped[key].append(chapter)

    for items in grouped.values():
        if len(items) == 1:
            passthrough.append(items[0])
            continue
        best = max(
            items,
            key=lambda item: (
                scores[str(item.get("storyline_id") or "")],
                str(item.get("storyline_id") or ""),
            ),
        )
        passthrough.append(best)
    return passthrough


def build_manifest() -> dict[str, Any]:
    nodes = read_jsonl(GRAPH_DIR / "nodes.jsonl")
    edges = read_jsonl(GRAPH_DIR / "edges.jsonl")
    overview = json.loads((GRAPH_DIR / "overview.json").read_text(encoding="utf-8"))

    overview_by_story = {item["storyline_id"]: item for item in overview}
    nodes_by_story: dict[str, list[dict[str, Any]]] = defaultdict(list)
    edges_by_story: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        nodes_by_story[node["storyline_id"]].append(node)
    for edge in edges:
        edges_by_story[edge["storyline_id"]].append(edge)

    chapters: list[dict[str, Any]] = []
    for storyline_id, item in sorted(overview_by_story.items()):
        chapter = chapter_from_storyline(item)
        line_key = line_key_for_chapter(chapter)
        chapter_nodes = nodes_by_story[storyline_id]
        chapter_edges = edges_by_story[storyline_id]
        node_ids = {node["node_id"] for node in chapter_nodes}
        outgoing = defaultdict(list)
        incoming = Counter()
        for edge in chapter_edges:
            outgoing[edge["source_node_id"]].append(edge)
            incoming[edge["target_node_id"]] += 1

        enriched_nodes = []
        for order, node in enumerate(traversal_order(chapter_nodes, chapter_edges), start=1):
            srt = srt_for_node(chapter, node)
            node_edges = [edge for edge in outgoing.get(node["node_id"], []) if edge["target_node_id"] in node_ids]
            enriched_nodes.append(
                {
                    **node,
                    "order": order,
                    "incoming_count": incoming[node["node_id"]],
                    "outgoing_edges": node_edges,
                    "srt": srt,
                }
            )

        chapters.append(
            {
                "line_key": line_key,
                "line_title": line_title(line_key),
                "chapter": chapter,
                "storyline_id": storyline_id,
                "title": chapter_title(item),
                "node_count": item["node_count"],
                "edge_count": item["edge_count"],
                "choice_edge_count": item["choice_edge_count"],
                "reports": sorted(item.get("chapter_reports", []), key=lambda r: r.get("endpoint_id") or 0),
                "nodes": enriched_nodes,
            }
        )

    chapters = dedupe_equivalent_chapters(chapters)
    chapters.sort(key=lambda item: (chapter_sort_key(item["chapter"]), item["storyline_id"]))

    addons = []
    for package, title in ADDON_EVENTS:
        folder = GAME_SRT_ROOT / "zh_GL" / package
        if not folder.exists():
            folder = GAME_SRT_ROOT / package
        files = []
        if folder.exists():
            for path in sorted(folder.glob("*.srt"), key=lambda p: p.name):
                files.append(
                    {
                        "file": path.name,
                        "relative": f"zh_GL/{package}/{path.name}",
                        "text": compact_srt_text(path),
                    }
                )
        addons.append({"package": package, "title": title, "files": files})

    return {
        "source": {
            "graph_dir": source_path_label(GRAPH_DIR),
            "srt_root": source_path_label(GAME_SRT_ROOT),
            "rule": "主线节点和分支归属来自 Storyline leadLink；字幕只挂到对应 video_key 节点下，不参与排序。",
        },
        "chapters": chapters,
        "addons": addons,
    }


def render_edge(edge: dict[str, Any]) -> str:
    letter = choice_letter(edge.get("choice_index"))
    if letter:
        lead = f"<span class=\"choice-letter\">{esc(letter)}</span> {esc(edge.get('choice_text_zh') or edge.get('choice_text_key'))}"
    elif edge.get("source_port") in {"endPointTrue", "endPointElse"}:
        lead = f"<span class=\"logic-port\">{esc(edge.get('source_port'))}</span>"
    else:
        lead = f"<span class=\"logic-port\">{esc(edge.get('source_port') or 'next')}</span>"
    return (
        f"<li>{lead}<span class=\"arrow\">→</span>"
        f"<a href=\"#node-{safe_id(edge['target_node_id'])}\">{esc(edge.get('target_label'))}</a>"
        f"<span class=\"target-kind\">{esc(edge.get('target_kind'))}</span></li>"
    )


def render_node(node: dict[str, Any]) -> str:
    kind = str(node.get("kind") or "")
    classes = ["node"]
    if kind == "ShowChoice":
        classes.append("is-choice")
    elif kind.startswith("EndPoint_"):
        classes.append("is-endpoint")
    elif kind.startswith("Function_") or kind.startswith("Logic_") or kind.startswith("Getter_"):
        classes.append("is-logic")
    srt = node.get("srt")
    edges = node.get("outgoing_edges") or []
    choices = node.get("choices") or []
    choice_html = ""
    if choices:
        choice_items = []
        for choice in choices:
            letter = choice_letter(choice.get("index"))
            choice_items.append(
                f"<li><span class=\"choice-letter\">{esc(letter)}</span>{esc(choice.get('choice_text_zh') or choice.get('choice_text_key'))}</li>"
            )
        choice_html = f"<ol class=\"choice-list\">{''.join(choice_items)}</ol>"
    srt_html = ""
    if srt:
        srt_html = (
            "<details class=\"srt-block\">"
            f"<summary>{esc(srt['relative'])}</summary>"
            f"<pre>{esc(srt['text'])}</pre>"
            "</details>"
        )
    target_video = ""
    if node.get("endpoint_target_video_key"):
        target_video = f"<div class=\"endpoint-target\">回退锚点：{esc(node.get('endpoint_target_video_key'))}</div>"
    edge_html = (
        f"<ul class=\"edge-list\">{''.join(render_edge(edge) for edge in edges)}</ul>"
        if edges
        else "<div class=\"no-edge\">无后续 leadLink</div>"
    )
    subtitle = node.get("title_zh") or node.get("storyline_title_zh") or ""
    if node.get("title_zh") and node.get("storyline_title_zh") and node.get("title_zh") != node.get("storyline_title_zh"):
        subtitle = f"{node.get('title_zh')} / {node.get('storyline_title_zh')}"
    return f"""
<article class="{' '.join(classes)}" id="node-{safe_id(node['node_id'])}">
  <div class="node-head">
    <div>
      <div class="node-index">#{node['order']:03d}</div>
      <h4>{esc(node_title(node))}</h4>
      <p>{esc(subtitle)}</p>
    </div>
    <div class="kind">{esc(kind)}</div>
  </div>
  <div class="node-meta">
    <span>hash {esc(node.get('hash'))}</span>
    <span>入边 {node.get('incoming_count', 0)}</span>
    <span>出边 {len(edges)}</span>
    {f'<span>endpoint {esc(node.get("endpoint_id"))}</span>' if node.get("endpoint_id") else ''}
  </div>
  {f'<div class="annotation">{esc(node.get("annotation"))}</div>' if node.get("annotation") else ''}
  {target_video}
  {choice_html}
  {edge_html}
  {srt_html}
</article>
"""


def render_chapter(chapter: dict[str, Any]) -> str:
    reports = " / ".join(
        esc(report.get("title_zh") or report.get("storyline_title_zh") or report.get("annotation"))
        for report in chapter["reports"]
        if report.get("title_zh") or report.get("storyline_title_zh") or report.get("annotation")
    )
    nodes = "\n".join(render_node(node) for node in chapter["nodes"])
    return f"""
<section class="chapter" id="{esc(chapter['chapter'])}">
  <div class="chapter-head">
    <div>
      <span class="chapter-code">{esc(chapter['chapter'])}</span>
      <h3>{esc(chapter['title'])}</h3>
      <p>{reports}</p>
    </div>
    <div class="chapter-stats">
      <span>{chapter['node_count']} 节点</span>
      <span>{chapter['edge_count']} 边</span>
      <span>{chapter['choice_edge_count']} 选择边</span>
    </div>
  </div>
  <div class="nodes">{nodes}</div>
</section>
"""


def render_addon(addon: dict[str, Any]) -> str:
    files_html = []
    for item in addon["files"]:
        files_html.append(
            f"""
<details class="addon-file">
  <summary>{esc(item['file'])}<span>{esc(item['relative'])}</span></summary>
  <pre>{esc(item['text'])}</pre>
</details>
"""
        )
    return f"""
<section class="addon" id="{esc(addon['package'])}">
  <div class="chapter-head addon-head">
    <div>
      <span class="chapter-code">{esc(addon['package'])}</span>
      <h3>{esc(addon['title'])}</h3>
      <p>按 zh_GL 字幕文件名顺序展开；此区不声明 Storyline 跳转边。</p>
    </div>
    <div class="chapter-stats"><span>{len(addon['files'])} 字幕</span></div>
  </div>
  {''.join(files_html)}
</section>
"""


def render_html(manifest: dict[str, Any]) -> str:
    groups = [
        ("entry", "分线入口"),
        ("empress", "女帝篇"),
        ("new_world", "新世界篇"),
    ]
    nav_items = []
    body_sections = []
    for key, title in groups:
        chapters = [chapter for chapter in manifest["chapters"] if chapter["line_key"] == key]
        if not chapters:
            continue
        nav_items.append(f"<a href=\"#line-{key}\">{esc(title)}<span>{len(chapters)}</span></a>")
        body_sections.append(f"<h2 id=\"line-{key}\">{esc(title)}</h2>")
        body_sections.extend(render_chapter(chapter) for chapter in chapters)
    nav_items.append(f"<a href=\"#line-addons\">附加包<span>{len(manifest['addons'])}</span></a>")
    body_sections.append("<h2 id=\"line-addons\">附加包</h2>")
    body_sections.extend(render_addon(addon) for addon in manifest["addons"])

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>盛世天下 女帝篇 Storyline 路径图</title>
  <style>
    :root {{
      --paper: #faf8f2;
      --panel: #ffffff;
      --ink: #161719;
      --muted: #606873;
      --line: #d7d0c4;
      --gold: #a67520;
      --red: #a73535;
      --blue: #12627e;
      --green: #2f6f58;
      --slate: #27313f;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: "Microsoft YaHei", "Noto Sans SC", "Segoe UI", sans-serif;
      line-height: 1.55;
      letter-spacing: 0;
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 20;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 18px;
      align-items: end;
      padding: 18px 28px;
      background: rgba(250, 248, 242, .96);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(10px);
    }}
    h1 {{ margin: 0; font-size: 24px; font-weight: 800; }}
    .subtitle {{ margin: 4px 0 0; color: var(--muted); font-size: 13px; max-width: 960px; }}
    nav {{ display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }}
    nav a {{
      text-decoration: none;
      color: var(--slate);
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 13px;
      font-weight: 700;
    }}
    nav span {{ margin-left: 6px; color: var(--muted); font-weight: 600; }}
    main {{ max-width: 1480px; margin: 0 auto; padding: 24px 28px 80px; }}
    h2 {{ margin: 34px 0 14px; font-size: 28px; }}
    .chapter, .addon {{
      margin: 0 0 24px;
      border-top: 3px solid var(--slate);
      background: rgba(255,255,255,.55);
      box-shadow: 0 12px 28px rgba(39,49,63,.06);
    }}
    .chapter-head {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 16px;
      padding: 18px 20px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }}
    .chapter-code {{
      display: inline-block;
      margin-bottom: 4px;
      color: var(--gold);
      font-weight: 800;
      font-size: 13px;
      text-transform: uppercase;
    }}
    h3 {{ margin: 0; font-size: 21px; }}
    .chapter-head p {{ margin: 4px 0 0; color: var(--muted); font-size: 13px; }}
    .chapter-stats {{ display: flex; gap: 8px; align-items: start; flex-wrap: wrap; justify-content: flex-end; }}
    .chapter-stats span {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 9px;
      background: #fbfbfb;
      font-size: 12px;
      color: var(--slate);
      font-weight: 700;
    }}
    .nodes {{ padding: 16px; }}
    .node {{
      border: 1px solid var(--line);
      border-left: 5px solid var(--slate);
      border-radius: 6px;
      background: var(--panel);
      padding: 14px;
      margin: 0 0 12px;
    }}
    .node.is-choice {{ border-left-color: var(--blue); }}
    .node.is-endpoint {{ border-left-color: var(--red); }}
    .node.is-logic {{ border-left-color: var(--green); }}
    .node-head {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: start;
    }}
    .node-index {{ color: var(--muted); font-size: 12px; font-family: Consolas, "Cascadia Mono", monospace; }}
    h4 {{ margin: 0; font-size: 18px; overflow-wrap: anywhere; }}
    .node-head p {{ margin: 3px 0 0; color: var(--muted); font-size: 13px; }}
    .kind {{
      color: var(--slate);
      background: #f1f4f5;
      border-radius: 4px;
      padding: 4px 7px;
      font-size: 12px;
      font-family: Consolas, "Cascadia Mono", monospace;
      white-space: nowrap;
    }}
    .node-meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; color: var(--muted); font-size: 12px; }}
    .node-meta span {{ background: #f8f7f3; border-radius: 4px; padding: 2px 6px; }}
    .annotation, .endpoint-target {{
      margin-top: 10px;
      padding: 8px 10px;
      background: #f8f7f3;
      border-left: 3px solid var(--line);
      color: #30343a;
      white-space: pre-wrap;
    }}
    .endpoint-target {{ border-left-color: var(--red); }}
    .choice-list, .edge-list {{ margin: 12px 0 0; padding: 0; list-style: none; display: grid; gap: 7px; }}
    .choice-list li, .edge-list li {{
      border: 1px solid var(--line);
      border-radius: 5px;
      background: #fff;
      padding: 8px 10px;
    }}
    .choice-letter {{
      display: inline-grid;
      place-items: center;
      width: 24px;
      height: 24px;
      margin-right: 8px;
      border-radius: 50%;
      background: var(--slate);
      color: #fff;
      font-weight: 800;
      font-size: 12px;
    }}
    .logic-port {{
      display: inline-block;
      min-width: 86px;
      margin-right: 8px;
      color: var(--green);
      font-family: Consolas, "Cascadia Mono", monospace;
      font-weight: 700;
    }}
    .arrow {{ margin: 0 8px; color: var(--muted); }}
    .edge-list a {{ color: var(--blue); text-decoration: none; font-weight: 800; }}
    .target-kind {{ margin-left: 8px; color: var(--muted); font-size: 12px; font-family: Consolas, "Cascadia Mono", monospace; }}
    .no-edge {{ margin-top: 12px; color: var(--muted); font-size: 13px; }}
    details.srt-block, details.addon-file {{
      margin-top: 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fbfbfb;
    }}
    summary {{ cursor: pointer; padding: 9px 11px; font-weight: 800; color: var(--slate); }}
    summary span {{ margin-left: 10px; color: var(--muted); font-weight: 500; font-size: 12px; }}
    pre {{
      margin: 0;
      padding: 12px;
      border-top: 1px solid var(--line);
      overflow: auto;
      white-space: pre-wrap;
      font-family: Consolas, "Cascadia Mono", monospace;
      font-size: 13px;
      line-height: 1.45;
      background: #fff;
    }}
    .addon {{ border-top-color: var(--gold); }}
    .addon-head {{ background: #fffdf7; }}
    @media (max-width: 760px) {{
      header {{ grid-template-columns: 1fr; align-items: start; padding: 14px; }}
      nav {{ justify-content: flex-start; }}
      main {{ padding: 16px 14px 56px; }}
      .chapter-head, .node-head {{ grid-template-columns: 1fr; }}
      .chapter-stats {{ justify-content: flex-start; }}
      .kind {{ white-space: normal; }}
    }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>盛世天下 女帝篇 Storyline 路径图</h1>
      <p class="subtitle">{esc(manifest['source']['rule'])}</p>
    </div>
    <nav>{''.join(nav_items)}</nav>
  </header>
  <main>
    {''.join(body_sections)}
  </main>
</body>
</html>
"""


def main() -> int:
    manifest = build_manifest()
    OUTPUT_JSON.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUTPUT_HTML.write_text(render_html(manifest), encoding="utf-8")
    main_chapters = [item for item in manifest["chapters"] if item["line_key"] in {"entry", "empress", "new_world"}]
    print(
        f"wrote {OUTPUT_HTML} chapters={len(main_chapters)} "
        f"addons={len(manifest['addons'])} nodes={sum(len(c['nodes']) for c in main_chapters)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
