# -*- coding: utf-8 -*-
"""amo_schedule.ScheduleMixin 的覆盖率测试：日记 / 天气提醒 / 城市跟随配置。

覆盖点：
- 5.1.1 / 5.2.1 两次配置迁移（含幂等）；
- 每日日记：时间闸、防重、补写多天、失败重试、写盘落点；
- 天气提醒：一天两槽位（早上只判断、晚上才发）、试跑、平台回退、全失败重试；
- 天气查询上下文（缓存数据拼句）、城市跟随改配置、中文城市名回填。

时钟/随机全部固定：patch 模块级 `_now` / `now_ts` / `today_str`；
模型调用用假 LLM（`persona` / `chat` / `chat_raw` 都是本地字符串），不联网。
"""
from __future__ import annotations

import asyncio
import datetime
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import astrbot_stub  # noqa: E402

astrbot_stub.install()

import amo_schedule  # noqa: E402
from amo_db import AmoDB  # noqa: E402
from amo_schedule import ScheduleMixin  # noqa: E402

UID = "302578963"
QQ = "aiocqhttp:FriendMessage:%s" % UID
TODAY = "2026-11-10"
TS = 1_800_000_000.0
NOW = datetime.datetime(2026, 11, 10, 10, 30)


def patch_time(now=NOW, ts=TS, today=TODAY):
    return mock.patch.multiple(
        amo_schedule,
        _now=lambda: now,
        now_ts=lambda: ts,
        today_str=lambda: today,
    )


class FakeMem:
    """假的外部记忆插件（Astr_Amo_data）门面。"""

    def __init__(self, rows=None, exc=None):
        self.rows = rows or []
        self.exc = exc

    async def messages_between(self, *args):
        if self.exc:
            raise self.exc
        return self.rows


class FakeState:
    def __init__(self):
        self.weather = {}
        self.schedule_profile = {"city": "东莞"}
        self.forecast = []
        self.refresh_calls = []
        self.fetch_calls = []
        self.prompt_raises = False

    async def refresh_weather(self, force=False):
        self.refresh_calls.append(force)
        if self.weather is None:
            raise RuntimeError("接口挂了")
        return self.weather

    async def _fetch_qweather_daily(self, key, city, days, fresh=False):
        self.fetch_calls.append({"key": key, "city": city, "days": days, "fresh": fresh})
        return list(self.forecast)

    def snapshot(self):
        return {"activity": {"activity": "上班"}}

    def prompt_text(self, snap):
        if self.prompt_raises:
            raise RuntimeError("state 坏了")
        return "【状态】正在上班"


class FakeLLM:
    def __init__(self, chat="", chat_raw="", persona="你是大肥鱼"):
        self.chat_text = chat
        self.chat_raw_text = chat_raw
        self.persona_text = persona
        self.chat_calls = []
        self.raw_calls = []

    async def persona(self, umo):
        return self.persona_text

    async def chat(self, umo, system, prompt, limit=60):
        self.chat_calls.append({"umo": umo, "system": system, "prompt": prompt, "limit": limit})
        return self.chat_text

    async def chat_raw(self, umo, system, prompt):
        self.raw_calls.append({"umo": umo, "system": system, "prompt": prompt})
        return self.chat_raw_text


