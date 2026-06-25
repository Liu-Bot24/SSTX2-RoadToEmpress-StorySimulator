from pathlib import Path
import tempfile
import unittest

from road_state_tracker.config_inventory import build_config_inventory, config_text_prefix, inspect_config_file
from test_text_index import field_string, top_message, varint


def field_varint(number: int, value: int) -> bytes:
    return varint((number << 3) | 0) + varint(value)


class ConfigInventoryTests(unittest.TestCase):
    def test_inspect_encrypted_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "VideoConfig.pbin"
            path.write_bytes(b"AESType_" + bytes(range(16)))

            item = inspect_config_file(path)

        self.assertTrue(item["encrypted"])
        self.assertEqual(item["payload_length"], 16)
        self.assertEqual(item["payload_mod16"], 0)
        self.assertEqual(item["text_prefix"], "TID_VideoConfig")
        self.assertNotIn("protobuf_summary", item)

    def test_summarize_plain_config_video_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Envoy.pbin"
            nested = field_string(1, "009_C010A_003") + field_varint(2, 1)
            path.write_bytes(
                top_message(
                    field_varint(1, 1),
                    field_string(2, "009_059"),
                    top_message(nested),
                )
            )

            item = inspect_config_file(path)

        self.assertFalse(item["encrypted"])
        self.assertTrue(item["protobuf_summary"]["parseable"])
        self.assertEqual(item["protobuf_summary"]["top_record_count"], 1)
        self.assertIn("009_C010A_003", item["protobuf_summary"]["sample_video_keys"])

    def test_build_inventory_counts_non_textclient_configs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "Data" / "StreamingAssets" / "res" / "main" / "cfg" / "data"
            cfg.mkdir(parents=True)
            (cfg / "TextClientExcel.pbin").write_bytes(b"ignored")
            (cfg / "VideoConfig.pbin").write_bytes(b"AESType_" + bytes(range(16)))
            (cfg / "Envoy.pbin").write_bytes(top_message(field_varint(1, 1)))

            inventory = build_config_inventory(root)

        self.assertEqual(inventory["config_count"], 2)
        self.assertEqual(inventory["encrypted_count"], 1)
        self.assertEqual(inventory["plaintext_count"], 1)

    def test_config_text_prefix_handles_non_config_suffix(self) -> None:
        self.assertEqual(config_text_prefix("Envoy.pbin"), "TID_EnvoyConfig")
        self.assertEqual(config_text_prefix("mallConfig.pbin"), "TID_mallConfig")
