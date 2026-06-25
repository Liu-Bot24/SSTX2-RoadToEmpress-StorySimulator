from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_LOG_DIR = Path(os.environ.get("USERPROFILE", "")) / "AppData" / "LocalLow" / "n1studio" / "sstx2"
DEFAULT_PLAYER_LOG = DEFAULT_LOG_DIR / "Player.log"
UNLOCK_EVENT_TYPES = {
    "unlock_toast_requested",
    "unlock_toast_confirmed",
    "character_unlocked",
    "character_description_unlocked",
    "item_content_unlocked",
    "item_description_unlocked",
}
CURRENT_PROGRESS_EVENT_TYPES = {
    "choice_shown",
    "ordinary_video_execute",
    "traceback_video_execute",
    "video_play_started",
}

SHOW_CHOICE_RE = re.compile(
    r"ShowChoice\.OnExecute hash:(?P<hash>\S+) "
    r"runtimeKey:(?P<runtime_key>[^,]+),"
    r"staticKey:(?P<static_key>[^,]+), "
    r"multiLanguage: (?P<multi_language>True|False)\s+(?P<text>.*)$"
)
TITLE_PROMPT_RE = re.compile(r"(?P<title>.+?)\s+(?P<condition>True|False)\s+(?P<prompt>.+)$")
PLAY_VIDEO_RE = re.compile(
    r"PlayVideoInternal: videoKey=(?P<video_key>[^,]+), "
    r"sequenceId=(?P<sequence_id>\d+), playState=(?P<play_state>\S+)"
)
PREPARE_VIDEO_RE = re.compile(
    r"PrepareVideoInternal: folderName=(?P<folder_name>[^,]+), "
    r"videoKey=(?P<video_key>[^,]+), sequenceId=(?P<sequence_id>\d+)"
)
PLAY_TIMING_RE = re.compile(
    r"\[VideoTiming\] PlayVideo invoke videoKey=(?P<video_key>\S+) .*?"
    r"wallTime=(?P<wall_time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)"
)
ENDPOINT_RE = re.compile(r"(?P<kind>EndPoint_[A-Za-z0-9_]+)\.OnExecute\s+(?P<endpoint_id>\S+)\s+(?P<raw_text>.*)$")
PLAY_TRACEBACK_RE = re.compile(
    r"PlayVideo_TraceBack\.OnExecute hash:(?P<hash>\S+) "
    r"runtimeKey:(?P<runtime_key>[^,]+),"
    r"staticKey:(?P<static_key>[^,]+), "
    r"multiLanguage: (?P<multi_language>True|False)\s+(?P<raw_text>.*)$"
)
PLAY_ORDINARY_RE = re.compile(
    r"PlayVideo_Ordinary\.OnExecute hash:(?P<hash>\S+) "
    r"runtimeKey:(?P<runtime_key>[^,]+),"
    r"staticKey:(?P<static_key>[^,]+), "
    r"multiLanguage: (?P<multi_language>True|False)\s+(?P<raw_text>.*)$"
)
SUBTITLE_RE = re.compile(r"\[Subtitle\] (?P<source>本地字幕加载成功|在线字幕下载成功): (?P<location>.*?/(?P<folder_name>chapter[^/\\]+)/(?P<video_key>[^/\\]+)\.srt)")
TOAST_UNLOCK_REQUEST_RE = re.compile(r"ToastHelper: SendToastUnlockReq for toast id=(?P<toast_id>\d+)")
TOAST_UNLOCK_CONFIRM_RE = re.compile(r"ToastHelper: 回包确认解锁，显示toast id=(?P<toast_id>\d+)")
UNLOCK_CHARACTER_RE = re.compile(r"OnUnlockCharacterRes, Ret:(?P<ret>-?\d+), id:(?P<character_id>\d+)")
CHARACTER_DESCRIPTION_RE = re.compile(r"ToastHelper: OnReceiveUnlockCharacterDesRes charId=(?P<character_id>\d+), contentKey=(?P<content_key>\d+)")
UNLOCK_ITEM_CONTENT_RE = re.compile(r"OnUnlockItemContentRes, Ret:(?P<ret>-?\d+), id:(?P<item_id>\d+) content: (?P<content_key>\d+)")
ITEM_DESCRIPTION_RE = re.compile(r"ToastHelper: OnReceiveUnlockItemDesRes id=(?P<item_id>\d+), desc=(?P<description_key>\d+)")
FSM_ENTER_RE = re.compile(r"FSM: Enter (?P<state>E(?:GameState|StoryExecState)\.[A-Za-z]+) from (?P<from_state>E(?:GameState|StoryExecState)\.[A-Za-z]+)")
FSM_EXIT_RE = re.compile(r"FSM: Exit (?P<state>E(?:GameState|StoryExecState)\.[A-Za-z]+) then goto (?P<to_state>E(?:GameState|StoryExecState)\.[A-Za-z]+)")


