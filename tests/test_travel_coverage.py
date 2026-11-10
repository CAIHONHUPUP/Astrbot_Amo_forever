# -*- coding: utf-8 -*-
"""amo_travel.TravelMixin 的覆盖率测试：跟去陪他 / 一个人旅游的状态机。

覆盖点（都是线上真可能走的路径，不是凑行数）：
- 城市跟随：问「要不要我过去」→ 同意出发（当天/次日）→ 被拒 → 回家；
- 独自旅游：问意愿（含一天问几次的上限）→ 出发 → 提醒 → 回来报平安 → 被叫回；
- 走 `_city_lookup` 真离线城市表，db 用假 kv 记录、state 用假对象记副作用；
- 时间/随机数全部固定传入（patch 模块级 `_now` / `now_ts` / `today_str` / `random`），
  不联网、不 sleep、不看真实时钟。
"""
from __future__ import annotations

import asyncio
import datetime
import os
import random
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import astrbot_stub  # noqa: E402

astrbot_stub.install()

import amo_travel  # noqa: E402
from amo_shared import _CITY_DEFAULT  # noqa: E402
from amo_travel import TravelMixin  # noqa: E402

UID = "302578963"
QQ = "aiocqhttp:FriendMessage:%s" % UID
NOW = datetime.datetime(2026, 11, 10, 9, 30)   # 固定「现在」= 2026-11-10 09:30
TODAY = "2026-11-10"
TS = 1_800_000_000.0


def patch_time(now=NOW, ts=TS, today=TODAY):
    """把模块级的时钟函数换成固定值（不依赖真实时间）。"""
    return mock.patch.multiple(
        amo_travel,
        _now=lambda: now,
        now_ts=lambda: ts,
        today_str=lambda: today,
    )


def patch_rng(seed=0):
    """固定随机数：同 seed 结果可复现。"""
    return mock.patch.object(amo_travel, "random", random.Random(seed))


class FakeDB:
    """只实现 travel 用到的 kv / profiles 两个口子。"""

    def __init__(self):
        self.store = {}
        self.writes = []

    def kv_get(self, key, default=None):
        return self.store.get(key, default)

    def kv_set(self, key, value):
        self.store[key] = value
        self.writes.append((key, value))

    def list_profiles(self, limit=1):
        return [{"uid": UID, "name": "他"}][:limit]


class FakeState:
    def __init__(self):
        self.mood = {"疲惫": 80, "郁闷": 50, "开心": 10}
        self.nudges = []
        self.follow_starts = []
        self.overlays = []

    def nudge(self, **kwargs):
        self.nudges.append(kwargs)

    def health_info(self):
        return {"status": "疲惫", "sick": False}

    def apply_follow_start(self, city, start_hour=9, spots=None, keep_past=True):
        self.follow_starts.append({
            "city": city, "start_hour": start_hour,
            "spots": [dict(x) for x in (spots or [])], "keep_past": keep_past,
        })

    def apply_travel_overlay(self, city=None):
        self.overlays.append(city)


class FakeEvent:
    def __init__(self, text, private=True):
        self.message_str = text
        self._private = private
        self.sent = []

    def is_private_chat(self):
        return self._private

    async def send(self, chain):
        self.sent.append(chain)
        return True


class FakePlugin(TravelMixin):
    """假 plugin：mixins 是真的，外部依赖（db/state/推送）是假的。"""

    def __init__(self, spots=None):
        self.db = FakeDB()
        self.state = FakeState()
        self.spots = spots if spots is not None else [
            {"city": "东莞", "name": "松山湖", "area": "", "projects": ["骑车", "看湖"]},
            {"city": "清远", "name": "古龙峡", "area": "清城", "projects": ["漂流", "玻璃桥"]},
            {"city": "杭州", "name": "西湖", "area": "", "projects": ["坐船", "逛苏堤"]},
        ]
        self.cfg_values = {
            "city_follow_enabled": True,
            "wander_enabled": True,
            "wander_prob_low": 0.85,
            "wander_prob_good": 0.15,
            "wander_ask_three_times": False,
        }
        self.memory_ok = True
        self.memories = []
        self.weather_cities = []
        self.sent = []
        self.marked = []
        self.pending = []
        self._last_umo = QQ

    # ---- 配置 ----
    def cfg(self, key, default=None):
        return self.cfg_values.get(key, default)

    def cfg_bool(self, key, default=False):
        value = self.cfg(key, default)
        return value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes")

    def cfg_float(self, key, default=0.0):
        try:
            return float(self.cfg(key, default))
        except (TypeError, ValueError):
            return default

    def cfg_str(self, key, default=""):
        value = self.cfg(key, default)
        return default if value is None else str(value)

    # ---- 外部依赖 ----
    def scenic_spots(self):
        return self.spots

    async def _write_memory_checked(self, uid, content, kind="", tier=1):
        if not self.memory_ok:
            return False
        self.memories.append((uid, content, kind, tier))
        return True

    async def _switch_weather_city(self, hit):
        self.weather_cities.append(hit)

    def _first_private_umo(self):
        return QQ

    async def _send_to_umo(self, umo, text):
        self.sent.append((umo, text))
        return True

    def _mark_bot_initiated(self, umo):
        self.marked.append(umo)

    def _set_proactive_pending(self, uid, kind, text, umo=""):
        self.pending.append((uid, kind, text, umo))


