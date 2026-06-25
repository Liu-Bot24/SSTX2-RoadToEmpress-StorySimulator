import unittest
from unittest.mock import patch

from road_state_tracker.monitoring import build_monitor_payload
from road_state_tracker.runtime_state import collect_runtime_snapshot_from_text, parse_runtime_events


class MonitoringTests(unittest.TestCase):
    def test_monitor_payload_redacts_story_text_and_keeps_mechanism_fields(self) -> None:
        text = "\n".join(
            [
                "ShowChoice.OnExecute hash:aaa runtimeKey:CL001,staticKey:CL001, multiLanguage: True 选择标题 True 选择提示",
                "PlayVideoInternal: videoKey=CL001, sequenceId=1, playState=NormalPlay",
                "FSM: Enter EStoryExecState.Select from EStoryExecState.None",
                "PrepareVideoInternal: folderName=chapter001, videoKey=A, sequenceId=2",
                "PrepareVideoInternal: folderName=chapter001, videoKey=B, sequenceId=3",
                "[Subtitle] 本地字幕加载成功: SSTX2/Global/srt/zh_GL/chapter001/CL001.srt",
                "[Subtitle] 在线字幕下载成功: remote/srt/zh_GL/chapter001/FUTURE.srt",
            ]
        )
        snapshot = collect_runtime_snapshot_from_text(
            text=text,
            raw=text.encode("utf-8"),
            before_stat=_FakeStat(len(text)),
            after_stat=_FakeStat(len(text)),
            log_path=_FakePath("Player.log"),
            event_limit=None,
        )

        payload = build_monitor_payload(snapshot, parse_runtime_events(text), tail_limit=10)

        self.assertTrue(payload["context_boundary"]["current_choice"]["title"]["redacted"])
        strengths = [event["evidence_strength"] for event in payload["recent_mechanism_events"]]
        self.assertIn("candidate_only", strengths)
        self.assertIn("loaded_subtitle_for_current_video", strengths)
        self.assertIn("loaded_subtitle_not_current_video", strengths)
        self.assertEqual(payload["context_boundary"]["counts"]["candidate_targets"], 2)
        self.assertIsNotNone(payload["context_boundary"]["context_session_id"])
        self.assertIsNotNone(payload["context_boundary"]["current_choice"]["choice_window_id"])
        self.assertEqual(len(payload["context_boundary"]["candidate_targets"]), 2)
        self.assertEqual(
            payload["context_boundary"]["candidate_targets"][0]["choice_window_id"],
            payload["context_boundary"]["current_choice"]["choice_window_id"],
        )
        self.assertEqual(payload["phase"]["name"], "choice_visible")

    def test_monitor_phase_distinguishes_selected_target_playback(self) -> None:
        text = "\n".join(
            [
                "ShowChoice.OnExecute hash:aaa runtimeKey:CL001,staticKey:CL001, multiLanguage: True 选择标题 True 选择提示",
                "PlayVideoInternal: videoKey=CL001, sequenceId=1, playState=NormalPlay",
                "FSM: Enter EStoryExecState.Select from EStoryExecState.None",
                "PrepareVideoInternal: folderName=chapter001, videoKey=A, sequenceId=2",
                "PrepareVideoInternal: folderName=chapter001, videoKey=B, sequenceId=3",
                "PlayVideo_Ordinary.OnExecute hash:bbb runtimeKey:A,staticKey:A, multiLanguage: True False",
                "FSM: Exit EStoryExecState.Select then goto EStoryExecState.Null",
                "PlayVideoInternal: videoKey=A, sequenceId=4, playState=NormalPlay",
            ]
        )
        snapshot = collect_runtime_snapshot_from_text(
            text=text,
            raw=text.encode("utf-8"),
            before_stat=_FakeStat(len(text)),
            after_stat=_FakeStat(len(text)),
            log_path=_FakePath("Player.log"),
            event_limit=None,
        )

        payload = build_monitor_payload(snapshot, parse_runtime_events(text), tail_limit=10)

        self.assertEqual(payload["phase"]["name"], "selected_target_playing")
        self.assertFalse(payload["latest_choice_state"]["active"])
        self.assertEqual(payload["phase"]["latest_choice_key"], "CL001")
        self.assertEqual(payload["phase"]["selected_target_key"], "A")

    def test_monitor_reports_unresolved_unlock_ids_without_guessing_names(self) -> None:
        text = "\n".join(
            [
                "PlayVideoInternal: videoKey=V001, sequenceId=1, playState=NormalPlay",
                "ToastHelper: SendToastUnlockReq for toast id=20056",
                "ToastHelper: OnReceiveUnlockCharacterDesRes charId=103, contentKey=2",
                "ToastHelper: 回包确认解锁，显示toast id=20056",
                "ToastHelper: OnReceiveUnlockCharacterDesRes charId=105, contentKey=1",
            ]
        )
        snapshot = collect_runtime_snapshot_from_text(
            text=text,
            raw=text.encode("utf-8"),
            before_stat=_FakeStat(len(text)),
            after_stat=_FakeStat(len(text)),
            log_path=_FakePath("Player.log"),
            event_limit=None,
        )

        with patch(
            "road_state_tracker.monitoring.load_mappings",
            return_value={"characters": {"105": {"name": "角色甲"}}, "items": {}, "candidates": {"characters": {}, "items": {}}},
        ):
            payload = build_monitor_payload(snapshot, parse_runtime_events(text), tail_limit=10)

        self.assertEqual(len(payload["unresolved_unlocks"]), 1)
        self.assertEqual(payload["unresolved_unlocks"][0]["entity_id"], "103")
        self.assertEqual(payload["unresolved_unlocks"][0]["content_key"], 2)
        self.assertIn("do not infer", payload["unresolved_unlocks"][0]["policy"])

    def test_monitor_ignores_failed_unlock_responses(self) -> None:
        text = "\n".join(
            [
                "PlayVideoInternal: videoKey=V001, sequenceId=1, playState=NormalPlay",
                "OnUnlockCharacterRes, Ret:-1, id:999",
                "OnUnlockItemContentRes, Ret:-1, id:200 content: 1",
            ]
        )
        snapshot = collect_runtime_snapshot_from_text(
            text=text,
            raw=text.encode("utf-8"),
            before_stat=_FakeStat(len(text)),
            after_stat=_FakeStat(len(text)),
            log_path=_FakePath("Player.log"),
            event_limit=None,
        )

        with patch(
            "road_state_tracker.monitoring.load_mappings",
            return_value={"characters": {}, "items": {}, "candidates": {"characters": {}, "items": {}}},
        ):
            payload = build_monitor_payload(snapshot, parse_runtime_events(text), tail_limit=10)

        self.assertEqual(payload["unresolved_unlocks"], [])
        self.assertEqual(payload["new_unresolved_unlocks"], [])

    def test_monitor_separates_full_context_from_recent_unlock_window(self) -> None:
        text = "\n".join(
            [
                "PlayVideoInternal: videoKey=OLD, sequenceId=1, playState=NormalPlay",
                "OnUnlockCharacterRes, Ret:0, id:101",
                "ShowChoice.OnExecute hash:aaa runtimeKey:CL001,staticKey:CL001, multiLanguage: True 选择标题 True 选择提示",
                "FSM: Enter EStoryExecState.Select from EStoryExecState.None",
                "ToastHelper: OnReceiveUnlockCharacterDesRes charId=103, contentKey=2",
            ]
        )
        snapshot = collect_runtime_snapshot_from_text(
            text=text,
            raw=text.encode("utf-8"),
            before_stat=_FakeStat(len(text)),
            after_stat=_FakeStat(len(text)),
            log_path=_FakePath("Player.log"),
            event_limit=None,
        )
        events = parse_runtime_events(text)
        recent_events = [event for event in events if event.line_no >= 5]

        with patch(
            "road_state_tracker.monitoring.load_mappings",
            return_value={"characters": {}, "items": {}, "candidates": {"characters": {}, "items": {}}},
        ):
            payload = build_monitor_payload(snapshot, events, tail_limit=10, recent_events=recent_events)

        self.assertEqual(payload["context_boundary"]["current_choice"]["runtime_key"], "CL001")
        self.assertEqual({unlock["entity_id"] for unlock in payload["unresolved_unlocks"]}, {"101", "103"})
        self.assertEqual(len(payload["new_unresolved_unlocks"]), 1)
        self.assertEqual(payload["new_unresolved_unlocks"][0]["entity_id"], "103")

    def test_monitor_phase_does_not_expose_old_choice_after_chapter_reentry(self) -> None:
        text = "\n".join(
            [
                "ShowChoice.OnExecute hash:aaa runtimeKey:CL001,staticKey:CL001, multiLanguage: True 选择标题 True 选择提示",
                "PlayVideo_Ordinary.OnExecute hash:bbb runtimeKey:A,staticKey:A, multiLanguage: True False",
                "FSM: Exit EStoryExecState.Select then goto EStoryExecState.Null",
                "PlayVideoInternal: videoKey=A, sequenceId=1, playState=NormalPlay",
                "EndPoint_ChapterReport.OnExecute 10101 测试章节标题 描述 测试章节标题 chapter102/chapter102_1",
                "PlayVideoInternal: videoKey=J009_004, sequenceId=2, playState=RewardPlay",
                "EntryPoint_ChapterStart.OnExecute",
                "PlayVideo_TraceBack.OnExecute hash:ccc runtimeKey:011_001,staticKey:011_001, multiLanguage: True False",
                "PlayVideoInternal: videoKey=011_001, sequenceId=3, playState=NormalPlay",
            ]
        )
        snapshot = collect_runtime_snapshot_from_text(
            text=text,
            raw=text.encode("utf-8"),
            before_stat=_FakeStat(len(text)),
            after_stat=_FakeStat(len(text)),
            log_path=_FakePath("Player.log"),
            event_limit=None,
        )

        payload = build_monitor_payload(snapshot, parse_runtime_events(text), tail_limit=10)

        self.assertEqual(payload["context_boundary"]["current_scope_reason"], "reentry_after_chapter_boundary")
        self.assertIsNone(payload["context_boundary"]["current_choice"])
        self.assertEqual(payload["phase"]["name"], "playing")
        self.assertIsNone(payload["phase"]["latest_choice_key"])
        self.assertIsNone(payload["phase"]["selected_target_key"])
        self.assertFalse(payload["phase"]["latest_choice_in_current_scope"])
        self.assertFalse(payload["latest_choice_state"]["in_current_scope"])

    def test_monitor_reports_terminal_pending_reentry_after_bad_end(self) -> None:
        text = "\n".join(
            [
                "ShowChoice.OnExecute hash:aaa runtimeKey:CL001,staticKey:CL001, multiLanguage: True 选择标题 True 选择提示",
                "PlayVideo_Ordinary.OnExecute hash:bbb runtimeKey:A,staticKey:A, multiLanguage: True False",
                "FSM: Exit EStoryExecState.Select then goto EStoryExecState.Null",
                "PlayVideoInternal: videoKey=A, sequenceId=1, playState=NormalPlay",
                "EndPoint_BadEnd.OnExecute 1 坏结局 描述 坏结局 CL001 结局001 001",
                "PrepareFailPanelAndVideoTransition ready",
            ]
        )
        snapshot = collect_runtime_snapshot_from_text(
            text=text,
            raw=text.encode("utf-8"),
            before_stat=_FakeStat(len(text)),
            after_stat=_FakeStat(len(text)),
            log_path=_FakePath("Player.log"),
            event_limit=None,
        )

        payload = build_monitor_payload(snapshot, parse_runtime_events(text), tail_limit=10)

        self.assertEqual(payload["context_boundary"]["current_scope_reason"], "terminal_pending_reentry")
        self.assertIsNone(payload["context_boundary"]["current_choice"])
        self.assertEqual(payload["phase"]["name"], "terminal_pending_reentry")
        self.assertIsNone(payload["phase"]["latest_choice_key"])
        self.assertFalse(payload["latest_choice_state"]["in_current_scope"])


class _FakeStat:
    st_mtime = 86400

    def __init__(self, size: int) -> None:
        self.st_size = size


class _FakePath:
    def __init__(self, value: str) -> None:
        self.value = value

    def __str__(self) -> str:
        return self.value


if __name__ == "__main__":
    unittest.main()