class FakeConfig(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.saved = 0
        self.save_error = None

    def save_config(self):
        if self.save_error:
            raise self.save_error
        self.saved += 1
        return True


class FakePlugin(ScheduleMixin):
    def __init__(self, tmp):
        self.tmp = tmp
        self.db = AmoDB(tmp)
        self.db.init()
        self.config = FakeConfig()
        self.cfg_values = {
            "diary_enabled": True,
            "diary_time": "10:00",
            "weather_city": "东莞",
            "weather_alert_enabled": True,
            "weather_alert_time": "20:00",
            "weather_alert_morning_time": "08:00",
            "weather_alert_temp_drop": 8,
            "hefeng_key": "key-123",
            "delay_min_minutes": 4,
            "delay_max_minutes": 18,
        }
        self.state = FakeState()
        self.llm = FakeLLM()
        self._last_umo = QQ
        self._running = True
        self._ready = True
        self._last_reply_at = {}
        self.recent = []
        self.sent = []
        self.composed = []
        self.spawned = []
        self.mem = None
        self._diary_data_root = lambda: tmp

    # ---- 配置 ----
    def cfg(self, key, default=None):
        return self.cfg_values.get(key, default)

    def cfg_bool(self, key, default=False):
        value = self.cfg(key, default)
        return value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes", "on")

    def cfg_int(self, key, default=0):
        try:
            return int(float(self.cfg(key, default)))
        except (TypeError, ValueError):
            return default

    def cfg_str(self, key, default=""):
        value = self.cfg(key, default)
        return default if value is None else str(value)

    # ---- 依赖 ----
    def _city_lookup(self, text):
        from amo_city_index import resolve_city
        return resolve_city(text)

    def _first_private_umo(self):
        return QQ

    def _recent(self, umo, limit=10):
        if isinstance(self.recent, Exception):
            raise self.recent
        return list(self.recent)[-limit:]

    def _data_mem(self):
        return self.mem

    def _data_bot_id(self):
        return "bot"

    async def _data_call(self, name, *args):
        method = getattr(self.mem, name, None)
        if method is None:
            raise AttributeError(name)
        return await method(*args)

    def _spawn(self, coro):
        self.spawned.append(coro)

    async def _compose_reply(self, event, text, snap, profile, *args, **kwargs):
        self.composed.append({"text": text, "note": kwargs.get("note")})
        if isinstance(self.compose_error, Exception):
            raise self.compose_error
        return self.compose_reply

    async def _send_to_umo(self, umo, text):
        self.sent.append((umo, text))
        return True

    compose_error = None
    compose_reply = "忙着呢，刚看到"


def make_plugin():
    tmp = tempfile.mkdtemp(prefix="amo-sched-")
    plugin = FakePlugin(tmp)
    plugin._tmp = tmp
    return plugin


class _FakeAsyncio:
    """替身 asyncio：sleep 立刻返回（或按需抛 CancelledError），不真等待。"""

    CancelledError = asyncio.CancelledError

    def __init__(self, cancel=False):
        self.cancel = cancel

    async def sleep(self, delay):
        if self.cancel:
            raise asyncio.CancelledError()
        return None


class MigrationTests(unittest.TestCase):
    def test_511_migration_clears_old_defaults(self):
        plugin = make_plugin()
        plugin.cfg_values.update({
            "schedule_city": "贵阳",
            "schedule_home": "观山湖区·小窝",
            "schedule_workplace": "公司（贵阳·观山湖区）",
            "schedule_car": "黑色奔驰C级",
            "weather_city": "贵阳",
        })
        plugin.config.update({"weather_city": "贵阳", "schedule_city": "贵阳"})
        plugin._migrate_schedule_defaults()
        self.assertEqual(plugin.config["schedule_city"], "")
        self.assertEqual(plugin.config["schedule_workplace"], "")
        self.assertEqual(plugin.config["weather_city"], "")
        self.assertEqual(plugin.config.saved, 1)
        self.assertTrue(plugin.db.kv_get("schedule_defaults_511"))

    def test_511_migration_keeps_custom_values(self):
        plugin = make_plugin()
        plugin.cfg_values.update({
            "schedule_city": "东莞",
            "schedule_home": "莞城·小窝",
            "weather_city": "101281601",
        })
        plugin.config.update({"weather_city": "101281601"})
        plugin._migrate_schedule_defaults()
        self.assertEqual(plugin.config["weather_city"], "101281601")
        self.assertEqual(plugin.config.saved, 0)
        self.assertTrue(plugin.db.kv_get("schedule_defaults_511"))

    def test_511_migration_is_idempotent(self):
        plugin = make_plugin()
        plugin.db.kv_set("schedule_defaults_511", True)
        plugin.cfg_values["schedule_city"] = "贵阳"
        plugin.config["schedule_city"] = "贵阳"
        plugin._migrate_schedule_defaults()
        self.assertEqual(plugin.config["schedule_city"], "贵阳")
        self.assertEqual(plugin.config.saved, 0)

    def test_511_migration_swallows_errors(self):
        plugin = make_plugin()
        original = plugin.db.kv_get
        plugin.db.kv_get = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db 挂了"))
        plugin._migrate_schedule_defaults()   # 不抛
        plugin.db.kv_get = original
        self.assertFalse(plugin.db.kv_get("schedule_defaults_511", False))

    def test_521_migration_clears_cached_diary(self):
        plugin = make_plugin()
        plugin.db.save_diary("2026-11-08", "08:00", "旧日记")
        plugin._migrate_diary_continuity()
        rows = plugin.db.conn.execute("SELECT COUNT(*) AS n FROM schedule_diary").fetchone()
        self.assertEqual(rows["n"], 0)
        self.assertTrue(plugin.db.kv_get("diary_continuity_521"))

    def test_521_migration_runs_once(self):
        plugin = make_plugin()
        plugin.db.kv_set("diary_continuity_521", True)
        plugin.db.save_diary("2026-11-08", "08:00", "新日记")
        plugin._migrate_diary_continuity()
        rows = plugin.db.conn.execute("SELECT COUNT(*) AS n FROM schedule_diary").fetchone()
        self.assertEqual(rows["n"], 1)


class DelayedReplyTests(unittest.TestCase):
    def make(self, **kwargs):
        plugin = make_plugin()
        plugin.event = types.SimpleNamespace(
            unified_msg_origin=QQ, message_str="在吗")
        return plugin

    def run_runner(self, plugin, fake=None):
        fake = fake or _FakeAsyncio()
        with mock.patch.object(amo_schedule, "asyncio", fake):
            asyncio.run(plugin.spawned.pop())

    def test_not_running_skips(self):
        plugin = self.make()
        plugin._running = False
        plugin._schedule_delayed_reply(plugin.event, {})
        self.run_runner(plugin)
        self.assertEqual(plugin.sent, [])

    def test_expired_because_replied(self):
        plugin = self.make()
        plugin._last_reply_at[QQ] = amo_schedule.now_ts() + 60
        plugin._schedule_delayed_reply(plugin.event, {})
        self.run_runner(plugin)
        self.assertEqual(plugin.composed, [])

    def test_expired_because_new_message(self):
        plugin = self.make()
        plugin.recent = [{"role": "user", "content": "新消息",
                          "created_at": amo_schedule.now_ts() + 60}]
        plugin._schedule_delayed_reply(plugin.event, {})
        self.run_runner(plugin)
        self.assertEqual(plugin.composed, [])

    def test_sends_after_delay(self):
        plugin = self.make()
        plugin._schedule_delayed_reply(plugin.event, {})
        self.assertEqual(len(plugin.spawned), 1)
        self.run_runner(plugin)
        self.assertEqual(plugin.composed[0]["text"], "在吗")
        self.assertIn("忙完", plugin.composed[0]["note"])
        self.assertEqual(plugin.sent, [(QQ, "忙着呢，刚看到")])

    def test_cancelled_is_quiet(self):
        plugin = self.make()
        plugin._schedule_delayed_reply(plugin.event, {})
        self.run_runner(plugin, _FakeAsyncio(cancel=True))
        self.assertEqual(plugin.sent, [])

    def test_compose_error_is_swallowed(self):
        plugin = self.make()
        plugin.compose_error = RuntimeError("模型挂了")
        plugin._schedule_delayed_reply(plugin.event, {})
        self.run_runner(plugin)
        self.assertEqual(plugin.sent, [])


class DiaryPathTests(unittest.TestCase):
    def test_data_root_uses_astrbot_data_path(self):
        plugin = make_plugin()
        base = types.ModuleType("astrbot.core.utils")
        base.__path__ = []
        leaf = types.ModuleType("astrbot.core.utils.astrbot_path")
        leaf.get_astrbot_data_path = lambda: plugin.tmp
        with mock.patch.dict(sys.modules, {
            "astrbot.core.utils": base,
            "astrbot.core.utils.astrbot_path": leaf,
        }):
            root = ScheduleMixin._diary_data_root(plugin)
        self.assertEqual(root, os.path.join(plugin.tmp, "plugin_data", "Astrbot_Amo_forever"))

    def test_diary_dir_default_and_relative(self):
        plugin = make_plugin()
        plugin.cfg_values["diary_dir"] = ""
        self.assertEqual(plugin._diary_dir(), os.path.join(plugin.tmp, "diary"))
        plugin.cfg_values["diary_dir"] = "日记"
        self.assertEqual(plugin._diary_dir(), os.path.join(plugin.tmp, "日记"))
        plugin.cfg_values["diary_dir"] = "D:\\\\old\\\\diary"
        self.assertEqual(plugin._diary_dir(), os.path.join(plugin.tmp, "diary"))

    def test_diary_clock_parsing(self):
        plugin = make_plugin()
        self.assertEqual(plugin._diary_clock(), (10, 0))
        plugin.cfg_values["diary_time"] = "7:5"
        self.assertEqual(plugin._diary_clock(), (7, 5))
        plugin.cfg_values["diary_time"] = "没填时间"
        self.assertEqual(plugin._diary_clock(), (10, 0))
        plugin.cfg_values["diary_time"] = "99:99"
        self.assertEqual(plugin._diary_clock(), (23, 59))


class DailyDiaryTests(unittest.TestCase):
    def seed_day(self, plugin, day="2026-11-09"):
        plugin.db.save_diary(day, "08:00", "起床洗漱，窗外在下小雨")
        plugin.db.save_diary(day, "12:00", "跟他一起点了外卖")
        plugin.llm.chat_raw_text = (
            "```\n我的日记\n今天他陪我吃了一整天，虽然下雨但心情很好，晚上一起看了剧。\n```"
        )

    def test_disabled_does_nothing(self):
        plugin = make_plugin()
        plugin.cfg_values["diary_enabled"] = False
        self.seed_day(plugin)
        with patch_time():
            asyncio.run(plugin._maybe_daily_diary())
        self.assertFalse(os.path.exists(os.path.join(plugin.tmp, "diary")))

    def test_before_diary_time_does_nothing(self):
        plugin = make_plugin()
        self.seed_day(plugin)
        early = datetime.datetime(2026, 11, 10, 9, 0)
        with patch_time(now=early):
            asyncio.run(plugin._maybe_daily_diary())
        self.assertEqual(plugin.llm.raw_calls, [])

    def test_busy_flag_does_nothing(self):
        plugin = make_plugin()
        self.seed_day(plugin)
        plugin._diary_writing = True
        with patch_time():
            asyncio.run(plugin._maybe_daily_diary())
        self.assertEqual(plugin.llm.raw_calls, [])

    def test_writes_yesterdays_diary(self):
        plugin = make_plugin()
        self.seed_day(plugin)
        with patch_time():
            asyncio.run(plugin._maybe_daily_diary())
        self.assertEqual(len(plugin.llm.raw_calls), 1)
        self.assertIn("起床洗漱", plugin.llm.raw_calls[0]["prompt"])
        path = plugin.db.kv_get("diary_written:2026-11-09")
        self.assertTrue(path and os.path.exists(path))
        with open(path, encoding="utf-8") as stream:
            body = stream.read()
        self.assertIn("今天他陪我吃了一整天", body)
        self.assertNotIn("```", body)          # 代码块围栏被剥掉
        self.assertIn("我的日记2026年11月09日", body)   # 文件自带日期标题
        self.assertNotIn("11月9日", body)       # 模型自己写的标题行被剥掉
        self.assertEqual(plugin.db.kv_get("diary_last_day"), "2026-11-09")

    def test_already_written_is_skipped(self):
        plugin = make_plugin()
        self.seed_day(plugin)
        plugin.db.kv_set("diary_written:2026-11-09", "x.md")
        plugin.db.kv_set("diary_last_day", "2026-11-09")
        with patch_time():
            asyncio.run(plugin._maybe_daily_diary())
        self.assertEqual(plugin.llm.raw_calls, [])

    def test_recent_attempt_backs_off(self):
        plugin = make_plugin()
        self.seed_day(plugin)
        plugin.db.kv_set("diary_attempt:2026-11-09", TS)   # 30 分钟内的重试要跳过
        with patch_time():
            asyncio.run(plugin._maybe_daily_diary())
        self.assertEqual(plugin.llm.raw_calls, [])

    def test_gap_is_capped_at_seven_days(self):
        plugin = make_plugin()
        plugin.db.kv_set("diary_last_day", "2026-11-01")
        for day in ("2026-11-03", "2026-11-05", "2026-11-09"):
            plugin.db.save_diary(day, "08:00", "当天的小日记")
        plugin.llm.chat_raw_text = "今天过得还不错，跟他聊了很多，心情挺平静的。"
        with patch_time():
            asyncio.run(plugin._maybe_daily_diary())
        written = [day for day in ("2026-11-03", "2026-11-04", "2026-11-05",
                                   "2026-11-06", "2026-11-07", "2026-11-08",
                                   "2026-11-09")
                   if plugin.db.kv_get("diary_written:" + day)]
        # 只有 11-03 / 11-05 / 11-09 有素材；其余空日记只记重试时间，不写文件
        self.assertEqual(written, ["2026-11-03", "2026-11-05", "2026-11-09"])
        self.assertEqual(len(plugin.llm.raw_calls), 3)
        self.assertEqual(plugin.db.kv_get("diary_last_day"), "2026-11-09")
        self.assertEqual(plugin.db.kv_get("diary_attempt:2026-11-04"), TS)

    def test_empty_generation_marks_attempt(self):
        plugin = make_plugin()
        with patch_time():
            asyncio.run(plugin._maybe_daily_diary())   # 没有任何素材 → 空日记
        self.assertEqual(plugin.llm.raw_calls, [])
        self.assertEqual(plugin.db.kv_get("diary_attempt:2026-11-09"), TS)

    def test_write_failure_marks_attempt(self):
        plugin = make_plugin()
        self.seed_day(plugin)
        with patch_time(), mock.patch.object(amo_schedule, "_diary_write",
                                             side_effect=OSError("磁盘满了")):
            asyncio.run(plugin._maybe_daily_diary())
        self.assertEqual(plugin.db.kv_get("diary_attempt:2026-11-09"), TS)
        self.assertIsNone(plugin.db.kv_get("diary_written:2026-11-09"))


class DiaryLinesTests(unittest.TestCase):
    def test_without_memory_plugin(self):
        plugin = make_plugin()
        day = datetime.date(2026, 11, 9)
        with patch_time():
            self.assertEqual(asyncio.run(plugin._diary_chat_lines(day)), [])

    def test_rows_are_formatted(self):
        plugin = make_plugin()
        plugin.mem = FakeMem([
            {"role": "user", "name": "", "content": "今天\n好累"},
            {"role": "bot", "name": "大肥鱼", "content": "抱抱"},
            {"role": "system", "name": "", "content": "忽略我"},
            {"role": "user", "name": "他", "content": "   "},
        ])
        lines = asyncio.run(plugin._diary_chat_lines(datetime.date(2026, 11, 9)))
        self.assertEqual(lines, ["他：今天 好累", "我：抱抱"])

    def test_memory_call_error_returns_empty(self):
        plugin = make_plugin()
        plugin.mem = FakeMem(exc=RuntimeError("外部插件超时"))
        self.assertEqual(asyncio.run(plugin._diary_chat_lines(datetime.date(2026, 11, 9))), [])

    def test_hourly_lines_merge_travel_and_rejects(self):
        plugin = make_plugin()
        plugin.db.save_diary("2026-11-09", "08:00", "起床洗漱")
        plugin.db.save_diary("2026-11-09", "09:00", "")
        plugin.db.kv_set("travel_log", [
            {"day": "2026-11-09", "hour": "07:00", "city": "清远", "journey": True},
            {"day": "2026-11-09", "hour": "10:00", "city": "杭州", "solo": True},
            {"day": "2026-11-09", "hour": "11:00", "city": "杭州", "solo": True, "back": True},
            {"day": "2026-11-09", "hour": "12:00", "city": "广州", "back": True},
            {"day": "2026-11-09", "hour": "13:00", "city": "佛山"},
            {"day": "2026-11-08", "hour": "13:00", "city": "佛山"},
            "垃圾数据",
        ])
        plugin.db.kv_set("follow_reject_log", [
            {"day": "2026-11-09", "hour": "14:00", "city": "清远"},
            {"day": "2026-11-08", "hour": "14:00", "city": "清远"},
        ])
        lines = plugin._diary_hourly_lines(datetime.date(2026, 11, 9))
        self.assertEqual(lines[0], "08:00 起床洗漱")
        self.assertIn("07:00 她坐车去清远陪他，路上约 2 小时", lines)
        self.assertIn("10:00 她自己出门去杭州旅游，晚上住酒店", lines)
        self.assertIn("11:00 她自己从杭州旅游回来了", lines)
        self.assertIn("12:00 跟他从广州回来了", lines)
        self.assertIn("13:00 跟他出门到了佛山，晚上住酒店", lines)
        self.assertIn("14:00 她说想陪他去清远，他说让她好好上班，她闷闷不乐", lines)
        self.assertFalse([line for line in lines if "2026-11-08" in line])

    def test_hourly_query_error_returns_empty(self):
        plugin = make_plugin()
        original = plugin.db._conn
        plugin.db._conn = types.SimpleNamespace(
            execute=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("表没了")))
        try:
            self.assertEqual(plugin._diary_hourly_lines(datetime.date(2026, 11, 9)), [])
        finally:
            plugin.db._conn = original