def make_plugin(spots=None):
    return FakePlugin(spots=spots)


class CityLookupTests(unittest.TestCase):
    def test_offline_table_resolves_city(self):
        plugin = make_plugin()
        hit = plugin._city_lookup("东莞")
        self.assertEqual(hit["id"], "101281601")
        self.assertEqual(hit["name"], _CITY_DEFAULT)

    def test_unknown_city_returns_none(self):
        plugin = make_plugin()
        self.assertIsNone(plugin._city_lookup("这个城市不存在啊"))

    def test_missing_module_returns_none(self):
        plugin = make_plugin()
        with mock.patch.object(FakePlugin, "_city_module", lambda self: None):
            self.assertIsNone(plugin._city_lookup("东莞"))


class FollowCityTests(unittest.TestCase):
    def follow(self, plugin, text, relation="相恋", private=True):
        event = FakeEvent(text, private=private)
        return asyncio.run(plugin._maybe_follow_city(event, UID, {"relation": relation}))

    def test_switch_off_returns_empty(self):
        plugin = make_plugin()
        plugin.cfg_values["city_follow_enabled"] = False
        with patch_time():
            self.assertEqual(self.follow(plugin, "我到杭州了"), "")
        self.assertEqual(plugin.db.store, {})

    def test_group_chat_is_ignored(self):
        plugin = make_plugin()
        with patch_time():
            self.assertEqual(self.follow(plugin, "我到杭州了", private=False), "")
        self.assertNotIn("he_city", plugin.db.store)

    def test_not_lover_is_ignored(self):
        plugin = make_plugin()
        with patch_time():
            self.assertEqual(self.follow(plugin, "我到杭州了", relation="普通"), "")
        self.assertNotIn("follow_offer", plugin.db.store)

    def test_invite_without_his_city_asks_where(self):
        plugin = make_plugin()
        with patch_time():
            text = self.follow(plugin, "你过来吧")
        self.assertIn("先问一句他在哪", text)
        self.assertNotIn("travel", plugin.db.store)

    def test_invite_when_both_in_home_city(self):
        plugin = make_plugin()
        plugin.db.kv_set("he_city", _CITY_DEFAULT)
        with patch_time():
            text = self.follow(plugin, "你过来吧")
        self.assertIn("我不就在你旁边", text)
        self.assertNotIn("travel", plugin.db.store)

    def test_invite_starts_following_trip_now(self):
        plugin = make_plugin()
        plugin.db.kv_set("he_city", "清远")
        plugin.db.kv_set("follow_declined", {"city": "清远", "day": "2026-11-09"})
        with patch_time(), patch_rng(0):
            text = self.follow(plugin, "你过来吧")
        trip = plugin.db.kv_get("travel")
        self.assertEqual(trip["city"], "清远")
        self.assertEqual(trip["phase"], "touring")
        self.assertEqual(trip["start_day"], TODAY)
        self.assertEqual(trip["start_hour"], 9)
        self.assertEqual(plugin.db.kv_get("his_city"), "清远")
        # 当天出发：立刻换天气 + 日程叠加，并写一条「坐车去陪他」的记忆
        self.assertEqual(plugin.weather_cities[0]["name"], "清远")
        self.assertEqual(plugin.state.follow_starts[0]["city"], "清远")
        self.assertIn("坐车去 清远 陪他", plugin.memories[0][1])
        self.assertIn("【出发】", text)
        self.assertIn("现在", text)
        # 景点来自离线表，只取前 4 个
        self.assertTrue(trip["spots"])
        self.assertLessEqual(len(trip["spots"]), 4)
        # 之前被拒的标记作废
        self.assertEqual(plugin.db.kv_get("follow_declined"), {})

    def test_follow_offer_agreed_starts_trip(self):
        plugin = make_plugin()
        plugin.db.kv_set("his_city", "东莞")
        plugin.db.kv_set("follow_offer", {
            "ts": TS - 10, "city": "清远", "id": "101281301", "tomorrow": False,
        })
        with patch_time(), patch_rng(0):
            text = self.follow(plugin, "好呀")
        trip = plugin.db.kv_get("travel")
        self.assertEqual(trip["city"], "清远")
        self.assertEqual(trip["id"], "101281301")
        self.assertEqual(plugin.db.kv_get("follow_offer"), {})
        self.assertIn("【出发】", text)

    def test_follow_offer_refused_makes_her_sad(self):
        plugin = make_plugin()
        plugin.db.kv_set("follow_offer", {
            "ts": TS - 10, "city": "清远", "id": "101281301", "tomorrow": False,
        })
        with patch_time(), patch_rng(0):
            text = self.follow(plugin, "你好好上班吧")
        self.assertIn("【被拒绝】", text)
        self.assertEqual(plugin.db.kv_get("follow_offer"), {})
        self.assertEqual(plugin.db.kv_get("follow_declined"),
                         {"city": "清远", "day": TODAY})
        self.assertEqual(plugin.state.nudges[0], {"委屈": 10, "郁闷": 8, "开心": -6})
        self.assertIn("他让她好好上班", plugin.memories[0][1])
        self.assertEqual(plugin.db.kv_get("follow_reject_log")[0]["city"], "清远")
        self.assertNotIn("travel", plugin.db.store)

    def test_expired_offer_is_cleared(self):
        plugin = make_plugin()
        plugin.db.kv_set("follow_offer", {
            "ts": TS - 3600, "city": "清远", "id": "101281301", "tomorrow": False,
        })
        with patch_time():
            self.assertEqual(self.follow(plugin, "今天好累"), "")
        self.assertEqual(plugin.db.kv_get("follow_offer"), {})

    def test_new_city_sets_offer_block(self):
        plugin = make_plugin()
        plugin.db.kv_set("his_city", "东莞")
        plugin.db.kv_set("wander_offer", {"ts": TS, "want": True, "city": "清远"})
        with patch_time(), patch_rng(0):
            text = self.follow(plugin, "我到杭州了")
        offer = plugin.db.kv_get("follow_offer")
        self.assertEqual(offer["city"], "杭州")
        self.assertEqual(offer["id"], "101210101")
        self.assertFalse(offer["tomorrow"])
        self.assertEqual(plugin.db.kv_get("he_city"), "杭州")
        self.assertEqual(plugin.db.kv_get("wander_offer"), {})
        self.assertIn("【他在 杭州】", text)

    def test_late_night_detection_waits_until_tomorrow(self):
        plugin = make_plugin()
        late = datetime.datetime(2026, 11, 10, 23, 10)
        with patch_time(now=late), patch_rng(0):
            text = self.follow(plugin, "我到杭州了")
        self.assertTrue(plugin.db.kv_get("follow_offer")["tomorrow"])
        self.assertIn("明天一早", text)

    def test_same_city_again_is_silent(self):
        plugin = make_plugin()
        plugin.db.kv_set("he_city", "杭州")
        plugin.db.kv_set("follow_declined", {"city": "杭州", "day": TODAY})
        with patch_time(), patch_rng(0):
            text = self.follow(plugin, "我到杭州了")
        self.assertIn("别再主动提这事", text)
        self.assertNotIn("follow_offer", plugin.db.store)

    def test_back_home_city_resets_offer(self):
        plugin = make_plugin()
        plugin.db.kv_set("he_city", "杭州")
        plugin.db.kv_set("follow_declined", {"city": "杭州", "day": TODAY})
        with patch_time(), patch_rng(0):
            text = self.follow(plugin, "我到东莞了")
        self.assertEqual(text, "")
        self.assertEqual(plugin.db.kv_get("he_city"), _CITY_DEFAULT)
        self.assertEqual(plugin.db.kv_get("follow_declined"), {})

    def test_return_home_ends_the_trip(self):
        plugin = make_plugin()
        plugin.db.kv_set("travel", {"city": "清远", "phase": "touring"})
        plugin.db.kv_set("his_city", "清远")
        plugin.db.kv_set("he_city", "清远")
        with patch_time(), patch_rng(0):
            text = self.follow(plugin, "回来吧，别玩了")
        self.assertIn("【回家】", text)
        self.assertEqual(plugin.db.kv_get("travel"), {})
        self.assertEqual(plugin.db.kv_get("his_city"), _CITY_DEFAULT)
        self.assertEqual(plugin.db.kv_get("he_city"), _CITY_DEFAULT)
        self.assertEqual(plugin.weather_cities[0]["name"], _CITY_DEFAULT)
        self.assertEqual(plugin.state.overlays[-1], _CITY_DEFAULT)
        self.assertEqual(plugin.memories[0][1], "她 2026-11-10 从 清远 回来了")
        self.assertTrue(plugin.db.kv_get("travel_log")[-1]["back"])

    def test_travelling_blocks_other_offers(self):
        plugin = make_plugin()
        plugin.db.kv_set("travel", {"city": "清远"})
        with patch_time():
            self.assertEqual(self.follow(plugin, "我到杭州了"), "")
        self.assertNotIn("follow_offer", plugin.db.store)
        plugin.db.kv_set("travel", {})
        plugin.db.kv_set("wander_trip", {"city": "杭州"})
        with patch_time():
            self.assertEqual(self.follow(plugin, "我到清远了"), "")
        self.assertNotIn("follow_offer", plugin.db.store)


