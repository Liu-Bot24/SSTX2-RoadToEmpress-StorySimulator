from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PATCH_VERSION = "0.1.1"
SRT_RELATIVE_ROOT = Path("Data") / "StreamingAssets" / "res" / "main" / "SSTX2" / "Global" / "srt"
TEXTCLIENT_RELATIVE_DIR = Path("Data") / "StreamingAssets" / "res" / "main" / "cfg" / "data"
DEFAULT_LANGUAGE = "zh_GL,zh_TW"
DEFAULT_BACKUP_DIRNAME = ".sstx2_historical_text_patch_backup"
PATCH_MANIFEST_PATH = Path(__file__).with_name("patch_manifest.json")
PATCH_MANIFEST_TW_PATH = Path(__file__).with_name("patch_manifest_zh_TW.json")
CHINESE_TEXT_FIELD_NUMBERS = {2, 4, 6}
ONLINE_SUBTITLE_HOST = "eo.roadtoempress.com"
HOSTS_MARKER_BEGIN = "# SSTX2 historical text patch: block online subtitles begin"
HOSTS_MARKER_END = "# SSTX2 historical text patch: block online subtitles end"
LEGACY_HOSTS_MARKER = "# SSTX2 temporary block online subtitles"
HOSTS_PATH_OVERRIDE: Path | None = None


@dataclass
class Replacement:
    id: str
    source: str
    target: str
    modes: set[str]
    targets: set[str]
    textclient_keys: set[str]
    exact_text_only: bool
    skip_when_near: list[str]
    near_window: int


@dataclass
class PatchStats:
    processed_files: int = 0
    changed_files: int = 0
    replacements: int = 0
    skipped_files: int = 0

    def add(self, other: "PatchStats") -> None:
        self.processed_files += other.processed_files
        self.changed_files += other.changed_files
        self.replacements += other.replacements
        self.skipped_files += other.skipped_files


@dataclass
class WireField:
    field_number: int
    wire_type: int
    value: int | bytes


def read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    start = offset
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
        if shift > 70:
            raise ValueError(f"varint too long at byte {start}")
    raise ValueError("truncated varint")


def encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("negative varint is not supported")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def parse_wire_fields(data: bytes) -> list[WireField]:
    offset = 0
    fields: list[WireField] = []
    while offset < len(data):
        key, offset = read_varint(data, offset)
        field_number = key >> 3
        wire_type = key & 7
        if wire_type == 0:
            value, offset = read_varint(data, offset)
        elif wire_type == 1:
            value = data[offset : offset + 8]
            offset += 8
        elif wire_type == 2:
            length, offset = read_varint(data, offset)
            value = data[offset : offset + length]
            offset += length
        elif wire_type == 5:
            value = data[offset : offset + 4]
            offset += 4
        else:
            raise ValueError(f"unsupported wire type {wire_type} at byte {offset}")
        fields.append(WireField(field_number, wire_type, value))
    return fields


def serialize_wire_fields(fields: list[WireField]) -> bytes:
    out = bytearray()
    for field in fields:
        out.extend(encode_varint((field.field_number << 3) | field.wire_type))
        if field.wire_type == 0:
            if not isinstance(field.value, int):
                raise TypeError("varint field value must be int")
            out.extend(encode_varint(field.value))
        elif field.wire_type == 1:
            if not isinstance(field.value, bytes) or len(field.value) != 8:
                raise TypeError("64-bit field value must be 8 bytes")
            out.extend(field.value)
        elif field.wire_type == 2:
            if not isinstance(field.value, bytes):
                raise TypeError("length-delimited field value must be bytes")
            out.extend(encode_varint(len(field.value)))
            out.extend(field.value)
        elif field.wire_type == 5:
            if not isinstance(field.value, bytes) or len(field.value) != 4:
                raise TypeError("32-bit field value must be 4 bytes")
            out.extend(field.value)
        else:
            raise ValueError(f"unsupported wire type {field.wire_type}")
    return bytes(out)


def decode_utf8(value: bytes) -> str | None:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return None


