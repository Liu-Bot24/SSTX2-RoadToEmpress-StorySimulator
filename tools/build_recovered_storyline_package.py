from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any


VIDEO_KEY_RE = re.compile(
    r"\b(?:CL\d{3}_[A-Z0-9_]+|QL\d{3}_[A-Z0-9_]+|[BNH]\d{2}_[A-Z0-9_]+|\d{3}_C[A-Z0-9_]+|\d{3}_\d{3}|[A-Z]\d{2}_[A-Z0-9_]+|EndPoint_[A-Za-z0-9_]+)\b"
)


def load_text_map(path: Path) -> dict[str, str]:
    text_map: dict[str, str] = {}
    if not path.exists():
        return text_map
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        raw_key = item.get("raw_key") or f"Key:{item.get('key')}"
        zh = item.get("zh_CN") or item.get("zh_GL") or item.get("zh") or item.get("zh_TW")
        if raw_key and zh:
            text_map[raw_key] = zh
    return text_map


def resolve(text_map: dict[str, str], value: Any) -> Any:
    if isinstance(value, str) and value.startswith("Key:"):
        return text_map.get(value, value)
    return value


def infer_video_prefix(video_key: str | None) -> str | None:
    if not video_key:
        return None
    season_match = re.search(r"(?:^|_)(S\d{2})(?:_|$)", video_key)
    if season_match:
        return season_match.group(1)
    parts = video_key.split("_")
    for part in parts:
        if re.fullmatch(r"\d{3}", part):
            return part
    short_number = next((part for part in parts if re.fullmatch(r"\d{2}", part)), None)
    return f"0{short_number}" if short_number else None


def node_label(node: dict[str, Any]) -> str:
    return (
        node.get("video_key")
        or node.get("annotation")
        or node.get("title_zh")
        or node.get("storyline_title_zh")
        or node.get("kind")
        or node.get("node_id")
        or ""
    )


def normalize_node(storyline_id: str, node: dict[str, Any], text_map: dict[str, str]) -> dict[str, Any]:
    data_info = node.get("dataInfo") or {}
    parameter = data_info.get("parameterValue") or {}
    kind = (node.get("baseInfo") or {}).get("key")
    choices = []
    for idx, choice in enumerate(parameter.get("choice") or []):
        choice_key = choice.get("choiceText")
        choices.append(
            {
                "index": idx,
                "choice_text_key": choice_key,
                "choice_text_zh": resolve(text_map, choice_key),
                "important": choice.get("importantChoice"),
                "hidden": choice.get("choiceHidden"),
            }
        )
    video_key = parameter.get("videoKey")
    title = parameter.get("title")
    storyline_title = parameter.get("storylineTitle")
    return {
        "storyline_id": storyline_id,
        "node_id": f"{storyline_id}:{node.get('hash')}",
        "hash": node.get("hash"),
        "kind": kind,
        "annotation": data_info.get("annotation"),
        "video_key": video_key,
        "video_prefix": infer_video_prefix(video_key),
        "title_key": title,
        "title_zh": resolve(text_map, title),
        "storyline_title_key": storyline_title,
        "storyline_title_zh": resolve(text_map, storyline_title),
        "endpoint_id": parameter.get("id"),
        "endpoint_target_video_key": parameter.get("targetVideoKey"),
        "choices": choices,
    }


def normalize_edge(storyline_id: str, link: dict[str, Any], nodes_by_hash: dict[str, dict[str, Any]]) -> dict[str, Any]:
    info = link.get("baseInfo") or {}
    src = info.get("from") or {}
    dst = info.get("to") or {}
    source = nodes_by_hash.get(src.get("hashNode"))
    target = nodes_by_hash.get(dst.get("hashNode"))
    choice_index = src.get("indexGroup") if src.get("searchKeyGroup") == "choice" else None
    choice_text_zh = None
    choice_text_key = None
    if source and isinstance(choice_index, int) and choice_index >= 0:
        choices = source.get("choices") or []
        if choice_index < len(choices):
            choice_text_key = choices[choice_index].get("choice_text_key")
            choice_text_zh = choices[choice_index].get("choice_text_zh")
    return {
        "storyline_id": storyline_id,
        "edge_id": f"{storyline_id}:{link.get('hash')}",
        "hash": link.get("hash"),
        "source_node_id": source.get("node_id") if source else f"{storyline_id}:{src.get('hashNode')}",
        "source_hash": src.get("hashNode"),
        "source_kind": source.get("kind") if source else None,
        "source_label": node_label(source) if source else src.get("hashNode"),
        "source_port": src.get("searchKey"),
        "source_group": src.get("searchKeyGroup"),
        "source_index_group": src.get("indexGroup"),
        "choice_index": choice_index,
        "choice_text_key": choice_text_key,
        "choice_text_zh": choice_text_zh,
        "target_node_id": target.get("node_id") if target else f"{storyline_id}:{dst.get('hashNode')}",
        "target_hash": dst.get("hashNode"),
        "target_kind": target.get("kind") if target else None,
        "target_label": node_label(target) if target else dst.get("hashNode"),
        "target_port": dst.get("searchKey"),
    }


