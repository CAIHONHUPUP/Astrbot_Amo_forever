# -*- coding: utf-8 -*-
"""主动分享生图：判断与出图分开，出图在后台任务里，不阻塞回复。"""

import asyncio
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import astrbot_stub  # noqa: E402

astrbot_stub.install()

import main as amo_main  # noqa: E402


class FakeDB:
    def __init__(self):
        self.kv = {}

    def kv_get(self, key, default=None):
        return self.kv.get(key, default)

    def kv_set(self, key, value):
        self.kv[key] = value


class FakeState:
    def current_activity(self):
        return {"activity": "在家看书", "place": "家"}


class FakeEvent:
    def __init__(self, private=True):
        self.unified_msg_origin = "umo"
        self._private = private

    def is_private_chat(self):
        return self._private

    def get_sender_id(self):
        return "u1"


class FakeImage:
    def __init__(self, data=b"IMG", delay=0):
        self.data = data
        self.delay = delay
        self.calls = []

    async def draw_for(self, umo, uid="", prompt=""):
        self.calls.append(prompt)
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.data


def make(**cfg):
    conf = {"image_share_enable": True, "image_share_probability": 1.0,
            "image_share_cooldown_minutes": 0, "image_share_daily_limit": 2,
            "image_share_timeout": 5}
    conf.update(cfg)
    plugin = object.__new__(amo_main.HumanCorePlugin)
    plugin.config = conf
    plugin.db = FakeDB()
    plugin.state = FakeState()
    plugin._last_reply_at = {}
    plugin.context = object()
    plugin.image = FakeImage()
    plugin._image_plugin = lambda: plugin.image
    plugin.sent = []

    async def fake_send(umo, data, text=""):
        plugin.sent.append(data)
        return True

    plugin._send_image_to_umo = fake_send
    return plugin


def run(coro):
    return asyncio.run(coro)


class ShareDecisionTests(unittest.TestCase):
    def test_disabled(self):
        self.assertIsNone(run(make(image_share_enable=False)._share_decision(FakeEvent())))

    def test_probability_zero(self):
        self.assertIsNone(run(make(image_share_probability=0)._share_decision(FakeEvent())))

    def test_group_skipped_when_private_only(self):
        p = make(image_share_private_only=True)
        self.assertIsNone(run(p._share_decision(FakeEvent(private=False))))

    def test_cooldown_blocks(self):
        p = make(image_share_cooldown_minutes=180)
        p.db.kv["image_share_last"] = amo_main.now_ts()
        self.assertIsNone(run(p._share_decision(FakeEvent())))

    def test_daily_limit_blocks(self):
        p = make(image_share_daily_limit=1)
        p.db.kv["image_share_day"] = {"date": amo_main.today_str(), "count": 1}
        self.assertIsNone(run(p._share_decision(FakeEvent())))

    def test_missing_plugin(self):
        p = make()
        p._image_plugin = lambda: None
        self.assertIsNone(run(p._share_decision(FakeEvent())))

    def test_decision_has_prompt_from_activity(self):
        p = make()
        decision = run(p._share_decision(FakeEvent()))
        self.assertIsNotNone(decision)
        self.assertIn("在家看书", decision["prompt"])
        self.assertEqual(decision["umo"], "umo")


class ShareTaskTests(unittest.TestCase):
    def test_task_draws_sends_and_records(self):
        p = make()
        decision = run(p._share_decision(FakeEvent()))
        run(p._share_image_task(decision))
        self.assertEqual(len(p.image.calls), 1)
        self.assertEqual(p.sent, [b"IMG"])
        self.assertEqual(p.db.kv["image_share_day"]["count"], 1)

    def test_task_timeout_does_not_send(self):
        p = make(image_share_timeout=1)
        p.image.delay = 5
        decision = run(p._share_decision(FakeEvent()))
        run(p._share_image_task(decision))
        self.assertEqual(p.sent, [])
        self.assertNotIn("image_share_last", p.db.kv)

    def test_task_handles_empty_image(self):
        p = make()
        p.image.data = None
        decision = run(p._share_decision(FakeEvent()))
        run(p._share_image_task(decision))
        self.assertEqual(p.sent, [])

    def test_maybe_share_does_not_block(self):
        """入口只做判断：出图慢也不能卡住调用方。"""
        p = make()
        p.image.delay = 5
        event = FakeEvent()

        async def scenario():
            started = asyncio.get_event_loop().time()
            await p._maybe_share_image(event)
            elapsed = asyncio.get_event_loop().time() - started
            await asyncio.sleep(0)
            return elapsed

        elapsed = asyncio.run(scenario())
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
