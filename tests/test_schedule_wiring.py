# -*- coding: utf-8 -*-
"""日程改动的接线测试：日子类型 → 骨架、按用户的话改日程、/日程 文本。

这些是"逻辑对了但没接上"的高发区：day_types / schedule_change 的纯函数测试
过了，不代表插件里真的用上了（之前就出现过 self.schedule 挂错对象、
外出日时间传成整数、schedule_text_of 挂错类这类问题）。
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import astrbot_stub  # noqa: E402

astrbot_stub.install()

import amo_schedule as AS  # noqa: E402
import schedule_engine as SE  # noqa: E402
from amo_db import AmoDB  # noqa: E402
from amo_human_state import HumanState  # noqa: E402
from amo_shared import _now, today_str  # noqa: E402


class _FakePlugin:
    persona_name = "大肥鱼"

    def __init__(self, **config):
        self.config = dict(config)

    def cfg(self, key, default=None):
        value = self.config.get(key, default)
        return default if value is None else value

    def cfg_list(self, key, default=None):
        value = self.cfg(key, [] if default is None else default)
        return value if isinstance(value, list) else []

    def cfg_str(self, key, default=""):
        return str(self.config.get(key, default))

    def cfg_bool(self, key, default=False):
        return bool(self.config.get(key, default))

    def cfg_int(self, key, default=0):
        return int(self.config.get(key, default))

    def cfg_float(self, key, default=0.0):
        return float(self.config.get(key, default))


class _FakeState:
    def __init__(self):
        self.p = _FakePlugin()


def _ctx(**over):
    ctx = {
        "home": "家",
        "workplace": "公司",
        "city": "东莞",
        "car": "",
        "scenic": {"name": "松山湖"},
        "good_weather": True,
        "meta": {"rest": False, "label": "周末"},
        "weather": {"temp": 22, "text": "晴"},
        "mood": {},
        "health": {"sick": False, "status": "健康"},
        "period": {},
        "yesterday": {},
        "event": {"kind": "none"},
        "day_type": {"id": "outing", "name": "外出日", "guide": "出门玩一整天"},
        "profile": {},
        "world": {},
        "location": "东莞",
    }
    ctx.update(over)
    return ctx


class OutingSkeletonTests(unittest.TestCase):
    def setUp(self):
        self.engine = SE.ScheduleEngine(_FakeState())

    def test_outing_is_hourly_and_really_goes_out(self):
        items = self.engine.build_skeleton(_ctx())
        self.assertEqual(len(items), 24)
        self.assertEqual(items[0]["start"], "00:00")
        self.assertEqual(items[-1]["end"], "24:00")
        for index, item in enumerate(items):
            self.assertEqual(item["start"], "%02d:00" % index, item)
            self.assertEqual(item["end"], "24:00" if index == 23 else "%02d:00" % (index + 1))
        activities = [str(item.get("activity") or "") for item in items]
        self.assertIn("起床", activities[8])
        self.assertTrue(any("逛" in text for text in activities), activities)
        self.assertFalse(any("赶去" in text for text in activities), activities)
        zones = {str(item.get("zone") or "") for item in items}
        self.assertTrue(zones <= {"home", "road", "scenic", "mall", "restaurant"}, zones)

    def test_bad_weather_falls_back_to_rest(self):
        items = self.engine.build_skeleton(_ctx(good_weather=False))
        activities = [str(item.get("activity") or "") for item in items]
        self.assertFalse(any("慢慢逛" in text for text in activities), activities)

    def test_sick_falls_back_to_rest(self):
        items = self.engine.build_skeleton(_ctx(health={"sick": True, "status": "生病"}))
        activities = [str(item.get("activity") or "") for item in items]
        self.assertFalse(any("慢慢逛" in text for text in activities), activities)

    def test_overtime_day_type_keeps_her_late(self):
        items = self.engine.build_skeleton(_ctx(
            day_type={"id": "overtime", "name": "加班日", "guide": ""},
        ))
        # 18:00 还走不了、19:00 在公司吃外卖，20:00 才收尾
        self.assertIn("还没", items[18]["activity"])
        self.assertIn("外卖", items[19]["activity"])
        self.assertEqual(items[21]["activity"], "下班回家")


class _Event:
    def __init__(self, text, private=True):
        self.message_str = text
        self._private = private

    def is_private_chat(self):
        return self._private

    def get_sender_id(self):
        return "10001"


class _DB:
    def __init__(self):
        self.calls = 0
        self.kv = {}
        self.saved = {}

    def kv_get(self, key, default=None):
        return self.kv.get(key, default)

    def kv_set(self, key, value):
        self.kv[key] = value

    def get_schedule(self, day):
        return self.saved.get(day, [])

    def save_schedule(self, day, items):
        self.calls += 1
        self.saved[day] = items


class _SchedulePlugin(AS.ScheduleMixin):
    def __init__(self):
        self.db = _DB()
        self.state = types.SimpleNamespace(schedule={})
        self.gift = None
        self.config = {"schedule_change_enabled": True, "schedule_change_owner_ids": ""}

    def cfg_bool(self, key, default=False):
        return bool(self.config.get(key, default))

    def cfg_str(self, key, default=""):
        return str(self.config.get(key, default))

    def _canonical_uid(self, event):
        return event.get_sender_id()


class ScheduleChangeWiringTests(unittest.TestCase):
    def _items(self):
        hour = _now().hour
        return [
            {"start": "%02d:00" % hour, "end": "24:00", "activity": "上班", "place": "公司",
             "category": "commute", "zone": "road"},
        ]

    def test_owner_private_message_rewrites_schedule(self):
        plugin = _SchedulePlugin()
        day = today_str()
        plugin.state.schedule[day] = self._items()
        asyncio.run(plugin._apply_user_schedule_change(_Event("我来接你"), "我来接你"))
        self.assertEqual(plugin.db.calls, 1)
        self.assertTrue(any("来接我" in item["activity"] for item in plugin.db.saved[day]))
        self.assertEqual(plugin.state.schedule[day][0]["start"], "%02d:00" % _now().hour)

    def test_group_message_is_ignored(self):
        plugin = _SchedulePlugin()
        plugin.state.schedule[today_str()] = self._items()
        asyncio.run(plugin._apply_user_schedule_change(_Event("我来接你", private=False), "我来接你"))
        self.assertEqual(plugin.db.calls, 0)

    def test_disabled_config_blocks_change(self):
        plugin = _SchedulePlugin()
        plugin.config["schedule_change_enabled"] = False
        plugin.state.schedule[today_str()] = self._items()
        asyncio.run(plugin._apply_user_schedule_change(_Event("我来接你"), "我来接你"))
        self.assertEqual(plugin.db.calls, 0)

    def test_owner_ids_filter(self):
        plugin = _SchedulePlugin()
        plugin.config["schedule_change_owner_ids"] = "99999"
        plugin.state.schedule[today_str()] = self._items()
        asyncio.run(plugin._apply_user_schedule_change(_Event("我来接你"), "我来接你"))
        self.assertEqual(plugin.db.calls, 0)


class EnrichPromptTests(unittest.TestCase):
    def test_day_type_guide_reaches_the_prompt(self):
        class _LLM:
            prompt = ""

            async def chat_raw(self, umo, system, prompt):
                self.prompt = prompt
                return "[" + ",".join(['"改写的活动"'] * 24) + "]"

        engine = SE.ScheduleEngine(_FakeState())
        items = [
            {"start": "%02d:00" % hour, "end": "24:00" if hour == 23 else "%02d:00" % (hour + 1),
             "activity": "活动%d" % hour, "place": "家", "category": "rest", "zone": "home"}
            for hour in range(24)
        ]
        llm = _LLM()
        out = asyncio.run(engine.enrich("umo", _ctx(day="2026-11-14"), items, llm))
        self.assertIn("今天是「外出日」", llm.prompt)
        self.assertIn("出门玩一整天", llm.prompt)
        self.assertEqual(len(out), 24)


class ScheduleTextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="amo-sched-text-")
        self._saved = {}
        for name in ("astrbot.core.utils", "astrbot.core.utils.astrbot_path"):
            self._saved[name] = sys.modules.get(name)
            module = types.ModuleType(name)
            module.__path__ = []
            sys.modules[name] = module
        path_module = types.ModuleType("astrbot.core.utils.astrbot_path")
        path_module.get_astrbot_data_path = lambda: self.tmp
        sys.modules["astrbot.core.utils.astrbot_path"] = path_module
        plugin = _FakePlugin()
        plugin.db = AmoDB(self.tmp)
        plugin.db.init()
        plugin.bot_name = "大肥鱼"
        plugin._reload_config_if_changed = lambda: None
        plugin._sync_weather_city_config = lambda: None
        self.plugin = plugin
        self.state = HumanState(plugin)

    def tearDown(self):
        try:
            self.plugin.db.conn.close()
        except Exception:
            pass
        for name, module in self._saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def test_schedule_text_uses_day_type_and_items(self):
        day = "2026-11-14"
        self.state.schedule[day] = [
            {"start": "10:00", "end": "11:00", "activity": "在松山湖慢慢逛", "place": "松山湖"},
            {"start": "11:00", "end": "12:00", "activity": "找店吃饭", "place": "松山湖附近"},
        ]
        self.plugin.db.kv_set("day_types", {day: {"id": "outing", "name": "外出日", "guide": ""}})
        text = self.state.schedule_text_of(day)
        self.assertIn("今天是外出日", text)
        self.assertIn("慢慢逛", text)
        self.assertIn("找店吃饭", text)

    def test_schedule_text_missing_day(self):
        self.assertEqual(self.state.schedule_text_of("2026-01-01"), "那天还没有安排。")

    def test_day_types_config_is_read(self):
        self.plugin.config["schedule_day_types"] = [
            {"id": "x", "name": "特例", "enabled": True, "weight": 1, "scope": "any", "guide": ""},
        ]
        types = self.state._day_types()
        self.assertEqual([item["id"] for item in types], ["x"])

    def test_day_type_is_cached_per_day(self):
        day = "2026-11-14"
        first = self.state._today_day_type(day)
        store = self.plugin.db.kv_get("day_types") or {}
        self.assertIn(day, store)
        # 中途改权重也不会让当天换类型（否则会和已经生成的日程对不上）
        self.plugin.config["schedule_day_types"] = [
            {"id": "y", "name": "改过的", "enabled": True, "weight": 1, "scope": "any", "guide": ""},
        ]
        second = self.state._today_day_type(day)
        self.assertEqual(first["id"], second["id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
