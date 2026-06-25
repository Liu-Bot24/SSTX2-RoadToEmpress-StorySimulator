import unittest

from road_state_tracker.prompt_allowlist import build_prompt_allowlist
from road_state_tracker.runtime_state import parse_runtime_events


class PromptAllowlistTests(unittest.TestCase):
    def test_bad_end_reentry_keeps_failure_text_out_of_main_context(self) -> None:
        text = "\n".join(
            [
                "ShowChoice.OnExecute hash:aaa runtimeKey:CL001,staticKey:CL001, multiLanguage: True 旧选择 True 怎么办?",
                "PlayVideo_Ordinary.OnExecute hash:bbb runtimeKey:A,staticKey:A, multiLanguage: True False",
                "FSM: Exit EStoryExecState.Select then goto EStoryExecState.Null",
                "PlayVideoInternal: videoKey=A, sequenceId=1, playState=NormalPlay",
                "EndPoint_BadEnd.OnExecute 1 测试终点 禁止进入主上下文的测试文本 测试终点 CL001 结局001 001",
                "ShowChoice.OnExecute hash:ccc runtimeKey:CL001,staticKey:CL001, multiLanguage: True 新选择 True 怎么办?",
            ]
        )

        packet = build_prompt_allowlist(parse_runtime_events(text), redact=False)

        self.assertEqual(packet["current_scope_reason"], "reentry_after_endpoint")
        self.assertEqual(packet["main_context"]["current_choice"]["runtime_key"], "CL001")
        self.assertEqual(packet["main_context"]["current_choice"]["title"], "新选择")
        self.assertEqual(len(packet["risk_memory"]), 1)
        self.assertEqual(packet["risk_memory"][0]["endpoint_id"], "1")
        self.assertNotIn("evidence", packet["risk_memory"][0])
        self.assertNotIn("endpoint_title", packet["risk_memory"][0])
        self.assertNotIn("测试终点", str(packet["risk_memory"]))
        self.assertNotIn("禁止进入主上下文的测试文本", str(packet["main_context"]))

    def test_candidates_are_option_keys_only_and_dossiers_are_optional(self) -> None:
        text = "\n".join(
            [
                "ShowChoice.OnExecute hash:aaa runtimeKey:CL001,staticKey:CL001, multiLanguage: True 选择 True 怎么办?",
                "PrepareVideoInternal: folderName=chapter001, videoKey=A, sequenceId=2",
                "PrepareVideoInternal: folderName=chapter001, videoKey=B, sequenceId=3",
                "ToastHelper: SendToastUnlockReq for toast id=20138",
                "OnUnlockItemContentRes, Ret:0, id:159 content: 1",
            ]
        )

        packet = build_prompt_allowlist(parse_runtime_events(text), redact=False)

        candidates = packet["main_context"]["candidate_targets"]
        self.assertEqual([candidate["video_key"] for candidate in candidates], ["A", "B"])
        self.assertTrue(all(candidate["policy"].startswith("option key only") for candidate in candidates))
        self.assertEqual(packet["optional_dossiers"][0]["event_type"], "unlock_toast_requested")
        self.assertEqual(packet["optional_dossiers"][1]["entity_type"], "item")
        self.assertEqual(packet["optional_dossiers"][1]["entity_id"], "159")
        self.assertNotIn("item_content_unlocked", [event["event_type"] for event in packet["main_context"]["known_events"]])

    def test_failed_unlock_responses_do_not_enter_optional_dossiers(self) -> None:
        text = "\n".join(
            [
                "ShowChoice.OnExecute hash:aaa runtimeKey:CL001,staticKey:CL001, multiLanguage: True 选择 True 怎么办?",
                "OnUnlockCharacterRes, Ret:-1, id:999",
                "OnUnlockItemContentRes, Ret:-1, id:200 content: 1",
            ]
        )

        packet = build_prompt_allowlist(parse_runtime_events(text), redact=False)

        self.assertEqual(packet["optional_dossiers"], [])

    def test_redacted_by_default(self) -> None:
        text = "ShowChoice.OnExecute hash:aaa runtimeKey:CL001,staticKey:CL001, multiLanguage: True 选择标题 True 选择提示"

        packet = build_prompt_allowlist(parse_runtime_events(text))

        self.assertTrue(packet["main_context"]["current_choice"]["title"]["redacted"])
        self.assertTrue(packet["main_context"]["current_choice"]["prompt"]["redacted"])


if __name__ == "__main__":
    unittest.main()