class StartFollowTripTests(unittest.TestCase):
    def test_empty_city_clears_offer(self):
        plugin = make_plugin()
        plugin.db.kv_set("follow_offer", {"city": "清远"})
        with patch_time():
            self.assertEqual(asyncio.run(plugin._start_follow_trip(UID, {"city": " "})), "")
        self.assertEqual(plugin.db.kv_get("follow_offer"), {})
        self.assertNotIn("travel", plugin.db.store)

    def test_tomorrow_keeps_weather_and_schedule(self):
        plugin = make_plugin()
        plugin.db.kv_set("his_city", "东莞")
        with patch_time(), patch_rng(1):
            text = asyncio.run(plugin._start_follow_trip(
                UID, {"city": "清远", "id": "", "tomorrow": True}))
        trip = plugin.db.kv_get("travel")
        self.assertEqual(trip["phase"], "journey")
        self.assertEqual(trip["start_day"], "2026-11-11")
        self.assertEqual(trip["start_hour"], 9)
        self.assertEqual(plugin.weather_cities, [])
        self.assertEqual(plugin.state.follow_starts, [])
        self.assertIn("明天一早", text)
        # 出发日仍记进 travel_log
        self.assertTrue(plugin.db.kv_get("travel_log")[0]["journey"])
        self.assertEqual(plugin.db.kv_get("travel_log")[0]["hour"], "09:00")

    def test_memory_failure_is_swallowed(self):
        plugin = make_plugin()
        plugin.memory_ok = False
        with patch_time(), patch_rng(0):
            text = asyncio.run(plugin._start_follow_trip(
                UID, {"city": "清远", "id": "", "tomorrow": False}))
        self.assertEqual(plugin.memories, [])
        self.assertIn("清远", text)

    def test_log_is_capped_at_ten(self):
        plugin = make_plugin()
        plugin.db.kv_set("travel_log", [{"day": "2026-10-%02d" % i, "hour": "08:00",
                                         "city": "清远"} for i in range(1, 13)])
        with patch_time(), patch_rng(0):
            asyncio.run(plugin._start_follow_trip(
                UID, {"city": "清远", "id": "", "tomorrow": True}))
        self.assertEqual(len(plugin.db.kv_get("travel_log")), 10)
        self.assertEqual(plugin.db.kv_get("travel_log")[-1]["city"], "清远")


