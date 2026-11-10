# -*- coding: utf-8 -*-
"""引用回复的跨平台规则：私聊永不引用，群聊才按人数 + 概率。"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import astrbot_stub  # noqa: E402

astrbot_stub.install()

from main import HumanCorePlugin  # noqa: E402

QQ_PRIVATE = "大肥鱼:FriendMessage:302578963"
LARK_PRIVATE = "lark:FriendMessage:ou_cec66ea605ad17f62632fb044bc5f6ac"
QQ_GROUP = "aiocqhttp:GroupMessage:123456"
LARK_GROUP = "lark:GroupMessage:oc_abc"


class FakeQuote:
    def __init__(self, allow=True):
        self.allow = allow

    def _should_quote_group(self, umo):
        return self.allow


class QuoteAllowedTests(unittest.TestCase):
    def test_private_never_quotes_on_any_platform(self):
        for umo in (QQ_PRIVATE, LARK_PRIVATE, "webchat:FriendMessage:abc"):
            self.assertFalse(HumanCorePlugin._quote_allowed(FakeQuote(True), umo))

    def test_group_quotes_when_policy_says_yes(self):
        for umo in (QQ_GROUP, LARK_GROUP):
            self.assertTrue(HumanCorePlugin._quote_allowed(FakeQuote(True), umo))

    def test_group_skips_when_policy_says_no(self):
        self.assertFalse(HumanCorePlugin._quote_allowed(FakeQuote(False), QQ_GROUP))

    def test_explicit_private_flag_wins(self):
        self.assertFalse(HumanCorePlugin._quote_allowed(FakeQuote(True), QQ_GROUP, False))

    def test_unknown_umo_never_quotes(self):
        self.assertFalse(HumanCorePlugin._quote_allowed(FakeQuote(True), ""))


class QuoteProbabilityTests(unittest.TestCase):
    def _fake(self, count, threshold, prob):
        class Fake:
            def cfg_int(self, key, default=0):
                return threshold if key == "quote_group_speaker_threshold" else default

            def cfg_float(self, key, default=0.0):
                return prob if key == "quote_group_probability" else default

            def _group_speaker_count(self, umo):
                return count

        return Fake()

    def test_below_threshold_never_quotes(self):
        self.assertFalse(HumanCorePlugin._should_quote_group(self._fake(2, 3, 1.0), QQ_GROUP))

    def test_probability_zero_never_quotes(self):
        self.assertFalse(HumanCorePlugin._should_quote_group(self._fake(5, 3, 0.0), QQ_GROUP))

    def test_probability_one_always_quotes(self):
        self.assertTrue(HumanCorePlugin._should_quote_group(self._fake(5, 3, 1.0), LARK_GROUP))

    def test_threshold_zero_disables(self):
        self.assertFalse(HumanCorePlugin._should_quote_group(self._fake(5, 0, 1.0), QQ_GROUP))

    def test_probability_is_respected(self):
        import main as main_module

        original = main_module.random.random
        try:
            main_module.random.random = lambda: 0.3
            self.assertTrue(HumanCorePlugin._should_quote_group(self._fake(5, 3, 0.4), QQ_GROUP))
            main_module.random.random = lambda: 0.5
            self.assertFalse(HumanCorePlugin._should_quote_group(self._fake(5, 3, 0.4), QQ_GROUP))
        finally:
            main_module.random.random = original


if __name__ == "__main__":
    unittest.main()
