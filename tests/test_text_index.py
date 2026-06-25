from pathlib import Path
import tempfile
import unittest

from road_state_tracker.text_index import build_choice_groups, build_tid_text_index, parse_textclient_pbin


def varint(value: int) -> bytes:
    output = bytearray()
    while True:
        chunk = value & 0x7F
        value >>= 7
        if value:
            output.append(chunk | 0x80)
        else:
            output.append(chunk)
            return bytes(output)


def field_string(number: int, value: str) -> bytes:
    raw = value.encode("utf-8")
    return varint((number << 3) | 2) + varint(len(raw)) + raw


def top_message(*fields: bytes) -> bytes:
    payload = b"".join(fields)
    return varint((1 << 3) | 2) + varint(len(payload)) + payload


class TextIndexTests(unittest.TestCase):
    def test_parse_positive_textclient_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "TextClientchapter101.pbin"
            path.write_bytes(
                top_message(
                    field_string(1, "Key:ShowChoice-CL010_009_002.title"),
                    field_string(2, "测试中文文本"),
                    field_string(8, "Test English text."),
                )
            )

            rows, reason = parse_textclient_pbin(path, root)

        self.assertIsNone(reason)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["key"], "ShowChoice-CL010_009_002.title")
        self.assertEqual(rows[0]["zh"], "测试中文文本")
        self.assertEqual(rows[0]["zh_CN"], "测试中文文本")
        self.assertEqual(rows[0]["en_US"], "Test English text.")
        self.assertEqual(rows[0]["language_texts"]["en_US"], "Test English text.")
        self.assertEqual(rows[0]["chapter_hint"], "101")

    def test_zh_gl_is_preferred_for_display_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "TextClientExcel.pbin"
            path.write_bytes(
                top_message(
                    field_string(1, "TID_CharacterConfig_1"),
                    field_string(2, "大陆简体"),
                    field_string(4, "当前简体"),
                    field_string(8, "English"),
                )
            )

            rows, reason = parse_textclient_pbin(path, root)

        self.assertIsNone(reason)
        self.assertEqual(rows[0]["zh"], "当前简体")
        self.assertEqual(rows[0]["zh_CN"], "大陆简体")
        self.assertEqual(rows[0]["zh_GL"], "当前简体")

    def test_skip_encrypted_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "CharacterConfig.pbin"
            path.write_bytes(b"AESType_" + b"x" * 16)

            rows, reason = parse_textclient_pbin(path, root)

        self.assertEqual(rows, [])
        self.assertEqual(reason, "encrypted")

    def test_build_choice_group(self) -> None:
        rows = [
            {"key": "ShowChoice-A.storylineTitle", "zh": "标题", "source_file": "TextClientchapter1.pbin", "chapter_hint": "1"},
            {"key": "ShowChoice-A.title", "zh": "你选择？", "source_file": "TextClientchapter1.pbin", "chapter_hint": "1"},
            {"key": "ShowChoice-A.choice+0.choiceText", "zh": "选项一", "source_file": "TextClientchapter1.pbin", "chapter_hint": "1"},
            {"key": "ShowChoice-A.choice+1.choiceText", "zh": "选项二", "source_file": "TextClientchapter1.pbin", "chapter_hint": "1"},
        ]

        groups = build_choice_groups(rows)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["prompt"], "你选择？")
        self.assertEqual(groups[0]["choices"][0]["text"], "选项一")
        self.assertEqual(groups[0]["choices"][1]["text"], "选项二")

    def test_tid_index_prefers_richer_language_row(self) -> None:
        rows = [
            {
                "key": "TID_CharacterConfig_1",
                "source_file": "TextClientExamplezh_CN.pbin",
                "zh": "角色甲",
                "zh_CN": "角色甲",
                "zh_GL": "",
                "zh_TW": "",
                "en_US": "",
                "language_texts": {"zh_CN": "角色甲"},
            },
            {
                "key": "TID_CharacterConfig_1",
                "source_file": "TextClientExcel.pbin",
                "zh": "角色甲",
                "zh_CN": "角色甲",
                "zh_GL": "角色甲",
                "zh_TW": "角色甲繁体",
                "en_US": "Role A",
                "language_texts": {"zh_CN": "角色甲", "zh_GL": "角色甲", "zh_TW": "角色甲繁体", "en_US": "Role A"},
            },
        ]

        tid_rows = build_tid_text_index(rows)

        self.assertEqual(len(tid_rows), 1)
        self.assertEqual(tid_rows[0]["source_file"], "TextClientExcel.pbin")
        self.assertEqual(tid_rows[0]["en_US"], "Role A")


if __name__ == "__main__":
    unittest.main()