class WanderTests(unittest.TestCase):
    def wander(self, plugin, text):
        event = FakeEvent(text)
        return asyncio.run(plugin._maybe_wander(event, UID, {"relation": "相恋"}))

    def test_switch_off(self):
        plugin = make_plugin()
        plugin.cfg_values["wander_enabled"] = False
        with patch_time():
            self.assertEqual(self.wander(plugin, "你想出去玩吗"), "")

    def test_group_and_stranger_ignored(self):
        plugin = make_plugin()
        event = FakeEvent("你想出去玩吗", private=False)
        with patch_time():
            self.assertEqual(asyncio.run(plugin._maybe_wander(event, UID, {"relation": "相恋"})), "")
        event = FakeEvent("你想出去玩吗")
        with patch_time():
            self.assertEqual(asyncio.run(plugin._maybe_wander(event, UID, {"relation": "普通"})), "")

    def test_busy_with_follow_blocks_wander(self):
        plugin = make_plugin()
        plugin.db.kv_set("follow_offer", {"city": "清远"})
        with patch_time():
            self.assertEqual(self.wander(plugin, "你想出去玩吗"), "")

    def test_question_offers_a_city(self):
        plugin = make_plugin()
        with patch_time(), patch_rng(0):
            text = self.wander(plugin, "想不想出去玩")
        offer = plugin.db.kv_get("wander_offer")
        self.assertTrue(offer["want"])
        self.assertEqual(offer["city"], "清远")
        self.assertEqual(offer["ts"], TS)
        self.assertEqual(plugin.db.kv_get("wander_asked_day"), TODAY)
        self.assertEqual(plugin.db.kv_get("wander_ask_count"), 1)
        self.assertIn("【旅游提议】", text)
        self.assertIn("清远", text)
        # 1 天的行程也允许，但天数不会超 3
        self.assertTrue(offer["spots"])

    def test_question_declined_once_a_day(self):
        plugin = make_plugin()
        plugin.db.kv_set("wander_asked_day", TODAY)
        plugin.db.kv_set("wander_ask_count", 3)
        with patch_time(), patch_rng(0):
            text = self.wander(plugin, "你想出去玩吗")
        self.assertIn("今天已经问过 3 次了", text)
        self.assertEqual(plugin.db.kv_get("wander_ask_count"), 3)

    def test_question_without_want_keeps_her_home(self):
        plugin = make_plugin()
        with patch_time(), patch_rng(0), mock.patch.object(amo_travel, "_wander_want", lambda *a, **k: False):
            text = self.wander(plugin, "你想出去玩吗")
        offer = plugin.db.kv_get("wander_offer")
        self.assertEqual(offer, {"ts": TS, "want": False})
        self.assertIn("不想去", text)

    def test_agree_starts_solo_trip(self):
        plugin = make_plugin()
        plugin.db.kv_set("wander_offer", {
            "ts": TS, "want": True, "city": "清远",
            "spots": ["古龙峡"], "spot_rows": [{"name": "古龙峡", "city": "清远"}],
        })
        with patch_time(), patch_rng(0):
            text = self.wander(plugin, "好啊")
        trip = plugin.db.kv_get("wander_trip")
        self.assertEqual(trip["city"], "清远")
        self.assertEqual(trip["day"], TODAY)
        self.assertEqual(trip["phase"], "applied")
        self.assertEqual(trip["spots"], ["古龙峡"])
        self.assertIn("一个人去 清远 旅游", plugin.memories[0][1])
        self.assertIn("【出发】", text)

    def test_refuse_keeps_her_home(self):
        plugin = make_plugin()
        plugin.db.kv_set("wander_offer", {"ts": TS, "want": True, "city": "清远"})
        with patch_time(), patch_rng(0):
            text = self.wander(plugin, "算了，别去了")
        self.assertEqual(plugin.db.kv_get("wander_offer"), {})
        self.assertEqual(plugin.state.nudges[0], {"委屈": 5, "郁闷": 4})
        self.assertIn("【不出去了】", text)

    def test_trip_announcement_repeats_until_announced(self):
        plugin = make_plugin()
        plugin.db.kv_set("wander_trip", {
            "city": "清远", "day": TODAY, "return_day": TODAY,
            "spots": ["古龙峡"], "phase": "applied",
        })
        with patch_time():
            text = self.wander(plugin, "你在干嘛")
        self.assertIn("【独自旅行】", text)
        self.assertIn("第 1 天", text)

    def test_called_home_ends_solo_trip(self):
        plugin = make_plugin()
        plugin.db.kv_set("wander_trip", {"city": "清远", "day": TODAY})
        plugin.db.kv_set("his_city", "东莞")
        with patch_time(), patch_rng(0):
            text = self.wander(plugin, "早点回来吧")
        self.assertIn("【旅游】", text)
        self.assertEqual(plugin.db.kv_get("wander_trip"), {})
        self.assertEqual(plugin.memories[0][1], "她 2026-11-10 从 清远 旅游回来了")
        self.assertEqual(plugin.weather_cities[0]["name"], "东莞")
        self.assertEqual(plugin.state.overlays[-1], "东莞")

    def test_nothing_matches_returns_empty(self):
        plugin = make_plugin()
        with patch_time():
            self.assertEqual(self.wander(plugin, "今天上班好累"), "")


