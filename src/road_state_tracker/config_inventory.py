from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .protobuf_wire import parse_wire_fields

CONFIG_RELATIVE_DIR = Path("Data") / "StreamingAssets" / "res" / "main" / "cfg" / "data"
ENCRYPTED_PREFIX = b"AESType_"
VIDEO_KEY_RE = re.compile(r"^(?:[A-Z]{0,3}\d{3}_|B\d+_)?[A-Z0-9_]*\d{3}(?:_[A-Z0-9]+)*$")
TID_PREFIX_RE = re.compile(r"(TID_[A-Za-z0-9]+Config)_")


def config_data_dir(game_root: Path) -> Path:
    return game_root / CONFIG_RELATIVE_DIR


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    total = len(data)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def inspect_config_file(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    encrypted = data.startswith(ENCRYPTED_PREFIX)
    payload = data[len(ENCRYPTED_PREFIX) :] if encrypted else data
    result: dict[str, Any] = {
        "name": path.name,
        "length": len(data),
        "encrypted": encrypted,
        "header_ascii": data[: len(ENCRYPTED_PREFIX)].decode("ascii", errors="replace"),
        "payload_length": len(payload),
        "payload_mod16": len(payload) % 16,
        "payload_entropy": round(shannon_entropy(payload), 3),
        "text_prefix": config_text_prefix(path.name),
    }
    if not encrypted:
        result["protobuf_summary"] = summarize_plain_protobuf(data)
    return result


def config_text_prefix(filename: str) -> str | None:
    stem = Path(filename).stem
    if not stem or stem.startswith("TextClient"):
        return None
    if stem.endswith("Config"):
        return f"TID_{stem}"
    return f"TID_{stem}Config"


def summarize_plain_protobuf(data: bytes) -> dict[str, Any]:
    try:
        fields = parse_wire_fields(data)
    except Exception as exc:
        return {"parseable": False, "error": str(exc)}

    top_counter = Counter(str(field_no) for field_no, _, _ in fields)
    record_count = sum(1 for field_no, wire_type, _ in fields if field_no == 1 and wire_type == 2)
    strings: list[str] = []
    _collect_strings(data, strings, depth=0, max_depth=5)
    unique_strings = sorted(set(strings))
    video_keys = [value for value in unique_strings if looks_like_video_key(value)]
    tid_refs = [value for value in unique_strings if value.startswith("TID_")]
    return {
        "parseable": True,
        "top_field_counts": dict(sorted(top_counter.items(), key=lambda item: int(item[0]))),
        "top_record_count": record_count,
        "string_count": len(unique_strings),
        "video_key_count": len(video_keys),
        "tid_ref_count": len(tid_refs),
        "sample_video_keys": video_keys[:12],
        "sample_tid_refs": tid_refs[:12],
    }


def _collect_strings(data: bytes, strings: list[str], *, depth: int, max_depth: int) -> None:
    if depth > max_depth:
        return
    try:
        fields = parse_wire_fields(data)
    except Exception:
        return
    for _, wire_type, value in fields:
        if wire_type != 2:
            continue
        if isinstance(value, bytes):
            try:
                text = value.decode("utf-8")
            except UnicodeDecodeError:
                text = ""
            if text and all(char.isprintable() for char in text):
                strings.append(text)
            _collect_strings(value, strings, depth=depth + 1, max_depth=max_depth)


def looks_like_video_key(value: str) -> bool:
    if not value or len(value) > 64:
        return False
    if not any(char.isdigit() for char in value):
        return False
    if "_" not in value:
        return False
    return bool(VIDEO_KEY_RE.match(value))


def load_tid_prefix_counts(index_dir: Path) -> dict[str, int]:
    path = index_dir / "tid_text_index.jsonl"
    if not path.exists():
        return {}
    counts: Counter[str] = Counter()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            prefix = row.get("prefix")
            if not prefix:
                match = TID_PREFIX_RE.match(str(row.get("key", "")))
                prefix = match.group(1) if match else None
            if prefix:
                counts[prefix] += 1
    return dict(counts)


def build_config_inventory(game_root: Path, index_dir: Path | None = None) -> dict[str, Any]:
    cfg_dir = config_data_dir(game_root)
    files = [
        inspect_config_file(path)
        for path in sorted(cfg_dir.glob("*.pbin"))
        if not path.name.startswith("TextClient")
    ]
    tid_counts = load_tid_prefix_counts(index_dir) if index_dir else {}
    for item in files:
        prefix = item.get("text_prefix")
        item["tid_text_count"] = tid_counts.get(prefix, 0) if prefix else 0
    encrypted_count = sum(1 for item in files if item["encrypted"])
    return {
        "game_root": str(game_root),
        "config_dir": str(cfg_dir),
        "config_count": len(files),
        "encrypted_count": encrypted_count,
        "plaintext_count": len(files) - encrypted_count,
        "tid_prefix_count": len(tid_counts),
        "files": files,
    }