@dataclass
class VideoRef:
    video_key: str
    sequence_id: int | None = None
    folder_name: str | None = None
    play_state: str | None = None
    wall_time: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "video_key": self.video_key,
            "sequence_id": self.sequence_id,
            "folder_name": self.folder_name,
            "play_state": self.play_state,
            "wall_time": self.wall_time,
        }


@dataclass
class ChoiceState:
    hash: str
    runtime_key: str
    static_key: str
    multi_language: bool
    raw_text: str
    title: str | None = None
    condition: str | None = None
    prompt: str | None = None
    folder_name: str | None = None
    active: bool = False
    current_video: VideoRef | None = None
    selected_target: VideoRef | None = None
    prepared_targets: list[VideoRef] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": "choice",
            "active": self.active,
            "hash": self.hash,
            "runtime_key": self.runtime_key,
            "static_key": self.static_key,
            "multi_language": self.multi_language,
            "raw_text": self.raw_text,
            "title": self.title,
            "condition": self.condition,
            "prompt": self.prompt,
            "folder_name": self.folder_name,
            "current_video": self.current_video.as_dict() if self.current_video else None,
            "selected_target": self.selected_target.as_dict() if self.selected_target else None,
            "prepared_targets": [target.as_dict() for target in self.prepared_targets],
        }


@dataclass
class EndpointState:
    kind: str
    endpoint_id: str
    raw_text: str
    title: str | None = None
    description: str | None = None
    source_ref: str | None = None
    endpoint_role: str = "story_boundary"

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "endpoint_id": self.endpoint_id,
            "raw_text": self.raw_text,
            "title": self.title,
            "description": self.description,
            "source_ref": self.source_ref,
            "endpoint_role": self.endpoint_role,
        }


@dataclass
class RuntimeEvent:
    line_no: int
    event_type: str
    known_to_context: bool
    data: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "line_no": self.line_no,
            "event_type": self.event_type,
            "known_to_context": self.known_to_context,
            **self.data,
        }


def parse_player_log(text: str) -> ChoiceState | None:
    latest: ChoiceState | None = None
    awaiting_selected_target = False
    choice_candidate_window = False

    for line in text.splitlines():
        show_match = SHOW_CHOICE_RE.search(line)
        if show_match:
            raw_text = show_match.group("text").strip()
            title = condition = prompt = None
            text_match = TITLE_PROMPT_RE.match(raw_text)
            if text_match:
                title = text_match.group("title").strip()
                condition = text_match.group("condition")
                prompt = text_match.group("prompt").strip()

            latest = ChoiceState(
                hash=show_match.group("hash"),
                runtime_key=show_match.group("runtime_key"),
                static_key=show_match.group("static_key"),
                multi_language=show_match.group("multi_language") == "True",
                raw_text=raw_text,
                title=title,
                condition=condition,
                prompt=prompt,
            )
            awaiting_selected_target = False
            choice_candidate_window = True
            continue

        if latest is None:
            continue

        if "FSM: Enter EStoryExecState.Select" in line:
            latest.active = True
            awaiting_selected_target = False
            choice_candidate_window = True
            continue

        if "FSM: Exit EStoryExecState.Select" in line:
            latest.active = False
            awaiting_selected_target = True
            choice_candidate_window = False
            continue

        play_match = PLAY_VIDEO_RE.search(line)
        if play_match:
            video_ref = VideoRef(
                video_key=play_match.group("video_key"),
                sequence_id=int(play_match.group("sequence_id")),
                play_state=play_match.group("play_state"),
            )
            if play_match.group("video_key") == latest.runtime_key:
                latest.current_video = video_ref
            elif awaiting_selected_target:
                latest.selected_target = video_ref
                awaiting_selected_target = False
            continue

        prepare_match = PREPARE_VIDEO_RE.search(line)
        if prepare_match and choice_candidate_window:
            if latest.folder_name is None:
                latest.folder_name = prepare_match.group("folder_name")
            latest.prepared_targets.append(
                VideoRef(
                    video_key=prepare_match.group("video_key"),
                    sequence_id=int(prepare_match.group("sequence_id")),
                    folder_name=prepare_match.group("folder_name"),
                )
            )
            continue

        timing_match = PLAY_TIMING_RE.search(line)
        if timing_match and latest.current_video and timing_match.group("video_key") == latest.current_video.video_key:
            latest.current_video.wall_time = timing_match.group("wall_time")
        if timing_match and latest.selected_target and timing_match.group("video_key") == latest.selected_target.video_key:
            latest.selected_target.wall_time = timing_match.group("wall_time")

    return latest