class GenerateDiaryTests(unittest.TestCase):
    def test_requires_writer(self):
        plugin = make_plugin()
        with mock.patch.object(amo_schedule, "_diary_write", None):
            self.assertEqual(asyncio.run(plugin._generate_daily_diary(datetime.date(2026, 11, 9))), "")

    def test_no_material_returns_empty(self):
        plugin = make_plugin()
        self.assertEqual(asyncio.run(plugin._generate_daily_diary(datetime.date(2026, 11, 9))), "")

    def test_strips_fences_and_header(self):
        plugin = make_plugin()
        plugin.db.save_diary("2026-11-09", "08:00", "起床")
        plugin.llm.chat_raw_text = "```markdown\n我的日记 · 11月9日\n\n今天跟他一起做饭，很平常但挺好。\n```"
        text = asyncio.run(plugin._generate_daily_diary(datetime.date(2026, 11, 9)))
        self.assertEqual(text, "今天跟他一起做饭，很平常但挺好。")

    def test_too_short_is_rejected(self):
        plugin = make_plugin()
        plugin.db.save_diary("2026-11-09", "08:00", "起床")
        plugin.llm.chat_raw_text = "今天挺好"
        self.assertEqual(asyncio.run(plugin._generate_daily_diary(datetime.date(2026, 11, 9))), "")

    def test_model_error_returns_empty(self):
        plugin = make_plugin()
        plugin.db.save_diary("2026-11-09", "08:00", "起床")

        async def boom(*args, **kwargs):
            raise RuntimeError("模型超时")

        plugin.llm.chat_raw = boom
        self.assertEqual(asyncio.run(plugin._generate_daily_diary(datetime.date(2026, 11, 9))), "")

    def test_persona_error_falls_back(self):
        plugin = make_plugin()
        plugin.db.save_diary("2026-11-09", "08:00", "起床")

        async def boom(*args, **kwargs):
            raise RuntimeError("人格词没读到")

        plugin.llm.persona = boom
        plugin.llm.chat_raw_text = "今天起床很早，做了早饭，心情还不错。"
        text = asyncio.run(plugin._generate_daily_diary(datetime.date(2026, 11, 9)))
        self.assertTrue(text.startswith("今天起床很早"))
        system = plugin.llm.raw_calls[0]["system"]
        self.assertIn("普通女孩", system)      # 退回默认人格描述


