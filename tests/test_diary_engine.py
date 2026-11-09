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

    def test_copy_folder_to_new_root_keeps_dates(self):
        diary_engine.write_diary(self.root, date(2026, 11, 8), "a")
        diary_engine.write_diary(self.root, date(2025, 12, 31), "b")
        new_root = tempfile.mkdtemp(prefix="amo-diary-copy-")
        try:
            shutil.copytree(self.root, new_root, dirs_exist_ok=True)
            tree = diary_engine.list_tree(new_root)
            self.assertEqual(tree["total"], 2)
            self.assertEqual(tree["latest"], "2026-11-08")
            self.assertEqual([y["year"] for y in tree["years"]], [2026, 2025])
            self.assertIn("a", diary_engine.read_diary(new_root, date(2026, 11, 8)))
        finally:
            shutil.rmtree(new_root, ignore_errors=True)

    def test_renamed_file_still_readable_by_folder_date(self):
        path = diary_engine.write_diary(self.root, date(2026, 11, 8), "随手记的内容")
        os.rename(path, os.path.join(os.path.dirname(path), "随手记.txt"))
        tree = diary_engine.list_tree(self.root)
        self.assertEqual(tree["total"], 1)
        self.assertEqual(tree["years"][0]["months"][0]["days"][0]["date"], "2026-11-08")
        self.assertIn("随手记的内容", diary_engine.read_diary(self.root, date(2026, 11, 8)))

    def test_build_prompt_grounds_in_schedule(self):
        prompt = diary_engine.build_prompt(
            date(2026, 11, 8),
            ["他：我在修 bug", "我：好"],
            ["13:00 在工位写报告", "19:30 在家煮番茄蛋汤"],
        )
        self.assertIn("2026年11月08日", prompt)
        self.assertIn("13:00 在工位写报告", prompt)
        self.assertIn("他：我在修 bug", prompt)
        self.assertIn("不许编", prompt)
        self.assertIn("骨架", prompt)

    def test_build_prompt_handles_empty_material(self):
        prompt = diary_engine.build_prompt(date(2026, 11, 8), [], [])
        self.assertIn("这天没怎么聊", prompt)
        self.assertIn("没有小日记", prompt)


if __name__ == "__main__":
    unittest.main()
