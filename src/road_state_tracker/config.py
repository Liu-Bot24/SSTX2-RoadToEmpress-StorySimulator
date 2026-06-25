from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_GAME_ROOT = Path(os.environ.get("SSTX2_GAME_ROOT", "roadtoempress2"))
DEFAULT_INDEX_DIR = Path("data") / "index" / "roadtoempress2"
DEFAULT_LANGUAGE = "zh_GL"


@dataclass(frozen=True)
class TrackerConfig:
    game_root: Path = DEFAULT_GAME_ROOT
    index_dir: Path = DEFAULT_INDEX_DIR
    language: str = DEFAULT_LANGUAGE


def resolve_game_root(game_root: str | Path | None) -> Path:
    return Path(game_root).expanduser().resolve() if game_root else DEFAULT_GAME_ROOT


def resolve_index_dir(index_dir: str | Path | None) -> Path:
    return Path(index_dir).expanduser().resolve() if index_dir else DEFAULT_INDEX_DIR.resolve()

