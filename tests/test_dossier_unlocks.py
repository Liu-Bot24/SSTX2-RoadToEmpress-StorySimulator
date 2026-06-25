import unittest

from road_state_tracker.dossier_unlocks import build_dossier_unlocks
from road_state_tracker.runtime_state import RuntimeEvent


class DossierUnlockTests(unittest.TestCase):
    def test_unknown_item_content_and_description_are_aggregated(self) -> None:
        events = [
            RuntimeEvent(
                line_no=10,
                event_type="item_content_unlocked",
                known_to_context=True,
                data={
                    "item_id": 159,
                    "content_key": 1,
                    "ret": 0,
                    "toast_id": "20140",
                    "current_video_key": "011_001",
                    "current_folder_name": "chapter103",
                },
            ),
            RuntimeEvent(
                line_no=11,
                event_type="item_description_unlocked",
                known_to_context=True,
                data={
                    "item_id": 159,
                    "description_key": 1,
                    "toast_id": "20140",
                    "current_video_key": "011_001",
                    "current_folder_name": "chapter103",
                },
            ),
        ]

        payload = build_dossier_unlocks(events, mappings=_mappings())

        self.assertEqual(payload["totals"]["unknown"], 1)
        self.assertEqual(payload["totals"]["usable"], 1)
        self.assertEqual(len(payload["unknown_queue"]), 1)
        record = payload["unknown_queue"][0]
        self.assertEqual(record["entity_type"], "item")
        self.assertEqual(record["entity_id"], "159")
        self.assertEqual(record["unlock_kind"], "entity_first_unlock")
        self.assertEqual(record["content_keys"], [1])
        self.assertEqual(record["description_keys"], [1])
        self.assertIn("do not infer", record["prompt_policy"])

    def test_confirmed_and_candidate_mappings_are_separated(self) -> None:
        events = [
            RuntimeEvent(20, "item_content_unlocked", True, {"item_id": 164, "content_key": 1, "ret": 0}),
            RuntimeEvent(21, "character_unlocked", True, {"character_id": 107, "ret": 0}),
        ]

        payload = build_dossier_unlocks(events, mappings=_mappings())

        self.assertEqual(payload["totals"]["confirmed"], 1)
        self.assertEqual(payload["totals"]["candidate"], 1)
        self.assertEqual(payload["confirmed_profiles"][0]["name"], "词条甲")
        self.assertEqual(payload["candidate_queue"][0]["name"], "角色乙")
        self.assertIn("not a prompt fact", payload["candidate_queue"][0]["prompt_policy"])

    def test_failed_ret_is_audit_only(self) -> None:
        events = [
            RuntimeEvent(
                line_no=30,
                event_type="item_content_unlocked",
                known_to_context=True,
                data={"item_id": 200, "content_key": 1, "ret": -1, "toast_id": "20999"},
            )
        ]

        payload = build_dossier_unlocks(events, mappings=_mappings())

        self.assertEqual(payload["totals"]["failed_only"], 1)
        self.assertEqual(payload["totals"]["usable"], 0)
        self.assertEqual(payload["unknown_queue"], [])
        self.assertEqual(payload["failed_events"][0]["ret"], -1)

    def test_description_without_first_unlock_stays_description_update(self) -> None:
        events = [
            RuntimeEvent(
                line_no=40,
                event_type="character_description_unlocked",
                known_to_context=True,
                data={"character_id": 105, "content_key": 2, "toast_id": "20056"},
            )
        ]

        payload = build_dossier_unlocks(events, mappings=_mappings())

        record = payload["confirmed_profiles"][0]
        self.assertEqual(record["unlock_kind"], "description_update")
        self.assertEqual(record["content_keys"], [2])


def _mappings() -> dict:
    return {
        "characters": {"105": {"name": "角色甲", "source": "fixture"}},
        "items": {"164": {"name": "词条甲", "source": "fixture"}},
        "candidates": {
            "characters": {
                "107": {
                    "candidate_name": "角色乙",
                    "confidence": "high",
                }
            },
            "items": {},
        },
    }


if __name__ == "__main__":
    unittest.main()
