# -*- coding: utf-8 -*-
"""主动分享生图：低频、可关、有冷却和日限。"""

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
        self.sent = []

    def is_private_chat(self):
        return self._private

    def get_sender_id(self):
        return "u1"

    async def send(self, chain):
        self.sent.append(chain)


class FakeImage:
    def __init__(self, data=b"IMG"):
        self.data = data
        self.calls = []

    async def draw_for(self, umo, uid="", prompt=""):
        self.calls.append(prompt)
        return self.data


def make(**cfg):
    conf = {"image_share_enable": True, "image_share_probability": 1.0,
            "image_share_cooldown_minutes": 0, "image_share_daily_limit": 2}
    conf.update(cfg)
    plugin = object.__new__(amo_main.HumanCorePlugin)
    plugin.config = conf
    plugin.db = FakeDB()
    plugin.state = FakeState()
    plugin._last_reply_at = {}
    plugin.context = object()
    plugin.image = FakeImage()
    plugin._image_plugin = lambda: plugin.image

    async def fake_send(event, data, text=""):
        event.sent.append(data)
        return True

    plugin._send_image_now = fake_send
    return plugin


def run(coro):
    return asyncio.run(coro)


class ImageShareTests(unittest.TestCase):
    def test_disabled_does_nothing(self):
        p = make(image_share_enable=False)
        ev = FakeEvent()
        run(p._maybe_share_image(ev))
        self.assertEqual(p.image.calls, [])
        self.assertEqual(ev.sent, [])

    def test_probability_zero_does_nothing(self):
        p = make(image_share_probability=0)
        run(p._maybe_share_image(FakeEvent()))
        self.assertEqual(p.image.calls, [])

    def test_shares_and_records_quota(self):
        p = make()
        ev = FakeEvent()
        run(p._maybe_share_image(ev))
        self.assertEqual(len(p.image.calls), 1)
        self.assertEqual(len(ev.sent), 1)
        self.assertEqual(p.db.kv["image_share_day"]["count"], 1)

    def test_prompt_uses_current_activity(self):
        p = make()
        self.assertIn("在家看书", p._image_share_prompt())
        self.assertIn("家", p._image_share_prompt())

    def test_group_skipped_when_private_only(self):
        p = make(image_share_private_only=True)
        run(p._maybe_share_image(FakeEvent(private=False)))
        self.assertEqual(p.image.calls, [])

    def test_cooldown_blocks_second_share(self):
        p = make(image_share_cooldown_minutes=180)
        run(p._maybe_share_image(FakeEvent()))
        run(p._maybe_share_image(FakeEvent()))
        self.assertEqual(len(p.image.calls), 1)

    def test_daily_limit_blocks(self):
        p = make(image_share_daily_limit=1)
        run(p._maybe_share_image(FakeEvent()))
        run(p._maybe_share_image(FakeEvent()))
        self.assertEqual(len(p.image.calls), 1)

    def test_missing_plugin_is_noop(self):
        p = make()
        p._image_plugin = lambda: None
        run(p._maybe_share_image(FakeEvent()))
        self.assertEqual(p.db.kv, {})


if __name__ == "__main__":
    unittest.main()
