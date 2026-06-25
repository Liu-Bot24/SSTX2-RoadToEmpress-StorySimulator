import unittest

from road_state_tracker.context_boundary import build_context_boundary, redact_story_text
from road_state_tracker.runtime_state import parse_runtime_events


class ContextBoundaryTests(unittest.TestCase):
    def test_candidate_targets_are_excluded_until_selected(self) -> None:
        packet = build_context_boundary(
            parse_runtime_events(
                "\n".join(
                    [
                        "ShowChoice.OnExecute hash:aaa runtimeKey:CL001,staticKey:CL001, multiLanguage: True 选择 True 怎么办?",
                        "FSM: Enter EStoryExecState.Select from EStoryExecState.None",
                        "PrepareVideoInternal: folderName=chapter001, videoKey=A, sequenceId=2",
                        "PrepareVideoInternal: folderName=chapter001, videoKey=B, sequenceId=3",
                        "PlayVideo_Ordinary.OnExecute hash:bbb runtimeKey:B,staticKey:B, multiLanguage: True False",
                        "FSM: Exit EStoryExecState.Select then goto EStoryExecState.Null",
                        "PlayVideoInternal: videoKey=B, sequenceId=4, playState=NormalPlay",
                    ]
                )
            )
        )

        excluded_keys = [event.get("video_key") for event in packet.excluded_events]
        self.assertEqual(excluded_keys, ["A", "B"])
        self.assertEqual(packet.selected_target["choice_key"], "CL001")
        self.assertEqual(packet.selected_target["target_video_key"], "B")
        self.assertIsNotNone(packet.context_session_id)
        self.assertIsNotNone(packet.current_choice["choice_window_id"])
        self.assertEqual(packet.candidate_targets[0]["choice_window_id"], packet.current_choice["choice_window_id"])
        self.assertEqual(packet.selected_target["choice_window_id"], packet.current_choice["choice_window_id"])
        self.assertEqual(packet.selected_target["context_session_id"], packet.context_session_id)

    def test_only_current_video_subtitle_enters_known_events(self) -> None:
        packet = build_context_boundary(
            parse_runtime_events(
                "\n".join(
                    [
                        "ShowChoice.OnExecute hash:aaa runtimeKey:CL001,staticKey:CL001, multiLanguage: True 选择 True 怎么办?",
                        "PlayVideoInternal: videoKey=CL001, sequenceId=1, playState=NormalPlay",
                        "[Subtitle] 本地字幕加载成功: SSTX2/Global/srt/zh_GL/chapter001/CL001.srt",
                        "[Subtitle] 在线字幕下载成功: remote/srt/zh_GL/chapter001/FUTURE.srt",
                    ]
                )
            )
        )

        known_subtitles = [event for event in packet.known_events if event["event_type"] == "subtitle_loaded"]
        excluded_subtitles = [event for event in packet.excluded_events if event["event_type"] == "subtitle_loaded"]
        self.assertEqual(known_subtitles[0]["video_key"], "CL001")
        self.assertEqual(excluded_subtitles[0]["video_key"], "FUTURE")

    def test_unlocks_are_auxiliary_not_known_context(self) -> None:
        packet = build_context_boundary(
            parse_runtime_events(
                "\n".join(
                    [
                        "ShowChoice.OnExecute hash:aaa runtimeKey:CL001,staticKey:CL001, multiLanguage: True 选择 True 怎么办?",
                        "ToastHelper: SendToastUnlockReq for toast id=20059",
                        "OnUnlockCharacterRes, Ret:0, id:105",
                    ]
                )
            )
        )

        self.assertEqual([event["classification"] for event in packet.auxiliary_events], ["dossier_unlock", "dossier_unlock"])
        self.assertNotIn("character_unlocked", [event["event_type"] for event in packet.known_events])

    def test_bad_end_reentry_resets_current_packet_and_keeps_risk_hint(self) -> None:
        packet = build_context_boundary(
            parse_runtime_events(
                "\n".join(
                    [
                        "ShowChoice.OnExecute hash:aaa runtimeKey:CL001,staticKey:CL001, multiLanguage: True 选择 True 怎么办?",
                        "PlayVideo_Ordinary.OnExecute hash:bbb runtimeKey:A,staticKey:A, multiLanguage: True False",
                        "FSM: Exit EStoryExecState.Select then goto EStoryExecState.Null",
                        "PlayVideoInternal: videoKey=A, sequenceId=4, playState=NormalPlay",
                        "EndPoint_BadEnd.OnExecute 1 坏结局 描述 坏结局 CL001 结局001 001",
                        "ShowChoice.OnExecute hash:ccc runtimeKey:CL001,staticKey:CL001, multiLanguage: True 选择 True 怎么办?",
                    ]
                )
            )
        )

        self.assertEqual(packet.current_scope_reason, "reentry_after_endpoint")
        self.assertEqual(packet.current_scope_start_line, 6)
        self.assertEqual(len(packet.risk_hints), 1)
        self.assertEqual(packet.risk_hints[0]["endpoint_title"], "坏结局")
        known_lines = [event["line_no"] for event in packet.known_events]
        self.assertEqual(known_lines, [6])

    def test_chapter_report_reentry_resets_without_risk_hint(self) -> None:
        packet = build_context_boundary(
            parse_runtime_events(
                "\n".join(
                    [
                        "ShowChoice.OnExecute hash:aaa runtimeKey:CL001,staticKey:CL001, multiLanguage: True 选择 True 怎么办?",
                        "PlayVideoInternal: videoKey=CL001, sequenceId=1, playState=NormalPlay",
                        "EndPoint_ChapterReport.OnExecute 10101 测试章节标题 描述 测试章节标题 chapter102/chapter102_1",
                        "EntryPoint_ChapterStart.OnExecute",
                        "PlayVideo_TraceBack.OnExecute hash:bbb runtimeKey:010_001,staticKey:010_001, multiLanguage: True False",
                    ]
                )
            )
        )

        self.assertEqual(packet.current_scope_reason, "reentry_after_chapter_boundary")
        self.assertEqual(packet.current_scope_start_line, 4)
        self.assertIsNotNone(packet.context_session_id)
        self.assertIn(":4:reentry_after_chapter_boundary:", packet.context_session_id)
        self.assertEqual(packet.risk_hints, [])
        self.assertEqual(packet.known_events[0]["event_type"], "traceback_video_execute")

    def test_chapter_report_ignores_standalone_video_until_chapter_entry(self) -> None:
        packet = build_context_boundary(
            parse_runtime_events(
                "\n".join(
                    [
                        "PlayVideoInternal: videoKey=OLD, sequenceId=1, playState=NormalPlay",
                        "EndPoint_ChapterReport.OnExecute 10101 测试章节标题 描述 测试章节标题 chapter102/chapter102_1",
                        "EndPoint_Camp.OnExecute hash:2620e534 camp1",
                        "FSM: Enter EGameState.StoryState from EGameState.StandAloneVideo",
                        "PlayVideoInternal: videoKey=J009_004, sequenceId=2, playState=NormalPlay",
                        "EntryPoint_ChapterStart.OnExecute",
                        "PlayVideo_TraceBack.OnExecute hash:bbb runtimeKey:010_001,staticKey:010_001, multiLanguage: True False",
                    ]
                )
            )
        )

        self.assertEqual(packet.current_scope_reason, "reentry_after_chapter_boundary")
        self.assertEqual(packet.current_scope_start_line, 6)
        known_video_keys = [event.get("video_key") or event.get("runtime_key") for event in packet.known_events]
        self.assertNotIn("J009_004", known_video_keys)

    def test_chapter_report_pending_reentry_keeps_reward_video_out_of_main_context(self) -> None:
        packet = build_context_boundary(
            parse_runtime_events(
                "\n".join(
                    [
                        "ShowChoice.OnExecute hash:aaa runtimeKey:CL001,staticKey:CL001, multiLanguage: True 选择 True 怎么办?",
                        "PlayVideoInternal: videoKey=CL001, sequenceId=1, playState=NormalPlay",
                        "EndPoint_ChapterReport.OnExecute 10101 测试章节标题 描述 测试章节标题 chapter102/chapter102_1",
                        "EndPoint_Camp.OnExecute hash:2620e534 camp1",
                        "PlayVideoInternal: videoKey=J009_004, sequenceId=2, playState=RewardPlay",
                        "FSM: Enter EGameState.StoryState from EGameState.StandAloneVideo",
                    ]
                )
            )
        )

        known_video_keys = [event.get("video_key") or event.get("runtime_key") for event in packet.known_events]
        auxiliary_video_keys = [event.get("video_key") or event.get("runtime_key") for event in packet.auxiliary_events]
        self.assertEqual(packet.current_scope_reason, "terminal_pending_reentry")
        self.assertIsNone(packet.current_choice)
        self.assertEqual(packet.candidate_targets, [])
        self.assertNotIn("J009_004", known_video_keys)
        self.assertIn("J009_004", auxiliary_video_keys)
        self.assertIn("post_endpoint_transition", [event["classification"] for event in packet.auxiliary_events])

    def test_bad_end_pending_reentry_clears_previous_choice(self) -> None:
        packet = build_context_boundary(
            parse_runtime_events(
                "\n".join(
                    [
                        "ShowChoice.OnExecute hash:aaa runtimeKey:CL001,staticKey:CL001, multiLanguage: True 选择 True 怎么办?",
                        "PlayVideo_Ordinary.OnExecute hash:bbb runtimeKey:A,staticKey:A, multiLanguage: True False",
                        "FSM: Exit EStoryExecState.Select then goto EStoryExecState.Null",
                        "PlayVideoInternal: videoKey=A, sequenceId=4, playState=NormalPlay",
                        "EndPoint_BadEnd.OnExecute 1 坏结局 描述 坏结局 CL001 结局001 001",
                        "PrepareFailPanelAndVideoTransition ready",
                    ]
                )
            )
        )

        self.assertEqual(packet.current_scope_reason, "terminal_pending_reentry")
        self.assertIsNone(packet.current_choice)
        self.assertIsNone(packet.selected_target)
        self.assertEqual(packet.candidate_targets, [])
        self.assertEqual(packet.known_events, [])
        self.assertEqual(len(packet.risk_hints), 1)

    def test_subchapter_report_can_reenter_on_chapter_result_state(self) -> None:
        packet = build_context_boundary(
            parse_runtime_events(
                "\n".join(
                    [
                        "PlayVideoInternal: videoKey=010_042, sequenceId=1, playState=NormalPlay",
                        "EndPoint_SubChapterReport.OnExecute 10201 测试小节标题 描述 测试小节标题 chapter102/chapter102_2",
                        "FSM: Enter EStoryExecState.ChapterResult from EStoryExecState.None",
                        "PlayVideo_TraceBack.OnExecute hash:bbb runtimeKey:010_147,staticKey:010_147, multiLanguage: True False",
                    ]
                )
            )
        )

        self.assertEqual(packet.current_scope_reason, "reentry_after_chapter_boundary")
        self.assertEqual(packet.current_scope_start_line, 3)
        self.assertEqual(packet.known_events[0]["event_type"], "traceback_video_execute")

    def test_new_choice_replaces_current_candidate_window(self) -> None:
        packet = build_context_boundary(
            parse_runtime_events(
                "\n".join(
                    [
                        "ShowChoice.OnExecute hash:aaa runtimeKey:CL001,staticKey:CL001, multiLanguage: True 选择一 True 怎么办?",
                        "PrepareVideoInternal: folderName=chapter001, videoKey=A, sequenceId=2",
                        "PrepareVideoInternal: folderName=chapter001, videoKey=B, sequenceId=3",
                        "PlayVideo_Ordinary.OnExecute hash:bbb runtimeKey:A,staticKey:A, multiLanguage: True False",
                        "FSM: Exit EStoryExecState.Select then goto EStoryExecState.Null",
                        "PlayVideoInternal: videoKey=A, sequenceId=4, playState=NormalPlay",
                        "ShowChoice.OnExecute hash:ccc runtimeKey:CL002,staticKey:CL002, multiLanguage: True 选择二 True 怎么办?",
                        "PrepareVideoInternal: folderName=chapter001, videoKey=C, sequenceId=5",
                    ]
                )
            )
        )

        self.assertEqual(packet.current_choice["runtime_key"], "CL002")
        self.assertEqual([candidate["video_key"] for candidate in packet.candidate_targets], ["C"])
        self.assertEqual(packet.selected_target, None)
        self.assertEqual(packet.candidate_targets[0]["choice_window_id"], packet.current_choice["choice_window_id"])

    def test_redact_story_text_keeps_mechanism_fields(self) -> None:
        payload = {
            "runtime_key": "CL001",
            "prompt": "剧情文本",
            "endpoint_title": "坏结局",
            "nested": {"title": "标题", "video_key": "V001"},
        }

        redacted = redact_story_text(payload)

        self.assertEqual(redacted["runtime_key"], "CL001")
        self.assertEqual(redacted["nested"]["video_key"], "V001")
        self.assertTrue(redacted["prompt"]["redacted"])
        self.assertEqual(redacted["prompt"]["char_count"], 4)
        self.assertTrue(redacted["endpoint_title"]["redacted"])
        self.assertTrue(redacted["nested"]["title"]["redacted"])


if __name__ == "__main__":
    unittest.main()
