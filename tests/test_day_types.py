"""day_types / schedule_change 的单元测试：不依赖 AstrBot，直接跑这两个模块。"""
import datetime
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import day_types as DT
import schedule_change as SC


class DayTypeTests(unittest.TestCase):
    def test_defaults_load(self):
        types = DT.normalize_day_types(None)
        self.assertGreaterEqual(len(types), 6)
        names = [t["name"] for t in types]
        for want in ("上班日", "休息日", "外出日", "宅家日", "加班日", "摸鱼日"):
            self.assertIn(want, names)

    def test_weekend_only_weekend_types(self):
        types = DT.normalize_day_types(None)
        for seed in ("2026-11-14", "2026-11-15", "2026-11-21"):
            picked = DT.pick_day_type(types, True, seed)
            self.assertIn(picked["scope"], ("weekend", "any"))

    def test_weekday_excludes_weekend_types(self):
        types = DT.normalize_day_types(None)
        for seed in ("2026-11-11", "2026-11-12", "2026-11-13"):
            picked = DT.pick_day_type(types, False, seed)
            self.assertIn(picked["scope"], ("weekday", "any"))

    def test_same_seed_same_result(self):
        types = DT.normalize_day_types(None)
        a = DT.pick_day_type(types, True, "2026-11-14")
        b = DT.pick_day_type(types, True, "2026-11-14")
        self.assertEqual(a["id"], b["id"])

    def test_disabled_type_never_picked(self):
        types = DT.normalize_day_types([
            {"id": "only", "name": "唯一", "enabled": True, "weight": 1, "scope": "any"},
            {"id": "off", "name": "关掉的", "enabled": False, "weight": 99, "scope": "any"},
        ])
        for seed in ("a", "b", "c", "d", "e"):
            self.assertEqual(DT.pick_day_type(types, False, seed)["id"], "only")

    def test_all_disabled_falls_back(self):
        types = DT.normalize_day_types([
            {"id": "off", "name": "关掉的", "enabled": False, "weight": 1, "scope": "any"},
        ])
        picked = DT.pick_day_type(types, False, "x")
        self.assertEqual(picked["id"], "workday")

    def test_bad_config_falls_back(self):
        for raw in ("不是列表", [None, 3, "x"], [{"weight": 5}], []):
            types = DT.normalize_day_types(raw)
            self.assertGreaterEqual(len(types), 6, raw)
            self.assertTrue(all(t["id"] and t["name"] for t in types))

    def test_template_key_is_ignored(self):
        types = DT.normalize_day_types([
            {"__template_key": "day_type", "id": "a", "name": "甲", "weight": 1,
             "scope": "any", "enabled": True, "guide": "随手"},
        ])
        self.assertEqual(types[0]["id"], "a")
        self.assertNotIn("__template_key", types[0])


class ScheduleChangeTests(unittest.TestCase):
    NOW = datetime.datetime(2026, 11, 10, 18, 10)

    def _items(self):
        return [
            {"start": "17:00", "end": "18:00", "activity": "上班", "place": "公司",
             "category": "work", "zone": "office"},
            {"start": "18:00", "end": "19:00", "activity": "下班通勤", "place": "路上",
             "category": "commute", "zone": "road"},
            {"start": "19:00", "end": "20:00", "activity": "吃晚饭", "place": "家",
             "category": "meal", "zone": "home"},
            {"start": "20:00", "end": "22:00", "activity": "刷手机", "place": "家",
             "category": "rest", "zone": "home"},
            {"start": "22:00", "end": "24:00", "activity": "睡觉", "place": "家",
             "category": "sleep", "zone": "home"},
        ]

    def test_detect_pickup(self):
        change = SC.detect_schedule_change("我下班来接你")
        self.assertIsNotNone(change)
        self.assertIn("来接我", change["activity"])

    def test_detect_reverse_pickup(self):
        change = SC.detect_schedule_change("你来接我")
        self.assertIsNotNone(change)
        self.assertIn("我去接他", change["activity"])

    def test_detect_sleep(self):
        change = SC.detect_schedule_change("一起睡吧")
        self.assertEqual(change["category"], "sleep")

    def test_negated_sentence_is_ignored(self):
        self.assertIsNone(SC.detect_schedule_change("别来接我"))
        self.assertIsNone(SC.detect_schedule_change("不想去吃"))
        self.assertIsNone(SC.detect_schedule_change("不用早点睡"))

    def test_no_match_chat(self):
        self.assertIsNone(SC.detect_schedule_change("今天天气不错啊"))

    def test_apply_rewrites_current_slot(self):
        items = self._items()
        out = SC.apply_change(items, SC.detect_schedule_change("来接我"), self.NOW)
        # 18:10 正处在下班通勤段 → 改这一段，时间不拆碎（拆碎会破坏整点日程）
        self.assertEqual(out[1]["start"], "18:00")
        self.assertIn("来接我", out[1]["activity"])
        self.assertEqual(out[2]["activity"], "吃晚饭")

    def test_apply_meal_anchors_to_next_meal(self):
        items = self._items()
        now = datetime.datetime(2026, 11, 10, 10, 0)
        out = SC.apply_change(items, SC.detect_schedule_change("晚上一起出去吃"), now)
        self.assertEqual(out[1]["activity"], "下班通勤")
        self.assertIn("出去吃饭", out[2]["activity"])

    def test_apply_does_not_mutate_input(self):
        items = self._items()
        before = [dict(x) for x in items]
        SC.apply_change(items, SC.detect_schedule_change("来接我"), self.NOW)
        self.assertEqual(items, before)

    def test_apply_sleep_merges_night(self):
        items = self._items()
        now = datetime.datetime(2026, 11, 10, 21, 30)
        out = SC.apply_change(items, SC.detect_schedule_change("该睡了"), now)
        self.assertEqual(out[3]["category"], "sleep")
        self.assertEqual(out[3]["activity"], "上床睡觉")
        self.assertEqual(out[4]["activity"], "睡觉")

    def test_sleep_is_ignored_in_daytime(self):
        items = self._items()
        now = datetime.datetime(2026, 11, 10, 15, 0)
        out = SC.apply_change(items, SC.detect_schedule_change("早点睡"), now)
        self.assertEqual(out, items)

    def test_does_not_wake_up_sleeping_target(self):
        items = self._items()
        now = datetime.datetime(2026, 11, 10, 23, 0)
        out = SC.apply_change(items, SC.detect_schedule_change("去吃点东西"), now)
        self.assertEqual(out, items)

    def test_idempotent(self):
        items = self._items()
        once = SC.apply_change(items, SC.detect_schedule_change("来接我"), self.NOW)
        twice = SC.apply_change(once, SC.detect_schedule_change("来接我"), self.NOW)
        self.assertEqual(once, twice)

    def test_apply_empty_items(self):
        self.assertEqual(SC.apply_change([], SC.detect_schedule_change("睡吧"), self.NOW), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