class WeatherAlertUmoTests(unittest.TestCase):
    def test_channels_sorted_and_deduped(self):
        plugin = make_plugin()
        plugin.db.touch_profile("1", "甲", "aiocqhttp", QQ, "", True)
        plugin.db.touch_profile("2", "乙", "lark", "lark:2", "", True)
        plugin.db.kv_set("channels:1", {
            "aiocqhttp": {"umo": QQ, "ts": 300},
            "lark": {"umo": "lark:1", "ts": 200},
        })
        umos = plugin._weather_alert_umos()
        # 最近活跃的排前面；私聊 umo 兜底时 ts=0 排最后；重复的不出现
        self.assertEqual(umos, [QQ, "lark:1", "lark:2"])
        self.assertEqual(plugin._pick_weather_alert_umo(), QQ)

    def test_profile_private_umo_is_last_resort(self):
        plugin = make_plugin()
        plugin.db.touch_profile("1", "甲", "aiocqhttp", QQ, "", True)
        umos = plugin._weather_alert_umos()
        self.assertEqual(umos, [QQ])

    def test_falls_back_to_last_umo(self):
        plugin = make_plugin()
        plugin._last_umo = "aiocqhttp:FriendMessage:9"
        self.assertEqual(plugin._weather_alert_umos(), ["aiocqhttp:FriendMessage:9"])

    def test_empty_when_nothing_known(self):
        plugin = make_plugin()
        plugin._last_umo = ""
        plugin._first_private_umo = lambda: ""
        self.assertEqual(plugin._weather_alert_umos(), [])
        self.assertEqual(plugin._pick_weather_alert_umo(), "")

    def test_db_error_falls_back(self):
        plugin = make_plugin()
        plugin.db.proactive_profiles = lambda limit=30: (_ for _ in ()).throw(RuntimeError("db 挂了"))
        self.assertEqual(plugin._weather_alert_umos(), [QQ])