def parse_runtime_events(text: str, limit: int | None = None) -> list[RuntimeEvent]:
    events: list[RuntimeEvent] = []
    current_video_key: str | None = None
    current_folder_name: str | None = None
    folders_by_video_key: dict[str, str] = {}
    current_unlock_toast_id: str | None = None
    in_select = False
    choice_candidate_window = False

    def runtime_context() -> dict[str, Any]:
        return {
            "current_video_key": current_video_key,
            "current_folder_name": current_folder_name,
        }

    for line_no, line in enumerate(text.splitlines(), 1):
        toast_unlock_request_match = TOAST_UNLOCK_REQUEST_RE.search(line)
        if toast_unlock_request_match:
            current_unlock_toast_id = toast_unlock_request_match.group("toast_id")
            events.append(
                RuntimeEvent(
                    line_no=line_no,
                    event_type="unlock_toast_requested",
                    known_to_context=True,
                    data={"toast_id": current_unlock_toast_id, **runtime_context()},
                )
            )
            continue

        unlock_character_match = UNLOCK_CHARACTER_RE.search(line)
        if unlock_character_match:
            events.append(
                RuntimeEvent(
                    line_no=line_no,
                    event_type="character_unlocked",
                    known_to_context=True,
                    data={
                        "character_id": int(unlock_character_match.group("character_id")),
                        "ret": int(unlock_character_match.group("ret")),
                        "toast_id": current_unlock_toast_id,
                        **runtime_context(),
                    },
                )
            )
            continue

        character_description_match = CHARACTER_DESCRIPTION_RE.search(line)
        if character_description_match:
            events.append(
                RuntimeEvent(
                    line_no=line_no,
                    event_type="character_description_unlocked",
                    known_to_context=True,
                    data={
                        "character_id": int(character_description_match.group("character_id")),
                        "content_key": int(character_description_match.group("content_key")),
                        "toast_id": current_unlock_toast_id,
                        **runtime_context(),
                    },
                )
            )
            continue

        unlock_item_content_match = UNLOCK_ITEM_CONTENT_RE.search(line)
        if unlock_item_content_match:
            events.append(
                RuntimeEvent(
                    line_no=line_no,
                    event_type="item_content_unlocked",
                    known_to_context=True,
                    data={
                        "item_id": int(unlock_item_content_match.group("item_id")),
                        "content_key": int(unlock_item_content_match.group("content_key")),
                        "ret": int(unlock_item_content_match.group("ret")),
                        "toast_id": current_unlock_toast_id,
                        **runtime_context(),
                    },
                )
            )
            continue

        item_description_match = ITEM_DESCRIPTION_RE.search(line)
        if item_description_match:
            events.append(
                RuntimeEvent(
                    line_no=line_no,
                    event_type="item_description_unlocked",
                    known_to_context=True,
                    data={
                        "item_id": int(item_description_match.group("item_id")),
                        "description_key": int(item_description_match.group("description_key")),
                        "toast_id": current_unlock_toast_id,
                        **runtime_context(),
                    },
                )
            )
            continue

        toast_unlock_confirm_match = TOAST_UNLOCK_CONFIRM_RE.search(line)
        if toast_unlock_confirm_match:
            events.append(
                RuntimeEvent(
                    line_no=line_no,
                    event_type="unlock_toast_confirmed",
                    known_to_context=True,
                    data={"toast_id": toast_unlock_confirm_match.group("toast_id"), **runtime_context()},
                )
            )
            continue

        show_match = SHOW_CHOICE_RE.search(line)
        if show_match:
            raw_text = show_match.group("text").strip()
            title = condition = prompt = None
            text_match = TITLE_PROMPT_RE.match(raw_text)
            if text_match:
                title = text_match.group("title").strip()
                condition = text_match.group("condition")
                prompt = text_match.group("prompt").strip()
            events.append(
                RuntimeEvent(
                    line_no=line_no,
                    event_type="choice_shown",
                    known_to_context=True,
                    data={
                        "hash": show_match.group("hash"),
                        "runtime_key": show_match.group("runtime_key"),
                        "static_key": show_match.group("static_key"),
                        "raw_text": raw_text,
                        "title": title,
                        "condition": condition,
                        "prompt": prompt,
                    },
                )
            )
            choice_candidate_window = True
            continue

        if "FSM: Enter EStoryExecState.Select" in line:
            in_select = True
            choice_candidate_window = True
            events.append(RuntimeEvent(line_no, "select_enter", True, {}))
            continue

        if "FSM: Exit EStoryExecState.Select" in line:
            in_select = False
            choice_candidate_window = False
            events.append(RuntimeEvent(line_no, "select_exit", True, {}))
            continue

        if "PrepareFailPanelAndVideoTransition" in line:
            events.append(RuntimeEvent(line_no, "fail_panel_transition", True, runtime_context()))
            continue

        if "EntryPoint_ChapterStart.OnExecute" in line:
            events.append(RuntimeEvent(line_no, "chapter_start_entry", True, runtime_context()))
            continue

        fsm_enter_match = FSM_ENTER_RE.search(line)
        if fsm_enter_match:
            state = fsm_enter_match.group("state")
            event_type = _fsm_enter_event_type(state)
            if event_type:
                events.append(
                    RuntimeEvent(
                        line_no,
                        event_type,
                        True,
                        {
                            "state": state,
                            "from_state": fsm_enter_match.group("from_state"),
                            **runtime_context(),
                        },
                    )
                )
                continue

        fsm_exit_match = FSM_EXIT_RE.search(line)
        if fsm_exit_match:
            state = fsm_exit_match.group("state")
            event_type = _fsm_exit_event_type(state, fsm_exit_match.group("to_state"))
            if event_type:
                events.append(
                    RuntimeEvent(
                        line_no,
                        event_type,
                        True,
                        {
                            "state": state,
                            "to_state": fsm_exit_match.group("to_state"),
                            **runtime_context(),
                        },
                    )
                )
                continue

        prepare_match = PREPARE_VIDEO_RE.search(line)
        if prepare_match:
            folders_by_video_key[prepare_match.group("video_key")] = prepare_match.group("folder_name")
            event_type = "choice_candidate_prepared" if choice_candidate_window or in_select else "video_prepared"
            events.append(
                RuntimeEvent(
                    line_no=line_no,
                    event_type=event_type,
                    known_to_context=False,
                    data={
                        "folder_name": prepare_match.group("folder_name"),
                        "video_key": prepare_match.group("video_key"),
                        "sequence_id": int(prepare_match.group("sequence_id")),
                    },
                )
            )
            continue

        play_match = PLAY_VIDEO_RE.search(line)
        if play_match:
            current_video_key = play_match.group("video_key")
            current_folder_name = folders_by_video_key.get(current_video_key, current_folder_name)
            events.append(
                RuntimeEvent(
                    line_no=line_no,
                    event_type="video_play_started",
                    known_to_context=True,
                    data={
                        "video_key": current_video_key,
                        "sequence_id": int(play_match.group("sequence_id")),
                        "play_state": play_match.group("play_state"),
                    },
                )
            )
            continue

        timing_match = PLAY_TIMING_RE.search(line)
        if timing_match:
            events.append(
                RuntimeEvent(
                    line_no=line_no,
                    event_type="video_play_timing",
                    known_to_context=timing_match.group("video_key") == current_video_key,
                    data={"video_key": timing_match.group("video_key"), "wall_time": timing_match.group("wall_time")},
                )
            )
            continue

        traceback_match = PLAY_TRACEBACK_RE.search(line)
        if traceback_match:
            raw_text = traceback_match.group("raw_text").strip()
            events.append(
                RuntimeEvent(
                    line_no=line_no,
                    event_type="traceback_video_execute",
                    known_to_context=True,
                    data={
                        "hash": traceback_match.group("hash"),
                        "runtime_key": traceback_match.group("runtime_key"),
                        "static_key": traceback_match.group("static_key"),
                        "raw_text": raw_text,
                    },
                )
            )
            continue

        ordinary_match = PLAY_ORDINARY_RE.search(line)
        if ordinary_match:
            events.append(
                RuntimeEvent(
                    line_no=line_no,
                    event_type="ordinary_video_execute",
                    known_to_context=True,
                    data={
                        "hash": ordinary_match.group("hash"),
                        "runtime_key": ordinary_match.group("runtime_key"),
                        "static_key": ordinary_match.group("static_key"),
                        "raw_text": ordinary_match.group("raw_text").strip(),
                    },
                )
            )
            continue

        subtitle_match = SUBTITLE_RE.search(line)
        if subtitle_match:
            subtitle_folder_name = subtitle_match.group("folder_name")
            video_key = subtitle_match.group("video_key")
            matches_current_video = video_key == current_video_key
            matched_current_folder_name = current_folder_name
            if matches_current_video and matched_current_folder_name is None:
                matched_current_folder_name = subtitle_folder_name
                current_folder_name = subtitle_folder_name
            source_label = "local" if subtitle_match.group("source") == "本地字幕加载成功" else "online"
            events.append(
                RuntimeEvent(
                    line_no=line_no,
                    event_type="subtitle_loaded",
                    known_to_context=matches_current_video,
                    data={
                        "source": source_label,
                        "folder_name": subtitle_folder_name,
                        "video_key": video_key,
                        "matched_current_video_key": current_video_key,
                        "matched_current_folder_name": matched_current_folder_name,
                        "admission_reason": "subtitle_matches_current_video"
                        if matches_current_video
                        else "subtitle_does_not_match_current_video",
                        "location": subtitle_match.group("location"),
                    },
                )
            )
            continue

        endpoint_match = ENDPOINT_RE.search(line)
        if endpoint_match:
            endpoint = _parse_endpoint_match(endpoint_match)
            events.append(
                RuntimeEvent(
                    line_no=line_no,
                    event_type="endpoint",
                    known_to_context=True,
                    data=endpoint.as_dict(),
                )
            )

    return events[-limit:] if limit is not None and limit >= 0 else events


