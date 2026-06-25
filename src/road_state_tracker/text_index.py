from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .protobuf_wire import parse_wire_fields


LANG_FIELDS = {
    2: "zh_CN",
    4: "zh_GL",
    6: "zh_TW",
    8: "en_US",
    10: "ja_JP",
    12: "ko_KR",
    14: "de_DE",
    16: "fr_FR",
    18: "es_ES",
    28: "th_TH",
}


@dataclass(frozen=True)
class IndexSummary:
    game_root: str
    index_dir: str
    textclient_files: int
    textclient_rows_total: int
    textclient_zh_rows_deduped: int
    choice_groups: int
    srt_files: int
    srt_rows: int
    tid_text_rows: int


def decode_utf8(value: bytes) -> str | None:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return None


def clean_key(key: str) -> str:
    return re.sub(r"^(Key:|KEY:)", "", key).strip()


def classify_key(key: str) -> str:
    normalized = clean_key(key)
    if ".choice+" in normalized or ".choiceText+" in normalized:
        return "choice_text"
    if normalized.endswith(".storylineTitle"):
        return "storyline_title"
    if normalized.endswith(".title"):
        return "choice_prompt_or_title"
    if normalized.startswith(("PlayVideo_", "Deprecated@PlayVideo_")):
        return "video_text"
    if normalized.startswith(("EndPoint_", "Deprecated@EndPoint_")):
        return "ending_or_report"
    return "other"


def chapter_hint(source_file: str, key: str) -> str | None:
    source_match = re.match(r"TextClientchapter(.+)\.pbin$", source_file)
    if source_match:
        return source_match.group(1)
    key_match = re.search(r"(?:^|[_-])(\d{3})(?:[_-]|$)", clean_key(key))
    return key_match.group(1) if key_match else None


def display_zh(text_fields: dict[int, str]) -> str:
    return text_fields.get(4) or text_fields.get(2) or ""


def tid_prefix(key: str) -> str | None:
    match = re.match(r"(TID_[A-Za-z0-9]+Config)_", clean_key(key))
    return match.group(1) if match else None


def text_length_bucket(text: str) -> str:
    stripped = text.strip()
    if len(stripped) <= 8:
        return "short_name_or_label_candidate"
    if len(stripped) <= 32:
        return "short_label_or_title_candidate"
    return "long_profile_or_description_candidate"


def row_quality(row: dict[str, Any]) -> tuple[int, int]:
    language_count = len(row.get("language_texts", {}))
    source_bonus = 1 if row.get("source_file") == "TextClientExcel.pbin" else 0
    return language_count, source_bonus


def parse_textclient_pbin(path: Path, game_root: Path) -> tuple[list[dict[str, Any]], str | None]:
    data = path.read_bytes()
    if data.startswith(b"AESType_"):
        return [], "encrypted"

    rows: list[dict[str, Any]] = []
    for _, wire_type, value in parse_wire_fields(data):
        if wire_type != 2 or not isinstance(value, bytes):
            continue
        try:
            sub_fields = parse_wire_fields(value)
        except ValueError:
            continue

        text_fields: dict[int, str] = {}
        for field_number, sub_wire, sub_value in sub_fields:
            if sub_wire == 2 and isinstance(sub_value, bytes):
                decoded = decode_utf8(sub_value)
                if decoded is not None:
                    text_fields[field_number] = decoded

        raw_key = text_fields.get(1, "")
        language_texts = {
            name: text_fields[number]
            for number, name in LANG_FIELDS.items()
            if number in text_fields
        }
        zh = display_zh(text_fields)
        if not raw_key:
            continue

        rows.append(
            {
                "source_file": path.name,
                "relative_path": str(path.relative_to(game_root)),
                "key": clean_key(raw_key),
                "raw_key": raw_key,
                "kind": classify_key(raw_key),
                "chapter_hint": chapter_hint(path.name, raw_key),
                "zh": zh,
                "zh_CN": language_texts.get("zh_CN", ""),
                "zh_GL": language_texts.get("zh_GL", ""),
                "zh_TW": language_texts.get("zh_TW", ""),
                "en_US": language_texts.get("en_US", ""),
                "language_texts": language_texts,
                "translations": language_texts,
            }
        )
    return rows, None