class CleanAlertTests(unittest.TestCase):
    def test_keeps_plain_sentence(self):
        self.assertEqual(ScheduleMixin._clean_weather_alert("明天要下大雨，记得带伞"),
                         "明天要下大雨，记得带伞")

    def test_strips_prefix_and_quotes(self):
        self.assertEqual(ScheduleMixin._clean_weather_alert("“天气提醒：明天降温”"),
                         "明天降温")

    def test_rejects_assistant_tone(self):
        for text in ("请注意保暖", "建议您带伞", "作为AI我不能预报", "温馨提示：请注意保暖"):
            self.assertEqual(ScheduleMixin._clean_weather_alert(text), "", text)

    def test_rejects_too_long(self):
        self.assertEqual(ScheduleMixin._clean_weather_alert("明天" * 60), "")
        self.assertEqual(ScheduleMixin._clean_weather_alert(None), "")


class WeatherAlertTextTests(unittest.TestCase):
    def setUp(self):
        self.plugin = make_plugin()
        self.plugin.recent = [
            {"role": "user", "content": "今天加班到很晚"},
            {"role": "bot", "content": "那你早点休息"},
            {"role": "user", "content": ""},
        ]

    def test_uses_model_sentence(self):
        self.plugin.llm.chat_text = "明天雨挺大，你出门记得带伞"
        text = asyncio.run(self.plugin._weather_alert_text(
            QQ, {"textDay": "中雨", "textNight": "小雨", "tempMax": 15}, "明天有雨"))
        self.assertEqual(text, "明天雨挺大，你出门记得带伞")
        call = self.plugin.llm.chat_calls[0]
        self.assertEqual(call["limit"], 60)
        self.assertIn("明天天气：中雨 小雨", call["prompt"])
        self.assertIn("明天最高 15℃", call["prompt"])
        self.assertIn("他：今天加班到很晚", call["prompt"])
        self.assertIn("你：那你早点休息", call["prompt"])
        self.assertIn("【状态】正在上班", call["prompt"])
        self.assertIn("你是大肥鱼", call["system"])

    def test_bad_model_sentence_falls_back(self):
        self.plugin.llm.chat_text = "温馨提示：请注意保暖，建议您带伞"
        text = asyncio.run(self.plugin._weather_alert_text(QQ, {}, "明天有雨，伞别忘了"))
        self.assertEqual(text, "明天有雨，伞别忘了")

    def test_state_and_recent_errors_are_swallowed(self):
        self.plugin.recent = RuntimeError("消息表坏了")
        self.plugin.state.prompt_raises = True
        self.plugin.llm.chat_text = ""
        text = asyncio.run(self.plugin._weather_alert_text(QQ, {}, "明天有雨"))
        self.assertEqual(text, "明天有雨")
        self.assertNotIn("最近聊天", self.plugin.llm.chat_calls[0]["prompt"])