def parse_current_video_context(text: str) -> tuple[VideoRef | None, list[VideoRef]]:
    current_video: VideoRef | None = None
    prepared_after_current: list[VideoRef] = []
    folders_by_video_key: dict[str, str] = {}

    for line in text.splitlines():
        prepare_match = PREPARE_VIDEO_RE.search(line)
        if prepare_match:
            video_ref = VideoRef(
                video_key=prepare_match.group("video_key"),
                sequence_id=int(prepare_match.group("sequence_id")),
                folder_name=prepare_match.group("folder_name"),
            )
            folders_by_video_key[video_ref.video_key] = video_ref.folder_name or ""
            if current_video is not None:
                prepared_after_current.append(video_ref)
            continue

        play_match = PLAY_VIDEO_RE.search(line)
        if play_match:
            video_key = play_match.group("video_key")
            current_video = VideoRef(
                video_key=video_key,
                sequence_id=int(play_match.group("sequence_id")),
                folder_name=folders_by_video_key.get(video_key) or None,
                play_state=play_match.group("play_state"),
            )
            prepared_after_current = []
            continue

        timing_match = PLAY_TIMING_RE.search(line)
        if timing_match and current_video and timing_match.group("video_key") == current_video.video_key:
            current_video.wall_time = timing_match.group("wall_time")

    return current_video, prepared_after_current