def load_replacements(mode: str, manifest_path: Path = PATCH_MANIFEST_PATH) -> list[Replacement]:
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected: dict[str, tuple[int, Replacement]] = {}
    for item in raw.get("replacements", []):
        modes = set(item.get("modes") or [])
        if mode not in modes:
            continue
        source = str(item.get("from") or "")
        target = str(item.get("to") or "")
        if not source or source == target:
            continue
        priority = 1 if item.get("sourceGroup") == "game_ui_extra" else 0
        replacement = Replacement(
            id=str(item.get("id") or source),
            source=source,
            target=target,
            modes=modes,
            targets=set(item.get("targets") or ["srt", "textclient"]),
            textclient_keys={str(value) for value in item.get("textClientKeys", []) if value},
            exact_text_only=bool(item.get("exactTextOnly")),
            skip_when_near=[str(value) for value in item.get("skipWhenNear", []) if value],
            near_window=int(item.get("nearWindow") or 8),
        )
        current = selected.get(source)
        if current is None or priority >= current[0]:
            selected[source] = (priority, replacement)
    replacements = [replacement for _, replacement in selected.values()]
    return sorted(replacements, key=lambda replacement: (-len(replacement.source), replacement.source))


def nearby_text(text: str, offset: int, source: str, radius: int) -> str:
    start = max(0, offset - radius)
    end = min(len(text), offset + len(source) + radius)
    return text[start:end]


def replacement_applies(replacement: Replacement, target: str, record_key: str | None) -> bool:
    if target not in replacement.targets:
        return False
    if replacement.textclient_keys and record_key not in replacement.textclient_keys:
        return False
    return True


def apply_replacements_to_text(
    text: str,
    replacements: list[Replacement],
    target: str,
    record_key: str | None = None,
) -> tuple[str, int]:
    output = text
    total = 0
    for replacement in replacements:
        if not replacement_applies(replacement, target, record_key):
            continue
        if replacement.exact_text_only:
            if output == replacement.source:
                output = replacement.target
                total += 1
            continue
        if replacement.source not in output:
            continue
        cursor = 0
        chunks: list[str] = []
        changed = 0
        while cursor < len(output):
            index = output.find(replacement.source, cursor)
            if index == -1:
                chunks.append(output[cursor:])
                break
            chunks.append(output[cursor:index])
            should_skip = False
            if replacement.skip_when_near:
                segment = nearby_text(output, index, replacement.source, replacement.near_window)
                should_skip = any(phrase in segment for phrase in replacement.skip_when_near)
            if should_skip:
                chunks.append(replacement.source)
            else:
                chunks.append(replacement.target)
                changed += 1
            cursor = index + len(replacement.source)
        if changed:
            output = "".join(chunks)
            total += changed
    return output, total


def detect_text_encoding(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return "utf-16"
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "gb18030"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def relative_to_game_root(path: Path, game_root: Path) -> str:
    return path.resolve().relative_to(game_root.resolve()).as_posix()


def backup_file(path: Path, game_root: Path, backup_root: Path, manifest: dict[str, Any]) -> None:
    rel = relative_to_game_root(path, game_root)
    original = path.read_bytes()
    backup_path = backup_root / rel
    if rel not in manifest["files"]:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_path)
        manifest["files"][rel] = {
            "sha256": sha256(original),
            "size": len(original),
            "backup": rel,
        }


def load_manifest(backup_root: Path) -> dict[str, Any]:
    manifest_path = backup_root / "manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "schemaVersion": 1,
        "patchVersion": PATCH_VERSION,
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "files": {},
    }


def save_manifest(backup_root: Path, manifest: dict[str, Any]) -> None:
    backup_root.mkdir(parents=True, exist_ok=True)
    manifest["updatedAt"] = datetime.now().isoformat(timespec="seconds")
    (backup_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def hosts_path() -> Path:
    if HOSTS_PATH_OVERRIDE is not None:
        return HOSTS_PATH_OVERRIDE
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    return system_root / "System32" / "drivers" / "etc" / "hosts"


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def hosts_has_active_block(text: str) -> bool:
    for line in normalize_newlines(text).split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) >= 2 and parts[1].lower() == ONLINE_SUBTITLE_HOST:
            return parts[0] in {"127.0.0.1", "0.0.0.0"}
    return False


