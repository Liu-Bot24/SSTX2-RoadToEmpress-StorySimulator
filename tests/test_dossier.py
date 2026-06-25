import json
import tempfile
import unittest
from pathlib import Path

from road_state_tracker.dossier import build_dossier


class DossierTests(unittest.TestCase):
    def test_static_mapping_resolves_to_static_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_dir = root / "index"
            index_dir.mkdir()
            mapping_path = root / "mappings.json"
            mapping_path.write_text(
                json.dumps(
                    {
                        "characters": {"105": {"name": "角色甲", "source": "fixture"}},
                        "items": {},
                        "candidates": {"characters": {}, "items": {}},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (index_dir / "tid_text_index.jsonl").write_text(
                json.dumps(
                    {
                        "key": "TID_CharacterCardConfig_872420",
                        "prefix": "TID_CharacterCardConfig",
                        "zh": "角色甲",
                        "en_US": "Role A",
                        "source_file": "TextClientExcel.pbin",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            dossier = build_dossier(index_dir, "105", mapping_path=mapping_path)

        self.assertEqual(dossier["resolved"]["mapping"]["scope"], "profile_unlocked")
        self.assertEqual(dossier["resolved"]["search_text"], "角色甲")
        self.assertEqual(dossier["evidence"][0]["category"], "character_card_candidate")

    def test_candidate_mapping_stays_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_dir = root / "index"
            index_dir.mkdir()
            mapping_path = root / "mappings.json"
            mapping_path.write_text(
                json.dumps(
                    {
                        "characters": {},
                        "items": {},
                        "candidates": {
                            "characters": {
                                "107": {
                                    "candidate_name": "角色乙",
                                    "confidence": "high",
                                    "evidence_type": "anchored_sequence_candidate",
                                }
                            },
                            "items": {},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (index_dir / "tid_text_index.jsonl").write_text(
                json.dumps(
                    {
                        "key": "TID_CharacterCardConfig_559063",
                        "prefix": "TID_CharacterCardConfig",
                        "zh": "角色乙",
                        "en_US": "Role B",
                        "source_file": "TextClientExcel.pbin",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            dossier = build_dossier(index_dir, "107", mapping_path=mapping_path)

        self.assertEqual(dossier["resolved"]["mapping"]["scope"], "candidate_mapping")
        self.assertEqual(dossier["resolved"]["mapping"]["candidate_name"], "角色乙")
        self.assertEqual(dossier["evidence"][0]["zh"], "角色乙")


if __name__ == "__main__":
    unittest.main()