def parse_latest_endpoint(text: str) -> EndpointState | None:
    latest: EndpointState | None = None
    for line in text.splitlines():
        match = ENDPOINT_RE.search(line)
        if not match:
            continue
        latest = _parse_endpoint_match(match)
    return latest


def _parse_endpoint_match(match: re.Match[str]) -> EndpointState:
    raw_text = match.group("raw_text").strip()
    parts = raw_text.split()
    title = description = source_ref = None
    kind = match.group("kind")
    endpoint_role = _endpoint_role(kind)
    if kind in {"EndPoint_ChapterReport", "EndPoint_SubChapterReport"} and len(parts) >= 3:
        source_ref = parts[-1]
        body = parts[:-1]
        title = " ".join(body[:2])
        duplicate_index = None
        for index in range(2, len(body) - 1):
            if " ".join(body[index : index + 2]) == title:
                duplicate_index = index
                break
        if duplicate_index is not None:
            description = " ".join(body[2:duplicate_index]) or None
        else:
            description = " ".join(body[2:]) or None
    elif kind == "EndPoint_Camp":
        title = raw_text or None
    elif len(parts) >= 3 and parts[0] in parts[1:]:
        duplicate_index = parts.index(parts[0], 1)
        title = parts[0]
        description = " ".join(parts[1:duplicate_index]) or None
        source_ref = parts[duplicate_index + 1] if len(parts) > duplicate_index + 1 else None
    elif parts:
        title = parts[0]
        source_ref = parts[-1] if len(parts) > 1 else None

    return EndpointState(
        kind=kind,
        endpoint_id=match.group("endpoint_id"),
        raw_text=raw_text,
        title=title,
        description=description,
        source_ref=source_ref,
        endpoint_role=endpoint_role,
    )