class StartSoloTripTests(unittest.TestCase):
    def test_empty_city_clears_offer(self):
        plugin = make_plugin()
        plugin.db.kv_set("wander_offer", {"want": True, "city": ""})
        with patch_time():
            self.assertEqual(asyncio.run(plugin._start_solo_trip(UID, {"city": ""})), "")
        self.assertEqual(plugin.db.kv_get("wander_offer"), {})

    def test_multi_day_trip_is_planned(self):
        plugin = make_plugin()
        with patch_time(), patch_rng(0):          # seed 0 → 3 天
            text = asyncio.run(plugin._start_solo_trip(UID, {
                "city": "清远", "spot_rows": [{"name": "古龙峡", "city": "清远"}],
            }))
        trip = plugin.db.kv_get("wander_trip")
        self.assertEqual(trip["days"], 3)
        self.assertEqual(trip["return_day"], "2026-11-12")
        self.assertEqual(trip["return_hour"], 12)
        self.assertEqual(trip["id"], "101281301")
        self.assertIn("玩 3 天", text)
        self.assertIn("第 3 天中午回来", text)
        self.assertEqual(plugin.weather_cities[0]["name"], "清远")
        self.assertEqual(plugin.state.overlays[-1], "清远")

    def test_late_start_waits_until_tomorrow(self):
        plugin = make_plugin()
        late = datetime.datetime(2026, 11, 10, 22, 40)
        with patch_time(now=late), patch_rng(1):   # seed 1 → 1 天
            text = asyncio.run(plugin._start_solo_trip(UID, {"city": "清远"}))
        trip = plugin.db.kv_get("wander_trip")
        self.assertEqual(trip["day"], "2026-11-11")
        self.assertEqual(trip["phase"], "planned")
        self.assertEqual(plugin.weather_cities, [])
        self.assertEqual(plugin.state.overlays, [])
        self.assertIn("明天", text)

    def test_evening_one_day_trip_becomes_two(self):
        plugin = make_plugin()
        evening = datetime.datetime(2026, 11, 10, 18, 10)
        with patch_time(now=evening), patch_rng(1):   # seed 1 → 1 天，傍晚出门改成 2 天
            asyncio.run(plugin._start_solo_trip(UID, {"city": "清远"}))
        trip = plugin.db.kv_get("wander_trip")
        self.assertEqual(trip["days"], 2)
        self.assertEqual(trip["return_day"], "2026-11-11")
        self.assertEqual(trip["return_hour"], 12)

    def test_log_is_capped_and_marked_solo(self):
        plugin = make_plugin()
        plugin.db.kv_set("travel_log", [{"day": "2026-10-01", "hour": "08:00", "city": "x"}] * 12)
        with patch_time(), patch_rng(0):
            asyncio.run(plugin._start_solo_trip(UID, {"city": "清远"}))
        log = plugin.db.kv_get("travel_log")
        self.assertEqual(len(log), 10)
        self.assertTrue(log[-1]["solo"])


