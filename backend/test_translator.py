import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from backend.translator import (
    Translator,
    build_translation_prompt,
    normalize_target_language,
    resolve_model_path,
)


class ModelSelectionTests(unittest.TestCase):
    def test_custom_name_outside_default_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            model = root / "翻译模型 Q8.gguf"
            model.write_bytes(b"GGUFtest")
            cfg = root / "settings.json"
            cfg.write_text(json.dumps({"model_path": str(model)}), encoding="utf-8")
            with patch("backend.translator.settings_path", return_value=cfg):
                self.assertEqual(resolve_model_path(), (str(model), True))

    def test_relative_model_is_resolved_from_application_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            model = root / "custom.gguf"
            model.write_bytes(b"GGUFtest")
            cfg = root / "settings.json"
            cfg.write_text('{"model_path":"custom.gguf"}', encoding="utf-8")
            with patch("backend.translator.settings_path", return_value=cfg), patch("backend.translator.application_dir", return_value=root):
                self.assertEqual(resolve_model_path(), (str(model), True))

    def test_missing_custom_model_does_not_trigger_default_download(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg = Path(folder) / "settings.json"
            cfg.write_text('{"model_path":"missing.gguf"}', encoding="utf-8")
            engine = Translator()
            with patch("backend.translator.settings_path", return_value=cfg), patch.object(engine, "_download_model") as download:
                engine._setup_worker(None, None)
                download.assert_not_called()
                self.assertFalse(engine.ready)

    def test_rejects_invalid_gguf_header(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            model = root / "invalid.gguf"
            model.write_bytes(b"not a model")
            cfg = root / "settings.json"
            cfg.write_text(json.dumps({"model_path": str(model)}), encoding="utf-8")
            with patch("backend.translator.settings_path", return_value=cfg):
                with self.assertRaisesRegex(ValueError, "有效的 GGUF"):
                    resolve_model_path()


class FakeModel:
    def __init__(self):
        self.prompts = []

    def create_chat_completion(self, messages, **kwargs):
        prompt = messages[0]["content"]
        self.prompts.append(prompt)
        return {
            "choices": [
                {
                    "message": {
                        "content": f"result-{len(self.prompts)}",
                    }
                }
            ]
        }


class TranslatorLanguageTests(unittest.TestCase):
    def setUp(self):
        self.translator = Translator()
        self.translator.ready = True
        self.translator._model = FakeModel()

    def test_normalizes_language_codes_names_and_locales(self):
        self.assertEqual(normalize_target_language("vi"), "vi")
        self.assertEqual(normalize_target_language("vi-VN"), "vi")
        self.assertEqual(normalize_target_language("越南语"), "vi")
        self.assertEqual(normalize_target_language("Vietnamese"), "vi")
        self.assertEqual(normalize_target_language("zh-Hant"), "zh-hant")
        self.assertIsNone(normalize_target_language(None))

    def test_rejects_unsupported_language(self):
        with self.assertRaisesRegex(ValueError, "不支持的目标语言"):
            normalize_target_language("unknown")

    def test_translates_to_explicit_vietnamese(self):
        result, error = self.translator.translate("你好", "vi")

        self.assertIsNone(error)
        self.assertEqual(result, "result-1")
        self.assertIn("into Vietnamese", self.translator._model.prompts[0])
        self.assertTrue(self.translator._model.prompts[0].endswith("\n\n你好"))

    def test_builds_official_prompt_with_full_language_name(self):
        prompt = build_translation_prompt("vi", "欢迎使用")

        self.assertIn("into Vietnamese", prompt)
        self.assertNotIn("vi", prompt)
        self.assertTrue(prompt.endswith("\n\n欢迎使用"))

    def test_cache_is_isolated_by_target_language(self):
        first, _ = self.translator.translate("你好", "vi")
        second, _ = self.translator.translate("你好", "en")
        cached, _ = self.translator.translate("你好", "vi")

        self.assertEqual(first, "result-1")
        self.assertEqual(second, "result-2")
        self.assertEqual(cached, first)
        self.assertEqual(len(self.translator._model.prompts), 2)

    def test_automatic_mode_keeps_existing_direction(self):
        _, error = self.translator.translate("你好")

        self.assertIsNone(error)
        self.assertIn("into English", self.translator._model.prompts[0])

    def test_long_text_is_chunked_and_joined(self):
        long_text = "这是一段用于验证长文分块翻译的中文文本。" * 200

        result, error = self.translator.translate(long_text, "vi")

        self.assertIsNone(error)
        self.assertGreater(len(self.translator._model.prompts), 1)
        expected = "\n".join(
            f"result-{i + 1}" for i in range(len(self.translator._model.prompts))
        )
        self.assertEqual(result, expected)

    def test_short_text_stays_single_inference(self):
        result, error = self.translator.translate("你好世界", "vi")

        self.assertIsNone(error)
        self.assertEqual(len(self.translator._model.prompts), 1)
        self.assertEqual(result, "result-1")

    def test_device_info_structure(self):
        info = self.translator.device_info
        self.assertIn("configured", info)
        self.assertIn("actual", info)
        self.assertIn("gpu_layers", info)


if __name__ == "__main__":
    unittest.main()