def _endpoint_role(kind: str) -> str:
    if kind == "EndPoint_Camp":
        return "auxiliary_marker"
    if kind in {"EndPoint_ChapterReport", "EndPoint_SubChapterReport"}:
        return "chapter_boundary"
    if "BadEnd" in kind:
        return "bad_end_boundary"
    return "story_boundary"


def read_latest_choice_state(player_log: str | Path | None = None) -> tuple[ChoiceState | None, Path]:
    log_path = Path(player_log).expanduser().resolve() if player_log else DEFAULT_PLAYER_LOG
    text = log_path.read_text(encoding="utf-8", errors="replace")
    return parse_player_log(text), log_path


def get_process_open_files(game_root: str | Path | None = None, process_name: str = "sstx2.exe") -> dict[str, Any]:
    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        return {"available": False, "error": "psutil is not installed", "files": []}

    root = Path(game_root).resolve() if game_root else None
    files: list[str] = []
    pids: list[int] = []
    errors: list[str] = []

    for process in psutil.process_iter(["pid", "name"]):
        if (process.info.get("name") or "").lower() != process_name.lower():
            continue
        pids.append(int(process.info["pid"]))
        try:
            for open_file in process.open_files():
                path = Path(open_file.path)
                if root is None or _is_relative_to(path, root):
                    files.append(str(path))
        except Exception as exc:  # pragma: no cover - depends on OS permissions and process state
            errors.append(f"{process.info['pid']}: {type(exc).__name__}: {exc}")

    return {
        "available": True,
        "process_name": process_name,
        "pids": pids,
        "files": sorted(set(files), key=str.lower),
        "errors": errors,
    }


