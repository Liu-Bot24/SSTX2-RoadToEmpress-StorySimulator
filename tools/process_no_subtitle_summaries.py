from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import generate_video_summary_overlay as overlay


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / "data" / "runtime" / "summary_generation" / "no_subtitle_processing"
SUMMARY_DOC_DIR = PROJECT_ROOT / "data" / "knowledge" / "video_summaries" / "docs"
KEYLIKE_RE = re.compile(r"^[A-Za-z0-9_]+$")
QTE_RE = re.compile(r"QTE|限时|连按|操作成功|操作失败|倒计时|拼命", re.IGNORECASE)


def now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def project_rel(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""), encoding="utf-8")


def cue_count_for_node(node: dict[str, Any]) -> int:
    try:
        text = overlay.subtitle_doc_path(node).read_text(encoding="utf-8")
    except Exception:
        return -1
    return overlay.subtitle_cue_count_from_text(text)


def valid_title(node: dict[str, Any]) -> str:
    return overlay.effective_metadata_title(node)


def is_qte_node(node: dict[str, Any], official: str, title: str) -> bool:
    if str(node.get("kind") or "") == "PlayVideo_TraceBack":
        return True
    if re.search(r"(?:^|_)Q\d+", str(node.get("videoKey") or "")):
        return True
    return bool(QTE_RE.search("\n".join([official, title, str(node.get("annotation") or "")])))


def classify_node(node: dict[str, Any]) -> str:
    official = overlay.valid_official_annotation(node)
    title = valid_title(node)
    if official and is_qte_node(node, official, title):
        return "official_qte"
    if official:
        return "official"
    if title:
        return "title_only"
    return "key_only"


def load_video_nodes() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    nodes, by_id, incoming = overlay.load_graph()
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in nodes:
        if node.get("kind") not in {"PlayVideo_Ordinary", "PlayVideo_TraceBack"}:
            continue
        video_key = str(node.get("videoKey") or "")
        if not video_key or video_key in seen:
            continue
        seen.add(video_key)
        unique.append(node)
    return unique, by_id, incoming


def line_label(node: dict[str, Any]) -> str:
    return " / ".join(
        part
        for part in [
            str(node.get("lineTitle") or "").strip(),
            str(node.get("chapterTitle") or node.get("_graphChapterTitle") or "").strip(),
            str(node.get("chapter") or "").strip(),
        ]
        if part
    )