class WeatherQueryTests(unittest.TestCase):
    def test_without_key_uses_cached_now(self):
        plugin = make_plugin()
        plugin.cfg_values["hefeng_key"] = ""
        plugin.state.weather = {"city": "东莞", "text": "多云", "temp": 23,
                                "humidity": 55, "wind": "北风3级"}
        text = asyncio.run(plugin._weather_query_context("今天热不热"))
        self.assertIn("【天气查询】", text)
        self.assertIn("现在 东莞 多云 23℃ 湿度55% 北风3级", text)
        self.assertEqual(plugin.state.fetch_calls, [])

    def test_with_forecast(self):
        plugin = make_plugin()
        plugin.state.weather = {"city": "东莞", "text": "多云", "temp": 25}
        plugin.state.forecast = [
            {"textDay": "多云", "textNight": "多云", "tempMax": 26, "tempMin": 18},
            {"textDay": "中雨", "textNight": "小雨", "tempMax": 18, "tempMin": 12},
        ]
        text = asyncio.run(plugin._weather_query_context())
        self.assertIn("明天 中雨 小雨 12~18℃", text)
        self.assertIn("明天有雨，记得带伞", text)
        self.assertIn("明天比今天最高温低 8℃，多穿件", text)
        self.assertEqual(plugin.state.fetch_calls[0]["city"], "东莞")

    def test_refresh_error_uses_state_weather(self):
        plugin = make_plugin()
        plugin.cfg_values["hefeng_key"] = ""
        plugin.state.weather = {"city": "东莞", "text": "晴", "temp": 20}
        plugin.state.refresh_weather = lambda force=False: (_ for _ in ()).throw(RuntimeError("挂了"))
        # refresh_weather 是 async：用真正的协程抛错
        async def boom(force=False):
            raise RuntimeError("接口挂了")
        plugin.state.refresh_weather = boom
        text = asyncio.run(plugin._weather_query_context())
        self.assertIn("现在 东莞 晴 20℃", text)

    def test_no_data_at_all(self):
        plugin = make_plugin()
        plugin.cfg_values["hefeng_key"] = ""
        plugin.state.weather = {}
        text = asyncio.run(plugin._weather_query_context())
        self.assertIn("取不到天气数据", text)
        self.assertIn("别编温度", text)