def collect_process_state(game_root: str | Path | None = None, process_name: str = "sstx2.exe") -> dict[str, Any]:
    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        return {"available": False, "error": "psutil is not installed", "processes": []}

    root = Path(game_root).resolve() if game_root else None
    window_titles = _window_titles_by_pid()
    processes: list[dict[str, Any]] = []

    for process in psutil.process_iter(["pid", "name"]):
        if (process.info.get("name") or "").lower() != process_name.lower():
            continue

        pid = int(process.info["pid"])
        errors: list[str] = []
        exe = cwd = None
        create_time = None

        try:
            exe = process.exe()
        except Exception as exc:  # pragma: no cover - depends on OS permissions and process state
            errors.append(f"exe: {type(exc).__name__}: {exc}")

        try:
            cwd = process.cwd()
        except Exception as exc:  # pragma: no cover - depends on OS permissions and process state
            errors.append(f"cwd: {type(exc).__name__}: {exc}")

        try:
            create_time = datetime.fromtimestamp(process.create_time()).astimezone().isoformat()
        except Exception as exc:  # pragma: no cover - depends on OS permissions and process state
            errors.append(f"create_time: {type(exc).__name__}: {exc}")

        exe_path = Path(exe).resolve() if exe else None
        cwd_path = Path(cwd).resolve() if cwd else None
        processes.append(
            {
                "pid": pid,
                "name": process.info.get("name"),
                "exe": str(exe_path) if exe_path else None,
                "cwd": str(cwd_path) if cwd_path else None,
                "create_time": create_time,
                "window_titles": window_titles.get(pid, []),
                "matches_game_root": bool(root and exe_path and _is_relative_to(exe_path, root)),
                "matches_window_title": any("Road to Empress" in title for title in window_titles.get(pid, [])),
                "errors": errors,
            }
        )

    return {
        "available": True,
        "process_name": process_name,
        "game_root": str(root) if root else None,
        "log_dir": str(DEFAULT_LOG_DIR),
        "log_dir_exists": DEFAULT_LOG_DIR.exists(),
        "processes": processes,
        "matched": any(
            process["matches_game_root"] or process["matches_window_title"]
            for process in processes
        ),
    }


def collect_runtime_state(
    game_root: str | Path | None = None,
    player_log: str | Path | None = None,
    include_handles: bool = True,
) -> dict[str, Any]:
    log_path = Path(player_log).expanduser().resolve() if player_log else DEFAULT_PLAYER_LOG
    text = log_path.read_text(encoding="utf-8", errors="replace")
    payload = _collect_runtime_payload_from_text(text, log_path)
    if include_handles:
        payload["process"] = collect_process_state(game_root)
        payload["open_files"] = get_process_open_files(game_root)
    return payload


def collect_runtime_snapshot(
    game_root: str | Path | None = None,
    player_log: str | Path | None = None,
    event_limit: int | None = 80,
    include_handles: bool = True,
) -> dict[str, Any]:
    log_path = Path(player_log).expanduser().resolve() if player_log else DEFAULT_PLAYER_LOG
    before_stat = log_path.stat()
    raw = log_path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    after_stat = log_path.stat()
    payload = collect_runtime_snapshot_from_text(text, raw, before_stat, after_stat, log_path, event_limit)
    if include_handles:
        payload["process"] = collect_process_state(game_root)
        payload["open_files"] = get_process_open_files(game_root)
    return payload


def collect_runtime_snapshot_from_text(
    text: str,
    raw: bytes,
    before_stat: os.stat_result,
    after_stat: os.stat_result,
    log_path: Path,
    event_limit: int | None,
) -> dict[str, Any]:
    payload = _collect_runtime_payload_from_text(text, log_path)
    payload["events"] = [event.as_dict() for event in parse_runtime_events(text, event_limit)]
    payload["snapshot"] = {
        "line_count": len(text.splitlines()),
        "bytes_read": len(raw),
        "size_before": before_stat.st_size,
        "size_after": after_stat.st_size,
        "mtime_before": datetime.fromtimestamp(before_stat.st_mtime).astimezone().isoformat(),
        "mtime_after": datetime.fromtimestamp(after_stat.st_mtime).astimezone().isoformat(),
        "grew_during_read": after_stat.st_size != before_stat.st_size or after_stat.st_mtime != before_stat.st_mtime,
    }
    return payload


def _collect_runtime_payload_from_text(text: str, log_path: Path) -> dict[str, Any]:
    state = parse_player_log(text)
    current_video, prepared_after_current = parse_current_video_context(text)
    return {
        "source": "player_log",
        "player_log": str(log_path),
        "state": state.as_dict() if state else {"type": "unknown", "active": False},
        "current_video": current_video.as_dict() if current_video else None,
        "prepared_after_current_video": [video.as_dict() for video in prepared_after_current],
        "latest_endpoint": latest_endpoint_context(text),
    }