def strip_legacy_hosts_block(text: str) -> tuple[str, bool]:
    lines = normalize_newlines(text).split("\n")
    output: list[str] = []
    removed = False
    index = 0
    while index < len(lines):
        if lines[index].strip() == LEGACY_HOSTS_MARKER:
            next_index = index + 1
            while next_index < len(lines) and not lines[next_index].strip():
                next_index += 1
            if next_index < len(lines):
                parts = lines[next_index].strip().split()
                if len(parts) >= 2 and parts[1].lower() == ONLINE_SUBTITLE_HOST and parts[0] in {"127.0.0.1", "0.0.0.0"}:
                    removed = True
                    index = next_index + 1
                    continue
        output.append(lines[index])
        index += 1
    return "\n".join(output), removed


def block_online_subtitles(backup_root: Path, manifest: dict[str, Any]) -> None:
    path = hosts_path()
    text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    if HOSTS_MARKER_BEGIN in text and HOSTS_MARKER_END in text:
        print(f"online subtitle domain already blocked: {ONLINE_SUBTITLE_HOST}")
        return
    text, removed_legacy = strip_legacy_hosts_block(text)
    if hosts_has_active_block(text):
        print(f"online subtitle domain already blocked outside patch: {ONLINE_SUBTITLE_HOST}")
        return

    backup_root.mkdir(parents=True, exist_ok=True)
    hosts_backup = backup_root / "hosts.before-online-subtitle-block"
    if not hosts_backup.exists() and path.exists():
        shutil.copy2(path, hosts_backup)
    manifest["hostsBlock"] = {
        "host": ONLINE_SUBTITLE_HOST,
        "backup": hosts_backup.name,
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
    }

    block = (
        f"{HOSTS_MARKER_BEGIN}\r\n"
        f"127.0.0.1 {ONLINE_SUBTITLE_HOST}\r\n"
        f"{HOSTS_MARKER_END}\r\n"
    )
    separator = "" if not text or text.endswith(("\n", "\r")) else "\r\n"
    payload = text.replace("\n", "\r\n") + separator + block if removed_legacy else separator + block
    if removed_legacy:
        path.write_text(payload, encoding="ascii", newline="")
    else:
        with path.open("a", encoding="ascii", newline="") as file:
            file.write(payload)
    print(f"blocked online subtitles: {ONLINE_SUBTITLE_HOST}")


def unblock_online_subtitles() -> None:
    path = hosts_path()
    if not path.exists():
        return
    data = path.read_bytes()
    begin_marker = HOSTS_MARKER_BEGIN.encode("ascii")
    end_marker = HOSTS_MARKER_END.encode("ascii")
    begin = data.find(begin_marker)
    end = data.find(end_marker)
    if begin == -1 or end == -1 or end < begin:
        print(f"online subtitle domain block not found: {ONLINE_SUBTITLE_HOST}")
        return
    end += len(end_marker)
    while end < len(data) and data[end] in b"\r\n":
        end += 1
    while begin > 0 and data[begin - 1] in b"\r\n":
        begin -= 1
    patched = data[:begin] + data[end:]
    path.write_bytes(patched)
    print(f"unblocked online subtitles: {ONLINE_SUBTITLE_HOST}")


