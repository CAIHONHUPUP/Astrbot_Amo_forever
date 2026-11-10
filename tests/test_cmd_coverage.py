# -*- coding: utf-8 -*-
"""amo_commands.CommandMixin 的覆盖率测试：用假 event 驱动 `/amo` 每个子命令。

覆盖点：
- `_args` / `_resolve_target`（@人、我、默认 uid 三条路）；
- `/amo help|segment|status|mood|profile|memories|rel|set|memo|forget|period|health|
  schedule|weather|worldview|threshold|say|clean` + 未知指令；
- 权限闸（非管理员每条写指令一句拒绝）、参数不足、字段校验；
- `_status_data` 的只读性（不 force 刷天气、不现生成日程）、心流阈值读写、外挂记忆条数缓存；
- `cmd_amo` / `cmd_status` / `cmd_profile` / `cmd_setrel` / `cmd_learn` / 礼物两个命令，
  以及 6 个 `heartflow_*` 命令（引擎缺失 / 正常两种）。

真 AmoDB + tempdir；时间用固定 ts；不联网、不调模型。
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import astrbot_stub  # noqa: E402

astrbot_stub.install()

import amo_commands  # noqa: E402
from amo_commands import CommandMixin  # noqa: E402
from amo_db import AmoDB  # noqa: E402
from amo_shared import RELATIONS, SCHEDULE_VERSION, Comp  # noqa: E402
from clock import from_timestamp  # noqa: E402

UID = "302578963"
OTHER = "123456"
QQ = "aiocqhttp:FriendMessage:%s" % UID
TODAY = "2026-11-10"
TS = 1_800_000_000.0


def patch_time(ts=TS, today=TODAY):
    return mock.patch.multiple(
        amo_commands,
        now_ts=lambda: ts,
        today_str=lambda: today,
    )


def run(coro):
    return asyncio.run(coro)


def collect(agen):
    async def drain():
        return [item async for item in agen]
    return asyncio.run(drain())


class FakeEvent:
    def __init__(self, text="", uid=UID, admin=True, comps=None):
        self.message_str = text
        self.uid = uid
        self.admin = admin
        self.comps = comps or []
        self.self_id = "bot-1"
        self.sent = []

    def plain_result(self, text):
        return {"plain": text}

    async def send(self, chain):
        self.sent.append(chain)
        return True

    def get_messages(self):
        return self.comps

    def get_self_id(self):
        return self.self_id

    def is_private_chat(self):
        return True


class FakeState:
    """只回答 amo_commands 会问到的问题，并把副作用记下来。"""

    def __init__(self):
        self.weather = {}
        self.worldview = ""
        self.schedule = {}
        self.schedule_context_value = ""
        self.schedule_result = []
        self.period_start = "2026-11-01"
        self.health = {"status": "健康", "note": "", "until": 0, "sick": False}
        self.calls = []

    def _simulate_weather(self):
        self.weather = {"city": "东莞", "text": "多云", "temp": 23.0,
                        "humidity": 55, "wind": "北风3级", "source": "simulate"}
        return self.weather

    async def refresh_weather(self, force=False):
        self.calls.append(("refresh_weather", force))
        return {"city": "东莞", "text": "晴", "temp": 25, "humidity": 40,
                "wind": "南风2级", "source": self.weather_source}

    weather_source = "qweather"

    def _fallback_world(self):
        self.calls.append(("fallback_world",))
        return {"city": "东莞", "occupation": "上班族"}

    async def ensure_worldview(self, umo, force=False):
        self.calls.append(("ensure_worldview", force))
        self.worldview = "她住在东莞，每天上班。"
        return self.worldview

    def worldview_text(self):
        return self.worldview

    def schedule_context(self, day):
        return self.schedule_context_value

    async def ensure_schedule(self, umo, force=False):
        self.calls.append(("ensure_schedule", force))
        return list(self.schedule_result)

    def snapshot(self):
        return {
            "datetime_text": "2026-11-10 10:30",
            "mood": {"开心": 70.0, "疲惫": 30.0},
            "dominant": "开心",
            "mood_score": 70.4,
            "period": {"phase": "经期", "day": 3, "tone": "腰酸"},
            "health": {"status": "健康", "note": "", "until": 0},
            "weather": {"city": "东莞", "text": "多云"},
            "weather_text": "东莞 多云 23℃",
            "activity": {"activity": "上班", "place": "公司"},
            "schedule": [],
        }

    def schedule_tree(self):
        return {"segments": []}

    def tone_text(self, snap, kind):
        return "轻轻的" + kind

    def period_info(self):
        return {"phase": "经期", "day": 3, "tone": "腰酸", "pain": 4,
                "cycle_days": 28, "bleed_days": 5, "days_to_next": 25,
                "next_start": "2026-12-05", "start": self.period_start}

    def set_period_start(self, value):
        if value == "2026-11-01":
            self.period_start = value
            return True
        return False

    def health_info(self):
        return dict(self.health)

    def set_health(self, status, hours, note):
        self.health = {"status": status, "note": note,
                       "until": TS + 86400 * hours, "sick": True}

    def current_activity(self):
        return {"activity": "上班", "place": "公司"}


class FakeHeartflow:
    reply_threshold = 0.4

    def __init__(self, value=0.55, activity=0.3, absolute=2.5, error=None):
        self.value = value
        self.activity = activity
        self.absolute = absolute
        self.error = error
        self.calls = []

    def _get_dynamic_threshold(self, umo):
        self.calls.append(umo)
        if self.error:
            raise self.error
        return self.value, self.activity, self.absolute

    async def heartflow_status(self, event):
        yield "status"

    async def heartflow_debug(self, event):
        yield "debug"

    async def heartflow_clear_buffer(self, event):
        yield "clear"

    async def heartflow_toggle_log(self, event):
        yield "toggle"

    async def heartflow_reset(self, event):
        yield "reset"

    async def heartflow_help(self, event):
        yield "help"


class FakeGift:
    def __init__(self, enabled=True, owner=True):
        self.enabled = enabled
        self.owner = owner
        self.manual = []

    def is_owner(self, event):
        return self.owner

    def command_text(self):
        return "🎁 心愿单：围巾"

    def manual_gift(self, event, item):
        self.manual.append(item)
        return "✅ 已送：" + str(item)


class FakePlugin(CommandMixin):
    def __init__(self, tmp):
        self.db = AmoDB(tmp)
        self.db.init()
        self.tmp = tmp
        self.state = FakeState()
        self.config = {}
        self.cfg_values = {
            "enable_group_reply": True,
            "enable_private_reply": True,
            "auto_active_msg": True,
            "enable_polish": True,
            "hefeng_key": "/tmp/hefeng.key",
            "weather_host": "https://m56hf38tfd.re.qweatherapi.com",
            "chat_log_days": 14,
            "seg_delay_type": "smart",
            "seg_keep_symbol": True,
            "seg_protect_paired_symbols": True,
        }
        self._last_umo = QQ
        self.heartflow = None
        self.segment_engine = None
        self.gift = None
        self._data_synced = True
        self._dialect_rows_value = [{"term": "莫"}, {"term": "晓得"}]
        self.memory_items = [
            {"id": 7, "tier": 1, "content": "他怕冷", "expires_at": 0},
            {"id": 8, "tier": 2, "content": "第一次见面", "expires_at": 0},
            {"id": 9, "tier": 0, "content": "旧事", "expires_at": TS - 86400 * 3},
        ]
        self.memory_queries = []
        self.memory_writes = []
        self.memory_write_ok = True
        self.lovers = []
        self.spawned = []
        self.ready_calls = 0
        self.seg_result = ["你好呀", "今天怎么样"]

    # ---- 配置 ----
    def cfg(self, key, default=None):
        return self.cfg_values.get(key, default)

    def cfg_bool(self, key, default=False):
        value = self.cfg(key, default)
        return value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes")

    def cfg_int(self, key, default=0):
        try:
            return int(float(self.cfg(key, default)))
        except (TypeError, ValueError):
            return default

    def cfg_str(self, key, default=""):
        value = self.cfg(key, default)
        return default if value is None else str(value)

    # ---- 身份 / 权限 ----
    def _canonical_uid(self, event):
        return str(getattr(event, "uid", UID))

    def _is_admin(self, event):
        return bool(getattr(event, "admin", False))

    # ---- 依赖 ----
    def _reload_config_if_changed(self):
        self.reload_calls = getattr(self, "reload_calls", 0) + 1

    def _first_private_umo(self):
        return QQ

    def _spawn(self, coro):
        # 只记名字再关掉协程：后台任务在真机上跑，单测里不 await（否则会真等/真刷）
        self.spawned.append(coro.__qualname__)
        coro.close()

    async def _all_memories(self, uid, keyword="", limit=50):
        self.memory_queries.append((uid, keyword, limit))
        return list(self.memory_items)[:limit]

    def _external_memory_write(self, uid, content, kind="fact", tier=1):
        if not self.memory_write_ok:
            return False
        self.memory_writes.append((uid, content, kind, tier))
        return True

    def _register_lover(self, uid):
        self.lovers.append(uid)

    def _data_connected(self):
        return True

    def _dialect_style(self):
        return "普通话"

    def _dialect_active(self):
        return False

    def _dialect_rows(self):
        return list(self._dialect_rows_value)

    def _segment(self, text):
        return list(self.seg_result)

    async def _ensure_ready(self):
        self.ready_calls += 1
        return True


def make_plugin():
    return FakePlugin(tempfile.mkdtemp(prefix="amo-cmd-"))


def seed_profile(plugin, uid=UID, **fields):
    plugin.db.touch_profile(uid, fields.pop("name", "他"), "aiocqhttp", QQ, "", True)
    if fields:
        plugin.db.update_profile(uid, **fields)
    return plugin.db.get_profile(uid)


class ArgsTests(unittest.TestCase):
    def setUp(self):
        self.plugin = make_plugin()

    def args(self, text):
        return CommandMixin._args(self.plugin, FakeEvent(text))

    def test_strips_command_prefix(self):
        self.assertEqual(self.args("/amo status"), ["status"])
        self.assertEqual(self.args("／amo  状态"), ["状态"])
        self.assertEqual(self.args("陪伴 心情"), ["心情"])
        self.assertEqual(self.args("astrbot_amo_forever clean"), ["clean"])

    def test_keeps_other_words(self):
        self.assertEqual(self.args("你好 世界"), ["你好", "世界"])
        self.assertEqual(self.args("AMO help"), ["help"])
        self.assertEqual(self.args(""), [])
        self.assertEqual(self.args("/amo"), [])


class ResolveTargetTests(unittest.TestCase):
    def setUp(self):
        self.plugin = make_plugin()

    def test_at_component_wins(self):
        event = FakeEvent("", comps=[Comp.At(qq=OTHER)])
        self.assertEqual(self.plugin._resolve_target(event, ["rel", "@x"], 1), OTHER)

    def test_at_self_is_ignored(self):
        event = FakeEvent("", comps=[Comp.At(qq="bot-1")])
        self.assertEqual(self.plugin._resolve_target(event, ["rel", "abc"], 1), "abc")
        event = FakeEvent("", comps=[Comp.At(qq="all")])
        self.assertEqual(self.plugin._resolve_target(event, ["rel", "abc"], 1), "abc")

    def test_index_token(self):
        event = FakeEvent("")
        self.assertEqual(self.plugin._resolve_target(event, ["rel", "我"], 1), UID)
        self.assertEqual(self.plugin._resolve_target(event, ["rel", "self"], 1), UID)
        self.assertEqual(self.plugin._resolve_target(event, ["rel", "@999"], 1), "999")
        self.assertEqual(self.plugin._resolve_target(event, ["rel", ""], 1), UID)

    def test_defaults_to_sender(self):
        self.assertEqual(self.plugin._resolve_target(FakeEvent(""), ["rel"], 1), UID)


class HelpAndSegmentTests(unittest.TestCase):
    def setUp(self):
        self.plugin = make_plugin()

    def test_help(self):
        event = FakeEvent("/amo help")
        text = run(self.plugin._handle_command(event))
        self.assertIn("/amo status", text)
        self.assertIn("/amo clean", text)

    def test_empty_command_is_help(self):
        self.assertIn("🌙 陪伴 指令", run(self.plugin._handle_command(FakeEvent("/amo"))))

    def test_segment_usage(self):
        text = run(self.plugin._handle_command(FakeEvent("/amo segment")))
        self.assertIn("分段测试：/amo segment 一段文字", text)
        self.assertIn("保留标点：是", text)
        self.assertIn("延迟：smart", text)

    def test_segment_result(self):
        text = run(self.plugin._handle_command(FakeEvent("/amo segment 你好呀，今天怎么样")))
        self.assertIn("分段结果（smart），共 2 段", text)
        self.assertIn("1. 你好呀", text)
        self.assertIn("2. 今天怎么样", text)

    def test_segment_empty_result(self):
        self.plugin.seg_result = []
        text = run(self.plugin._handle_command(FakeEvent("/amo segment 空格")))
        self.assertIn("（没有可发送的片段）", text)


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.plugin = make_plugin()

    def test_status_line(self):
        seed_profile(self.plugin)
        with patch_time():
            text = run(self.plugin._handle_command(FakeEvent("/amo status")))
        self.assertIn("🌙 陪伴 · 当前状态", text)
        self.assertIn("🕒 2026-11-10 10:30", text)
        self.assertIn("💛 心情：开心（开心70 疲惫30）", text)
        self.assertIn("🩸 生理期：经期 第3天（腰酸）", text)
        self.assertIn("🩺 身体：健康", text)
        self.assertIn("🌦 天气：东莞 多云 23℃", text)
        self.assertIn("📅 正在：上班（公司）", text)
        self.assertIn("📚 档案 1 · 记忆 3 · 消息 0", text)

    def test_status_is_read_only(self):
        """面板每 60 秒轮询一次：不能 force 刷天气，也不能现生成日程。"""
        seed_profile(self.plugin)
        self.plugin.state.worldview = "她住在东莞。"
        self.plugin.state.schedule[TODAY] = ["08:00-09:00 上班"]
        self.plugin.state.schedule_context_value = "有上下文"
        self.plugin.db.kv_set("schedule_version", SCHEDULE_VERSION)
        with patch_time():
            run(self.plugin._handle_command(FakeEvent("/amo status")))
        # 只有一个「刷天气」的后台任务，且是默认（非 force）参数
        self.assertEqual(self.plugin.spawned, ["FakeState.refresh_weather"])
        self.assertNotIn(("ensure_worldview", False), self.plugin.state.calls)
        self.assertNotIn(("ensure_schedule", False), self.plugin.state.calls)

    def test_status_spawns_background_work_when_missing(self):
        seed_profile(self.plugin)
        self.plugin.state.weather = {}
        with patch_time():
            run(self.plugin._handle_command(FakeEvent("/amo status")))
        # 天气/世界观/日程缺了都丢给后台，不在这里同步现做
        self.assertIn(("fallback_world",), self.plugin.state.calls)
        self.assertEqual(self.plugin.spawned, [
            "FakeState.refresh_weather",
            "FakeState.ensure_worldview",
            "FakeState.ensure_schedule",
        ])

    def test_memory_count_is_cached_for_30s(self):
        profile = seed_profile(self.plugin)
        self.plugin.db.kv_set("ext_mem_count_at_" + profile["uid"], TS - 5)
        self.plugin.db.kv_set("ext_mem_count_" + profile["uid"], 42)
        with patch_time():
            data = run(self.plugin._status_data())
        self.assertEqual(data["counts"]["memories"], 42)
        self.assertEqual(self.plugin.memory_queries, [])

    def test_memory_count_is_refreshed_when_stale(self):
        profile = seed_profile(self.plugin)
        self.plugin.db.kv_set("ext_mem_count_at_" + profile["uid"], TS - 600)
        self.plugin.db.kv_set("ext_mem_count_" + profile["uid"], 1)
        with patch_time():
            data = run(self.plugin._status_data())
        self.assertEqual(data["counts"]["memories"], 3)
        self.assertEqual(self.plugin.db.kv_get("ext_mem_count_" + profile["uid"]), 3)
        self.assertEqual(self.plugin.db.kv_get("ext_mem_count_at_" + profile["uid"]), TS)

    def test_without_profiles_memory_count_is_zero(self):
        with patch_time():
            data = run(self.plugin._status_data())
        self.assertEqual(data["counts"]["memories"], 0)
        self.assertEqual(self.plugin.memory_queries, [])

    def test_heartflow_threshold(self):
        self.plugin.heartflow = FakeHeartflow(value=0.66, activity=0.25, absolute=3.0)
        with patch_time():
            data = run(self.plugin._status_data())
        self.assertEqual(data["threshold"], {"value": 66.0, "base": 40.0, "absolute": 3.0})
        self.assertEqual(data["activity_rate"], 25.0)

    def test_heartflow_error_keeps_zero_threshold(self):
        self.plugin.heartflow = FakeHeartflow(error=RuntimeError("心流引擎炸了"))
        with patch_time():
            data = run(self.plugin._status_data())
        self.assertEqual(data["threshold"], {"value": 0.0, "base": 0.0, "absolute": 0.0})
        self.assertEqual(data["activity_rate"], 0.0)

    def test_status_payload_config(self):
        with patch_time():
            data = run(self.plugin._status_data())
        self.assertTrue(data["config"]["weather_key_set"])
        self.assertEqual(data["config"]["version"], amo_commands.PLUGIN_VERSION)
        self.assertEqual(data["config"]["dialect_style"], "普通话")
        self.assertFalse(data["config"]["dialect_enabled"])
        self.assertEqual(data["config"]["dialect_count"], 0)   # 关掉方言时不去数词条
        self.assertEqual(data["data_plugin"], {"name": "Astr_Amo_data",
                                               "connected": True, "synced": True})
        self.assertIn("weekday", data["day"])


class MoodTests(unittest.TestCase):
    def test_mood_bars(self):
        plugin = make_plugin()
        text = run(plugin._handle_command(FakeEvent("/amo mood")))
        self.assertIn("🎨 陪伴的十维心情", text)
        self.assertIn("开心 ███████░░░ 70", text)
        self.assertIn("疲惫 ███░░░░░░░ 30", text)
        self.assertIn("整体偏「开心」，语气：轻轻的普通", text)


class ProfileTests(unittest.TestCase):
    def test_unknown_profile(self):
        plugin = make_plugin()
        self.assertEqual(run(plugin._handle_command(FakeEvent("/amo profile"))),
                         "还没有这个人的档案。多聊几句就会自动建立。")

    def test_profile_detail(self):
        plugin = make_plugin()
        seed_profile(plugin, relation="相恋", alias="宝贝", birthday="05-20",
                     affection=88, notes="怕冷")
        text = run(plugin._handle_command(FakeEvent("/amo profile")))
        self.assertIn("📁 档案 · 他", text)
        self.assertIn("ID：" + UID, text)
        self.assertIn("称呼：宝贝", text)
        self.assertIn("生日：05-20", text)
        self.assertIn("关系：相恋", text)
        self.assertIn("好感：88", text)
        self.assertIn("记忆数：3", text)
        self.assertIn("备注：怕冷", text)

    def test_profile_defaults_for_empty_fields(self):
        plugin = make_plugin()
        seed_profile(plugin)
        text = run(plugin._handle_command(FakeEvent("/amo profile")))
        self.assertIn("称呼：未设置", text)
        self.assertIn("生日：未知", text)
        self.assertIn("备注：无", text)


class MemoriesTests(unittest.TestCase):
    def test_other_user_needs_admin(self):
        plugin = make_plugin()
        event = FakeEvent("/amo memories", admin=False, comps=[Comp.At(qq=OTHER)])
        self.assertEqual(run(plugin._handle_command(event)), "只有管理员才能查看别人的记忆。")

    def test_admin_sees_items(self):
        plugin = make_plugin()
        with patch_time():
            text = run(plugin._handle_command(FakeEvent("/amo memories @%s" % OTHER,
                                                        comps=[Comp.At(qq=OTHER)])))
        self.assertIn("📖 记忆 · " + OTHER, text)
        self.assertIn("#7 [重要|永久] 他怕冷", text)
        self.assertIn("#8 [珍贵|永久] 第一次见面", text)
        self.assertIn("#9 [普通|0天] 旧事", text)

    def test_self_memory_does_not_need_admin(self):
        plugin = make_plugin()
        text = run(plugin._handle_command(FakeEvent("/amo memories", admin=False)))
        self.assertIn("📖 记忆 · " + UID, text)

    def test_empty(self):
        plugin = make_plugin()
        plugin.memory_items = []
        self.assertEqual(run(plugin._handle_command(FakeEvent("/amo memories"))), "暂时没有记忆。")


class RelationTests(unittest.TestCase):
    def test_needs_admin(self):
        plugin = make_plugin()
        event = FakeEvent("/amo rel @%s 相恋" % OTHER, admin=False,
                          comps=[Comp.At(qq=OTHER)])
        self.assertEqual(run(plugin._handle_command(event)), "只有管理员才能调整关系。")

    def test_usage_when_short(self):
        plugin = make_plugin()
        text = run(plugin._handle_command(FakeEvent("/amo rel @%s" % OTHER, comps=[Comp.At(qq=OTHER)])))
        self.assertIn("用法：/amo rel @人", text)

    def test_invalid_relation(self):
        plugin = make_plugin()
        seed_profile(plugin, uid=OTHER)
        event = FakeEvent("/amo rel @%s 死党" % OTHER, comps=[Comp.At(qq=OTHER)])
        text = run(plugin._handle_command(event))
        self.assertIn("关系只能是：", text)
        self.assertIn("相恋", text)

    def test_updates_relation_and_registers_lover(self):
        plugin = make_plugin()
        seed_profile(plugin, uid=OTHER)
        event = FakeEvent("/amo rel @%s 相恋" % OTHER, comps=[Comp.At(qq=OTHER)])
        text = run(plugin._handle_command(event))
        self.assertEqual(text, "✅ 已将 " + OTHER + " 的关系设为「相恋」")
        self.assertEqual(plugin.db.get_profile(OTHER)["relation"], "相恋")
        self.assertEqual(plugin.lovers, [OTHER])
        self.assertEqual(plugin.memory_writes[0][1], "与角色的关系是相恋")
        self.assertEqual(plugin.memory_writes[0][3], 2)

    def test_plain_relation_does_not_touch_lovers(self):
        plugin = make_plugin()
        seed_profile(plugin, uid=OTHER, relation="相恋")
        event = FakeEvent("/amo rel @%s 普通" % OTHER, comps=[Comp.At(qq=OTHER)])
        run(plugin._handle_command(event))
        self.assertEqual(plugin.lovers, [])
        self.assertEqual(plugin.db.get_profile(OTHER)["relation"], "普通")
        self.assertTrue(set(RELATIONS))


class SetFieldTests(unittest.TestCase):
    def test_needs_admin(self):
        plugin = make_plugin()
        event = FakeEvent("/amo set @1 name x", admin=False, comps=[Comp.At(qq="1")])
        self.assertEqual(run(plugin._handle_command(event)), "只有管理员才能修改档案。")

    def test_usage_when_short(self):
        plugin = make_plugin()
        event = FakeEvent("/amo set @1 name", comps=[Comp.At(qq="1")])
        self.assertIn("用法：/amo set @人", run(plugin._handle_command(event)))

    def test_relation_must_use_rel(self):
        plugin = make_plugin()
        seed_profile(plugin, uid=OTHER)
        event = FakeEvent("/amo set @%s relation 相恋" % OTHER, comps=[Comp.At(qq=OTHER)])
        self.assertEqual(run(plugin._handle_command(event)), "请用 /amo rel 设置关系。")

    def test_birthday_formats(self):
        plugin = make_plugin()
        seed_profile(plugin, uid=OTHER)
        bad = FakeEvent("/amo set @%s birthday 生日" % OTHER, comps=[Comp.At(qq=OTHER)])
        self.assertIn("生日格式：MM-DD 或 YYYY-MM-DD", run(plugin._handle_command(bad)))
        good = FakeEvent("/amo set @%s birthday 5-6" % OTHER, comps=[Comp.At(qq=OTHER)])
        text = run(plugin._handle_command(good))
        self.assertEqual(text, "✅ 已更新 " + OTHER + " 的 birthday")
        self.assertEqual(plugin.db.get_profile(OTHER)["birthday"], "05-06")

    def test_birthday_with_year(self):
        plugin = make_plugin()
        seed_profile(plugin, uid=OTHER)
        event = FakeEvent("/amo set @%s birthday 1998-12-31" % OTHER, comps=[Comp.At(qq=OTHER)])
        run(plugin._handle_command(event))
        self.assertEqual(plugin.db.get_profile(OTHER)["birthday"], "12-31")

    def test_affection_is_clamped(self):
        plugin = make_plugin()
        seed_profile(plugin, uid=OTHER)
        event = FakeEvent("/amo set @%s affection 999" % OTHER, comps=[Comp.At(qq=OTHER)])
        text = run(plugin._handle_command(event))
        self.assertEqual(text, "✅ 已更新 " + OTHER + " 的 affection")
        self.assertEqual(plugin.db.get_profile(OTHER)["affection"], 100)

    def test_unknown_field(self):
        plugin = make_plugin()
        seed_profile(plugin, uid=OTHER)
        event = FakeEvent("/amo set @%s relation_at 1" % OTHER, comps=[Comp.At(qq=OTHER)])
        self.assertIn("可修改字段：", run(plugin._handle_command(event)))

    def test_name_with_spaces(self):
        plugin = make_plugin()
        seed_profile(plugin, uid=OTHER)
        event = FakeEvent("/amo set @%s notes 怕 冷 还 怕 黑" % OTHER, comps=[Comp.At(qq=OTHER)])
        run(plugin._handle_command(event))
        self.assertEqual(plugin.db.get_profile(OTHER)["notes"], "怕 冷 还 怕 黑")


class MemoTests(unittest.TestCase):
    def test_needs_admin(self):
        plugin = make_plugin()
        event = FakeEvent("/amo memo @1 内容", admin=False, comps=[Comp.At(qq="1")])
        self.assertIn("只有管理员才能手动写入记忆。", run(plugin._handle_command(event)))

    def test_usage_when_short(self):
        plugin = make_plugin()
        event = FakeEvent("/amo memo @1", comps=[Comp.At(qq="1")])
        self.assertIn("用法：/amo memo", run(plugin._handle_command(event)))

    def test_empty_content(self):
        plugin = make_plugin()
        event = FakeEvent("/amo memo @1 2", comps=[Comp.At(qq="1")])
        self.assertEqual(run(plugin._handle_command(event)), "内容不能为空。")

    def test_writes_with_tier(self):
        plugin = make_plugin()
        seed_profile(plugin, uid=OTHER)
        event = FakeEvent("/amo memo @%s 他怕冷 2" % OTHER, comps=[Comp.At(qq=OTHER)])
        self.assertEqual(run(plugin._handle_command(event)), "✅ 已记住：他怕冷")
        self.assertEqual(plugin.memory_writes[0], (OTHER, "他怕冷", "manual", 2))

    def test_default_tier_is_important(self):
        plugin = make_plugin()
        seed_profile(plugin, uid=OTHER)
        event = FakeEvent("/amo memo @%s 他爱吃辣" % OTHER, comps=[Comp.At(qq=OTHER)])
        run(plugin._handle_command(event))
        self.assertEqual(plugin.memory_writes[0][3], 1)

    def test_write_failure(self):
        plugin = make_plugin()
        plugin.memory_write_ok = False
        seed_profile(plugin, uid=OTHER)
        event = FakeEvent("/amo memo @%s 他怕冷" % OTHER, comps=[Comp.At(qq=OTHER)])
        text = run(plugin._handle_command(event))
        self.assertIn("没能写进记忆插件", text)

    def test_forget_points_to_memory_plugin(self):
        plugin = make_plugin()
        text = run(plugin._handle_command(FakeEvent("/amo forget 7")))
        self.assertIn("记忆由外挂插件保存", text)
        event = FakeEvent("/amo forget 7", admin=False)
        self.assertIn("只有管理员才能删除记忆。", run(plugin._handle_command(event)))
        short = FakeEvent("/amo forget")
        self.assertIn("用法：/amo forget", run(plugin._handle_command(short)))


class PeriodTests(unittest.TestCase):
    def test_period_info(self):
        plugin = make_plugin()
        text = run(plugin._handle_command(FakeEvent("/amo period")))
        self.assertIn("阶段：经期 第3天", text)
        self.assertIn("状态：腰酸", text)
        self.assertIn("疼痛：4/10", text)
        self.assertIn("周期：28天｜经期：5天", text)
        self.assertIn("距离下次：25天（预计 2026-12-05）", text)
        self.assertIn("起始日：2026-11-01", text)

    def test_set_start(self):
        plugin = make_plugin()
        text = run(plugin._handle_command(FakeEvent("/amo period set 2026-11-01")))
        self.assertEqual(text, "✅ 生理期起始日已设为 2026-11-01")

    def test_bad_date(self):
        plugin = make_plugin()
        text = run(plugin._handle_command(FakeEvent("/amo period set 明天")))
        self.assertEqual(text, "日期格式应为 YYYY-MM-DD")

    def test_set_needs_admin(self):
        plugin = make_plugin()
        event = FakeEvent("/amo period set 2026-11-01", admin=False)
        self.assertEqual(run(plugin._handle_command(event)), "只有管理员才能调整生理期。")


class HealthTests(unittest.TestCase):
    def test_health_info_with_note(self):
        plugin = make_plugin()
        plugin.state.health = {"status": "轻微不适", "note": "昨晚没睡好",
                               "until": TS, "sick": True}
        text = run(plugin._handle_command(FakeEvent("/amo health")))
        self.assertIn("🩺 身体状态：轻微不适", text)
        self.assertIn("备注：昨晚没睡好", text)
        self.assertIn("恢复时间：" + from_timestamp(TS).strftime("%m-%d %H:%M"), text)

    def test_health_info_without_note(self):
        plugin = make_plugin()
        text = run(plugin._handle_command(FakeEvent("/amo health")))
        self.assertIn("🩺 身体状态：健康", text)
        self.assertNotIn("备注：", text)
        self.assertIn("恢复时间：—", text)

    def test_set_health(self):
        plugin = make_plugin()
        text = run(plugin._handle_command(FakeEvent("/amo health set 感冒")))
        self.assertEqual(text, "✅ 健康状态已设为 感冒")
        self.assertEqual(plugin.state.health["status"], "感冒")
        self.assertEqual(plugin.state.health["note"], "管理员设置")

    def test_invalid_status(self):
        plugin = make_plugin()
        text = run(plugin._handle_command(FakeEvent("/amo health set 想睡觉")))
        self.assertIn("状态：健康 / 轻微不适 / 感冒 / 低烧 / 疲惫", text)

    def test_needs_admin(self):
        plugin = make_plugin()
        event = FakeEvent("/amo health set 感冒", admin=False)
        self.assertEqual(run(plugin._handle_command(event)), "只有管理员才能调整健康状态。")


class ScheduleTests(unittest.TestCase):
    def test_list_from_state(self):
        plugin = make_plugin()
        plugin.state.schedule[TODAY] = [
            {"start": "08:00", "end": "09:00", "activity": "上班", "place": "公司"},
            {"start": "12:00", "end": "13:00", "activity": "吃饭", "place": "楼下"},
        ]
        with patch_time():
            text = run(plugin._handle_command(FakeEvent("/amo schedule")))
        self.assertIn("📅 今日日程", text)
        self.assertIn("08:00-09:00 上班（公司）", text)
        self.assertIn("12:00-13:00 吃饭（楼下）", text)
        self.assertIn("现在应该在：上班", text)
        self.assertNotIn(("ensure_schedule", False), plugin.state.calls)

    def test_generates_when_missing(self):
        plugin = make_plugin()
        plugin.state.schedule_result = [
            {"start": "07:00", "end": "08:00", "activity": "起床", "place": "家"},
        ]
        with patch_time():
            text = run(plugin._handle_command(FakeEvent("/amo schedule")))
        self.assertIn(("ensure_schedule", False), plugin.state.calls)
        self.assertIn("07:00-08:00 起床（家）", text)

    def test_regen(self):
        plugin = make_plugin()
        plugin.state.schedule_result = [{"start": "07:00"}]
        text = run(plugin._handle_command(FakeEvent("/amo schedule regen")))
        self.assertEqual(text, "✅ 日程已重新生成，共 1 条。")
        self.assertIn(("ensure_schedule", True), plugin.state.calls)

    def test_regen_needs_admin(self):
        plugin = make_plugin()
        event = FakeEvent("/amo schedule regen", admin=False)
        self.assertEqual(run(plugin._handle_command(event)), "只有管理员才能重生成日程。")


class WeatherTests(unittest.TestCase):
    def test_weather_line(self):
        plugin = make_plugin()
        plugin.state.weather_source = "simulate"
        text = run(plugin._handle_command(FakeEvent("/amo weather")))
        self.assertIn("🌦 东莞 晴 25℃", text)
        self.assertIn("湿度：40%", text)
        self.assertIn("风：南风2级", text)
        self.assertIn("来源：本地模拟", text)

    def test_weather_refresh_forces_fetch(self):
        plugin = make_plugin()
        text = run(plugin._handle_command(FakeEvent("/amo weather refresh")))
        self.assertIn("来源：和风天气", text)
        self.assertEqual(plugin.state.calls, [("refresh_weather", True),
                                              ("refresh_weather", False)])


class WorldviewTests(unittest.TestCase):
    def test_worldview_text(self):
        plugin = make_plugin()
        plugin.state.worldview = "她住在东莞。"
        text = run(plugin._handle_command(FakeEvent("/amo worldview")))
        # 少了就现取：这里校验的是「取完再拼」，内容是假 state 刚生成的
        self.assertEqual(text, "🌍 世界观\n" + plugin.state.worldview)
        self.assertIn(("ensure_worldview", False), plugin.state.calls)

    def test_regen(self):
        plugin = make_plugin()
        text = run(plugin._handle_command(FakeEvent("/amo worldview regen")))
        self.assertEqual(text, "✅ 世界观已重新生成。")
        self.assertIn(("ensure_worldview", True), plugin.state.calls)

    def test_regen_needs_admin(self):
        plugin = make_plugin()
        event = FakeEvent("/amo worldview regen", admin=False)
        self.assertEqual(run(plugin._handle_command(event)), "只有管理员才能重生成世界观。")


class ThresholdTests(unittest.TestCase):
    def test_threshold(self):
        plugin = make_plugin()
        plugin.heartflow = FakeHeartflow(value=0.55, activity=0.3, absolute=2.5)
        with patch_time():
            text = run(plugin._handle_command(FakeEvent("/amo threshold")))
        self.assertIn("当前动态阈值：0.55", text)
        self.assertIn("基础阈值：0.4", text)
        self.assertIn("绝对分数阈值：2.5/10", text)
        self.assertIn("当前群活跃度：30.0%", text)


class SayAndCleanTests(unittest.TestCase):
    def test_say_sends_message(self):
        plugin = make_plugin()
        event = FakeEvent("/amo say 你好呀")
        with mock.patch.object(amo_commands, "MessageChain",
                               lambda items: ("chain", [item.text for item in items])):
            text = run(plugin._handle_command(event))
        self.assertEqual(text, "")
        self.assertEqual(event.sent, [("chain", ["你好呀"])])

    def test_say_needs_admin(self):
        plugin = make_plugin()
        event = FakeEvent("/amo say 你好", admin=False)
        self.assertEqual(run(plugin._handle_command(event)), "只有管理员才能测试发言。")

    def test_say_needs_content(self):
        plugin = make_plugin()
        self.assertEqual(run(plugin._handle_command(FakeEvent("/amo say"))), "用法：/amo say 内容")

    def test_clean_purges_old_messages(self):
        plugin = make_plugin()
        plugin.db.conn.execute(
            "INSERT INTO messages(umo, uid, name, role, content, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (QQ, UID, "他", "user", "旧消息", 1.0),
        )
        plugin.db.conn.commit()
        text = run(plugin._handle_command(FakeEvent("/amo clean")))
        self.assertEqual(text, "✅ 已清理过期聊天记录。")
        self.assertEqual(plugin.db.counts()["messages"], 0)

    def test_clean_needs_admin(self):
        plugin = make_plugin()
        event = FakeEvent("/amo clean", admin=False)
        self.assertEqual(run(plugin._handle_command(event)), "只有管理员才能清理。")

    def test_unknown_command(self):
        plugin = make_plugin()
        text = run(plugin._handle_command(FakeEvent("/amo 跳舞")))
        self.assertEqual(text, "未知指令。发送 /amo help 查看帮助。")


class HandlerTests(unittest.TestCase):
    def setUp(self):
        self.plugin = make_plugin()

    def test_cmd_amo_yields_reply(self):
        event = FakeEvent("/amo help")
        items = collect(self.plugin.cmd_amo(event))
        self.assertEqual(len(items), 1)
        self.assertIn("/amo status", items[0]["plain"])
        self.assertEqual(self.plugin.ready_calls, 1)

    def test_cmd_amo_wraps_errors(self):
        def boom(plugin_self, event):
            raise RuntimeError("炸了")
        with mock.patch.object(FakePlugin, "_handle_command", boom):
            items = collect(self.plugin.cmd_amo(FakeEvent("/amo status")))
        self.assertEqual(items[0]["plain"], "处理失败：炸了")

    def test_cmd_amo_silent_when_no_message(self):
        with mock.patch.object(FakePlugin, "_handle_command", lambda self, e: _async("")):
            self.assertEqual(collect(self.plugin.cmd_amo(FakeEvent("/amo say"))), [])

    def test_cmd_status(self):
        seed_profile(self.plugin)
        items = collect(self.plugin.cmd_status(FakeEvent("/c_status")))
        self.assertIn("🌙 陪伴 · 当前状态", items[0]["plain"])

    def test_cmd_profile_missing(self):
        items = collect(self.plugin.cmd_profile(FakeEvent("/c_profile")))
        self.assertEqual(items[0]["plain"], "还没有你的档案。")

    def test_cmd_profile_existing(self):
        seed_profile(self.plugin, relation="熟识")
        items = collect(self.plugin.cmd_profile(FakeEvent("/c_profile")))
        self.assertIn("🤍 关系：熟识", items[0]["plain"])
        self.assertIn("📖 记忆条数：3", items[0]["plain"])

    def test_cmd_setrel_good(self):
        seed_profile(self.plugin)
        items = collect(self.plugin.cmd_setrel(FakeEvent("/c_setrel 相恋")))
        self.assertEqual(items[0]["plain"], "✅ 关系已设置为：相恋")
        self.assertEqual(self.plugin.db.get_profile(UID)["relation"], "相恋")

    def test_cmd_setrel_bad(self):
        items = collect(self.plugin.cmd_setrel(FakeEvent("/c_setrel 死党")))
        self.assertIn("用法：/c_setrel", items[0]["plain"])

    def test_cmd_setrel_needs_admin(self):
        items = collect(self.plugin.cmd_setrel(FakeEvent("/c_setrel 相恋", admin=False)))
        self.assertEqual(items[0]["plain"], "只有管理员才能调整关系。")

    def test_cmd_learn(self):
        seed_profile(self.plugin)
        items = collect(self.plugin.cmd_learn(FakeEvent("/learn_and_gate 他喜欢喝冰美式")))
        self.assertEqual(items[0]["plain"], "✅ 已经记下来啦。")
        self.assertEqual(self.plugin.memory_writes[0][1], "他喜欢喝冰美式")
        self.assertEqual(self.plugin.memory_writes[0][2], "manual")

    def test_cmd_learn_empty(self):
        items = collect(self.plugin.cmd_learn(FakeEvent("/learn_and_gate")))
        self.assertEqual(items[0]["plain"], "请输入要学习的内容")

    def test_cmd_learn_write_failure(self):
        self.plugin.memory_write_ok = False
        items = collect(self.plugin.cmd_learn(FakeEvent("/learn_and_gate 记一下")))
        self.assertIn("没能写进记忆插件", items[0]["plain"])

    def test_gift_list(self):
        self.plugin.gift = FakeGift()
        items = collect(self.plugin.cmd_gift_list(FakeEvent("/礼物")))
        self.assertEqual(items[0]["plain"], "🎁 心愿单：围巾")

    def test_gift_list_disabled(self):
        self.plugin.gift = None
        self.assertEqual(collect(self.plugin.cmd_gift_list(FakeEvent("/礼物")))[0]["plain"],
                         "礼物功能还没开。")
        self.plugin.gift = FakeGift(enabled=False)
        self.assertEqual(collect(self.plugin.cmd_gift_list(FakeEvent("/礼物")))[0]["plain"],
                         "礼物功能还没开。")

    def test_gift_list_needs_owner(self):
        self.plugin.gift = FakeGift(owner=False)
        self.assertEqual(collect(self.plugin.cmd_gift_list(FakeEvent("/礼物")))[0]["plain"],
                         "这个只给主人看哦。")

    def test_gift_send(self):
        self.plugin.gift = FakeGift()
        items = collect(self.plugin.cmd_gift_send(FakeEvent("/送礼 围巾"), "围巾"))
        self.assertEqual(items[0]["plain"], "✅ 已送：围巾")
        self.assertEqual(self.plugin.gift.manual, ["围巾"])

    def test_gift_send_disabled_and_owner(self):
        self.plugin.gift = FakeGift(enabled=False)
        self.assertEqual(collect(self.plugin.cmd_gift_send(FakeEvent("/送礼 x"), "x"))[0]["plain"],
                         "礼物功能还没开。")
        self.plugin.gift = FakeGift(owner=False)
        self.assertEqual(collect(self.plugin.cmd_gift_send(FakeEvent("/送礼 x"), "x"))[0]["plain"],
                         "这个只给主人用哦。")


class HeartflowHandlerTests(unittest.TestCase):
    def test_without_engine(self):
        plugin = make_plugin()
        handlers = (
            plugin.cmd_heartflow, plugin.cmd_heartflow_debug, plugin.cmd_heartflow_clear,
            plugin.cmd_heartflow_log, plugin.cmd_heartflow_reset, plugin.cmd_heartflow_help,
        )
        for handler in handlers:
            items = collect(handler(FakeEvent("/heartflow")))
            self.assertEqual(items[0]["plain"], "心流引擎未加载", handler.__name__)
        self.assertEqual(plugin.ready_calls, 6)

    def test_with_engine(self):
        plugin = make_plugin()
        plugin.heartflow = FakeHeartflow()
        pairs = (
            (plugin.cmd_heartflow, "status"),
            (plugin.cmd_heartflow_debug, "debug"),
            (plugin.cmd_heartflow_clear, "clear"),
            (plugin.cmd_heartflow_log, "toggle"),
            (plugin.cmd_heartflow_reset, "reset"),
            (plugin.cmd_heartflow_help, "help"),
        )
        for handler, expected in pairs:
            self.assertEqual(collect(handler(FakeEvent("/heartflow"))), [expected])


async def _async(value):
    return value


if __name__ == "__main__":
    unittest.main()
