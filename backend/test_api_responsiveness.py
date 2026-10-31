import asyncio
import threading
import unittest
from unittest.mock import patch

from backend.api_server import (
    ChatCompletionRequest, ChatMessage, chat_completions, health_check,
    translator_engine,
)


class InferenceResponsivenessTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_remains_responsive_during_translation(self):
        started = threading.Event()
        finish = threading.Event()

        def slow_translation(*args):
            with translator_engine._inference_lock:
                started.set()
                finish.wait(1)
                return "translated", None

        with patch.object(translator_engine, "ready", True), patch.object(translator_engine, "translate", slow_translation):
            task = asyncio.create_task(chat_completions(ChatCompletionRequest(messages=[ChatMessage(role="user", content="test")])))
            try:
                for _ in range(100):
                    if started.is_set():
                        break
                    await asyncio.sleep(0.002)
                self.assertTrue(started.is_set())
                self.assertFalse(task.done(), "inference blocked the event loop")
                health = await asyncio.wait_for(asyncio.to_thread(health_check), 0.2)
                self.assertTrue(health["translator_ready"])
                self.assertTrue(health["busy"])
            finally:
                finish.set()
                await task


if __name__ == "__main__":
    unittest.main()
