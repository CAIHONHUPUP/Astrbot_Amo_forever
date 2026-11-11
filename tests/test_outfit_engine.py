# -*- coding: utf-8 -*-
"""日程穿搭：性别、场景、硬约束（不穿泳装出门）。"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import astrbot_stub  # noqa: E402

astrbot_stub.install()

import main as amo_main  # noqa: E402
import outfit_engine  # noqa: E402


class FakePlugin:
    def __init__(self, gender="自动", enable=True):
        self.conf = {"outfit_gender": gender, "outfit_enable": enable}

    def cfg_bool(self, name, default=False):
        return bool(self.conf.get(name, default))

    def cfg_str(self, name, default=""):
        return str(self.conf.get(name, default))


def engine(gender="自动"):
    return outfit_engine.OutfitEngine(FakePlugin(gender))


DAY = "2026-11-11"


class GenderTests(unittest.TestCase):
    def test_gender_from_persona(self):
        self.assertEqual(engine().gender("她是一个女孩，妻子"), "女")
        self.assertEqual(engine().gender("他是一个男生，少年"), "男")

    def test_gender_override(self):
        self.assertEqual(engine("男").gender("她是女孩"), "男")


class SceneTests(unittest.TestCase):
    def test_work_outfit_is_not_swim_or_pyjamas(self):
        items = [{"activity": "上班", "place": "公司", "category": "work"}]
        outfit = engine().assign(items, DAY)[0]["outfit"]
        self.assertNotIn("泳", outfit)
        self.assertNotIn("睡衣", outfit)
        self.assertNotIn("家居服", outfit)

    def test_beach_allows_swim(self):
        items = [{"activity": "游泳", "place": "海边", "category": "play"}]
        outfit = engine().assign(items, DAY)[0]["outfit"]
        self.assertIn("泳", outfit)

    def test_swim_never_outside_beach(self):
        self.assertEqual(engine()._safe("泳装外搭防晒衫", "work"), "")
        self.assertEqual(engine()._safe("纯棉睡衣", "out"), "")

    def test_male_pool_has_no_swimsuit_ashore(self):
        items = [{"activity": "上班", "place": "公司", "category": "work"}]
        outfit = engine("男").assign(items, DAY)[0]["outfit"]
        self.assertNotIn("裙", outfit)
        self.assertNotIn("泳", outfit)


class StabilityTests(unittest.TestCase):
    def test_same_segment_same_outfit(self):
        first = engine().assign(
            [{"activity": "上班", "place": "公司", "category": "work"}], DAY)[0]["outfit"]
        second = engine().assign(
            [{"activity": "上班", "place": "公司", "category": "work"}], DAY)[0]["outfit"]
        self.assertEqual(first, second)

    def test_home_place_words(self):
        items = [{"activity": "瘫在沙发上", "place": "南明区·小窝", "category": "rest"}]
        outfit = engine().assign(items, DAY)[0]["outfit"]
        self.assertTrue(any(word in outfit for word in ("家居", "睡衣", "T恤", "针织")))

    def test_same_scene_hours_share_outfit(self):
        """上班不同小时的活动文案不同，但衣服必须是同一套。"""
        items = [
            {"start": "09:00", "end": "10:00", "activity": "过接口清单", "place": "公司",
             "category": "work"},
            {"start": "10:00", "end": "11:00", "activity": "埋头改文档", "place": "公司",
             "category": "work"},
            {"start": "11:00", "end": "12:00", "activity": "跟产品掰扯需求", "place": "公司",
             "category": "work"},
        ]
        engine().assign(items, DAY)
        self.assertEqual(len({item["outfit"] for item in items}), 1)

    def test_one_outfit_while_out_then_homewear(self):
        items = [
            {"start": "09:00", "end": "12:00", "activity": "上班", "place": "公司",
             "category": "work"},
            {"start": "12:00", "end": "13:00", "activity": "吃午饭", "place": "公司附近",
             "category": "meal"},
            {"start": "19:00", "end": "21:00", "activity": "在家追剧", "place": "家",
             "category": "rest"},
            {"start": "23:00", "end": "24:00", "activity": "睡觉", "place": "家",
             "category": "sleep"},
        ]
        engine().assign(items, DAY)
        self.assertEqual(items[0]["outfit"], items[1]["outfit"])   # 外出同套
        self.assertNotEqual(items[0]["outfit"], items[2]["outfit"])  # 回家换家居服
        self.assertNotEqual(items[2]["outfit"], items[3]["outfit"])  # 睡觉换睡衣

    def test_normal_change_does_not_switch(self):
        items = [
            {"start": "09:00", "end": "18:00", "activity": "上班", "place": "公司",
             "category": "work"},
            {"start": "19:00", "end": "19:30", "activity": "回家换衣服", "place": "家",
             "category": "rest"},
            {"start": "20:00", "end": "21:00", "activity": "出门买东西", "place": "商场",
             "category": "play"},
        ]
        engine().assign(items, DAY)
        self.assertEqual(items[0]["outfit"], items[2]["outfit"])

    def test_emergency_change_switches(self):
        items = [
            {"start": "15:00", "end": "16:00", "activity": "上班", "place": "公司",
             "category": "work"},
            {"start": "16:00", "end": "16:30", "activity": "下大雨淋湿了，回家换衣服",
             "place": "家", "category": "rest"},
            {"start": "16:30", "end": "18:00", "activity": "回公司继续上班", "place": "公司",
             "category": "work"},
        ]
        engine().assign(items, DAY)
        self.assertNotEqual(items[0]["outfit"], items[2]["outfit"])

    def test_hourly_schedule_keeps_outfit(self):
        items = [
            {"start": "09:00", "end": "18:00", "activity": "上班", "place": "公司",
             "category": "work"},
            {"start": "20:00", "end": "22:00", "activity": "在家追剧", "place": "家",
             "category": "rest"},
        ]
        engine().assign(items, DAY)
        hourly = amo_main.HumanState._hourly_schedule(items)
        work_hours = [item for item in hourly if item["activity"] == "上班"]
        self.assertTrue(work_hours)
        self.assertTrue(all(item.get("outfit") for item in work_hours))
        self.assertEqual(len({item["outfit"] for item in work_hours}), 1)

    def test_disabled_engine_leaves_items_alone(self):
        items = [{"activity": "上班", "place": "公司", "category": "work"}]
        outfit_engine.OutfitEngine(FakePlugin(enable=False)).assign(items, DAY)
        self.assertNotIn("outfit", items[0])


if __name__ == "__main__":
    unittest.main()
