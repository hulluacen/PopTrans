import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.glossary import Glossary, REFERENCE_TOKEN_BUDGET
from backend.translator import Translator, estimate_tokens, SOURCE_MAX_TOKENS, _split_long_text


class GlossaryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "glossary.json"
        self.data = {"enabled": True, "domain": "西门子／卷绕", "entries": [
            {"source": "web", "target": "膜材", "context": "仅用于连续料带；网页语境采用其他含义", "source_lang": "en", "target_lang": "zh", "enabled": True},
            {"source": "web tension", "target": "料带张力", "context": "张力控制", "source_lang": "en", "target_lang": "zh", "enabled": True},
        ]}
        self.write()
        self.glossary = Glossary(self.path)

    def write(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    def reference(self, text, target="zh"):
        return self.glossary.reference(self.glossary.snapshot(), text, target, estimate_tokens)

    def test_whole_word_case_and_language_direction(self):
        self.assertIn('"source": "web"', self.reference("WEB transport"))
        self.assertEqual(self.reference("websocket rewinder"), "")
        self.assertEqual(self.reference("web transport", "en"), "")
        self.assertEqual(self.reference("web transport", "vi"), "")

    def test_longer_phrase_wins_without_duplicate_short_reference(self):
        reference = self.reference("The web tension is high.")
        self.assertIn('"source": "web tension"', reference)
        self.assertNotIn('"source": "web"', reference)

    def test_reference_is_optional_and_retains_usage_notes(self):
        reference = self.reference("Open the web browser.")
        self.assertIn("If context suggests another meaning", reference)
        self.assertIn("网页语境采用其他含义", reference)

    def test_disabled_and_unrelated_entries_do_not_change_prompt(self):
        self.assertEqual(self.reference("The motor is running."), "")
        self.data["enabled"] = False
        self.write()
        self.assertEqual(self.reference("web transport"), "")

    def test_reference_budget_is_bounded(self):
        self.data["entries"] = [{"source":f"term{i}","target":"参考译法"*8,"context":"适用语境"*20,"source_lang":"en","target_lang":"zh"} for i in range(100)]
        self.write()
        reference = self.reference(" ".join(f"term{i}" for i in range(100)))
        self.assertLessEqual(estimate_tokens(reference), REFERENCE_TOKEN_BUDGET)
        chunks, _ = _split_long_text("这是用于分块测试的正文。"*150, SOURCE_MAX_TOKENS-REFERENCE_TOKEN_BUDGET)
        self.assertTrue(all(estimate_tokens(chunk)<=SOURCE_MAX_TOKENS-REFERENCE_TOKEN_BUDGET+8 for chunk in chunks))

    def test_unchanged_file_is_not_reparsed_per_translation(self):
        original = Path.read_bytes
        with patch.object(Path, "read_bytes", autospec=True, side_effect=original) as read:
            for _ in range(50): self.glossary.snapshot()
            self.assertEqual(read.call_count, 1)

    def test_saved_glossary_invalidates_translation_cache(self):
        class FakeModel:
            def __init__(self): self.prompts = []
            def create_chat_completion(self, messages, **kwargs):
                self.prompts.append(messages[0]["content"])
                return {"choices":[{"message":{"content":f"result-{len(self.prompts)}"}}]}
        engine = Translator()
        engine.ready = True
        engine._model = FakeModel()
        engine._glossary = self.glossary
        text = "The web moves."
        first, _ = engine.translate(text, "zh")
        self.assertEqual(engine.translate(text, "zh")[0], first)
        self.data["entries"][0]["target"] = "连续膜材"
        self.write()
        second, _ = engine.translate(text, "zh")
        self.assertNotEqual(first, second)
        self.assertIn("连续膜材", engine._model.prompts[-1])

    def test_bad_file_does_not_break_translation(self):
        self.path.write_text("not JSON", encoding="utf-8")
        self.assertFalse(self.glossary.snapshot().enabled)


if __name__ == "__main__": unittest.main()
