# -*- coding: utf-8 -*-
"""大肥鱼日记的落盘、目录和读取。"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import diary_engine  # noqa: E402


class DiaryEngineTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="amo-diary-")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_path_layout(self):
        day = date(2026, 11, 8)
        path = diary_engine.diary_path(self.root, day)
        self.assertTrue(path.endswith(os.path.join("2026", "11", "08", "我的日记2026年11月08日.txt")))
        self.assertEqual(diary_engine.title_for(day), "我的日记2026年11月08日")

    def test_write_and_read(self):
        day = date(2026, 11, 8)
        body = "今天他一直在修代码。\n我在旁边看着，觉得他很认真。"
        path = diary_engine.write_diary(self.root, day, body)
        self.assertTrue(os.path.isfile(path))
        text = diary_engine.read_diary(self.root, day)
        self.assertTrue(text.startswith("我的日记2026年11月08日\n\n"))
        self.assertIn("今天他一直在修代码。", text)

    def test_missing_read_returns_empty(self):
        self.assertEqual(diary_engine.read_diary(self.root, date(2000, 1, 1)), "")

    def test_tree_groups_by_year_month_day(self):
        diary_engine.write_diary(self.root, date(2026, 11, 8), "a")
        diary_engine.write_diary(self.root, date(2026, 11, 9), "b")
        diary_engine.write_diary(self.root, date(2026, 10, 1), "c")
        diary_engine.write_diary(self.root, date(2025, 12, 31), "d")
        tree = diary_engine.list_tree(self.root)
        self.assertEqual(tree["total"], 4)
        self.assertEqual(tree["latest"], "2026-11-09")
        self.assertEqual([y["year"] for y in tree["years"]], [2026, 2025])
        self.assertEqual([m["month"] for m in tree["years"][0]["months"]], [11, 10])
        self.assertEqual([d["date"] for d in tree["years"][0]["months"][0]["days"]],
                         ["2026-11-09", "2026-11-08"])

    def test_parse_day_variants(self):
        for value in ("2026-11-08", "2026/11/8", "2026年11月8日", date(2026, 11, 8)):
            self.assertEqual(diary_engine.parse_day(value), date(2026, 11, 8))
        self.assertIsNone(diary_engine.parse_day("不是日期"))


if __name__ == "__main__":
    unittest.main()
