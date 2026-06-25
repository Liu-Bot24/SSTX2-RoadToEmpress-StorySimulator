from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRAPH_JSON = PROJECT_ROOT / "data" / "game" / "storyline_graph" / "storyline_graph_data.json"
SRT_ROOT = PROJECT_ROOT / "data" / "game" / "storyline_graph" / "srt"
SUBTITLE_DOC_DIR = PROJECT_ROOT / "data" / "knowledge" / "video_subtitles" / "docs"

SUBTITLE_LINE_RE = re.compile(
    r"^(?P<index>\d+)\.\s+`(?P<time>[^`]+)`\s+(?:\*\*(?P<speaker>[^*]+)\*\*[：:])?(?P<body>.*)$"
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def video_srt_paths() -> dict[str, Path]:
    data = read_json(GRAPH_JSON)
    mapping: dict[str, Path] = {}
    for chapter in data.get("chapters", []):
        for node in chapter.get("nodes", []):
            if node.get("kind") == "ShowChoice":
                continue
            video_key = str(node.get("videoKey") or "").strip()
            relative = str((node.get("srt") or {}).get("relative") or "").strip()
            if not video_key or not relative:
                continue
            path = SRT_ROOT.joinpath(*relative.replace("\\", "/").split("/"))
            previous = mapping.get(video_key)
            if previous and previous != path:
                raise ValueError(f"video key {video_key} maps to multiple SRT paths: {previous} / {path}")
            mapping[video_key] = path
    return mapping


def srt_time_range(value: str) -> str:
    parts = [part.strip() for part in re.split(r"\s+-\s+", value.strip(), maxsplit=1)]
    if len(parts) != 2:
        raise ValueError(f"invalid subtitle time range: {value}")
    return f"{parts[0]} --> {parts[1]}"


def parse_subtitle_doc(path: Path) -> tuple[str, str]:
    video_key = path.name.removesuffix(".subtitles.md")
    blocks: list[str] = []
    for line_number, line in enumerate(read_text(path).splitlines(), start=1):
        match = SUBTITLE_LINE_RE.match(line.strip())
        if not match:
            continue
        speaker = (match.group("speaker") or "").strip()
        body = (match.group("body") or "").strip()
        if not body:
            raise ValueError(f"{path} line {line_number}: subtitle body is empty")
        text = f"{speaker}：{body}" if speaker else body
        blocks.append(
            "\n".join(
                [
                    match.group("index"),
                    srt_time_range(match.group("time")),
                    text,
                ]
            )
        )
    return video_key, "\n\n".join(blocks)


def sync_srt_from_subtitle_md() -> dict[str, int]:
    paths = video_srt_paths()
    written = 0
    missing_srt = 0
    no_subtitle = 0
    for doc_path in sorted(SUBTITLE_DOC_DIR.glob("*.subtitles.md")):
        video_key, srt_text = parse_subtitle_doc(doc_path)
        if not srt_text:
            no_subtitle += 1
            continue
        target = paths.get(video_key)
        if not target:
            missing_srt += 1
            continue
        write_text(target, srt_text)
        written += 1
    return {"written": written, "no_subtitle": no_subtitle, "missing_srt": missing_srt}


def main() -> int:
    result = sync_srt_from_subtitle_md()
    print(
        "synced subtitle MD -> page SRT "
        f"written={result['written']} no_subtitle={result['no_subtitle']} missing_srt={result['missing_srt']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
