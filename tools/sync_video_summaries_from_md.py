from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_ROOT = PROJECT_ROOT / "data" / "knowledge" / "video_summaries"
SUMMARY_DOC_DIR = SUMMARY_ROOT / "docs"
SUMMARY_JSONL = SUMMARY_ROOT / "video_summaries.jsonl"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def read_existing_rows() -> list[dict[str, Any]]:
    if not SUMMARY_JSONL.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in read_text(SUMMARY_JSONL).splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def summary_status(row: dict[str, Any] | None) -> str:
    raw = str((row or {}).get("status") or "final").strip()
    return raw or "final"


def source_from_label(label: str, existing: dict[str, Any] | None) -> dict[str, Any]:
    existing_source = (existing or {}).get("source")
    if isinstance(existing_source, dict) and existing_source:
        return existing_source
    if "DeepSeek V4 Flash" in label:
        return {"kind": "ai_generated_summary", "model": "DeepSeek V4 Flash"}
    if "无字幕节点整理" in label:
        return {"kind": "metadata_context_summary", "label": label}
    if label:
        return {"kind": "markdown_summary", "label": label}
    return {"kind": "markdown_summary"}


def compact_block(lines: list[str]) -> str:
    return re.sub(r"\s+", " ", "\n".join(lines).strip()).strip()


def section_lines(block: list[str], title: str) -> list[str]:
    start = None
    target = title.lower()
    for index, line in enumerate(block):
        if line.strip().lower() == f"### {target}":
            start = index + 1
            break
    if start is None:
        return []
    end = len(block)
    for index in range(start, len(block)):
        if re.match(r"^#{2,6}\s+", block[index].strip()):
            end = index
            break
    result = block[start:end]
    while result and not result[0].strip():
        result.pop(0)
    while result and not result[-1].strip():
        result.pop()
    return result


def list_section(block: list[str], title: str) -> list[str]:
    items: list[str] = []
    for line in section_lines(block, title):
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        value = stripped[2:].strip()
        if value and value != "无":
            items.append(value)
    return items


def event_fact_section(block: list[str]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for value in list_section(block, "event_facts"):
        match = re.match(r"^(.*)（证据：(.+)）$", value)
        if match:
            evidence = [item.strip() for item in match.group(2).split("；") if item.strip()]
            facts.append({"fact": match.group(1).strip(), "evidence": evidence})
        else:
            facts.append({"fact": value, "evidence": []})
    return facts


def meta_value(block: list[str], label: str) -> str:
    prefix = f"- {label}："
    for line in block:
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped.removeprefix(prefix).strip().strip("`")
    return ""


def split_record_blocks(lines: list[str]) -> list[list[str]]:
    starts = [index for index, line in enumerate(lines) if re.match(r"^##\s+记录\s+\d+\s*$", line.strip())]
    if not starts:
        return [lines]
    blocks: list[list[str]] = []
    for offset, start in enumerate(starts):
        end = starts[offset + 1] if offset + 1 < len(starts) else len(lines)
        blocks.append(lines[start:end])
    return blocks


def parse_summary_doc(path: Path, existing_by_key: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    video_key = path.name.removesuffix(".summary.md")
    lines = read_text(path).splitlines()
    records: list[dict[str, Any]] = []
    existing = existing_by_key.get(video_key)
    for block in split_record_blocks(lines):
        display_summary = compact_block(section_lines(block, "display_summary"))
        if not display_summary:
            continue
        source_label = meta_value(block, "来源")
        confidence = meta_value(block, "confidence")
        records.append(
            {
                "video_key": video_key,
                "status": summary_status(existing),
                "summary": {
                    "display_summary": display_summary,
                    "detailed_summary": list_section(block, "detailed_summary"),
                    "event_facts": event_fact_section(block),
                    "context_refs": list_section(block, "context_refs"),
                    "risk_flags": list_section(block, "risk_flags"),
                    "confidence": confidence,
                },
                "source": source_from_label(source_label, existing),
            }
        )
    return records


def parse_summary_docs() -> list[dict[str, Any]]:
    existing_rows = read_existing_rows()
    existing_by_key = {
        str(row.get("video_key") or "").strip(): row
        for row in existing_rows
        if str(row.get("video_key") or "").strip()
    }
    rows_by_key: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(SUMMARY_DOC_DIR.glob("*.summary.md")):
        rows = parse_summary_doc(path, existing_by_key)
        if rows:
            rows_by_key[path.name.removesuffix(".summary.md")] = rows

    ordered_keys: list[str] = []
    for row in existing_rows:
        key = str(row.get("video_key") or "").strip()
        if key and key in rows_by_key and key not in ordered_keys:
            ordered_keys.append(key)
    for key in sorted(rows_by_key):
        if key not in ordered_keys:
            ordered_keys.append(key)

    result: list[dict[str, Any]] = []
    for key in ordered_keys:
        result.extend(rows_by_key[key])
    return result


def sync_jsonl_from_md() -> int:
    rows = parse_summary_docs()
    lines = [json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows]
    write_text(SUMMARY_JSONL, "\n".join(lines))
    return len(rows)


def main() -> int:
    count = sync_jsonl_from_md()
    print(f"synced {count} summary rows from Markdown docs -> {SUMMARY_JSONL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