def reachable_count(start_ids: list[str], out_edges: dict[str, list[dict[str, Any]]]) -> int:
    seen = set(start_ids)
    queue = deque(start_ids)
    while queue:
        current = queue.popleft()
        for edge in out_edges.get(current, []):
            target = edge["target_node_id"]
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return len(seen)


def summarize_storyline(storyline_id: str, source_file: str, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    kind_counts = Counter(node.get("kind") for node in nodes)
    prefix_counts = Counter(prefix for prefix in (node.get("video_prefix") for node in nodes) if prefix)
    incoming = Counter(edge["target_node_id"] for edge in edges)
    out_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        out_edges[edge["source_node_id"]].append(edge)
    starts = [node for node in nodes if node.get("kind", "").startswith("EntryPoint") or incoming[node["node_id"]] == 0]
    chapter_reports = [
        node
        for node in nodes
        if node.get("kind") in {"EndPoint_ChapterReport", "EndPoint_SubChapterReport", "EndPoint_FinalReport"}
    ]
    endpoints = [node for node in nodes if str(node.get("kind", "")).startswith("EndPoint_")]
    return {
        "storyline_id": storyline_id,
        "source_file": source_file,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "choice_edge_count": sum(1 for edge in edges if isinstance(edge.get("choice_index"), int) and edge.get("choice_index") >= 0),
        "node_kind_counts": dict(sorted(kind_counts.items())),
        "video_prefix_counts": dict(sorted(prefix_counts.items())),
        "start_nodes": [
            {
                "node_id": node["node_id"],
                "kind": node.get("kind"),
                "label": node_label(node),
                "title_zh": node.get("title_zh"),
            }
            for node in starts[:20]
        ],
        "chapter_reports": [
            {
                "kind": node.get("kind"),
                "endpoint_id": node.get("endpoint_id"),
                "annotation": node.get("annotation"),
                "title_zh": node.get("title_zh"),
                "storyline_title_zh": node.get("storyline_title_zh"),
            }
            for node in chapter_reports
        ],
        "endpoints": [
            {
                "kind": node.get("kind"),
                "endpoint_id": node.get("endpoint_id"),
                "annotation": node.get("annotation"),
                "title_zh": node.get("title_zh"),
                "target_video_key": node.get("endpoint_target_video_key"),
            }
            for node in endpoints
        ],
        "reachable_from_start_count": reachable_count([node["node_id"] for node in starts], out_edges),
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, overview: list[dict[str, Any]]) -> None:
    lines = [
        "# 已恢复 Storyline 路径图总览",
        "",
        "这份总览只覆盖当前已经从运行态内存恢复并落盘的 Storyline JSON。未恢复到 JSON 的章节不在本图中。",
        "",
        "| Storyline | 节点 | 边 | 选择边 | 视频前缀 | 章节/结算标题 |",
        "| --- | ---: | ---: | ---: | --- | --- |",
    ]
    for item in overview:
        prefixes = ", ".join(f"{k}:{v}" for k, v in item["video_prefix_counts"].items()) or "-"
        reports = "；".join(
            filter(
                None,
                [
                    report.get("title_zh") or report.get("storyline_title_zh") or report.get("annotation")
                    for report in item["chapter_reports"]
                ],
            )
        ) or "-"
        lines.append(
            f"| `{item['storyline_id']}` | {item['node_count']} | {item['edge_count']} | "
            f"{item['choice_edge_count']} | {prefixes} | {reports} |"
        )
    lines.extend(["", "## 恢复范围说明", ""])
    lines.append("- `leadLink` 是真实跳转边；`choiceEndPoint + indexGroup` 表示选择第几个选项。")
    lines.append("- `EndPoint_*` 的 `target_video_key` 是失败/结局后的回退锚点，不是当前路线继续播放。")
    lines.append("- 本图不使用 SRT 文件顺序，也不使用攻略顺序。")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_html(path: Path, overview: list[dict[str, Any]], nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    data = {"overview": overview, "nodes": nodes, "edges": edges}
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Road to Empress II Storyline Graph</title>
  <style>
    body {{ margin: 0; font-family: "Microsoft YaHei", "Noto Sans SC", Arial, sans-serif; background: #f7f3ea; color: #151515; }}
    header {{ position: sticky; top: 0; z-index: 5; background: #fffaf0; border-bottom: 1px solid #d5c6a8; padding: 14px 22px; }}
    h1 {{ margin: 0 0 8px; font-size: 22px; }}
    .toolbar {{ display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
    select, input {{ font: inherit; padding: 7px 9px; border: 1px solid #c9b995; border-radius: 4px; background: #fff; }}
    main {{ display: grid; grid-template-columns: 280px 1fr; gap: 0; min-height: calc(100vh - 78px); }}
    aside {{ border-right: 1px solid #d5c6a8; padding: 16px; background: #f0e6d4; overflow: auto; }}
    section {{ padding: 18px 22px 60px; overflow: auto; }}
    .story-btn {{ display: block; width: 100%; text-align: left; margin: 0 0 8px; padding: 10px; border: 1px solid #d1bea0; background: #fffaf0; border-radius: 6px; cursor: pointer; }}
    .story-btn.active {{ border-color: #9d762d; background: #fff3cf; }}
    .node {{ background: #fffaf2; border: 1px solid #d8c7aa; border-left: 5px solid #9d762d; border-radius: 6px; margin: 0 0 14px; padding: 14px; }}
    .node.choice {{ border-left-color: #236a88; }}
    .node.endpoint {{ border-left-color: #a33a3a; }}
    .node h2 {{ margin: 0 0 8px; font-size: 18px; }}
    .meta {{ color: #685c48; font-size: 13px; margin-bottom: 8px; }}
    .annotation {{ margin: 8px 0; line-height: 1.55; }}
    .edges {{ display: grid; gap: 8px; margin-top: 10px; }}
    .edge {{ border: 1px solid #ddceb3; border-radius: 4px; padding: 8px 10px; background: #fff; }}
    .edge a {{ color: #0f5c7a; text-decoration: none; font-weight: 700; }}
    .tag {{ display: inline-block; margin-right: 6px; padding: 2px 7px; border-radius: 999px; background: #eadabd; color: #3e3426; font-size: 12px; }}
    .empty {{ color: #776b58; }}
  </style>
</head>
<body>
  <header>
    <h1>Storyline 路径图</h1>
    <div class="toolbar">
      <select id="storySelect"></select>
      <input id="search" type="search" placeholder="搜索视频 key / 标题 / 选项">
    </div>
  </header>
  <main>
    <aside id="overview"></aside>
    <section id="content"></section>
  </main>
  <script id="graph-data" type="application/json">{payload}</script>
  <script>
    const data = JSON.parse(document.getElementById('graph-data').textContent);
    const nodesById = new Map(data.nodes.map(n => [n.node_id, n]));
    const outEdges = new Map();
    for (const edge of data.edges) {{
      if (!outEdges.has(edge.source_node_id)) outEdges.set(edge.source_node_id, []);
      outEdges.get(edge.source_node_id).push(edge);
    }}
    const storySelect = document.getElementById('storySelect');
    const overview = document.getElementById('overview');
    const content = document.getElementById('content');
    const search = document.getElementById('search');
    let currentStory = data.overview[0]?.storyline_id || '';
    function esc(s) {{ return String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c])); }}
    function nodeTitle(n) {{ return n.video_key || n.annotation || n.title_zh || n.storyline_title_zh || n.kind || n.node_id; }}
    function renderOverview() {{
      storySelect.innerHTML = data.overview.map(o => `<option value="${{esc(o.storyline_id)}}">${{esc(o.storyline_id)}} (${{
        o.node_count
      }} 节点)</option>`).join('');
      storySelect.value = currentStory;
      overview.innerHTML = data.overview.map(o => {{
        const reports = (o.chapter_reports || []).map(r => r.title_zh || r.storyline_title_zh || r.annotation).filter(Boolean).join(' / ');
        return `<button class="story-btn ${{o.storyline_id === currentStory ? 'active' : ''}}" data-story="${{esc(o.storyline_id)}}">
          <strong>${{esc(o.storyline_id)}}</strong><br>
          <span>${{o.node_count}} 节点 / ${{o.edge_count}} 边 / ${{o.choice_edge_count}} 选择边</span><br>
          <small>${{esc(reports || Object.keys(o.video_prefix_counts || {{}}).join(', '))}}</small>
        </button>`;
      }}).join('');
      overview.querySelectorAll('button').forEach(btn => btn.onclick = () => {{
        currentStory = btn.dataset.story;
        render();
      }});
    }}
    function renderNode(n) {{
      const kindClass = n.kind === 'ShowChoice' ? 'choice' : (String(n.kind || '').startsWith('EndPoint_') ? 'endpoint' : '');
      const edges = outEdges.get(n.node_id) || [];
      const edgeHtml = edges.length ? edges.map(e => {{
        const target = nodesById.get(e.target_node_id);
        const choice = e.choice_index !== null && e.choice_index !== undefined && e.choice_index >= 0
          ? `<span class="tag">选项 ${{e.choice_index}}</span>${{esc(e.choice_text_zh || e.choice_text_key || '')}}`
          : `<span class="tag">${{esc(e.source_port || 'next')}}</span>`;
        return `<div class="edge">${{choice}} → <a href="#${{esc(e.target_node_id)}}">${{esc(target ? nodeTitle(target) : e.target_label)}}</a></div>`;
      }}).join('') : '<div class="empty">没有后续边</div>';
      const choices = (n.choices || []).length ? `<div>${{n.choices.map(c => `<span class="tag">${{c.index}}</span>${{esc(c.choice_text_zh || c.choice_text_key)}}`).join(' ')}}</div>` : '';
      return `<article class="node ${{kindClass}}" id="${{esc(n.node_id)}}">
        <h2>${{esc(nodeTitle(n))}}</h2>
        <div class="meta">${{esc(n.kind)}} · hash=${{esc(n.hash)}}${{n.endpoint_id ? ' · endpoint=' + esc(n.endpoint_id) : ''}}</div>
        ${{n.storyline_title_zh ? `<div class="meta">故事线：${{esc(n.storyline_title_zh)}}</div>` : ''}}
        ${{n.title_zh && n.title_zh !== n.storyline_title_zh ? `<div class="annotation">${{esc(n.title_zh)}}</div>` : ''}}
        ${{n.annotation ? `<div class="annotation">${{esc(n.annotation)}}</div>` : ''}}
        ${{choices}}
        <div class="edges">${{edgeHtml}}</div>
      </article>`;
    }}
    function render() {{
      renderOverview();
      const q = search.value.trim().toLowerCase();
      const storyNodes = data.nodes.filter(n => n.storyline_id === currentStory).filter(n => {{
        if (!q) return true;
        return JSON.stringify(n).toLowerCase().includes(q);
      }});
      content.innerHTML = storyNodes.map(renderNode).join('') || '<p class="empty">没有匹配节点。</p>';
    }}
    storySelect.onchange = () => {{ currentStory = storySelect.value; render(); }};
    search.oninput = render;
    render();
  </script>
</body>
</html>
"""
    path.write_text(html_text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-dir", default="tools/recovered_storyline_json")
    parser.add_argument("--out-dir", default="data/game/storyline_graph")
    parser.add_argument("--text-index", default="data/index/roadtoempress2/textclient_zh.jsonl")
    args = parser.parse_args()

    text_map = load_text_map(Path(args.text_index))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_nodes: list[dict[str, Any]] = []
    all_edges: list[dict[str, Any]] = []
    overview: list[dict[str, Any]] = []

    for path in sorted(Path(args.json_dir).glob("*.json")):
        storyline_id = path.stem
        raw = json.loads(path.read_text(encoding="utf-8"))
        nodes = [normalize_node(storyline_id, node, text_map) for node in raw.get("node", [])]
        nodes_by_hash = {node["hash"]: node for node in nodes}
        edges = [normalize_edge(storyline_id, link, nodes_by_hash) for link in raw.get("leadLink", [])]
        all_nodes.extend(nodes)
        all_edges.extend(edges)
        overview.append(summarize_storyline(storyline_id, path.name, nodes, edges))

    overview.sort(key=lambda item: (min(item["video_prefix_counts"].keys()) if item["video_prefix_counts"] else "ZZZ", item["storyline_id"]))
    write_jsonl(out_dir / "nodes.jsonl", all_nodes)
    write_jsonl(out_dir / "edges.jsonl", all_edges)
    (out_dir / "overview.json").write_text(json.dumps(overview, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(
        out_dir / "choice_edges.csv",
        [edge for edge in all_edges if isinstance(edge.get("choice_index"), int) and edge.get("choice_index") >= 0],
        [
            "storyline_id",
            "source_label",
            "source_kind",
            "choice_index",
            "choice_text_zh",
            "target_label",
            "target_kind",
            "target_port",
        ],
    )
    write_csv(
        out_dir / "edges.csv",
        all_edges,
        [
            "storyline_id",
            "source_label",
            "source_kind",
            "source_port",
            "source_group",
            "source_index_group",
            "choice_index",
            "choice_text_zh",
            "target_label",
            "target_kind",
            "target_port",
        ],
    )
    write_markdown(out_dir / "README.md", overview)
    write_html(out_dir / "storyline_graph.html", overview, all_nodes, all_edges)
    print(f"storylines={len(overview)} nodes={len(all_nodes)} edges={len(all_edges)} out={out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