class WeatherAlertTests(unittest.TestCase):
    def setUp(self):
        self.plugin = make_plugin()
        self.plugin.db.touch_profile(UID, "他", "aiocqhttp", QQ, "", True)
        self.good = [
            {"textDay": "多云", "textNight": "多云", "tempMax": 26, "tempMin": 18},
            {"textDay": "中雨", "textNight": "小雨", "tempMax": 15, "tempMin": 9},
        ]

    def evening(self):
        return datetime.datetime(2026, 11, 10, 20, 30)

    def morning(self):
        return datetime.datetime(2026, 11, 10, 8, 30)

    def run_alert(self, now=None):
        with patch_time(now=now or self.evening()):
            asyncio.run(self.plugin._maybe_weather_alert())

    def test_switch_off(self):
        self.plugin.cfg_values["weather_alert_enabled"] = False
        self.run_alert()
        self.assertEqual(self.plugin.state.fetch_calls, [])

    def test_without_key(self):
        self.plugin.cfg_values["hefeng_key"] = ""
        self.run_alert()
        self.assertEqual(self.plugin.state.fetch_calls, [])

    def test_already_sent_today(self):
        self.plugin.db.kv_set("weather_alert_sent", TODAY)
        self.run_alert()
        self.assertEqual(self.plugin.state.fetch_calls, [])

    def test_already_checked_slot(self):
        self.plugin.db.kv_set("weather_alert_checked", "%s|morning" % TODAY)
        self.run_alert(datetime.datetime(2026, 11, 10, 9, 0))
        self.assertEqual(self.plugin.state.fetch_calls, [])

    def test_missing_forecast_marks_checked(self):
        self.plugin.state.forecast = [self.good[0]]
        self.run_alert()
        self.assertEqual(self.plugin.db.kv_get("weather_alert_checked"), "%s|evening" % TODAY)
        self.assertEqual(self.plugin.sent, [])

    def test_normal_weather_does_not_alert(self):
        self.plugin.state.forecast = [
            {"textDay": "多云", "tempMax": 26},
            {"textDay": "多云", "tempMax": 25},
        ]
        self.run_alert()
        self.assertEqual(self.plugin.sent, [])
        self.assertEqual(self.plugin.state.fetch_calls[0]["fresh"], True)

    def test_morning_only_judges(self):
        self.plugin.state.forecast = self.good
        self.run_alert(self.morning())
        self.assertEqual(self.plugin.sent, [])
        self.assertIsNone(self.plugin.db.kv_get("weather_alert_sent"))
        self.assertEqual(self.plugin.db.kv_get("weather_alert_checked"), "%s|morning" % TODAY)
        self.assertEqual(self.plugin.state.fetch_calls[0]["fresh"], False)

    def test_evening_sends_alert(self):
        self.plugin.state.forecast = self.good
        self.plugin.llm.chat_text = "明天雨挺大的，你出门记得带伞"
        self.run_alert()
        self.assertEqual(self.plugin.sent, [(QQ, "明天雨挺大的，你出门记得带伞")])
        self.assertEqual(self.plugin.db.kv_get("weather_alert_sent"), TODAY)
        self.assertEqual(self.plugin.db.kv_get("weather_alert_open"), TODAY)

    def test_dry_run_marks_sent_without_sending(self):
        self.plugin.state.forecast = self.good
        self.plugin.cfg_values["weather_alert_dry_run"] = True
        self.run_alert()
        self.assertEqual(self.plugin.sent, [])
        self.assertEqual(self.plugin.db.kv_get("weather_alert_sent"), TODAY)

    def test_platform_fallback(self):
        self.plugin.state.forecast = self.good
        self.plugin.db.kv_set("channels:%s" % UID, {
            "lark": {"umo": "lark:1", "ts": 300},
            "aiocqhttp": {"umo": QQ, "ts": 100},
        })
        sent = []

        async def flaky(umo, text):
            if umo == "lark:1":
                return False
            sent.append((umo, text))
            return True

        self.plugin._send_to_umo = flaky
        self.run_alert()
        self.assertEqual([item[0] for item in sent], [QQ])

    def test_all_platforms_fail_resets_checked(self):
        self.plugin.state.forecast = self.good

        async def never(umo, text):
            return False

        self.plugin._send_to_umo = never
        self.run_alert()
        self.assertEqual(self.plugin.db.kv_get("weather_alert_checked"), "")
        self.assertIsNone(self.plugin.db.kv_get("weather_alert_sent"))

    def test_no_session_logs_only(self):
        self.plugin.state.forecast = self.good
        self.plugin._last_umo = ""
        self.plugin._first_private_umo = lambda: ""
        self.plugin.db.proactive_profiles = lambda limit=30: []
        self.run_alert()
        self.assertEqual(self.plugin.sent, [])


