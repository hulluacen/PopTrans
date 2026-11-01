import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.glossary import Glossary, REFERENCE_TOKEN_BUDGET
from backend.translator import Translator, estimate_tokens, SOURCE_MAX_TOKENS, _split_long_text, build_translation_prompt, build_translation_messages


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
        self.assertIn('"web": "膜材"', self.reference("WEB transport"))
        self.assertEqual(self.reference("websocket rewinder"), "")
        self.assertEqual(self.reference("web transport", "en"), "")
        self.assertEqual(self.reference("web transport", "vi"), "")

    def test_longer_phrase_wins_without_duplicate_short_reference(self):
        reference = self.reference("The web tension is high.")
        self.assertIn('"web tension": "料带张力"', reference)
        self.assertNotIn('"web":', reference)

    def test_matching_priority_does_not_reorder_later_terms_to_the_front(self):
        self.data["entries"]=[
            {"source":s,"target":t,"context":"张力控制","source_lang":"en","target_lang":"zh","enabled":True}
            for s,t in [("dancer position","浮辊位置"),("dancer roll","浮辊"),("dancer","浮辊")]
        ]
        self.write()
        plan=self.glossary.plan(self.glossary.snapshot(),"The dancer roll moves. The dancer system measures dancer position.","zh",estimate_tokens)
        self.assertEqual([g["source"] for g in plan["groups"]],["dancer roll","dancer","dancer position"])

    def test_library_name_is_carried_as_a_domain_label(self):
        self.data["local_enabled"]=False
        self.data["libraries"]=[{"id":"film","name":"薄膜收放卷","enabled":True,"entries":self.data["entries"]}]
        self.write()
        plan=self.glossary.plan(self.glossary.snapshot(),"web transport","zh",estimate_tokens)
        self.assertEqual(plan["groups"][0]["candidates"][0]["library"],"薄膜收放卷")
        self.assertIn('domain: "薄膜收放卷"',plan["reference"])

    def test_reference_prioritizes_applicable_terms_and_retains_exceptions(self):
        reference = self.reference("Open the web browser.")
        self.assertIn("usage:", reference)
        self.assertNotIn("如果符合语境", reference)
        self.assertIn("网页语境采用其他含义", reference)
        messages = build_translation_messages("zh", "Open the web browser.", reference)
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertIn("when their context fits", messages[0]["content"])
        self.assertEqual(messages[1]["content"], build_translation_prompt("zh", "Open the web browser."))
        self.assertNotIn("网页语境", messages[1]["content"])

    def test_chinese_to_english_uses_readable_mapping(self):
        self.data["entries"] = [{"source":"浮辊","target":"dancer roll","context":"web tension control","source_lang":"zh","target_lang":"en","enabled":True}]
        self.write()
        reference = self.reference("调整浮辊位置。", "en")
        self.assertIn('"浮辊": "dancer roll"', reference)

    def test_chinese_alternatives_preserve_original_entry_and_io_notation(self):
        self.data["entries"][0]["target"] = "膜材／连续料带"
        self.data["entries"].append({"source":"port","target":"I/O 端口","source_lang":"en","target_lang":"zh"})
        self.write()
        plan = self.glossary.plan(self.glossary.snapshot(), "web port", "zh", estimate_tokens)
        self.assertIn('"web": "膜材或连续料带"', plan["reference"])
        self.assertIn('"port": "I/O 端口"', plan["reference"])
        self.assertEqual(plan["groups"][0]["candidates"][0]["target"], "膜材／连续料带")

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
                self.prompts.append("\n".join(m["content"] for m in messages))
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

    def test_library_switches_and_local_priority_preserve_meanings(self):
        entry={"source":"web","target":"外部库译法","context":"专业设备","source_lang":"en","target_lang":"zh","enabled":True}
        self.data["entries"].append({**entry,"target":"本地另一含义"})
        self.data["libraries"]=[{"id":"film","name":"薄膜库","enabled":True,"entries":[entry]}]
        self.write()
        reference=self.reference("web")
        self.assertIn("膜材",reference);self.assertIn("本地另一含义",reference);self.assertNotIn("外部库译法",reference)
        self.data["local_enabled"]=False;self.write()
        reference=self.reference("web")
        self.assertIn("外部库译法",reference);self.assertNotIn("本地另一含义",reference)
        self.data["libraries"][0]["enabled"]=False;self.write()
        self.assertEqual(self.reference("web"),"")
        self.data["libraries"][0]["enabled"]=True;self.data["enabled"]=False;self.write()
        self.assertEqual(self.reference("web"),"")

    def test_disabled_named_library_is_not_compiled_and_legacy_still_works(self):
        self.data["libraries"]=[{"id":"bad","name":"未启用库","enabled":False,"entries":[None]}]
        self.write()
        self.assertIn("膜材",self.reference("web"))

    def test_same_source_keeps_all_meanings_as_one_group(self):
        self.data["entries"].append({"source":"WEB","target":"网页","context":"浏览器","source_lang":"en","target_lang":"zh","enabled":True})
        self.write()
        plan=self.glossary.plan(self.glossary.snapshot(),"Open a web page.","zh",estimate_tokens)
        self.assertEqual(len(plan["groups"]),1)
        self.assertEqual({row["target"] for row in plan["groups"][0]["candidates"]},{"膜材","网页"})

    def test_oversized_meaning_group_is_not_partially_provided(self):
        self.data["entries"]=[{"source":"web","target":f"含义{i}","context":"这里是长篇的适用语境说明"*14,"source_lang":"en","target_lang":"zh","enabled":True} for i in range(4)]
        self.write()
        plan=self.glossary.plan(self.glossary.snapshot(),"web","zh",estimate_tokens)
        self.assertEqual(plan["groups"],[])
        self.assertEqual(plan["omitted_sources"],["web"])

    def test_reference_info_belongs_to_the_response_and_cached_version(self):
        class FakeModel:
            def create_chat_completion(self,**kwargs):
                content = "译文"
                return {"choices":[{"message":{"content":content}}]}
        engine=Translator();engine.ready=True;engine._model=FakeModel();engine._glossary=self.glossary
        _,error,first=engine.translate_with_info("web transport","zh")
        self.assertIsNone(error);self.assertEqual(first["groups"][0]["source"],"web")
        _,_,other=engine.translate_with_info("ordinary sentence","zh")
        self.assertEqual(other["groups"],[])
        _,_,cached=engine.translate_with_info("web transport","zh")
        self.assertEqual(first,cached)
        first["groups"].clear()
        self.assertTrue(engine.translate_with_info("web transport","zh")[2]["groups"])


if __name__ == "__main__": unittest.main()