def compact_text(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def display_label(node: dict[str, Any]) -> str:
    return compact_text(overlay.node_label(node))


def subtitle_excerpt(node: dict[str, Any], max_items: int = 2) -> list[str]:
    try:
        text = overlay.subtitle_doc_path(node).read_text(encoding="utf-8")
    except Exception:
        return []
    lines = []
    for line in text.splitlines():
        if re.match(r"^\s*\d+\.\s+`", line):
            lines.append(compact_text(re.sub(r"^\s*\d+\.\s+", "", line)))
    if len(lines) <= max_items * 2:
        return lines
    return lines[:max_items] + ["..."] + lines[-max_items:]


def existing_summary_map(rows: list[dict[str, Any]], zero_keys: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in rows:
        key = str(row.get("video_key") or "")
        if not key or key in zero_keys:
            continue
        summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
        display = compact_text(summary.get("display_summary"))
        if display and key not in result:
            result[key] = display
    return result


def context_for_node(node: dict[str, Any] | None, summaries: dict[str, str]) -> str:
    if not node:
        return ""
    key = str(node.get("videoKey") or "").strip()
    label = display_label(node)
    if not key:
        return f"{node.get('id')}：{label}"
    if key and key in summaries:
        return f"{key}：{summaries[key]}"
    excerpts = subtitle_excerpt(node)
    if excerpts:
        return f"{key}：字幕摘录 {' / '.join(excerpts)}"
    return f"{key or node.get('id')}：{label}"


def upstream_choice_text(
    node: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    incoming: dict[str, list[dict[str, Any]]],
) -> str:
    info = overlay.nearest_upstream_choice(str(node.get("id") or ""), by_id, incoming)
    if not info:
        return ""
    choice = info.get("node") or {}
    edge = info.get("edge") or {}
    question = compact_text(choice.get("title") or choice.get("storylineTitle") or choice.get("annotation"))
    answer = compact_text(edge.get("choiceText"))
    if question and answer:
        return f"上游选择：{question} / 当前选项：{answer}"
    return question or answer


def downstream_texts(node: dict[str, Any], by_id: dict[str, dict[str, Any]], summaries: dict[str, str]) -> list[str]:
    result = []
    for child in overlay.downstream_nodes(node, by_id, summaries)[:3]:
        edge = child.get("viaEdge") or {}
        prefix = ""
        if edge.get("choiceText"):
            prefix = f"{edge.get('choiceText')} → "
        elif edge.get("targetLabel"):
            prefix = f"{edge.get('targetLabel')} → "
        result.append(prefix + context_for_node(child, summaries))
    return [item for item in result if item.strip()]


def metadata_evidence_for_title(node: dict[str, Any]) -> list[str]:
    if compact_text(node.get("storylineTitle")) == valid_title(node):
        return ["metadata:target:storylineTitle"]
    if compact_text(node.get("title")) == valid_title(node):
        return ["metadata:target:title"]
    return ["metadata:target:videoKey"]


def make_summary(
    node: dict[str, Any],
    category: str,
    by_id: dict[str, dict[str, Any]],
    incoming: dict[str, list[dict[str, Any]]],
    summaries: dict[str, str],
) -> tuple[dict[str, Any], str]:
    video_key = str(node.get("videoKey") or "").strip()
    official = compact_text(overlay.valid_official_annotation(node))
    title = valid_title(node)
    title_text = compact_text(title)
    prev_nodes = overlay.upstream_videos(str(node.get("id") or ""), by_id, incoming, limit=3)
    previous = [context_for_node(item, summaries) for item in prev_nodes[:2]]
    downstream = downstream_texts(node, by_id, summaries)
    choice = upstream_choice_text(node, by_id, incoming)
    context_refs = [item for item in [choice, *[f"前文：{item}" for item in previous], *[f"后续：{item}" for item in downstream]] if item]
    if category == "official":
        display = official
        main_fact = official
        confidence = "high"
        confidence_bucket = "high_confidence"
        detail_focus = f"官方摘要明确写明：{official}"
        evidence = ["official_annotation:target"]
    elif category == "official_qte":
        display = title_text if title_text and title_text not in official else official
        if official and title_text and title_text not in official:
            display = f"{display}（{official}）"
        main_fact = f"该无字幕操作节点的官方摘要为：{official}"
        confidence = "high" if official else "medium"
        confidence_bucket = "high_confidence" if official else "needs_confirmation"
        detail_focus = f"这是无字幕操作/QTE节点；官方摘要为：{official}"
        evidence = ["official_annotation:target"]
    else:
        display = f"无字幕节点：{title_text}。"
        main_fact = f"本无字幕节点的路线图标题为「{title_text}」。"
        confidence = "medium" if (previous or downstream) else "low"
        confidence_bucket = "needs_confirmation"
        detail_focus = f"没有官方摘要；只能确认路线图标题为「{title_text}」。"
        evidence = metadata_evidence_for_title(node)

    detailed = [
        "目标视频片段文档明确标记为无字幕。",
        detail_focus,
    ]
    if previous:
        detailed.append(f"相邻前文参考：{previous[0]}")
    if downstream:
        detailed.append(f"相邻后文参考：{downstream[0]}")
    if category == "title_only":
        detailed.append("由于没有官方摘要，以上内容只作为节点定位和剧情标题说明，不扩写具体画面。")

    risk_flags = ["目标视频无字幕，不能从对白层面核实具体画面。"]
    if category == "title_only":
        risk_flags.append("无官方摘要；标题含义需要结合相邻节点理解，建议抽查确认。")
    if category == "official_qte":
        risk_flags.append("操作/QTE节点通常只表达动作或成败分叉，不应扩写为额外剧情。")

    summary = {
        "display_summary": display,
        "detailed_summary": detailed,
        "event_facts": [
            {
                "fact": f"本节点位于{line_label(node)}，video key 为 {video_key}。",
                "evidence": ["metadata:target:lineTitle", "metadata:target:chapterTitle", "metadata:target:videoKey"],
            },
            {
                "fact": f"本节点类型为 {node.get('kind') or ''}，字幕文档标记为无字幕。",
                "evidence": ["metadata:target:kind"],
            },
            {
                "fact": main_fact,
                "evidence": evidence,
            },
        ],
        "context_refs": context_refs or ["无可用相邻上下文。"],
        "risk_flags": risk_flags,
        "confidence": confidence,
        "sourceType": "local_no_subtitle",
        "noSubtitleCategory": category,
    }
    return summary, confidence_bucket


def write_raw_summary(node: dict[str, Any], summary: dict[str, Any], stamp: str) -> Path:
    chapter = str(node.get("chapter") or "unknown")
    video_key = str(node.get("videoKey") or "unknown")
    out_dir = overlay.RUN_DIR / chapter
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{video_key}.local-no-subtitle.{stamp}.raw.txt"
    overlay.write_text(out_path, json.dumps(summary, ensure_ascii=False, indent=2))
    meta_path = out_path.with_suffix(".meta.json")
    overlay.write_text(
        meta_path,
        json.dumps(
            {
                "model": "local-no-subtitle",
                "command": ["tools/process_no_subtitle_summaries.py"],
                "returncode": 0,
                "stdout": project_rel(out_path),
                "metadataOnly": True,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    verified_path = out_path.with_suffix(".verified.json")
    overlay.write_text(verified_path, json.dumps({"ok": True, "issues": [], "summary": summary}, ensure_ascii=False, indent=2))
    return out_path


def move_stale_docs(zero_keys: set[str], stamp: str, dry_run: bool) -> list[str]:
    moved: list[str] = []
    target_dir = RUNTIME_DIR / "quarantined_old_docs" / stamp
    for key in sorted(zero_keys):
        doc = SUMMARY_DOC_DIR / overlay.safe_summary_filename(key)
        if not doc.exists():
            continue
        moved.append(project_rel(doc))
        if dry_run:
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(doc), str(target_dir / doc.name))
    return moved


def run(apply: bool) -> Path:
    stamp = now_id()
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    nodes, by_id, incoming = load_video_nodes()
    zero_nodes = [node for node in nodes if cue_count_for_node(node) == 0]
    zero_keys = {str(node.get("videoKey") or "") for node in zero_nodes}
    rows_before = read_jsonl(overlay.SUMMARY_JSONL)
    summaries = existing_summary_map(rows_before, zero_keys)
    removed_rows = [row for row in rows_before if str(row.get("video_key") or "") in zero_keys]
    kept_rows = [row for row in rows_before if str(row.get("video_key") or "") not in zero_keys]
    old_by_key = {str(row.get("video_key") or ""): row for row in removed_rows}

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in zero_nodes:
        grouped[classify_node(node)].append(node)

    generated_records: list[dict[str, Any]] = []
    report_rows: list[dict[str, Any]] = []
    for category in ("official", "official_qte", "title_only"):
        for node in grouped.get(category, []):
            summary, bucket = make_summary(node, category, by_id, incoming, summaries)
            raw_path = write_raw_summary(node, summary, stamp) if apply else Path(f"DRY-RUN/{node.get('videoKey')}.raw.txt")
            generated_records.append(
                {
                    "video_key": str(node.get("videoKey") or ""),
                    "status": "final",
                    "source": {
                        "kind": "metadata_context_summary",
                        "basis": ["official_annotation", "storyline_title", "neighboring_nodes"],
                    },
                    "summary": summary,
                }
            )
            report_rows.append(
                {
                    "video_key": node.get("videoKey"),
                    "category": category,
                    "bucket": bucket,
                    "display_summary": summary["display_summary"],
                    "confidence": summary["confidence"],
                    "old_display_summary": (
                        (old_by_key.get(str(node.get("videoKey") or "")) or {}).get("summary") or {}
                    ).get("display_summary"),
                    "old_confidence": (
                        (old_by_key.get(str(node.get("videoKey") or "")) or {}).get("summary") or {}
                    ).get("confidence"),
                }
            )

    stale_docs = move_stale_docs(zero_keys, stamp, dry_run=not apply)
    if apply:
        backup = RUNTIME_DIR / f"video_summaries_before_no_subtitle_rebuild_{stamp}.jsonl"
        write_jsonl(backup, rows_before)
        write_jsonl(RUNTIME_DIR / f"removed_old_no_subtitle_records_{stamp}.jsonl", removed_rows)
        write_jsonl(overlay.SUMMARY_JSONL, kept_rows + generated_records)
        subprocess.run([sys.executable, "tools\\build_knowledge_navigation.py"], cwd=PROJECT_ROOT, check=True)

    category_counts = {name: len(items) for name, items in sorted(grouped.items())}
    bucket_counts = Counter(row["bucket"] for row in report_rows)
    report_path = RUNTIME_DIR / f"no_subtitle_report_{stamp}.md"
    lines = [
        "# 无字幕节点处理报告",
        "",
        f"- apply: {apply}",
        f"- zero_cue_total: {len(zero_nodes)}",
        f"- old_no_subtitle_baseline_records: {len(removed_rows)}",
        f"- new_records_generated: {len(generated_records)}",
        f"- stale_docs_to_move_if_apply: {len(stale_docs)}",
        "- note: apply=false 时不清理旧 30 条；旧记录只作为校验基线。",
        "",
        "## 分类数量",
        "",
    ]
    for name, count in category_counts.items():
        lines.append(f"- {name}: {count}")
    lines.extend(["", "## 结果桶", ""])
    for name, count in sorted(bucket_counts.items()):
        lines.append(f"- {name}: {count}")
    lines.extend(["", "## 已写入/将写入", ""])
    for row in report_rows:
        lines.append(f"- `{row['video_key']}` [{row['category']}/{row['bucket']}/{row['confidence']}] {row['display_summary']}")
    lines.extend(["", "## 与旧 30 条基线对比", ""])
    compared = [row for row in report_rows if row.get("old_display_summary")]
    for row in compared:
        changed = "相同" if compact_text(row["old_display_summary"]) == compact_text(row["display_summary"]) else "不同"
        lines.append(f"### `{row['video_key']}` [{row['category']}] {changed}")
        lines.append("")
        lines.append(f"- 旧版：{row['old_display_summary']}")
        lines.append(f"- 新草案：{row['display_summary']}")
        lines.append(f"- 旧 confidence：`{row.get('old_confidence')}`；新 confidence：`{row['confidence']}`")
        lines.append("")
    generated_keys = {str(row["video_key"]) for row in report_rows}
    old_only = [row for row in removed_rows if str(row.get("video_key") or "") not in generated_keys]
    lines.extend(["", "## 旧 30 条中本轮不重写的记录", ""])
    lines.append("这些旧记录属于无官方摘要且只有 key 的 D 类，按当前指令暂不处理，只保留作校验基线。")
    lines.append("")
    for row in old_only:
        summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
        lines.append(f"- `{row.get('video_key')}` {compact_text(summary.get('display_summary'))}")
    lines.extend(["", "## 暂不处理：无官方摘要且只有 key", ""])
    for node in grouped.get("key_only", []):
        lines.append(f"- `{node.get('videoKey')}` {line_label(node)}")
    lines.extend(["", "## 旧无字幕基线记录", ""])
    for row in removed_rows:
        lines.append(f"- `{row.get('video_key')}`")
    overlay.write_text(report_path, "\n".join(lines) + "\n")
    print(json.dumps(
        {
            "report": project_rel(report_path),
            "apply": apply,
            "zero_cue_total": len(zero_nodes),
            "category_counts": category_counts,
            "old_no_subtitle_baseline_records": len(removed_rows),
            "new_records_generated": len(generated_records),
            "stale_docs_to_move_if_apply": len(stale_docs),
            "bucket_counts": dict(bucket_counts),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Process no-subtitle video summary records separately from Claude runs.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    run(apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