def flush_dns() -> None:
    if sys.platform != "win32":
        return
    try:
        import subprocess

        subprocess.run(["ipconfig", "/flushdns"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def patch_text_file(path: Path, game_root: Path, backup_root: Path, manifest: dict[str, Any], replacements: list[Replacement]) -> PatchStats:
    stats = PatchStats(processed_files=1)
    data = path.read_bytes()
    encoding = detect_text_encoding(data)
    try:
        text = data.decode(encoding)
    except UnicodeDecodeError:
        stats.skipped_files += 1
        return stats
    patched, replacement_count = apply_replacements_to_text(text, replacements, target="srt")
    if not replacement_count:
        return stats
    stats.replacements += replacement_count
    stats.changed_files += 1
    backup_file(path, game_root, backup_root, manifest)
    path.write_text(patched, encoding=encoding, newline="")
    print(f"{relative_to_game_root(path, game_root)}: {replacement_count}")
    return stats


def patch_textclient_record(record: bytes, replacements_by_field: dict[int, list[Replacement]]) -> tuple[bytes, int]:
    try:
        fields = parse_wire_fields(record)
    except ValueError:
        return record, 0
    record_key = None
    has_key = False
    for field in fields:
        if (
            field.field_number == 1
            and field.wire_type == 2
            and isinstance(field.value, bytes)
        ):
            text = decode_utf8(field.value)
            if text is not None:
                record_key = text
                has_key = True
                break
    if not has_key:
        return record, 0
    changed = 0
    updated: list[WireField] = []
    for field in fields:
        if (
            field.field_number in CHINESE_TEXT_FIELD_NUMBERS
            and field.wire_type == 2
            and isinstance(field.value, bytes)
        ):
            text = decode_utf8(field.value)
            if text is not None:
                replacements = replacements_by_field.get(field.field_number, [])
                if not replacements:
                    updated.append(field)
                    continue
                patched, count = apply_replacements_to_text(
                    text,
                    replacements,
                    target="textclient",
                    record_key=record_key,
                )
                if count:
                    updated.append(WireField(field.field_number, field.wire_type, patched.encode("utf-8")))
                    changed += count
                    continue
        updated.append(field)
    if not changed:
        return record, 0
    return serialize_wire_fields(updated), changed


def replacements_for_textclient_file(
    path: Path,
    simplified_replacements: list[Replacement],
    traditional_replacements: list[Replacement],
) -> dict[int, list[Replacement]]:
    name = path.name.lower()
    if name == "textclientexcel.pbin":
        return {
            2: simplified_replacements,
            4: simplified_replacements,
            6: traditional_replacements,
        }
    if name.startswith("textclientchapter") and name.endswith(".pbin"):
        return {
            2: simplified_replacements,
            4: simplified_replacements,
            6: traditional_replacements,
        }
    if "zh_tw" in name:
        return {field_number: traditional_replacements for field_number in CHINESE_TEXT_FIELD_NUMBERS}
    if "zh_gl" in name or "zh_cn" in name:
        return {field_number: simplified_replacements for field_number in CHINESE_TEXT_FIELD_NUMBERS}
    return {}


def srt_languages(language: str) -> list[str]:
    return [item.strip() for item in language.split(",") if item.strip()]


def replacements_for_srt_language(
    language: str,
    simplified_replacements: list[Replacement],
    traditional_replacements: list[Replacement],
) -> list[Replacement]:
    return traditional_replacements if language.lower() == "zh_tw" else simplified_replacements


def patch_textclient_file(
    path: Path,
    game_root: Path,
    backup_root: Path,
    manifest: dict[str, Any],
    simplified_replacements: list[Replacement],
    traditional_replacements: list[Replacement],
) -> PatchStats:
    stats = PatchStats(processed_files=1)
    replacements_by_field = replacements_for_textclient_file(path, simplified_replacements, traditional_replacements)
    if not replacements_by_field:
        return stats
    data = path.read_bytes()
    if data.startswith(b"AESType_"):
        stats.skipped_files += 1
        print(f"skip encrypted: {relative_to_game_root(path, game_root)}")
        return stats
    try:
        fields = parse_wire_fields(data)
    except ValueError:
        stats.skipped_files += 1
        print(f"skip unreadable pbin: {relative_to_game_root(path, game_root)}")
        return stats

    replacement_count = 0
    updated: list[WireField] = []
    for field in fields:
        if field.wire_type == 2 and isinstance(field.value, bytes):
            patched_record, count = patch_textclient_record(field.value, replacements_by_field)
            if count:
                updated.append(WireField(field.field_number, field.wire_type, patched_record))
                replacement_count += count
                continue
        updated.append(field)
    if not replacement_count:
        return stats
    stats.replacements = replacement_count
    stats.changed_files = 1
    backup_file(path, game_root, backup_root, manifest)
    path.write_bytes(serialize_wire_fields(updated))
    print(f"{relative_to_game_root(path, game_root)}: {replacement_count}")
    return stats


def validate_game_root(game_root: Path, require_existing: bool = True) -> None:
    if require_existing and not game_root.exists():
        raise SystemExit(f"game root does not exist: {game_root}")
    srt_root = game_root / SRT_RELATIVE_ROOT
    cfg_dir = game_root / TEXTCLIENT_RELATIVE_DIR
    if require_existing and not srt_root.exists() and not cfg_dir.exists():
        raise SystemExit(
            "cannot find SSTX2 text directories. Expected at least one of:\n"
            f"  {srt_root}\n"
            f"  {cfg_dir}"
        )


def apply_patch(game_root: Path, mode: str, language: str, include_srt: bool, include_textclient: bool, backup_dirname: str) -> PatchStats:
    validate_game_root(game_root)
    simplified_replacements = load_replacements(mode, PATCH_MANIFEST_PATH)
    traditional_replacements = load_replacements(mode, PATCH_MANIFEST_TW_PATH)
    if not simplified_replacements and not traditional_replacements:
        raise SystemExit(f"no replacements for mode: {mode}")
    backup_root = game_root / backup_dirname
    manifest = load_manifest(backup_root)
    manifest.setdefault("runs", []).append(
        {
            "mode": mode,
            "language": language,
            "startedAt": datetime.now().isoformat(timespec="seconds"),
        }
    )
    block_online_subtitles(backup_root, manifest)
    flush_dns()

    total = PatchStats()
    if include_srt:
        for srt_language in srt_languages(language):
            srt_replacements = replacements_for_srt_language(
                srt_language,
                simplified_replacements,
                traditional_replacements,
            )
            srt_dir = game_root / SRT_RELATIVE_ROOT / srt_language
            if srt_dir.exists():
                for path in sorted(srt_dir.rglob("*.srt")):
                    total.add(patch_text_file(path, game_root, backup_root, manifest, srt_replacements))
            else:
                print(f"skip missing srt dir: {srt_dir}")
    if include_textclient:
        cfg_dir = game_root / TEXTCLIENT_RELATIVE_DIR
        if cfg_dir.exists():
            for path in sorted(cfg_dir.glob("TextClient*.pbin")):
                total.add(
                    patch_textclient_file(
                        path,
                        game_root,
                        backup_root,
                        manifest,
                        simplified_replacements,
                        traditional_replacements,
                    )
                )
        else:
            print(f"skip missing cfg dir: {cfg_dir}")

    save_manifest(backup_root, manifest)
    return total


def restore(game_root: Path, backup_dirname: str) -> PatchStats:
    validate_game_root(game_root, require_existing=True)
    backup_root = game_root / backup_dirname
    manifest_path = backup_root / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"backup manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stats = PatchStats()
    unblock_online_subtitles()
    flush_dns()
    for rel in sorted(manifest.get("files", {})):
        backup_file_path = backup_root / rel
        target = game_root / rel
        if not backup_file_path.exists():
            print(f"missing backup file: {backup_file_path}")
            stats.skipped_files += 1
            continue
        stats.processed_files += 1
        stats.changed_files += 1
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_file_path, target)
        print(f"restore {rel}")
    return stats


def print_summary(stats: PatchStats) -> None:
    print(
        "summary: "
        f"processed={stats.processed_files}, "
        f"changed={stats.changed_files}, "
        f"replacements={stats.replacements}, "
        f"skipped={stats.skipped_files}"
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Patch SSTX2 zh_GL subtitles and TextClient text to historical names.",
    )
    parser.add_argument("action", choices=["all", "phonetic", "restore"])
    parser.add_argument("game_root", help="SSTX2 game root directory, the folder containing Data\\StreamingAssets")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, help="subtitle language folder, default: zh_GL")
    parser.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIRNAME, help="backup directory name under game root")
    parser.add_argument("--no-srt", action="store_true", help="do not patch SRT subtitle files")
    parser.add_argument("--no-textclient", action="store_true", help="do not patch TextClient*.pbin files")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    game_root = Path(args.game_root).expanduser().resolve()
    try:
        if args.action == "restore":
            stats = restore(game_root, args.backup_dir)
        else:
            mode = args.action
            stats = apply_patch(
                game_root=game_root,
                mode=mode,
                language=args.language,
                include_srt=not args.no_srt,
                include_textclient=not args.no_textclient,
                backup_dirname=args.backup_dir,
            )
        print_summary(stats)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
