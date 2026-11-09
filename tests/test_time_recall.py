# -*- coding: utf-8 -*-
"""时间回看（识别时间问法 + 渲染提示词块）的单测。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from time_recall import looks_like_time_query, render_time_block  # noqa: E402


class DetectTests(unittest.TestCase):
    def test_time_questions(self):
        for text in (
            "昨天下午我们聊了啥",
            "前天你去干嘛了",
            "还记得上周三我说的事吗",
            "11月6号晚上10点我们在干嘛",
            "上个月你跟我说什么来着",
            "最近3天我提过什么",
            "六号晚上聊了啥",
        ):
            self.assertTrue(looks_like_time_query(text), text)

    def test_plain_questions_not_triggered(self):
        for text in (
            "今天天气怎么样",
            "你在干嘛",
            "帮我写个脚本",
            "晚饭吃什么",
            "",
        ):
            self.assertFalse(looks_like_time_query(text), text)


class RenderTests(unittest.TestCase):
    def test_block_has_label_and_lines(self):
        block = render_time_block("2026-11-08 13:00-18:00", [
            {"role": "user", "content": "在商场逛"},
            {"role": "bot", "content": "我陪你逛"},
        ])
        self.assertIn("2026-11-08 13:00-18:00", block)
        self.assertIn("· 他：在商场逛", block)
        self.assertIn("· 你：我陪你逛", block)

    def test_no_timestamp_per_line(self):
        block = render_time_block("昨天", [{"role": "user", "content": "吃了牛杂"}])
        self.assertNotRegex(block, r"· 他：\d{4}-\d{2}-\d{2}")

    def test_empty_messages(self):
        block = render_time_block("昨天下午", [])
        self.assertIn("没聊到什么", block)

    def test_limit(self):
        rows = [{"role": "user", "content": "第%d句" % i} for i in range(10)]
        block = render_time_block("昨天", rows, max_lines=3)
        self.assertEqual(block.count("· 他："), 3)


if __name__ == "__main__":
    unittest.main()