def latest_endpoint_context(text: str) -> dict[str, Any] | None:
    events = parse_runtime_events(text, None)
    endpoint_events = [event for event in events if event.event_type == "endpoint"]
    latest_endpoint_event = next(
        (
            event
            for event in reversed(endpoint_events)
            if event.data.get("endpoint_role") != "auxiliary_marker"
        ),
        None,
    )
    if latest_endpoint_event is None:
        latest_endpoint_event = endpoint_events[-1] if endpoint_events else None
    if latest_endpoint_event is None:
        return None

    endpoint_payload = {
        **latest_endpoint_event.data,
        "line_no": latest_endpoint_event.line_no,
        "is_current_position": latest_endpoint_event.data.get("endpoint_role") != "auxiliary_marker",
        "superseded_by": None,
        "auxiliary_endpoints_after": [
            {**event.data, "line_no": event.line_no}
            for event in endpoint_events
            if event.line_no > latest_endpoint_event.line_no
            and event.data.get("endpoint_role") == "auxiliary_marker"
        ],
    }
    for event in events:
        if event.line_no <= latest_endpoint_event.line_no:
            continue
        if event.event_type == "endpoint" and event.data.get("endpoint_role") == "auxiliary_marker":
            continue
        if event.event_type not in CURRENT_PROGRESS_EVENT_TYPES:
            continue
        endpoint_payload["is_current_position"] = False
        endpoint_payload["superseded_by"] = {
            "line_no": event.line_no,
            "event_type": event.event_type,
            "runtime_key": event.data.get("runtime_key"),
            "video_key": event.data.get("video_key"),
            "title": event.data.get("title"),
        }
        break
    return endpoint_payload


def collect_runtime_events(player_log: str | Path | None = None, limit: int | None = 80) -> dict[str, Any]:
    log_path = Path(player_log).expanduser().resolve() if player_log else DEFAULT_PLAYER_LOG
    text = log_path.read_text(encoding="utf-8", errors="replace")
    return {
        "source": "player_log",
        "player_log": str(log_path),
        "events": [event.as_dict() for event in parse_runtime_events(text, limit)],
    }


def collect_unlock_events(player_log: str | Path | None = None, limit: int | None = 80, since_line: int = 0) -> dict[str, Any]:
    log_path = Path(player_log).expanduser().resolve() if player_log else DEFAULT_PLAYER_LOG
    text = log_path.read_text(encoding="utf-8", errors="replace")
    all_events = [
        event.as_dict()
        for event in parse_runtime_events(text, None)
        if event.event_type in UNLOCK_EVENT_TYPES and event.line_no >= since_line
    ]
    selected_events = all_events[-limit:] if limit is not None and limit >= 0 else all_events
    return {
        "source": "player_log",
        "player_log": str(log_path),
        "since_line": since_line,
        "total_unlock_events": len(all_events),
        "events": selected_events,
    }


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
        return True
    except ValueError:
        return False


def _fsm_enter_event_type(state: str) -> str | None:
    return {
        "EGameState.StoryLine": "story_line_enter",
        "EGameState.StoryLineTemp": "story_line_temp_enter",
        "EGameState.StoryState": "story_state_enter",
        "EStoryExecState.Fail": "fail_state_enter",
        "EStoryExecState.ChapterResult": "chapter_result_enter",
    }.get(state)


def _fsm_exit_event_type(state: str, to_state: str) -> str | None:
    if state == "EGameState.StoryState" and to_state in {"EGameState.StoryLine", "EGameState.StoryLineTemp"}:
        return "story_state_exit_to_line"
    if state in {"EGameState.StoryLine", "EGameState.StoryLineTemp"} and to_state == "EGameState.StoryState":
        return "story_line_exit_to_state"
    return None


def _window_titles_by_pid() -> dict[int, list[str]]:
    if os.name != "nt":
        return {}

    try:
        import ctypes
        from ctypes import wintypes
    except Exception:  # pragma: no cover - ctypes is part of CPython on Windows
        return {}

    user32 = ctypes.windll.user32
    titles: dict[int, list[str]] = {}

    enum_windows_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    @enum_windows_proc
    def enum_proc(hwnd: Any, _lparam: Any) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()
        if title:
            titles.setdefault(int(pid.value), []).append(title)
        return True

    user32.EnumWindows(enum_proc, 0)
    return titles
