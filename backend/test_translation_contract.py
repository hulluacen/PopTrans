import unittest
from backend.translator import Translator, build_translation_messages, build_translation_prompt, validate_terminology_translation
from backend.glossary import Snapshot


class TranslationContractTests(unittest.TestCase):
    def test_no_terms_preserves_original_user_prompt(self):
        source='The "material web" moves.\nKeep its position.'
        expected="Translate the following text into Chinese. Note that you should only output the translated result without any additional explanation:\n\n"+source
        self.assertEqual(build_translation_prompt("zh",source),expected)
        self.assertEqual(build_translation_messages("zh",source),[{"role":"user","content":expected}])

    def test_reference_is_only_in_system_message_and_source_is_unchanged(self):
        source='The dancer roll is position-controlled.\nIts position changes.'
        reference='"dancer roll": "浮辊" [usage: "张力控制"]'
        messages=build_translation_messages("zh",source,reference)
        self.assertEqual([m["role"] for m in messages],["system","user"])
        self.assertIn(reference,messages[0]["content"])
        self.assertNotIn(reference,messages[1]["content"])
        self.assertEqual(messages[1]["content"],build_translation_prompt("zh",source))

    def test_does_not_replace_words_or_decode_json_in_the_translation(self):
        output='“浮辊”是一种基于位置控制的测量系统。\n\n第二段。'
        self.assertEqual(validate_terminology_translation(output,"source"),output)

    def test_rejects_reference_leak_but_preserves_literal_source(self):
        with self.assertRaisesRegex(ValueError,"术语说明混入"):
            validate_terminology_translation('Required terminology: dancer -> 浮辊',"The dancer roll moves.")
        literal="Required terminology"
        self.assertEqual(validate_terminology_translation(literal,literal),literal)

    def test_plaintext_generation_and_truncation_not_cached(self):
        class FakeGlossary:
            def snapshot(self):return Snapshot("test",True)
            def plan(self,*args):return {"reference":'"web": "膜材"',"groups":[],"omitted_sources":[]}
        class FakeModel:
            finish="stop"
            def create_chat_completion(self,**kwargs):
                assert "response_format" not in kwargs
                assert [m["role"] for m in kwargs["messages"]]==["system","user"]
                return {"choices":[{"message":{"content":"膜材移动。"},"finish_reason":self.finish}]}
        engine=Translator();engine.ready=True;engine._model=FakeModel();engine._glossary=FakeGlossary()
        self.assertEqual(engine.translate("web moves","zh"),("膜材移动。",None))
        engine._model.finish="length"
        result,error=engine.translate("web moves again","zh")
        self.assertIsNone(result);self.assertIn("截断",error)
        self.assertFalse(any(key[0]=="web moves again" for key in engine._translation_cache))


if __name__=="__main__":unittest.main()