def parse_textclient_files(game_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cfg_dir = game_root / "Data" / "StreamingAssets" / "res" / "main" / "cfg" / "data"
    files = sorted(cfg_dir.glob("TextClient*.pbin"))
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for path in files:
        parsed, reason = parse_textclient_pbin(path, game_root)
        if reason:
            skipped.append({"file": path.name, "reason": reason})
        rows.extend(parsed)

    deduped_by_identity: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if not row["zh"]:
            continue
        identity = (row["key"], row["zh"])
        existing = deduped_by_identity.get(identity)
        if existing is None or row_quality(row) > row_quality(existing):
            deduped_by_identity[identity] = row
    deduped = list(deduped_by_identity.values())

    stats = {
        "textclient_files": len(files),
        "rows_total": len(rows),
        "rows_zh_deduped": len(deduped),
        "skipped": skipped,
        "kind_counts": Counter(row["kind"] for row in deduped),
    }
    return deduped, stats


def parse_srt_files(game_root: Path, language: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    srt_root = game_root / "Data" / "StreamingAssets" / "res" / "main" / "SSTX2" / "Global" / "srt"
    lang_dir = srt_root / language
    if not lang_dir.exists():
        return [], {"files": 0, "rows": 0, "missing": True}

    rows: list[dict[str, Any]] = []
    files = sorted(lang_dir.rglob("*.srt"))
    for path in files:
        rows.extend(parse_srt_file(path, lang_dir, language))

    return rows, {"files": len(files), "rows": len(rows)}


def parse_srt_file(path: Path, lang_dir: Path, language: str) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())
    rows: list[dict[str, Any]] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        match = re.match(r"(.+?)\s*-->\s*(.+)", lines[1])
        if not match:
            continue
        rows.append(
            {
                "language": language,
                "relative_path": str(path.relative_to(lang_dir)),
                "chapter": path.parent.name,
                "scene_id": path.stem,
                "index": lines[0],
                "start": match.group(1).strip(),
                "end": match.group(2).strip(),
                "text": " ".join(lines[2:]).strip(),
            }
        )
    return rows


def choice_group_for_key(key: str) -> tuple[str | None, str | None, int | None]:
    normalized = clean_key(key)
    if normalized.endswith(".storylineTitle"):
        return normalized[: -len(".storylineTitle")], "storyline_title", None
    if normalized.endswith(".title"):
        return normalized[: -len(".title")], "title", None
    match = re.match(r"(.+)\.choice\+(\d+)\.choiceText$", normalized)
    if match:
        return match.group(1), "choice", int(match.group(2))
    match = re.match(r"(.+)\.choiceText\+(\d+)$", normalized)
    if match:
        return match.group(1), "choice", int(match.group(2))
    return None, None, None


def build_choice_groups(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = defaultdict(lambda: {"choices": {}})
    for row in rows:
        group_name, part, index = choice_group_for_key(row["key"])
        if group_name is None:
            continue
        group = groups[group_name]
        group["id"] = group_name
        group["source_file"] = group.get("source_file") or row["source_file"]
        group["chapter_hint"] = group.get("chapter_hint") or row.get("chapter_hint")
        if part == "storyline_title":
            group["storyline_title"] = row["zh"]
        elif part == "title":
            group["prompt"] = row["zh"]
        elif part == "choice" and index is not None:
            group["choices"][index] = row["zh"]

    output: list[dict[str, Any]] = []
    for group in groups.values():
        group["choices"] = [
            {"index": index, "text": text}
            for index, text in sorted(group["choices"].items())
        ]
        output.append(group)
    return sorted(output, key=lambda item: item["id"])


def build_tid_text_index(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows_by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row["key"]
        prefix = tid_prefix(key)
        if prefix is None:
            continue
        existing = rows_by_key.get(key)
        if existing is None or row_quality(row) > row_quality(existing):
            rows_by_key[key] = row

    output: list[dict[str, Any]] = []
    for key, row in rows_by_key.items():
        prefix = tid_prefix(key)
        if prefix is None:
            continue
        zh = row.get("zh", "")
        output.append(
            {
                "key": key,
                "prefix": prefix,
                "source_file": row.get("source_file"),
                "zh": zh,
                "zh_CN": row.get("zh_CN", ""),
                "zh_GL": row.get("zh_GL", ""),
                "zh_TW": row.get("zh_TW", ""),
                "en_US": row.get("en_US", ""),
                "language_texts": row.get("language_texts", {}),
                "text_length_bucket": text_length_bucket(zh),
            }
        )
    return sorted(output, key=lambda item: item["key"])


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_index(game_root: Path, index_dir: Path, language: str = "zh_GL") -> IndexSummary:
    index_dir.mkdir(parents=True, exist_ok=True)
    text_rows, text_stats = parse_textclient_files(game_root)
    srt_rows, srt_stats = parse_srt_files(game_root, language)
    choice_groups = build_choice_groups(text_rows)
    tid_text_rows = build_tid_text_index(text_rows)

    write_jsonl(index_dir / "textclient_zh.jsonl", text_rows)
    write_jsonl(index_dir / f"srt_{language}.jsonl", srt_rows)
    write_jsonl(index_dir / "choice_groups.jsonl", choice_groups)
    write_jsonl(index_dir / "tid_text_index.jsonl", tid_text_rows)

    summary = IndexSummary(
        game_root=str(game_root),
        index_dir=str(index_dir),
        textclient_files=text_stats["textclient_files"],
        textclient_rows_total=text_stats["rows_total"],
        textclient_zh_rows_deduped=text_stats["rows_zh_deduped"],
        choice_groups=len(choice_groups),
        srt_files=srt_stats["files"],
        srt_rows=srt_stats["rows"],
        tid_text_rows=len(tid_text_rows),
    )
    (index_dir / "summary.json").write_text(
        json.dumps(summary.__dict__, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def search_index(index_dir: Path, query: str, limit: int = 20) -> list[dict[str, Any]]:
    query = query.strip()
    if not query:
        return []

    candidates: list[dict[str, Any]] = []
    for filename, text_field in (
        ("choice_groups.jsonl", "prompt"),
        ("tid_text_index.jsonl", "zh"),
        ("textclient_zh.jsonl", "zh"),
        ("srt_zh_GL.jsonl", "text"),
    ):
        path = index_dir / filename
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                haystack = json.dumps(row, ensure_ascii=False)
                if query in haystack:
                    score = 100 if query in str(row.get(text_field, "")) else 50
                    candidates.append({"score": score, "source": filename, "row": row})

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:limit]
