from __future__ import annotations

import contextlib
import io
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "patch_sstx2_history.py"

spec = importlib.util.spec_from_file_location("patch_sstx2_history", MODULE_PATH)
patcher = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["patch_sstx2_history"] = patcher
spec.loader.exec_module(patcher)


class PatchSSTX2HistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manifest_path = self.root / "patch_manifest.json"
        self.manifest_tw_path = self.root / "patch_manifest_zh_TW.json"
        self.hosts_path = self.root / "hosts"
        self.original_manifest_path = patcher.PATCH_MANIFEST_PATH
        self.original_manifest_tw_path = patcher.PATCH_MANIFEST_TW_PATH
        self.original_hosts_path_override = patcher.HOSTS_PATH_OVERRIDE
        patcher.PATCH_MANIFEST_PATH = self.manifest_path
        patcher.PATCH_MANIFEST_TW_PATH = self.manifest_tw_path
        patcher.HOSTS_PATH_OVERRIDE = self.hosts_path
        self.manifest_path.write_text(
            json.dumps(
                {
                    "replacements": [
                        {"id": "phonetic-one", "from": "甲名", "to": "乙名", "modes": ["all", "phonetic"]},
                        {"id": "wujiejie-address", "from": "伍姐姐", "to": "武姐姐", "modes": ["all", "phonetic"]},
                        {"id": "all-only", "from": "丙名", "to": "丁名", "modes": ["all"]},
                        {"id": "byte-length-growth", "from": "短", "to": "更长文本", "modes": ["all"]},
                        {
                            "id": "contextual",
                            "from": "星名",
                            "to": "辰名",
                            "modes": ["all"],
                            "skipWhenNear": ["词星名词"],
                            "nearWindow": 3,
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.manifest_tw_path.write_text(self.manifest_path.read_text(encoding="utf-8"), encoding="utf-8")
        self.hosts_path.write_text("127.0.0.1 localhost\n", encoding="ascii")

    def tearDown(self) -> None:
        patcher.PATCH_MANIFEST_PATH = self.original_manifest_path
        patcher.PATCH_MANIFEST_TW_PATH = self.original_manifest_tw_path
        patcher.HOSTS_PATH_OVERRIDE = self.original_hosts_path_override
        self.temp.cleanup()

    def write_srt(self, text: str) -> Path:
        path = self.root / patcher.SRT_RELATIVE_ROOT / "zh_GL" / "chapter000" / "sample.srt"
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        return path

    def write_textclient(self, *records: tuple[str, str, str, str]) -> Path:
        cfg_dir = self.root / patcher.TEXTCLIENT_RELATIVE_DIR
        cfg_dir.mkdir(parents=True)
        top_fields = []
        for index, (key, zh_cn, zh_gl, zh_tw) in enumerate(records, 1):
            row = patcher.serialize_wire_fields(
                [
                    patcher.WireField(1, 2, key.encode("utf-8")),
                    patcher.WireField(2, 2, zh_cn.encode("utf-8")),
                    patcher.WireField(4, 2, zh_gl.encode("utf-8")),
                    patcher.WireField(6, 2, zh_tw.encode("utf-8")),
                ]
            )
            top_fields.append(patcher.WireField(index, 2, row))
        path = cfg_dir / "TextClientExcel.pbin"
        path.write_bytes(patcher.serialize_wire_fields(top_fields))
        return path

    def write_textclient_chapter(self) -> Path:
        cfg_dir = self.root / patcher.TEXTCLIENT_RELATIVE_DIR
        cfg_dir.mkdir(parents=True)
        row = patcher.serialize_wire_fields(
            [
                patcher.WireField(1, 2, b"KEY:sample.title"),
                patcher.WireField(2, 2, "甲名与伍姐姐".encode("utf-8")),
                patcher.WireField(4, 2, "伍姐姐".encode("utf-8")),
                patcher.WireField(6, 2, "伍姐姐".encode("utf-8")),
                patcher.WireField(8, 2, b"Sister Wu"),
                patcher.WireField(10, 2, "伍姉様".encode("utf-8")),
            ]
        )
        path = cfg_dir / "TextClientchapter999.pbin"
        path.write_bytes(patcher.serialize_wire_fields([patcher.WireField(1, 2, row)]))
        return path

    def test_phonetic_patch_and_restore(self) -> None:
        srt = self.write_srt("1\n00:00:00,000 --> 00:00:01,000\n甲名与丙名\n")
        with contextlib.redirect_stdout(io.StringIO()):
            stats = patcher.apply_patch(self.root, "phonetic", "zh_GL", True, False, ".backup")
        self.assertEqual(stats.changed_files, 1)
        self.assertIn("乙名", srt.read_text(encoding="utf-8"))
        self.assertIn("丙名", srt.read_text(encoding="utf-8"))
        self.assertIn(patcher.ONLINE_SUBTITLE_HOST, self.hosts_path.read_text(encoding="ascii"))

        with contextlib.redirect_stdout(io.StringIO()):
            patcher.restore(self.root, ".backup")
        self.assertIn("甲名与丙名", srt.read_text(encoding="utf-8"))
        self.assertNotIn(patcher.ONLINE_SUBTITLE_HOST, self.hosts_path.read_text(encoding="ascii"))

    def test_patch_takes_over_legacy_online_subtitle_block(self) -> None:
        self.hosts_path.write_text(
            "127.0.0.1 localhost\r\n"
            "# SSTX2 temporary block online subtitles\r\n"
            "127.0.0.1 eo.roadtoempress.com\r\n",
            encoding="ascii",
        )
        self.write_srt("1\n00:00:00,000 --> 00:00:01,000\n甲名\n")

        with contextlib.redirect_stdout(io.StringIO()):
            patcher.apply_patch(self.root, "phonetic", "zh_GL", True, False, ".backup")
        text = self.hosts_path.read_text(encoding="ascii")
        self.assertIn(patcher.HOSTS_MARKER_BEGIN, text)
        self.assertNotIn(patcher.LEGACY_HOSTS_MARKER, text)

        with contextlib.redirect_stdout(io.StringIO()):
            patcher.restore(self.root, ".backup")
        self.assertNotIn(patcher.ONLINE_SUBTITLE_HOST, self.hosts_path.read_text(encoding="ascii"))

    def test_all_mode_patches_srt_and_textclient_with_context_skip(self) -> None:
        srt = self.write_srt("1\n00:00:00,000 --> 00:00:01,000\n甲名、丙名、星名、词星名词\n")
        pbin = self.write_textclient(("Key_Test", "甲名", "星名和词星名词", "丙名和短"))

        with contextlib.redirect_stdout(io.StringIO()):
            stats = patcher.apply_patch(self.root, "all", "zh_GL", True, True, ".backup")
        self.assertEqual(stats.changed_files, 2)

        text = srt.read_text(encoding="utf-8")
        self.assertIn("乙名、丁名、辰名、词星名词", text)

        data = pbin.read_bytes()
        self.assertIn("乙名".encode("utf-8"), data)
        self.assertIn("辰名和词星名词".encode("utf-8"), data)
        self.assertIn("丁名".encode("utf-8"), data)
        self.assertIn("更长文本".encode("utf-8"), data)
        self.assertNotIn("甲名".encode("utf-8"), data)

        top_fields = patcher.parse_wire_fields(data)
        row_fields = patcher.parse_wire_fields(top_fields[0].value)
        zh_tw = next(field.value for field in row_fields if field.field_number == 6)
        self.assertEqual(zh_tw.decode("utf-8"), "丁名和更长文本")

    def test_textclient_chapter_patches_only_chinese_fields(self) -> None:
        pbin = self.write_textclient_chapter()

        with contextlib.redirect_stdout(io.StringIO()):
            stats = patcher.apply_patch(self.root, "phonetic", "zh_GL", False, True, ".backup")
        self.assertEqual(stats.changed_files, 1)

        data = pbin.read_bytes()
        self.assertIn("乙名与武姐姐".encode("utf-8"), data)
        self.assertNotIn("伍姐姐".encode("utf-8"), data)
        self.assertIn("Sister Wu".encode("utf-8"), data)
        self.assertIn("伍姉様".encode("utf-8"), data)


if __name__ == "__main__":
    unittest.main()
