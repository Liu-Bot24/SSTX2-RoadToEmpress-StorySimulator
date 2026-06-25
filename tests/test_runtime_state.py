import tempfile
import unittest
from pathlib import Path

from road_state_tracker.runtime_state import collect_runtime_snapshot, latest_endpoint_context, parse_current_video_context, parse_latest_endpoint, parse_player_log, parse_runtime_events


class RuntimeStateTests(unittest.TestCase):
    def test_parse_latest_active_choice_state(self) -> None:
        state = parse_player_log(
            "\n".join(
                [
                    "ShowChoice.OnExecute hash:e3bafe9a runtimeKey:CL050_X_250_025,staticKey:CL050_X_250_025, multiLanguage: True 测试选择甲 True 这是一个测试选择提示：请选择后续方向。",
                    "FSM: Enter EStoryExecState.Select from EStoryExecState.None",
                    "FSM: Exit EStoryExecState.Select then goto EStoryExecState.Null",
                    "ShowChoice.OnExecute hash:e1cec45b runtimeKey:CL051_X_020_027,staticKey:CL051_X_020_027, multiLanguage: True 测试选择乙 True 这是另一个测试选择提示。",
                    "PlayVideoInternal: videoKey=CL051_X_020_027, sequenceId=9, playState=NormalPlay",
                    "PrepareVideoInternal: folderName=chapter999, videoKey=B09_X_020_C051C_030, sequenceId=10",
                    "PrepareVideoInternal: folderName=chapter999, videoKey=B08_X_020_C051B_029, sequenceId=11",
                    "PrepareVideoInternal: folderName=chapter999, videoKey=X_020_C051A_028, sequenceId=12",
                    "FSM: Enter EStoryExecState.Select from EStoryExecState.None",
                    "[VideoTiming] PlayVideo invoke videoKey=CL051_X_020_027 loop=True startTime=-1 sequenceId=9 playState=NormalPlay wallTime=2026-06-11 17:12:35.708 realTime=622.701",
                ]
            )
        )

        self.assertIsNotNone(state)
        assert state is not None
        self.assertTrue(state.active)
        self.assertEqual(state.hash, "e1cec45b")
        self.assertEqual(state.runtime_key, "CL051_X_020_027")
        self.assertEqual(state.folder_name, "chapter999")
        self.assertEqual(state.title, "测试选择乙")
        self.assertEqual(state.prompt, "这是另一个测试选择提示。")
        self.assertEqual(state.current_video.video_key, "CL051_X_020_027")
        self.assertEqual([target.video_key for target in state.prepared_targets], ["B09_X_020_C051C_030", "B08_X_020_C051B_029", "X_020_C051A_028"])
        self.assertIsNone(state.selected_target)

    def test_parse_selected_target_without_polluting_prepared_targets(self) -> None:
        state = parse_player_log(
            "\n".join(
                [
                    "ShowChoice.OnExecute hash:e1cec45b runtimeKey:CL051_X_020_027,staticKey:CL051_X_020_027, multiLanguage: True 测试选择乙 True 这是另一个测试选择提示。",
                    "PlayVideoInternal: videoKey=CL051_X_020_027, sequenceId=9, playState=NormalPlay",
                    "PrepareVideoInternal: folderName=chapter999, videoKey=B09_X_020_C051C_030, sequenceId=10",
                    "PrepareVideoInternal: folderName=chapter999, videoKey=B08_X_020_C051B_029, sequenceId=11",
                    "PrepareVideoInternal: folderName=chapter999, videoKey=X_020_C051A_028, sequenceId=12",
                    "FSM: Enter EStoryExecState.Select from EStoryExecState.None",
                    "FSM: Exit EStoryExecState.Select then goto EStoryExecState.Null",
                    "PlayVideoInternal: videoKey=X_020_C051A_028, sequenceId=13, playState=NormalPlay",
                    "[VideoTiming] PlayVideo invoke videoKey=X_020_C051A_028 loop=False startTime=-1 sequenceId=13 playState=NormalPlay wallTime=2026-06-11 17:23:21.874 realTime=1268.867",
                    "PrepareVideoInternal: folderName=chapter999, videoKey=Q020_X_020_031, sequenceId=14",
                ]
            )
        )

        self.assertIsNotNone(state)
        assert state is not None
        self.assertFalse(state.active)
        self.assertEqual(state.selected_target.video_key, "X_020_C051A_028")
        self.assertEqual(state.selected_target.wall_time, "2026-06-11 17:23:21.874")
        self.assertEqual([target.video_key for target in state.prepared_targets], ["B09_X_020_C051C_030", "B08_X_020_C051B_029", "X_020_C051A_028"])
        self.assertNotIn("Q020_X_020_031", [target.video_key for target in state.prepared_targets])

    def test_no_choice_returns_none(self) -> None:
        self.assertIsNone(parse_player_log("PlayVideoInternal: videoKey=X_010_C050A_026, sequenceId=7, playState=NormalPlay"))

    def test_parse_current_video_context(self) -> None:
        current, prepared = parse_current_video_context(
            "\n".join(
                [
                    "PrepareVideoInternal: folderName=chapter999, videoKey=X_040_C053C_045, sequenceId=37",
                    "PlayVideoInternal: videoKey=X_040_C053C_045, sequenceId=37, playState=NormalPlay",
                    "[VideoTiming] PlayVideo invoke videoKey=X_040_C053C_045 loop=False startTime=-1 sequenceId=37 playState=NormalPlay wallTime=2026-06-11 17:25:23.212 realTime=1390.206",
                    "PrepareVideoInternal: folderName=chapter201, videoKey=S01_001, sequenceId=38",
                    "PlayVideoInternal: videoKey=S01_001, sequenceId=39, playState=NormalPlay",
                    "PrepareVideoInternal: folderName=chapter201, videoKey=CL010_S01_002, sequenceId=40",
                    "PrepareVideoInternal: folderName=chapter201, videoKey=S01_001, sequenceId=41",
                ]
            )
        )

        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current.video_key, "S01_001")
        self.assertEqual(current.folder_name, "chapter201")
        self.assertEqual([item.video_key for item in prepared], ["CL010_S01_002", "S01_001"])

    def test_parse_latest_endpoint(self) -> None:
        endpoint = parse_latest_endpoint(
            "\n".join(
                [
                    "EndPoint_ChapterReport.OnExecute 99901 前往【测试线路】 这是测试章节报告描述。 前往【测试线路】 chapter201/chapter201_1",
                    "EndPoint_BadEnd_NW.OnExecute 2101 测试坏结局 这是测试坏结局描述。 测试坏结局 CL010_S01_002",
                ]
            )
        )

        self.assertIsNotNone(endpoint)
        assert endpoint is not None
        self.assertEqual(endpoint.kind, "EndPoint_BadEnd_NW")
        self.assertEqual(endpoint.endpoint_id, "2101")
        self.assertEqual(endpoint.title, "测试坏结局")
        self.assertEqual(endpoint.description, "这是测试坏结局描述。")
        self.assertEqual(endpoint.source_ref, "CL010_S01_002")

    def test_parse_bad_end_with_ending_number_uses_story_anchor(self) -> None:
        endpoint = parse_latest_endpoint(
            "EndPoint_BadEnd.OnExecute 104 测试结局标题 这是测试结局说明。 测试结局标题 CL070_009_025 结局013 013"
        )

        self.assertIsNotNone(endpoint)
        assert endpoint is not None
        self.assertEqual(endpoint.kind, "EndPoint_BadEnd")
        self.assertEqual(endpoint.title, "测试结局标题")
        self.assertEqual(endpoint.description, "这是测试结局说明。")
        self.assertEqual(endpoint.source_ref, "CL070_009_025")

    def test_parse_chapter_report_endpoint(self) -> None:
        endpoint = parse_latest_endpoint(
            "EndPoint_ChapterReport.OnExecute 10101 测试章节 标题 这是测试章节说明。 测试章节 标题 chapter102/chapter102_1"
        )

        self.assertIsNotNone(endpoint)
        assert endpoint is not None
        self.assertEqual(endpoint.kind, "EndPoint_ChapterReport")
        self.assertEqual(endpoint.title, "测试章节 标题")
        self.assertEqual(endpoint.description, "这是测试章节说明。")
        self.assertEqual(endpoint.source_ref, "chapter102/chapter102_1")

    def test_parse_sub_chapter_report_endpoint(self) -> None:
        endpoint = parse_latest_endpoint(
            "EndPoint_SubChapterReport.OnExecute 10201 测试小节 标题 测试小节说明 测试小节 标题 chapter102/chapter102_2"
        )

        self.assertIsNotNone(endpoint)
        assert endpoint is not None
        self.assertEqual(endpoint.kind, "EndPoint_SubChapterReport")
        self.assertEqual(endpoint.endpoint_id, "10201")
        self.assertEqual(endpoint.title, "测试小节 标题")
        self.assertEqual(endpoint.description, "测试小节说明")
        self.assertEqual(endpoint.source_ref, "chapter102/chapter102_2")

    def test_parse_camp_endpoint_does_not_claim_story_anchor(self) -> None:
        endpoint = parse_latest_endpoint("EndPoint_Camp.OnExecute hash:2620e534 camp1 ")

        self.assertIsNotNone(endpoint)
        assert endpoint is not None
        self.assertEqual(endpoint.kind, "EndPoint_Camp")
        self.assertEqual(endpoint.title, "camp1")
        self.assertIsNone(endpoint.source_ref)
        self.assertEqual(endpoint.endpoint_role, "auxiliary_marker")

    def test_latest_endpoint_context_marks_current_endpoint(self) -> None:
        endpoint = latest_endpoint_context(
            "EndPoint_BadEnd.OnExecute 206 《测试结局》 测试结局描述。 《测试结局》 CL160_010_143 结局021 021"
        )

        self.assertIsNotNone(endpoint)
        assert endpoint is not None
        self.assertTrue(endpoint["is_current_position"])
        self.assertIsNone(endpoint["superseded_by"])
        self.assertEqual(endpoint["line_no"], 1)
        self.assertEqual(endpoint["source_ref"], "CL160_010_143")

    def test_latest_endpoint_context_marks_historical_after_reentry(self) -> None:
        endpoint = latest_endpoint_context(
            "\n".join(
                [
                    "EndPoint_BadEnd.OnExecute 206 《测试结局》 测试结局描述。 《测试结局》 CL160_010_143 结局021 021",
                    "PrepareVideoInternal: folderName=chapter102, videoKey=CL160_010_143, sequenceId=152",
                    "ShowChoice.OnExecute hash:0eaed481 runtimeKey:CL160_010_143,staticKey:CL160_010_143, multiLanguage: True 测试选择标题 True 这是测试选择提示文本。",
                ]
            )
        )

        self.assertIsNotNone(endpoint)
        assert endpoint is not None
        self.assertFalse(endpoint["is_current_position"])
        self.assertEqual(endpoint["superseded_by"]["event_type"], "choice_shown")
        self.assertEqual(endpoint["superseded_by"]["line_no"], 3)

    def test_latest_endpoint_context_keeps_chapter_report_when_camp_follows(self) -> None:
        endpoint = latest_endpoint_context(
            "\n".join(
                [
                    "EndPoint_ChapterReport.OnExecute 10203 第十九集 完 描述 第十九集 完 chapter103/chapter103_1",
                    "EndPoint_Camp.OnExecute hash:9bf7dcfa camp1",
                ]
            )
        )

        self.assertIsNotNone(endpoint)
        assert endpoint is not None
        self.assertEqual(endpoint["kind"], "EndPoint_ChapterReport")
        self.assertEqual(endpoint["endpoint_role"], "chapter_boundary")
        self.assertEqual(endpoint["source_ref"], "chapter103/chapter103_1")
        self.assertTrue(endpoint["is_current_position"])
        self.assertEqual(len(endpoint["auxiliary_endpoints_after"]), 1)
        self.assertEqual(endpoint["auxiliary_endpoints_after"][0]["kind"], "EndPoint_Camp")

    def test_latest_endpoint_context_does_not_treat_lone_camp_as_story_position(self) -> None:
        endpoint = latest_endpoint_context("EndPoint_Camp.OnExecute hash:9bf7dcfa camp1")

        self.assertIsNotNone(endpoint)
        assert endpoint is not None
        self.assertEqual(endpoint["kind"], "EndPoint_Camp")
        self.assertEqual(endpoint["endpoint_role"], "auxiliary_marker")
        self.assertFalse(endpoint["is_current_position"])

    def test_parse_runtime_events_marks_prepare_and_subtitles(self) -> None:
        events = parse_runtime_events(
            "\n".join(
                [
                    "PlayVideo_TraceBack.OnExecute hash:abec74ee runtimeKey:X_059,staticKey:X_059, multiLanguage: True 测试篇章 False",
                    "PlayVideoInternal: videoKey=X_059, sequenceId=4, playState=NormalPlay",
                    "PrepareVideoInternal: folderName=chapter999, videoKey=CL050_X_250_025, sequenceId=5",
                    "[Subtitle] 本地字幕加载成功: SSTX2/Global/srt/zh_GL/chapter999/X_059.srt",
                    "ShowChoice.OnExecute hash:e3bafe9a runtimeKey:CL050_X_250_025,staticKey:CL050_X_250_025, multiLanguage: True 测试选择甲 True 这是一个测试选择提示。",
                    "PrepareVideoInternal: folderName=chapter999, videoKey=X_250_C050B_047, sequenceId=7",
                    "PrepareVideoInternal: folderName=chapter999, videoKey=X_010_C050A_026, sequenceId=8",
                    "FSM: Enter EStoryExecState.Select from EStoryExecState.None",
                    "[Subtitle] 在线字幕下载成功: remote/srt/zh_GL/chapter999/X_250_C050B_047.srt",
                ]
            )
        )

        event_dicts = [event.as_dict() for event in events]
        self.assertEqual(event_dicts[0]["event_type"], "traceback_video_execute")
        self.assertTrue(event_dicts[0]["known_to_context"])
        self.assertEqual(event_dicts[2]["event_type"], "video_prepared")
        self.assertFalse(event_dicts[2]["known_to_context"])
        self.assertEqual(event_dicts[3]["event_type"], "subtitle_loaded")
        self.assertTrue(event_dicts[3]["known_to_context"])
        self.assertEqual(event_dicts[3]["matched_current_video_key"], "X_059")
        self.assertEqual(event_dicts[3]["matched_current_folder_name"], "chapter999")
        self.assertEqual(event_dicts[3]["admission_reason"], "subtitle_matches_current_video")
        candidate_events = [event for event in event_dicts if event["event_type"] == "choice_candidate_prepared"]
        self.assertEqual([event["video_key"] for event in candidate_events], ["X_250_C050B_047", "X_010_C050A_026"])
        self.assertFalse(candidate_events[0]["known_to_context"])
        online_subtitle = event_dicts[-1]
        self.assertEqual(online_subtitle["event_type"], "subtitle_loaded")
        self.assertFalse(online_subtitle["known_to_context"])
        self.assertEqual(online_subtitle["matched_current_video_key"], "X_059")
        self.assertEqual(online_subtitle["matched_current_folder_name"], "chapter999")
        self.assertEqual(online_subtitle["admission_reason"], "subtitle_does_not_match_current_video")

    def test_future_subtitle_does_not_pollute_unlock_current_folder(self) -> None:
        events = parse_runtime_events(
            "\n".join(
                [
                    "PrepareVideoInternal: folderName=chapter102, videoKey=010_142, sequenceId=1",
                    "PlayVideoInternal: videoKey=010_142, sequenceId=1, playState=NormalPlay",
                    "[Subtitle] 在线字幕下载成功: remote/srt/zh_GL/chapter103/011_001.srt",
                    "ToastHelper: OnReceiveUnlockCharacterDesRes charId=103, contentKey=2",
                ]
            )
        )

        event_dicts = [event.as_dict() for event in events]
        future_subtitle = event_dicts[2]
        unlock = event_dicts[3]
        self.assertFalse(future_subtitle["known_to_context"])
        self.assertEqual(future_subtitle["folder_name"], "chapter103")
        self.assertEqual(future_subtitle["matched_current_video_key"], "010_142")
        self.assertEqual(future_subtitle["matched_current_folder_name"], "chapter102")
        self.assertEqual(unlock["current_video_key"], "010_142")
        self.assertEqual(unlock["current_folder_name"], "chapter102")

    def test_parse_character_unlock_events(self) -> None:
        events = parse_runtime_events(
            "\n".join(
                [
                    "PrepareVideoInternal: folderName=chapter102, videoKey=010_017, sequenceId=103",
                    "PlayVideoInternal: videoKey=010_017, sequenceId=103, playState=NormalPlay",
                    "ToastHelper: SendToastUnlockReq for toast id=20059",
                    "OnUnlockCharacterRes, Ret:0, id:105",
                    "ToastHelper: OnUnlockCharacterRes id=105",
                    "ToastHelper: 回包确认解锁，显示toast id=20059",
                    "ToastHelper: OnReceiveUnlockCharacterDesRes charId=105, contentKey=1",
                ]
            )
        )

        event_dicts = [event.as_dict() for event in events]
        unlock_events = [event for event in event_dicts if event["event_type"].startswith(("unlock", "character"))]
        self.assertEqual(unlock_events[0]["event_type"], "unlock_toast_requested")
        self.assertEqual(unlock_events[0]["toast_id"], "20059")
        self.assertEqual(unlock_events[0]["current_video_key"], "010_017")
        self.assertEqual(unlock_events[0]["current_folder_name"], "chapter102")
        self.assertEqual(unlock_events[1]["event_type"], "character_unlocked")
        self.assertEqual(unlock_events[1]["character_id"], 105)
        self.assertEqual(unlock_events[1]["ret"], 0)
        self.assertEqual(unlock_events[1]["toast_id"], "20059")
        self.assertEqual(unlock_events[2]["event_type"], "unlock_toast_confirmed")
        self.assertEqual(unlock_events[3]["event_type"], "character_description_unlocked")
        self.assertEqual(unlock_events[3]["character_id"], 105)
        self.assertEqual(unlock_events[3]["content_key"], 1)
        self.assertEqual(unlock_events[3]["toast_id"], "20059")

    def test_parse_item_unlock_events(self) -> None:
        events = parse_runtime_events(
            "\n".join(
                [
                    "ToastHelper: SendToastUnlockReq for toast id=20008",
                    "OnUnlockItemContentRes, Ret:0, id:106 content: 1",
                    "ToastHelper: OnReceiveUnlockItemDesRes id=106, desc=1",
                ]
            )
        )

        event_dicts = [event.as_dict() for event in events]
        self.assertEqual(event_dicts[1]["event_type"], "item_content_unlocked")
        self.assertEqual(event_dicts[1]["item_id"], 106)
        self.assertEqual(event_dicts[1]["content_key"], 1)
        self.assertEqual(event_dicts[1]["toast_id"], "20008")
        self.assertEqual(event_dicts[2]["event_type"], "item_description_unlocked")
        self.assertEqual(event_dicts[2]["description_key"], 1)
        self.assertEqual(event_dicts[2]["toast_id"], "20008")

    def test_parse_state_machine_boundary_events(self) -> None:
        events = parse_runtime_events(
            "\n".join(
                [
                    "Using PrepareFailPanelAndVideoTransition from None to Fail",
                    "FSM: Enter EStoryExecState.Fail from EStoryExecState.None",
                    "FSM: Exit EGameState.StoryState then goto EGameState.StoryLineTemp",
                    "FSM: Enter EGameState.StoryLineTemp from EGameState.StoryState",
                    "FSM: Exit EGameState.StoryLineTemp then goto EGameState.StoryState",
                    "FSM: Enter EGameState.StoryState from EGameState.StoryLineTemp",
                    "FSM: Enter EStoryExecState.ChapterResult from EStoryExecState.None",
                    "EntryPoint_ChapterStart.OnExecute",
                ]
            )
        )

        event_types = [event.event_type for event in events]
        self.assertEqual(
            event_types,
            [
                "fail_panel_transition",
                "fail_state_enter",
                "story_state_exit_to_line",
                "story_line_temp_enter",
                "story_line_exit_to_state",
                "story_state_enter",
                "chapter_result_enter",
                "chapter_start_entry",
            ],
        )

    def test_collect_runtime_snapshot_uses_one_log_read_for_state_and_events(self) -> None:
        log_text = "\n".join(
            [
                "ShowChoice.OnExecute hash:81391ff2 runtimeKey:CL020_009_009,staticKey:CL020_009_009, multiLanguage: True 测试选择标题 True 这是测试选择提示。",
                "PlayVideoInternal: videoKey=CL020_009_009, sequenceId=10, playState=NormalPlay",
                "FSM: Enter EStoryExecState.Select from EStoryExecState.None",
                "PrepareVideoInternal: folderName=chapter101, videoKey=B01_009_C020A_010, sequenceId=11",
                "PrepareVideoInternal: folderName=chapter101, videoKey=009_C020B_011, sequenceId=12",
                "[VideoTiming] PlayVideo invoke videoKey=CL020_009_009 loop=True startTime=-1 sequenceId=10 playState=NormalPlay wallTime=2026-06-11 21:31:41.904 realTime=137.000",
                "PlayVideo_Ordinary.OnExecute hash:17cf0068 runtimeKey:009_C020B_011,staticKey:009_C020B_011, multiLanguage: True False",
                "FSM: Exit EStoryExecState.Select then goto EStoryExecState.Null",
                "PlayVideoInternal: videoKey=009_C020B_011, sequenceId=13, playState=NormalPlay",
                "PrepareVideoInternal: folderName=chapter101, videoKey=CL040_009_022, sequenceId=14",
                "[Subtitle] 本地字幕加载成功: SSTX2/Global/srt/zh_GL/chapter101/009_C020B_011.srt",
                "[VideoTiming] PlayVideo invoke videoKey=009_C020B_011 loop=False startTime=-1 sequenceId=13 playState=NormalPlay wallTime=2026-06-11 21:31:54.964 realTime=150.000",
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "Player.log"
            log_path.write_text(log_text, encoding="utf-8")
            snapshot = collect_runtime_snapshot(player_log=log_path, event_limit=12, include_handles=False)

        self.assertEqual(snapshot["state"]["runtime_key"], "CL020_009_009")
        self.assertEqual(snapshot["state"]["selected_target"]["video_key"], "009_C020B_011")
        self.assertEqual(snapshot["current_video"]["video_key"], "009_C020B_011")
        self.assertEqual([item["video_key"] for item in snapshot["prepared_after_current_video"]], ["CL040_009_022"])
        self.assertFalse(snapshot["snapshot"]["grew_during_read"])
        event_types = [event["event_type"] for event in snapshot["events"]]
        self.assertIn("choice_shown", event_types)
        self.assertIn("choice_candidate_prepared", event_types)
        self.assertEqual(snapshot["events"][-2]["event_type"], "subtitle_loaded")
        self.assertTrue(snapshot["events"][-2]["known_to_context"])


if __name__ == "__main__":
    unittest.main()