class SoloReturnTests(unittest.TestCase):
    def trip(self, **kwargs):
        base = {
            "city": "清远", "day": "2026-11-09", "days": 2,
            "return_day": TODAY, "return_hour": 9, "phase": "applied",
        }
        base.update(kwargs)
        return base

    def test_no_trip_returns_quietly(self):
        plugin = make_plugin()
        with patch_time():
            asyncio.run(plugin._maybe_solo_return())
        self.assertEqual(plugin.sent, [])
        self.assertEqual(plugin.memories, [])

    def test_announced_trip_is_skipped(self):
        plugin = make_plugin()
        plugin.db.kv_set("wander_trip", self.trip(announced=True))
        with patch_time():
            asyncio.run(plugin._maybe_solo_return())
        self.assertEqual(plugin.sent, [])

    def test_other_day_is_skipped(self):
        plugin = make_plugin()
        plugin.db.kv_set("wander_trip", self.trip(return_day="2026-11-12"))
        with patch_time():
            asyncio.run(plugin._maybe_solo_return())
        self.assertEqual(plugin.sent, [])

    def test_before_return_hour_is_skipped(self):
        plugin = make_plugin()
        plugin.db.kv_set("wander_trip", self.trip(return_hour=21))
        with patch_time():
            asyncio.run(plugin._maybe_solo_return())
        self.assertEqual(plugin.sent, [])
        self.assertFalse(plugin.db.kv_get("wander_trip").get("announced"))

    def test_returns_home_and_reports(self):
        plugin = make_plugin()
        plugin.db.kv_set("wander_trip", self.trip())
        plugin.db.kv_set("his_city", "东莞")
        with patch_time(), patch_rng(0):
            asyncio.run(plugin._maybe_solo_return())
        self.assertEqual(len(plugin.sent), 1)
        self.assertEqual(plugin.sent[0][0], QQ)
        self.assertIn(plugin.sent[0][1], ("我回来啦，刚到家。", "到家啦，你在干嘛呢？",
                                          "我回来了，你吃饭了没？"))
        self.assertEqual(plugin.marked, [QQ])
        self.assertEqual(plugin.pending[0][:2], (UID, "travel_back"))
        self.assertEqual(plugin.memories[0][1], "她 2026-11-10 从 清远 旅游回来了")
        self.assertEqual(plugin.weather_cities[0]["name"], "东莞")
        self.assertEqual(plugin.state.overlays[-1], "东莞")
        self.assertTrue(plugin.db.kv_get("wander_trip")["announced"])
        self.assertTrue(plugin.db.kv_get("travel_log")[-1]["back"])

    def test_without_private_umo_still_writes_memory(self):
        plugin = make_plugin()
        plugin.db.kv_set("wander_trip", self.trip())
        # 没有任何私聊会话：_first_private_umo 空、_last_umo 又是群 → 不报平安
        plugin._first_private_umo = lambda: ""
        plugin._last_umo = "aiocqhttp:GroupMessage:123"
        with patch_time(), patch_rng(0):
            asyncio.run(plugin._maybe_solo_return())
        self.assertEqual(plugin.sent, [])
        self.assertEqual(len(plugin.memories), 1)