class SwitchWeatherCityTests(unittest.TestCase):
    def test_ignores_incomplete_hit(self):
        plugin = make_plugin()
        asyncio.run(plugin._switch_weather_city({"id": "", "name": "东莞"}))
        asyncio.run(plugin._switch_weather_city({"id": "101281601", "name": ""}))
        self.assertEqual(plugin.config, {})
        self.assertEqual(plugin.state.refresh_calls, [])

    def test_updates_config_and_refreshes(self):
        plugin = make_plugin()
        asyncio.run(plugin._switch_weather_city({"id": "101210101", "name": "杭州"}))
        self.assertEqual(plugin.config["weather_city"], "101210101")
        self.assertEqual(plugin.config["weather_city_name"], "杭州")
        self.assertEqual(plugin.config.saved, 1)
        self.assertEqual(plugin.state.refresh_calls, [True])

    def test_unchanged_does_nothing(self):
        plugin = make_plugin()
        plugin.config.update({"weather_city": "101210101", "weather_city_name": "杭州"})
        plugin.cfg_values["weather_city_name"] = "杭州"
        asyncio.run(plugin._switch_weather_city({"id": "101210101", "name": "杭州"}))
        self.assertEqual(plugin.config.saved, 0)
        self.assertEqual(plugin.state.refresh_calls, [])

    def test_save_failure_still_refreshes(self):
        plugin = make_plugin()
        plugin.config.save_error = OSError("配置只读")
        asyncio.run(plugin._switch_weather_city({"id": "101210101", "name": "杭州"}))
        self.assertEqual(plugin.state.refresh_calls, [True])


class SyncWeatherCityTests(unittest.TestCase):
    def test_skips_empty_digits_and_coordinates(self):
        plugin = make_plugin()
        for raw in ("", "101281601", "113.75,23.02"):
            plugin.cfg_values["weather_city"] = raw
            self.assertFalse(plugin._sync_weather_city_config(), raw)

    def test_chinese_name_is_backfilled(self):
        plugin = make_plugin()
        plugin.cfg_values["weather_city"] = "杭州"
        self.assertTrue(plugin._sync_weather_city_config())
        self.assertEqual(plugin.config["weather_city"], "101210101")
        self.assertEqual(plugin.config["weather_city_name"], "杭州")
        self.assertEqual(plugin.config.saved, 1)
        # 已回填成数字后就跳过（幂等）
        plugin.cfg_values["weather_city"] = plugin.config["weather_city"]
        self.assertFalse(plugin._sync_weather_city_config())

    def test_unknown_name_warns_once(self):
        plugin = make_plugin()
        plugin.cfg_values["weather_city"] = "不存在的城市"
        self.assertFalse(plugin._sync_weather_city_config())
        first = plugin._city_warn_cache["不存在的城市"]
        # 一小时内再调不刷新缓存时间
        self.assertFalse(plugin._sync_weather_city_config())
        self.assertEqual(plugin._city_warn_cache["不存在的城市"], first)

    def test_ambiguous_name_is_noted(self):
        plugin = make_plugin()
        plugin.cfg_values["weather_city"] = "朝阳"
        self.assertTrue(plugin._sync_weather_city_config())
        self.assertEqual(plugin.config["weather_city"], "101071201")
        self.assertIn("amb:朝阳", plugin._city_warn_cache)

    def test_save_error_is_logged(self):
        plugin = make_plugin()
        plugin.cfg_values["weather_city"] = "杭州"
        plugin.config.save_error = OSError("写不进去")
        self.assertTrue(plugin._sync_weather_city_config())
        self.assertEqual(plugin.config["weather_city"], "101210101")


if __name__ == "__main__":
    unittest.main()