class EndSoloTripTests(unittest.TestCase):
    def test_no_trip_is_noop(self):
        plugin = make_plugin()
        with patch_time():
            asyncio.run(plugin._end_solo_trip(UID, "没在旅游"))
        self.assertEqual(plugin.memories, [])

    def test_clears_trip_and_goes_back_to_his_city(self):
        plugin = make_plugin()
        plugin.db.kv_set("wander_trip", {"city": "杭州", "day": TODAY})
        plugin.db.kv_set("his_city", "东莞")
        with patch_time(), patch_rng(0):
            asyncio.run(plugin._end_solo_trip(UID, "他让她回来"))
        self.assertEqual(plugin.db.kv_get("wander_trip"), {})
        self.assertEqual(plugin.memories[0][1], "她 2026-11-10 从 杭州 旅游回来了")
        entry = plugin.db.kv_get("travel_log")[-1]
        self.assertEqual(entry["city"], "杭州")
        self.assertTrue(entry["solo"] and entry["back"])
        self.assertEqual(plugin.weather_cities[0]["name"], "东莞")
        self.assertEqual(plugin.state.overlays[-1], "东莞")

    def test_memory_failure_does_not_break(self):
        plugin = make_plugin()
        plugin.memory_ok = False
        plugin.db.kv_set("wander_trip", {"city": "杭州", "day": TODAY})
        with patch_time(), patch_rng(0):
            asyncio.run(plugin._end_solo_trip(UID))
        self.assertEqual(plugin.db.kv_get("wander_trip"), {})
        self.assertEqual(plugin.state.overlays[-1], _CITY_DEFAULT)


if __name__ == "__main__":
    unittest.main()
