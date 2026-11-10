# -*- coding: utf-8 -*-
"""amo_runtime：消息钩子 / 后台单步 / 事件分发 / 里程碑与每日总结。

后台循环不真的跑起来（先 sleep 4 秒再无限转）：这里只按单步调用，
`_tick()` 就是后台循环的一轮，`_background_loop()` 用假 sleep 跑一圈就退出。
每条断言都落在状态机变化、返回值或落库副作用上，不是「没抛异常」。

装配用真的 `HumanCorePlugin`（和 test_plugin_boot 一样），这样钩子里调到的
其它 mixin 方法都是真实现；只在「外部世界」的边界上打桩：
- `_spawn`：记下协程名后 close，不起悬挂 task；
- 数据插件（Astr_Amo_data）的 mem 门面：假对象；
- 分段引擎 / LLM：发送与模型调用是外部副作用，用假对象；
- `_maybe_follow_city` / `_maybe_wander` / `_write_memory_checked`：别的模块的入口。
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import astrbot_stub  # noqa: E402

astrbot_stub.install()

import amo_message  # noqa: E402
import amo_runtime  # noqa: E402
import main  # noqa: E402
from astrbot.api.message_components import At, Plain, Reply  # noqa: E402
from astrbot.api.star import Context  # noqa: E402
from amo_shared import now_ts, today_str  # noqa: E402

QQ_UMO = "qq:FriendMessage:302578963"
GROUP_UMO = "qq:GroupMessage:100200"
UID = "302578963"


# --------------------------------------------------------------------------
# 假事件 / 假结果 / 假外部引擎
# --------------------------------------------------------------------------


class FakeResult:
    def __init__(self, chain=None, llm=True, boom=False):
        self.chain = list(chain or [])
        self._llm = llm
        self._boom = boom

    def is_llm_result(self):
        if self._boom:
            raise RuntimeError("is_llm_result 不可用")
        return self._llm


class FakeEvent:
    """够 amo_runtime 用的事件；不模拟平台行为。"""

    def __init__(self, text="在吗", private=True, umo=QQ_UMO, message_id="m1",
                 components=None, extra=None, result=None, send=None):
        self.message_str = text
        self.unified_msg_origin = umo
        self._private = private
        self.message_obj = types.SimpleNamespace(
            message=list(components or []), message_id=message_id)
        self._extra = dict(extra or {})
        self.result = result
        self.sent = []
        self._send = send
        self.sender_name = "阿明"
        self.sender_id = UID
        self.self_id = "10001"

    # ---- 事件接口 ----
    def is_private_chat(self):
        return self._private

    def get_sender_id(self):
        return self.sender_id

    def get_sender_name(self):
        return self.sender_name

    def get_self_id(self):
        return self.self_id

    def get_group_id(self):
        return "100200"

    def get_platform_name(self):
        return "aiocqhttp"

    def get_extra(self, key):
        return self._extra.get(key)

    def get_result(self):
        return self.result

    async def send(self, chain):
        if self._send is not None:
            return self._send(chain)
        self.sent.append(chain)
        return None


class BadEvent(FakeEvent):
    """取自身 id 会炸的事件：验证 _self_identity 的容错。"""

    def get_self_id(self):
        raise RuntimeError("平台不给 id")


class FakeSegment:
    def __init__(self, handled=True, boom=False):
        self.handled = handled
        self.boom = boom
        self.calls = []

    async def handle_segment_reply(self, event, quote_id=None, group=False, force=False):
        self.calls.append({"quote_id": quote_id, "group": group, "force": force})
        if self.boom:
            raise RuntimeError("分段引擎炸了")
        return self.handled


class FakeMem:
    """Astr_Amo_data 的 mem 门面。"""

    def __init__(self, messages=None, since_rows=None, remember_ok=True):
        self.messages = list(messages or [])
        self.since_rows = list(since_rows or [])
        self.remember_ok = remember_ok
        self.calls = []
        self.written = []

    async def messages_since(self, bot_id, uid, since, limit, umo=""):
        self.calls.append(("messages_since", uid, since, umo))
        return list(self.since_rows)

    async def recall_messages(self, bot_id, query="", umo="", limit=150):
        self.calls.append(("recall_messages", query, umo))
        return {"messages": list(self.messages)}

    async def remember(self, bot_id, uid, content, kind="fact", importance=0.5):
        self.written.append((uid, content, kind, importance))
        return {"ok": self.remember_ok}


class FakeKB:
    def __init__(self, text="黔灵山：早上人少"):
        self.text = text
        self.queries = []

    async def get_kb_by_name(self, name):
        return {"name": name}

    async def retrieve(self, query, names, top_m_final=4):
        self.queries.append((query, list(names), top_m_final))
        return {"context_text": self.text}


# --------------------------------------------------------------------------
# 装配基类
# --------------------------------------------------------------------------


class RuntimeCase(unittest.TestCase):
    config: dict | None = None

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="amo-runtime-")
        self._saved = {}
        for name in ("astrbot.core.utils", "astrbot.core.utils.astrbot_path"):
            self._saved[name] = sys.modules.get(name)
            module = types.ModuleType(name)
            module.__path__ = []
            sys.modules[name] = module
        path_module = types.ModuleType("astrbot.core.utils.astrbot_path")
        path_module.get_astrbot_data_path = lambda: self.tmp
        sys.modules["astrbot.core.utils.astrbot_path"] = path_module
        self.plugin = self.boot(self.config or {})

    def boot(self, config):
        """真的 new 一个插件并把 _ensure_ready 跑完；_spawn 只记名字不起 task。"""
        plugin = main.HumanCorePlugin(Context(), dict(config))
        spawned = []

        def spawn(coro):
            spawned.append(getattr(getattr(coro, "cr_code", None), "co_name", "?"))
            coro.close()  # 不留悬挂 task
            return None

        plugin._spawn = spawn
        plugin.spawned = spawned
        asyncio.run(plugin._ensure_ready())
        self.assertTrue(plugin._ready)
        return plugin

    def tearDown(self) -> None:
        try:
            self.plugin.db.conn.close()
        except Exception:
            pass
        for name, module in self._saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    # ---- 小工具 ----
    def add_profile(self, uid=UID, relation="相恋", private_umo=QQ_UMO, name="阿明"):
        if private_umo:
            self.plugin.db.touch_profile(uid, name, "qq", private_umo, "", True)
        else:
            self.plugin.db.touch_profile(uid, name, "qq", "qq:GroupMessage:1", "qq:GroupMessage:1", False)
        if relation:
            self.plugin.db.update_profile(uid, relation=relation)
        return self.plugin.db.get_profile(uid)

    def install_data_plugin(self, mem, store=None):
        star = types.SimpleNamespace(mem=mem, store=store)
        meta = types.SimpleNamespace(star_cls=star, name="Astr_Amo_data",
                                     module_path="data.astrbot_plugin_amo_data")
        self.plugin.context = types.SimpleNamespace(
            get_registered_star=lambda name: meta,
            get_all_stars=lambda: [meta],
            get_config=lambda: {},
        )
        return star

    def context_text(self, event):
        return asyncio.run(self.plugin._dynamic_context(event))


# --------------------------------------------------------------------------
# _self_identity
# --------------------------------------------------------------------------


class SelfIdentityTests(RuntimeCase):
    def test_role_name_and_fallback_nick(self) -> None:
        role, uid, nick, display = asyncio.run(self.plugin._self_identity(FakeEvent()))
        self.assertEqual(role, self.plugin.bot_name)
        self.assertEqual(uid, "10001")
        # 拿不到真实 QQ 昵称时用角色名兜底，但不许写进缓存
        self.assertEqual(nick, role)
        self.assertEqual(display, nick)
        self.assertFalse(getattr(self.plugin, "_self_nickname_uid", ""))

    def test_display_name_from_event_is_used_but_not_cached(self) -> None:
        event = FakeEvent()
        event.get_self_name = lambda: "小小鱼"
        role, uid, nick, display = asyncio.run(self.plugin._self_identity(event))
        self.assertEqual(display, "小小鱼")
        self.assertEqual(nick, "小小鱼")
        self.assertFalse(getattr(self.plugin, "_self_nickname_uid", ""))

    def test_login_info_dict_cached(self) -> None:
        event = FakeEvent()

        def call_action(name, **kwargs):
            if name == "get_login_info":
                return {"data": {"nickname": "机器人小号", "user_id": 555}}
            raise AssertionError("不该走到 " + name)

        event.bot = types.SimpleNamespace(api=types.SimpleNamespace(call_action=call_action))
        role, uid, nick, display = asyncio.run(self.plugin._self_identity(event))
        self.assertEqual(uid, "555")
        self.assertEqual(nick, "机器人小号")
        self.assertEqual(self.plugin._self_nickname, "机器人小号")
        self.assertEqual(self.plugin._self_nickname_uid, "555")
        self.assertEqual(self.plugin._self_display, "机器人小号")

    def test_login_info_awaitable(self) -> None:
        event = FakeEvent()

        async def call_action(name, **kwargs):
            if name == "get_login_info":
                return {"data": {"nickname": "异步小号", "user_id": 777}}
            raise AssertionError("不该走到 " + name)

        event.bot = types.SimpleNamespace(api=types.SimpleNamespace(call_action=call_action))
        _, uid, nick, _ = asyncio.run(self.plugin._self_identity(event))
        self.assertEqual((uid, nick), ("777", "异步小号"))

    def test_stranger_info_when_login_has_no_nickname(self) -> None:
        event = FakeEvent()
        seen = []

        def call_action(name, **kwargs):
            seen.append((name, kwargs))
            if name == "get_login_info":
                return {"data": {"user_id": 888}}
            if name == "get_stranger_info":
                return {"data": {"nickname": "陌生人昵称"}}
            raise AssertionError("不该走到 " + name)

        event.bot = types.SimpleNamespace(api=types.SimpleNamespace(call_action=call_action))
        _, uid, nick, _ = asyncio.run(self.plugin._self_identity(event))
        self.assertEqual(uid, "888")
        self.assertEqual(nick, "陌生人昵称")
        self.assertEqual(seen[-1][0], "get_stranger_info")
        self.assertEqual(seen[-1][1].get("user_id"), 888)

    def test_cached_nickname_skips_api(self) -> None:
        self.plugin._self_nickname_uid = "10001"
        self.plugin._self_nickname = "缓存昵称"
        event = FakeEvent()
        event.bot = types.SimpleNamespace(
            api=types.SimpleNamespace(call_action=lambda *a, **k: 1 / 0))
        _, _, nick, display = asyncio.run(self.plugin._self_identity(event))
        self.assertEqual(nick, "缓存昵称")
        # display_name 仍然回退成 qq_nick
        self.assertEqual(display, "缓存昵称")

    def test_bad_self_id_does_not_raise(self) -> None:
        role, uid, nick, _ = asyncio.run(self.plugin._self_identity(BadEvent()))
        self.assertEqual(uid, "")
        self.assertEqual(nick, role)

    def test_identity_logged_once_per_value(self) -> None:
        event = FakeEvent()
        asyncio.run(self.plugin._self_identity(event))
        first = self.plugin._self_identity_logged
        self.assertIn("|", first)
        asyncio.run(self.plugin._self_identity(event))
        self.assertEqual(self.plugin._self_identity_logged, first)


# --------------------------------------------------------------------------
# _lean_parts
# --------------------------------------------------------------------------


class LeanPartsTests(RuntimeCase):
    def test_full_style_returns_same_list(self) -> None:
        self.plugin.config["context_style"] = "full"
        parts = ["【昵称区分】长版", "【别编】长版", "别的"]
        out = self.plugin._lean_parts(parts)
        self.assertIs(out, parts)

    def test_lean_style_drops_and_replaces(self) -> None:
        self.plugin.config["context_style"] = "lean"
        dropped = "【昵称区分】这一整段会被删掉"
        out = self.plugin._lean_parts([dropped, "【别编】长版禁令", "【自造】原样保留", 42])
        self.assertEqual(len(out), 3)
        self.assertNotIn(dropped, out)
        self.assertEqual(out[0], self.plugin.LEAN_PARTS["【别编】"])
        self.assertIn("对方没明说", out[0])
        self.assertEqual(out[1], "【自造】原样保留")
        self.assertEqual(out[2], 42)

    def test_unclosed_bracket_is_kept(self) -> None:
        self.plugin.config["context_style"] = "lean"
        out = self.plugin._lean_parts(["【别编"])
        self.assertEqual(out, ["【别编"])


# --------------------------------------------------------------------------
# _dynamic_context：私聊
# --------------------------------------------------------------------------


class DynamicContextPrivateTests(RuntimeCase):
    def test_baseline_private_context(self) -> None:
        self.add_profile()
        text = self.context_text(FakeEvent("在吗"))
        self.assertIn("【你的角色名】" + self.plugin.bot_name, text)
        self.assertIn("【对方】QQ昵称：阿明", text)
        self.assertIn("【身份区分】", text)
        self.assertIn("【时间】", text)
        self.assertIn("【心情】", text)
        self.assertIn("【正在】", text)
        self.assertIn("【与对方关系】相恋", text)
        # 结尾那条硬规则必须在
        self.assertTrue(text.rstrip().endswith("晚点聊”。"))

    def test_unknown_sender_still_renders(self) -> None:
        text = self.context_text(FakeEvent("在吗"))
        self.assertIn("【对方】QQ昵称：阿明", text)
        self.assertIn("【与对方关系】普通", text)

    def test_consult_question_gets_style_hint(self) -> None:
        text = self.context_text(FakeEvent("怎么才能早点睡"))
        self.assertIn("【回答方式】", text)

    def test_plain_chat_has_no_consult_hint(self) -> None:
        text = self.context_text(FakeEvent("今天有点累"))
        self.assertNotIn("【回答方式】", text)

    def test_diary_question_adds_diary_block(self) -> None:
        text = self.context_text(FakeEvent("今天写日记了吗"))
        self.assertIn("【日记】", text)
        self.assertIn("不要主动跟他提日记", text)

    def test_amusement_question_not_diary(self) -> None:
        text = self.context_text(FakeEvent("今天有点累"))
        self.assertNotIn("【日记】", text)

    def test_weather_query_block(self) -> None:
        text = self.context_text(FakeEvent("今天天气怎么样"))
        self.assertIn("【天气怎么答】", text)

    def test_weather_query_can_be_disabled(self) -> None:
        self.plugin.config["weather_query_enabled"] = False
        text = self.context_text(FakeEvent("今天天气怎么样"))
        self.assertNotIn("【天气怎么答】", text)

    def test_scenic_question_uses_kb(self) -> None:
        kb = FakeKB("某景区：秋天最好")
        self.plugin.context.kb_manager = kb
        text = self.context_text(FakeEvent("这边有什么好玩的地方"))
        self.assertIn("【景区参考】", text)
        self.assertIn("某景区：秋天最好", text)
        self.assertTrue(kb.queries)

    def test_dialect_block_when_enabled(self) -> None:
        self.plugin.config["dialect_style"] = "贵州话"
        self.plugin.config["dialect_enabled"] = True
        text = self.context_text(FakeEvent("在吗"))
        self.assertIn("【方言】你的语种设定是「贵州话」", text)

    def test_dialect_block_absent_when_disabled(self) -> None:
        self.plugin.config["dialect_style"] = "普通话"
        text = self.context_text(FakeEvent("在吗"))
        self.assertNotIn("【方言】你的语种设定是", text)

    def test_dialect_reference_from_kb(self) -> None:
        self.plugin.config["dialect_style"] = "贵州话"
        self.plugin.config["dialect_enabled"] = True
        self.plugin.context.kb_manager = FakeKB("「安逸」= 舒服")
        text = self.context_text(FakeEvent("在吗"))
        self.assertIn("【方言参考】", text)
        self.assertIn("「安逸」= 舒服", text)

    def test_his_city_block(self) -> None:
        self.plugin.db.kv_set("his_city", "杭州")
        text = self.context_text(FakeEvent("在吗"))
        self.assertIn("杭州", text)

    def test_travel_block(self) -> None:
        self.plugin.db.kv_set("travel", {"city": "北京", "start_day": today_str()})
        text = self.context_text(FakeEvent("在吗"))
        self.assertIn("北京", text)

    def test_he_is_elsewhere_block(self) -> None:
        self.plugin.db.kv_set("his_city", "东莞")
        self.plugin.db.kv_set("he_city", "上海")
        text = self.context_text(FakeEvent("在吗"))
        self.assertIn("【他在】他现在在 上海", text)

    def test_he_is_elsewhere_skipped_while_travelling(self) -> None:
        self.plugin.db.kv_set("his_city", "东莞")
        self.plugin.db.kv_set("he_city", "上海")
        self.plugin.db.kv_set("travel", {"city": "北京", "start_day": today_str()})
        text = self.context_text(FakeEvent("在吗"))
        self.assertNotIn("【他在】", text)

    def test_lover_anger_block(self) -> None:
        self.add_profile(relation="相恋")
        self.plugin.state.mood["暴躁"] = 70.0
        text = self.context_text(FakeEvent("在吗"))
        self.assertIn("【恋人情绪】", text)

    def test_lover_anger_block_requires_relation(self) -> None:
        self.add_profile(relation="普通")
        self.plugin.state.mood["暴躁"] = 90.0
        text = self.context_text(FakeEvent("在吗"))
        self.assertNotIn("【恋人情绪】", text)

    def test_impersonation_warning(self) -> None:
        event = FakeEvent("在吗")
        event.amo_impersonation = True
        text = self.context_text(event)
        self.assertIn("【冒充警告】", text)

    def test_bot_initiated_turns_off_disturb(self) -> None:
        self.plugin._bot_initiated[QQ_UMO] = now_ts()
        text = self.context_text(FakeEvent("在吗"))
        self.assertIn("【你主动发起】", text)

    def test_identity_challenge_block(self) -> None:
        text = self.context_text(FakeEvent("你是不是AI啊"))
        self.assertIn("【身份质疑】", text)

    def test_identity_challenge_absent_for_normal_chat(self) -> None:
        text = self.context_text(FakeEvent("今天吃了碗面"))
        self.assertNotIn("【身份质疑】", text)

    def test_disturb_blocks_for_stranger(self) -> None:
        self.plugin._disturb_until[QQ_UMO] = now_ts() + 600
        text = self.context_text(FakeEvent("在吗"))
        self.assertIn("【被打扰】", text)
        self.assertIn("对不熟的人会直接怼", text)

    def test_disturb_blocks_for_lover(self) -> None:
        self.add_profile(relation="相恋")
        self.plugin._disturb_until[QQ_UMO] = now_ts() + 600
        text = self.context_text(FakeEvent("在吗"))
        self.assertIn("对亲近的人会抱怨", text)

    def test_depressed_block(self) -> None:
        self.plugin.db.kv_set("proactive_depressed_until_" + UID, now_ts() + 3600)
        text = self.context_text(FakeEvent("在吗"))
        self.assertIn("【低落】", text)

    def test_depressed_expired_is_skipped(self) -> None:
        self.plugin.db.kv_set("proactive_depressed_until_" + UID, now_ts() - 3600)
        text = self.context_text(FakeEvent("在吗"))
        self.assertNotIn("【低落】", text)

    def test_remember_alias_request(self) -> None:
        text = self.context_text(FakeEvent("记住，以后叫他阿明"))
        self.assertIn("【识人回应】", text)

    def test_weather_alert_already_sent_today(self) -> None:
        self.plugin.db.kv_set("weather_alert_open", today_str())
        text = self.context_text(FakeEvent("在吗"))
        self.assertIn("【天气提醒之后】", text)

    def test_weather_alert_note_only_in_private(self) -> None:
        self.plugin.db.kv_set("weather_alert_open", today_str())
        text = self.context_text(FakeEvent("群友在聊", private=False, umo=GROUP_UMO))
        self.assertNotIn("【天气提醒之后】", text)

    def test_debounce_merge_count(self) -> None:
        text = self.context_text(FakeEvent("在吗", extra={"amo_debounce_count": 3}))
        self.assertIn("对方在几秒内连发了 3 条", text)

    def test_single_message_has_no_merge_note(self) -> None:
        text = self.context_text(FakeEvent("在吗", extra={"amo_debounce_count": 1}))
        self.assertNotIn("【连发合并】", text)

    def test_recent_reply_note(self) -> None:
        self.plugin._last_reply_at[QQ_UMO] = now_ts() - 30
        text = self.context_text(FakeEvent("在吗"))
        self.assertIn("【刚答过】", text)

    def test_old_reply_has_no_recent_note(self) -> None:
        self.plugin._last_reply_at[QQ_UMO] = now_ts() - 600
        text = self.context_text(FakeEvent("在吗"))
        self.assertNotIn("【刚答过】", text)

    def test_gift_hint_appended(self) -> None:
        class FakeGift:
            async def build_hint(self, event):
                return "【逛街】他上次说想要围巾"

        self.plugin.gift = FakeGift()
        text = self.context_text(FakeEvent("在吗"))
        self.assertIn("【逛街】他上次说想要围巾", text)

    def test_gift_hint_failure_is_ignored(self) -> None:
        class BoomGift:
            async def build_hint(self, event):
                raise RuntimeError("礼物引擎炸了")

        self.plugin.gift = BoomGift()
        text = self.context_text(FakeEvent("在吗"))
        self.assertIn("【你的角色名】", text)
        self.assertNotIn("【逛街】", text)

    def test_first_person_experience_block(self) -> None:
        text = self.context_text(FakeEvent("我在楼下吃了碗面"))
        self.assertIn("【归属】他刚说的", text)
        self.assertIn("是他自己的经历", text)

    def test_attribution_alert_memory(self) -> None:
        self.plugin._attribution_alert[QQ_UMO] = now_ts() - 60
        text = self.context_text(FakeEvent("在吗"))
        self.assertIn("上一轮你把他的经历说成了自己的", text)

    def test_recent_conversation_block(self) -> None:
        self.plugin.db.add_message(QQ_UMO, UID, "阿明", "user", "刚才说要去买菜")
        self.plugin.db.add_message(QQ_UMO, "bot", self.plugin.bot_name, "bot", "好，我去做饭")
        text = self.context_text(FakeEvent("你刚才说过什么"))
        self.assertIn("【最近对话】", text)
        self.assertIn("好，我去做饭", text)

    def test_follow_and_wander_text_appended(self) -> None:
        async def follow(event, uid, profile):
            return "【邀请】他叫你一起回杭州"

        async def wander(event, uid, profile):
            return "【旅游】她想周末去海边"

        self.plugin._maybe_follow_city = follow
        self.plugin._maybe_wander = wander
        text = self.context_text(FakeEvent("在吗"))
        self.assertIn("【邀请】他叫你一起回杭州", text)
        self.assertIn("【旅游】她想周末去海边", text)

    def test_follow_failure_is_swallowed(self) -> None:
        async def follow(event, uid, profile):
            raise RuntimeError("城市跟随炸了")

        self.plugin._maybe_follow_city = follow
        text = self.context_text(FakeEvent("在吗"))
        self.assertIn("【你的角色名】", text)
        self.assertNotIn("【邀请】", text)


# --------------------------------------------------------------------------
# _dynamic_context：群聊
# --------------------------------------------------------------------------


class DynamicContextGroupTests(RuntimeCase):
    def group_event(self, text="今天这局打得不错", **kwargs):
        return FakeEvent(text, private=False, umo=GROUP_UMO, **kwargs)

    def seed_group_speakers(self, count):
        for index in range(count):
            uid = str(9000 + index)
            self.plugin.db.add_message(GROUP_UMO, uid, "群友%d" % index, "user",
                                       "第 %d 句" % index)

    def test_group_addressed_by_at(self) -> None:
        event = self.group_event("你看这个")
        event.is_at_or_wake_command = True
        text = self.context_text(event)
        self.assertIn("【群聊·对你说】", text)
        self.assertIn("【群聊称呼】", text)
        self.assertNotIn("【群聊·插话】", text)

    def test_group_heartflow_interject(self) -> None:
        event = self.group_event("今天这局打得不错")
        event.heartflow_mode_hint = "interject"
        event.heartflow_angle = "夸一句他们配合得好"
        text = self.context_text(event)
        self.assertIn("【群聊·插话】", text)
        self.assertIn("夸一句他们配合得好", text)

    def test_group_target_bot_is_direct(self) -> None:
        event = self.group_event("你看这个")
        event.heartflow_target = "bot"
        text = self.context_text(event)
        self.assertIn("【群聊·对你说】", text)

    def test_group_plain_chat_has_think_first_hint(self) -> None:
        text = self.context_text(self.group_event("他们俩在聊游戏"))
        self.assertIn("【群聊】这是群聊", text)
        self.assertIn("【先想再回】", text)

    def test_group_direct_skips_think_first_hint(self) -> None:
        event = self.group_event("你看这个")
        event.is_at_or_wake_command = True
        text = self.context_text(event)
        self.assertNotIn("【先想再回】", text)

    def test_group_speaker_count_block(self) -> None:
        self.seed_group_speakers(3)
        text = self.context_text(self.group_event("他们在聊什么"))
        self.assertIn("最近十分钟有 3 个人在说话", text)

    def test_group_speaker_threshold_adds_quiet_hint(self) -> None:
        self.plugin.config["quote_group_speaker_threshold"] = 2
        self.seed_group_speakers(3)
        text = self.context_text(self.group_event("他们在聊什么"))
        self.assertIn("人多、消息刷得快", text)

    def test_group_roster_block(self) -> None:
        self.seed_group_speakers(2)
        self.plugin.db.update_profile("9000", relation="熟识")
        text = self.context_text(self.group_event("他们在聊什么"))
        self.assertIn("【群里的人】", text)
        self.assertIn("群友0", text)

    def test_group_dialect_and_weather_still_apply(self) -> None:
        text = self.context_text(self.group_event("今天天气怎么样"))
        self.assertIn("【天气怎么答】", text)

    def test_private_has_no_group_blocks(self) -> None:
        text = self.context_text(FakeEvent("在吗"))
        self.assertNotIn("【群聊", text)
        self.assertNotIn("【群里的人】", text)


# --------------------------------------------------------------------------
# on_after_message_sent
# --------------------------------------------------------------------------


class AfterMessageSentTests(RuntimeCase):
    def test_records_last_reply_time(self) -> None:
        before = now_ts()
        event = FakeEvent()
        asyncio.run(self.plugin.on_after_message_sent(event))
        self.assertGreaterEqual(self.plugin._last_reply_at[QQ_UMO], before)

    def test_forwards_to_heartflow(self) -> None:
        seen = []

        class FakeHeartflow:
            async def on_after_message_sent(self, event):
                seen.append(event)

        event = FakeEvent()
        self.plugin.heartflow = FakeHeartflow()
        asyncio.run(self.plugin.on_after_message_sent(event))
        self.assertEqual(seen, [event])

    def test_heartflow_failure_is_swallowed(self) -> None:
        class BoomHeartflow:
            async def on_after_message_sent(self, event):
                raise RuntimeError("心流炸了")

        self.plugin.heartflow = BoomHeartflow()
        asyncio.run(self.plugin.on_after_message_sent(FakeEvent()))
        self.assertIn(QQ_UMO, self.plugin._last_reply_at)

    def test_no_heartflow_still_records(self) -> None:
        self.plugin.heartflow = None
        asyncio.run(self.plugin.on_after_message_sent(FakeEvent()))
        self.assertIn(QQ_UMO, self.plugin._last_reply_at)


# --------------------------------------------------------------------------
# on_message
# --------------------------------------------------------------------------


class OnMessageTests(RuntimeCase):
    def test_dispatches_to_handler(self) -> None:
        seen = []

        async def handler(event):
            seen.append(event)

        self.plugin._handle_message = handler
        event = FakeEvent()
        asyncio.run(self.plugin.on_message(event))
        self.assertEqual(seen, [event])

    def test_handler_exception_does_not_break_next_event(self) -> None:
        seen = []

        async def handler(event):
            seen.append(event.message_str)
            if event.message_str == "炸":
                raise RuntimeError("处理失败")

        self.plugin._handle_message = handler
        asyncio.run(self.plugin.on_message(FakeEvent("炸")))
        asyncio.run(self.plugin.on_message(FakeEvent("好的")))
        self.assertEqual(seen, ["炸", "好的"])

    def test_ensure_ready_failure_still_calls_handler(self) -> None:
        seen = []

        async def ready():
            raise RuntimeError("初始化失败")

        async def handler(event):
            seen.append(event)

        self.plugin._ensure_ready = ready
        self.plugin._handle_message = handler
        event = FakeEvent()
        asyncio.run(self.plugin.on_message(event))
        # 初始化炸了就不该再处理消息（错误被 on_message 吞掉）
        self.assertEqual(seen, [])


# --------------------------------------------------------------------------
# on_decorating_result
# --------------------------------------------------------------------------


class _ChainShim:
    """astrbot_stub 的 MessageChain 不接受参数，真 AstrBot 是接受 message 列表的。"""

    def __init__(self, chain=None):
        self.chain = list(chain or [])

    def message(self, text):
        self.chain.append(Plain(text))


class DecoratingResultTests(RuntimeCase):
    def setUp(self) -> None:
        super().setUp()
        self.segment = FakeSegment()
        self.plugin.segment_engine = self.segment
        # 只为对齐真 AstrBot 的 MessageChain(chain) 签名
        patcher = mock.patch.object(amo_message, "MessageChain", _ChainShim)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_hook(self, event):
        asyncio.run(self.plugin.on_decorating_result(event))

    def chain_text(self, result):
        return "".join(comp.text for comp in result.chain if isinstance(comp, Plain))

    def test_no_result_returns(self) -> None:
        event = FakeEvent()
        event.result = None
        self.run_hook(event)
        self.assertEqual(self.segment.calls, [])
        self.assertEqual(event.sent, [])

    def test_empty_chain_returns(self) -> None:
        event = FakeEvent(result=FakeResult([]))
        self.run_hook(event)
        self.assertEqual(self.segment.calls, [])

    def test_non_llm_result_returns(self) -> None:
        event = FakeEvent(result=FakeResult([Plain("插播一条")], llm=False))
        self.run_hook(event)
        self.assertEqual(self.chain_text(event.result), "插播一条")
        self.assertEqual(self.segment.calls, [])

    def test_is_llm_result_error_keeps_going(self) -> None:
        event = FakeEvent(result=FakeResult([Plain("继续说")], boom=True))
        self.run_hook(event)
        self.assertEqual(len(self.segment.calls), 1)
        self.assertEqual(self.chain_text(event.result), "继续说")

    def test_private_reply_component_stripped(self) -> None:
        event = FakeEvent(result=FakeResult([Reply(id="x1"), Plain("好呀")]))
        self.run_hook(event)
        self.assertFalse(any(isinstance(comp, Reply) for comp in event.result.chain))
        self.assertEqual(self.chain_text(event.result), "好呀")

    def test_group_keeps_quote_when_allowed(self) -> None:
        self.plugin.config["quote_group_probability"] = 1.0
        for index in range(3):
            self.plugin.db.add_message(GROUP_UMO, str(9000 + index), "群友", "user", "聊")
        event = FakeEvent("在吗", private=False, umo=GROUP_UMO,
                          result=FakeResult([Plain("好呀")]))
        self.run_hook(event)
        self.assertEqual(self.segment.calls[0]["quote_id"], "m1")
        self.assertTrue(self.segment.calls[0]["group"])

    def test_group_no_quote_for_small_group(self) -> None:
        self.plugin.config["quote_group_probability"] = 1.0
        event = FakeEvent("在吗", private=False, umo=GROUP_UMO,
                          result=FakeResult([Plain("好呀")]))
        self.run_hook(event)
        self.assertIsNone(self.segment.calls[0]["quote_id"])

    def test_defensive_reply_replaced_in_group(self) -> None:
        event = FakeEvent("他们俩在聊游戏", private=False, umo=GROUP_UMO,
                          result=FakeResult([Plain("你才人机呢")]))
        self.run_hook(event)
        self.assertEqual(self.chain_text(event.result), "你们聊你们的，我不抢话。")

    def test_ai_admission_replaced_in_private(self) -> None:
        event = FakeEvent("在吗", result=FakeResult([Plain("我是AI助手")]))
        self.run_hook(event)
        self.assertEqual(self.chain_text(event.result), "你才人机呢，你见过这么会聊天的机器人吗？")

    def test_model_leak_replaced(self) -> None:
        event = FakeEvent("在吗", result=FakeResult([Plain("我接的是deepseek")]))
        self.run_hook(event)
        self.assertEqual(self.chain_text(event.result), "秘密，不告诉你。")

    def test_blank_text_returns_without_sending(self) -> None:
        event = FakeEvent(result=FakeResult([Plain("   ")]))
        self.run_hook(event)
        self.assertEqual(self.chain_text(event.result), "   ")
        self.assertEqual(self.segment.calls, [])

    def test_attribution_leak_marks_alert(self) -> None:
        event = FakeEvent("我在楼下吃了碗面",
                          result=FakeResult([Plain("我也吃了碗面")]))
        self.run_hook(event)
        self.assertIn(QQ_UMO, self.plugin._attribution_alert)

    def test_gift_engine_observes_reply(self) -> None:
        seen = []

        class FakeGift:
            def observe_reply(self, event, text):
                seen.append(text)

        self.plugin.gift = FakeGift()
        event = FakeEvent(result=FakeResult([Plain("好呀")]))
        self.run_hook(event)
        self.assertEqual(seen, ["好呀"])

    def test_gift_engine_failure_is_swallowed(self) -> None:
        class BoomGift:
            def observe_reply(self, event, text):
                raise RuntimeError("礼物引擎炸了")

        self.plugin.gift = BoomGift()
        event = FakeEvent(result=FakeResult([Plain("好呀")]))
        self.run_hook(event)
        self.assertEqual(self.chain_text(event.result), "好呀")

    def test_polish_native_uses_polished_text(self) -> None:
        self.plugin.config["polish_native"] = True

        async def persona(umo):
            return "人设"

        async def polish(umo, text, tone, **kwargs):
            return "润色之后的回复"

        self.plugin.llm.persona = persona
        self.plugin.llm.polish = polish
        event = FakeEvent("在吗", result=FakeResult([Plain("原话")]))
        self.run_hook(event)
        self.assertEqual(self.chain_text(event.result), "润色之后的回复")

    def test_polish_returns_same_text_keeps_original(self) -> None:
        self.plugin.config["polish_native"] = True

        async def persona(umo):
            return ""

        async def polish(umo, text, tone, **kwargs):
            return text

        self.plugin.llm.persona = persona
        self.plugin.llm.polish = polish
        event = FakeEvent("在吗", result=FakeResult([Plain("原话")]))
        self.run_hook(event)
        self.assertEqual(self.chain_text(event.result), "原话")

    def test_brushoff_removed(self) -> None:
        event = FakeEvent("在吗", result=FakeResult([Plain("好呀，你先忙吧。")]))
        self.run_hook(event)
        text = self.chain_text(event.result)
        self.assertNotIn("你先忙", text)
        self.assertIn("好呀", text)

    def test_segment_handled_keeps_chain(self) -> None:
        self.segment.handled = True
        event = FakeEvent(result=FakeResult([Plain("好呀")]))
        self.run_hook(event)
        self.assertEqual(len(self.segment.calls), 1)
        self.assertEqual(self.chain_text(event.result), "好呀")
        self.assertNotIn(QQ_UMO, self.plugin._last_bot_saved)

    def test_segment_not_handled_restores_and_remembers(self) -> None:
        self.segment.handled = False
        event = FakeEvent(result=FakeResult([Plain("好呀")]))
        self.run_hook(event)
        self.assertEqual(self.chain_text(event.result), "好呀")
        self.assertIn(QQ_UMO, self.plugin._last_bot_saved)
        self.assertEqual(self.plugin._last_bot_saved[QQ_UMO][0], "好呀")

    def test_segment_exception_restores_and_remembers(self) -> None:
        self.segment.boom = True
        event = FakeEvent(result=FakeResult([Plain("好呀")]))
        self.run_hook(event)
        self.assertEqual(self.chain_text(event.result), "好呀")
        self.assertIn(QQ_UMO, self.plugin._last_bot_saved)

    def test_at_component_allowed(self) -> None:
        event = FakeEvent(result=FakeResult([Plain("看这个"), At(qq="1")]))
        self.run_hook(event)
        self.assertEqual(len(self.segment.calls), 1)

    def test_unknown_component_returns_before_sending(self) -> None:
        junk = types.SimpleNamespace(kind="image")
        event = FakeEvent(result=FakeResult([Plain("图"), junk]))
        self.run_hook(event)
        self.assertEqual(self.segment.calls, [])
        self.assertIn(junk, event.result.chain)

    def test_takeover_sends_directly(self) -> None:
        self.plugin.segment_engine = None
        self.plugin.context = types.SimpleNamespace(
            get_config=lambda: {"platform_settings": {"reply_with_quote": True}})
        event = FakeEvent(result=FakeResult([Plain("好呀")]))
        self.run_hook(event)
        self.assertEqual(event.result.chain, [])
        self.assertEqual(len(event.sent), 1)
        self.assertEqual("".join(comp.text for comp in event.sent[0].chain), "好呀")
        self.assertTrue(self.plugin._core_decor_logged)

    def test_takeover_send_failure_keeps_chain(self) -> None:
        self.plugin.segment_engine = None
        self.plugin.context = types.SimpleNamespace(
            get_config=lambda: {"platform_settings": {"reply_with_mention": True}})

        def boom(chain):
            raise RuntimeError("发送失败")

        event = FakeEvent(result=FakeResult([Plain("好呀")]), send=boom)
        self.run_hook(event)
        self.assertEqual(self.chain_text(event.result), "好呀")
        self.assertIn(QQ_UMO, self.plugin._last_bot_saved)

    def test_seg_disabled_sends_directly(self) -> None:
        self.plugin.config["seg_enable"] = False
        self.plugin.context = types.SimpleNamespace(
            get_config=lambda: {"platform_settings": {"reply_with_quote": True}})
        event = FakeEvent(result=FakeResult([Plain("好呀")]))
        self.run_hook(event)
        self.assertEqual(event.result.chain, [])
        self.assertEqual(len(event.sent), 1)

    def test_seg_disabled_without_takeover_remembers(self) -> None:
        self.plugin.config["seg_enable"] = False
        event = FakeEvent(result=FakeResult([Plain("好呀")]))
        self.run_hook(event)
        self.assertEqual(self.chain_text(event.result), "好呀")
        self.assertIn(QQ_UMO, self.plugin._last_bot_saved)


# --------------------------------------------------------------------------
# _background_loop
# --------------------------------------------------------------------------


class BackgroundLoopTests(RuntimeCase):
    def test_one_round_then_stop(self) -> None:
        ticks = []
        self.plugin._running = True

        async def tick():
            ticks.append(1)
            self.plugin._running = False

        async def fake_sleep(delay):
            return None

        self.plugin._tick = tick
        with mock.patch.object(amo_runtime.asyncio, "sleep", fake_sleep):
            self.assertIsNone(asyncio.run(self.plugin._background_loop()))
        self.assertEqual(len(ticks), 1)

    def test_cancel_during_initial_sleep(self) -> None:
        ticks = []

        async def tick():
            ticks.append(1)

        async def cancel_sleep(delay):
            raise asyncio.CancelledError()

        self.plugin._tick = tick
        with mock.patch.object(amo_runtime.asyncio, "sleep", cancel_sleep):
            self.assertIsNone(asyncio.run(self.plugin._background_loop()))
        self.assertEqual(ticks, [])

    def test_cancel_inside_tick_exits(self) -> None:
        ticks = []

        async def tick():
            ticks.append(1)
            raise asyncio.CancelledError()

        async def fake_sleep(delay):
            return None

        self.plugin._tick = tick
        with mock.patch.object(amo_runtime.asyncio, "sleep", fake_sleep):
            self.assertIsNone(asyncio.run(self.plugin._background_loop()))
        self.assertEqual(len(ticks), 1)

    def test_tick_exception_is_logged_and_loop_continues(self) -> None:
        ticks = []

        async def tick():
            ticks.append(1)
            raise RuntimeError("这一轮炸了")

        state = {"n": 0}

        async def fake_sleep(delay):
            state["n"] += 1
            if state["n"] > 1:
                raise asyncio.CancelledError()
            return None

        self.plugin._tick = tick
        with mock.patch.object(amo_runtime.asyncio, "sleep", fake_sleep):
            self.assertIsNone(asyncio.run(self.plugin._background_loop()))
        self.assertEqual(len(ticks), 1)
        self.assertEqual(state["n"], 2)


# --------------------------------------------------------------------------
# _tick
# --------------------------------------------------------------------------


class TickTests(RuntimeCase):
    def test_tick_refreshes_world_state(self) -> None:
        self.add_profile()
        self.plugin.spawned.clear()
        asyncio.run(self.plugin._tick())
        # 后台任务真的被排了（这里只记名字，不跑）
        self.assertIn("_maybe_daily_diary", self.plugin.spawned)
        self.assertIn("_maybe_solo_return", self.plugin.spawned)
        self.assertIn("_maybe_milestone_archive", self.plugin.spawned)
        self.assertIn("_sync_with_data_plugin", self.plugin.spawned)
        # 状态副作用
        self.assertEqual(self.plugin.state.last_health_roll, today_str())
        self.assertIn(today_str(), self.plugin.state.schedule)
        self.assertEqual(self.plugin.db.kv_get("weather", {}).get("source"), "simulate")
        for attr in ("_last_purge", "_last_pending_check", "_last_relation_decay",
                     "_last_auto_learn", "_last_diary_check", "_last_milestone_check",
                     "_proactive_last", "_last_ritual"):
            self.assertGreater(getattr(self.plugin, attr), 0, attr)

    def test_tick_skips_when_not_ready(self) -> None:
        self.plugin._ready = False
        self.plugin.spawned.clear()
        asyncio.run(self.plugin._tick())
        self.assertEqual(self.plugin.spawned, [])
        self.assertEqual(self.plugin._last_purge, 0.0)

    def test_tick_switches_to_digest_when_data_probe_is_fresh(self) -> None:
        self.plugin._last_data_probe = now_ts()
        self.plugin.spawned.clear()
        asyncio.run(self.plugin._tick())
        self.assertIn("_maybe_daily_digest", self.plugin.spawned)
        self.assertNotIn("_sync_with_data_plugin", self.plugin.spawned)

    def test_digest_only_once_per_interval(self) -> None:
        self.plugin._last_data_probe = now_ts()
        asyncio.run(self.plugin._tick())          # 第一次：排 digest
        self.plugin.spawned.clear()
        asyncio.run(self.plugin._tick())          # 第二次：300 秒内不再排
        self.assertNotIn("_maybe_daily_digest", self.plugin.spawned)

    def test_data_sync_retries_when_data_plugin_appears(self) -> None:
        mem = FakeMem()
        self.install_data_plugin(mem)
        self.plugin._data_synced = False
        self.plugin._last_data_sync_try = 0.0
        self.plugin.spawned.clear()
        asyncio.run(self.plugin._tick())
        self.assertIn("_sync_with_data_plugin", self.plugin.spawned)
        self.assertGreater(self.plugin._last_data_sync_try, 0)

    def test_data_sync_retry_is_throttled(self) -> None:
        mem = FakeMem()
        self.install_data_plugin(mem)
        self.plugin._data_synced = False
        self.plugin._last_data_sync_try = now_ts()
        self.plugin.spawned.clear()
        asyncio.run(self.plugin._tick())
        self.assertNotIn("_sync_with_data_plugin", self.plugin.spawned)

    def test_late_night_saves_schedule_once(self) -> None:
        self.add_profile()
        night = datetime(2026, 1, 1, 23, 59)
        with mock.patch.object(amo_runtime, "_now", lambda: night):
            asyncio.run(self.plugin._tick())
            self.assertEqual(self.plugin._last_schedule_save, today_str())
            saved = self.plugin.db.get_schedule(today_str())
            self.assertTrue(saved)
            self.assertEqual(len(saved), len(self.plugin.state.schedule[today_str()]))
            # 同一分钟内再跑一轮：不重复保存
            self.plugin.state.schedule[today_str()] = [
                {"start": "00:00", "end": "24:00", "activity": "改过的", "place": "家",
                 "category": "rest"}]
            asyncio.run(self.plugin._tick())
            self.assertNotEqual(self.plugin.db.get_schedule(today_str())[0]["activity"], "改过的")


# --------------------------------------------------------------------------
# _first_private_umo / _maybe_milestone_archive
# --------------------------------------------------------------------------


class FirstPrivateUmoTests(RuntimeCase):
    def test_empty_without_profiles(self) -> None:
        self.assertEqual(self.plugin._first_private_umo(), "")

    def test_returns_first_private_umo(self) -> None:
        self.add_profile(private_umo="")
        self.add_profile(uid="2222", private_umo="lark:FriendMessage:2222")
        self.assertEqual(self.plugin._first_private_umo(), "lark:FriendMessage:2222")


class MilestoneLockTests(RuntimeCase):
    def test_reentrant_call_is_skipped(self) -> None:
        calls = []

        async def once():
            calls.append(1)

        self.plugin._milestone_archive_once = once
        self.plugin._milestone_running = True
        asyncio.run(self.plugin._maybe_milestone_archive())
        self.assertEqual(calls, [])
        self.assertTrue(self.plugin._milestone_running)

    def test_lock_released_after_run(self) -> None:
        calls = []

        async def once():
            calls.append(1)

        self.plugin._milestone_archive_once = once
        asyncio.run(self.plugin._maybe_milestone_archive())
        self.assertEqual(calls, [1])
        self.assertFalse(self.plugin._milestone_running)

    def test_lock_released_after_exception(self) -> None:
        async def boom():
            raise RuntimeError("归档炸了")

        self.plugin._milestone_archive_once = boom
        with self.assertRaises(RuntimeError):
            asyncio.run(self.plugin._maybe_milestone_archive())
        self.assertFalse(self.plugin._milestone_running)


# --------------------------------------------------------------------------
# _milestone_archive_once
# --------------------------------------------------------------------------


class MilestoneTests(RuntimeCase):
    config = {"milestone_enabled": True, "milestone_every_turns": 2,
              "milestone_min_messages": 4}

    def setUp(self) -> None:
        super().setUp()
        self.mem = FakeMem()
        self.install_data_plugin(self.mem)
        self.add_profile(relation="相恋", private_umo=QQ_UMO)
        self.now = datetime(2026, 1, 2, 10, 0)
        self.written = []

        async def write(uid, content, kind="fact", tier=1):
            self.written.append((uid, content, kind, tier))
            return True

        self.plugin._write_memory_checked = write
        self.summary = "他最近在赶项目，周末约好一起看电影。"

        async def chat_raw(umo, system, prompt):
            self.last_prompt = prompt
            return self.summary

        self.plugin.llm.chat_raw = chat_raw

    def pair_rows(self, pairs=2):
        rows = []
        stamp = now_ts()
        for index in range(pairs):
            rows.append({"role": "user", "content": "他第 %d 句" % index,
                         "created_at": int(stamp) + index * 2})
            rows.append({"role": "bot", "content": "我第 %d 句" % index,
                         "created_at": int(stamp) + index * 2 + 1})
        return rows

    def test_disabled_does_nothing(self) -> None:
        self.plugin.config["milestone_enabled"] = False
        asyncio.run(self.plugin._milestone_archive_once())
        self.assertEqual(self.mem.calls, [])

    def test_no_data_plugin_returns(self) -> None:
        self.plugin.context = types.SimpleNamespace(
            get_registered_star=lambda name: None, get_all_stars=lambda: [],
            get_config=lambda: {})
        self.plugin._milestone_running = False
        asyncio.run(self.plugin._milestone_archive_once())
        self.assertEqual(self.mem.calls, [])

    def test_first_run_sets_baseline_only(self) -> None:
        self.mem.since_rows = self.pair_rows()
        asyncio.run(self.plugin._milestone_archive_once())
        self.assertGreater(self.plugin.db.kv_get("milestone_ts:" + UID, 0), 0)
        self.assertEqual(self.written, [])

    def test_not_enough_rows_skips(self) -> None:
        self.plugin.db.kv_set("milestone_ts:" + UID, now_ts() - 100)
        self.mem.since_rows = [{"role": "user", "content": "只有一句", "created_at": now_ts()}]
        asyncio.run(self.plugin._milestone_archive_once())
        self.assertEqual(self.written, [])

    def test_archives_and_advances_cursor(self) -> None:
        since = now_ts() - 100
        self.plugin.db.kv_set("milestone_ts:" + UID, since)
        rows = self.pair_rows()
        self.mem.since_rows = rows
        with mock.patch.object(amo_runtime, "_now", lambda: self.now):
            asyncio.run(self.plugin._milestone_archive_once())
        self.assertEqual(len(self.written), 1)
        uid, content, kind, tier = self.written[0]
        self.assertEqual((uid, kind, tier), (UID, "milestone", 2))
        self.assertIn("【里程碑 2026-01-02】", content)
        self.assertIn("他最近在赶项目", content)
        self.assertIn("2026-01-02", self.last_prompt)
        self.assertEqual(self.plugin.db.kv_get("milestone_ts:" + UID), rows[-1]["created_at"] + 1)

    def test_short_summary_keeps_cursor(self) -> None:
        since = now_ts() - 100
        self.plugin.db.kv_set("milestone_ts:" + UID, since)
        self.mem.since_rows = self.pair_rows()
        self.summary = "短"
        asyncio.run(self.plugin._milestone_archive_once())
        self.assertEqual(self.written, [])
        self.assertEqual(self.plugin.db.kv_get("milestone_ts:" + UID), since)

    def test_llm_failure_keeps_cursor(self) -> None:
        since = now_ts() - 100
        self.plugin.db.kv_set("milestone_ts:" + UID, since)

        async def boom(umo, system, prompt):
            raise RuntimeError("模型炸了")

        self.plugin.llm.chat_raw = boom
        self.mem.since_rows = self.pair_rows()
        asyncio.run(self.plugin._milestone_archive_once())
        self.assertEqual(self.written, [])
        self.assertEqual(self.plugin.db.kv_get("milestone_ts:" + UID), since)

    def test_write_failure_keeps_cursor(self) -> None:
        since = now_ts() - 100
        self.plugin.db.kv_set("milestone_ts:" + UID, since)

        async def write(uid, content, kind="fact", tier=1):
            self.written.append((uid, content, kind, tier))
            return False

        self.plugin._write_memory_checked = write
        self.mem.since_rows = self.pair_rows()
        asyncio.run(self.plugin._milestone_archive_once())
        self.assertEqual(len(self.written), 1)
        self.assertEqual(self.plugin.db.kv_get("milestone_ts:" + UID), since)

    def test_profiles_without_chat_are_skipped(self) -> None:
        self.plugin.db.update_profile(UID, relation="普通")
        self.mem.since_rows = self.pair_rows()
        asyncio.run(self.plugin._milestone_archive_once())
        self.assertEqual(self.mem.calls, [])
        self.assertEqual(self.written, [])


# --------------------------------------------------------------------------
# _maybe_daily_digest
# --------------------------------------------------------------------------


class DailyDigestTests(RuntimeCase):
    config = {"daily_digest_enabled": True, "daily_digest_hour": 6}

    def setUp(self) -> None:
        super().setUp()
        self.mem = FakeMem()
        self.install_data_plugin(self.mem)
        self.add_profile(relation="相恋", private_umo=QQ_UMO)
        self.now = datetime(2026, 1, 2, 10, 0)
        self.written = []

        async def write(uid, content, kind="fact", tier=1):
            self.written.append((uid, content, kind, tier))
            return True

        self.plugin._write_memory_checked = write
        self.summary = "他今天加班到很晚。我提醒他早点睡。"

        async def chat_raw(umo, system, prompt):
            self.last_prompt = prompt
            return self.summary

        self.plugin.llm.chat_raw = chat_raw

    def chat_rows(self, count=8):
        rows = []
        stamp = now_ts() - 3600
        for index in range(count):
            rows.append({"role": "user" if index % 2 == 0 else "bot",
                         "content": "第 %d 句聊天内容" % index,
                         "created_at": stamp + index})
        return rows

    def run_digest(self):
        with mock.patch.object(amo_runtime, "_now", lambda: self.now):
            asyncio.run(self.plugin._maybe_daily_digest())

    def test_disabled_does_nothing(self) -> None:
        self.plugin.config["daily_digest_enabled"] = False
        self.mem.messages = self.chat_rows()
        self.run_digest()
        self.assertEqual(self.mem.calls, [])
        self.assertEqual(self.written, [])

    def test_before_digest_hour_does_nothing(self) -> None:
        self.now = datetime(2026, 1, 2, 3, 0)
        self.mem.messages = self.chat_rows()
        self.run_digest()
        self.assertEqual(self.mem.calls, [])

    def test_guard_prevents_second_run(self) -> None:
        self.plugin.db.kv_set("daily_digest:2026-01-02", "2026-01-02")
        self.mem.messages = self.chat_rows()
        self.run_digest()
        self.assertEqual(self.mem.calls, [])

    def test_no_data_plugin_returns(self) -> None:
        self.plugin.context = types.SimpleNamespace(
            get_registered_star=lambda name: None, get_all_stars=lambda: [],
            get_config=lambda: {})
        self.run_digest()
        self.assertEqual(self.written, [])

    def test_too_few_lines_marks_guard_without_writing(self) -> None:
        self.mem.messages = self.chat_rows(2)
        self.run_digest()
        self.assertEqual(self.written, [])
        self.assertEqual(self.plugin.db.kv_get("daily_digest:2026-01-02"), "2026-01-02")

    def test_writes_digest_and_marks_guard(self) -> None:
        self.mem.messages = self.chat_rows(8)
        self.run_digest()
        self.assertEqual(len(self.written), 1)
        uid, content, kind, tier = self.written[0]
        self.assertEqual((uid, kind, tier), (UID, "daily_digest", 2))
        self.assertTrue(content.startswith("【2026-01-01】"))
        self.assertIn("他今天加班到很晚。", content)
        self.assertEqual(self.plugin.db.kv_get("daily_digest:2026-01-02"), "2026-01-02")

    def test_subject_is_added_to_bare_sentences(self) -> None:
        self.summary = "加班到很晚。我提醒他早点睡。"
        self.mem.messages = self.chat_rows(8)
        self.run_digest()
        content = self.written[0][1]
        self.assertIn("他加班到很晚。", content)
        self.assertIn("我提醒他早点睡。", content)

    def test_empty_summary_counts_as_failure(self) -> None:
        async def empty(umo, system, prompt):
            return ""

        self.plugin.llm.chat_raw = empty
        self.mem.messages = self.chat_rows(8)
        self.run_digest()
        self.assertEqual(self.written, [])
        self.assertEqual(self.plugin.db.kv_get("daily_digest_tries:2026-01-02"), 1)
        self.assertEqual(self.plugin.db.kv_get("daily_digest:2026-01-02", ""), "")

    def test_third_failure_gives_up_for_today(self) -> None:
        async def empty(umo, system, prompt):
            return ""

        self.plugin.llm.chat_raw = empty
        self.plugin.db.kv_set("daily_digest_tries:2026-01-02", 2)
        self.mem.messages = self.chat_rows(8)
        self.run_digest()
        self.assertEqual(self.plugin.db.kv_get("daily_digest_tries:2026-01-02"), 3)
        self.assertEqual(self.plugin.db.kv_get("daily_digest:2026-01-02"), "2026-01-02")

    def test_write_failure_counts_as_failure(self) -> None:
        async def write(uid, content, kind="fact", tier=1):
            self.written.append((uid, content, kind, tier))
            return False

        self.plugin._write_memory_checked = write
        self.mem.messages = self.chat_rows(8)
        self.run_digest()
        self.assertEqual(len(self.written), 1)
        self.assertEqual(self.plugin.db.kv_get("daily_digest_tries:2026-01-02"), 1)
        self.assertEqual(self.plugin.db.kv_get("daily_digest:2026-01-02", ""), "")

    def test_duplicate_rows_are_deduped(self) -> None:
        rows = self.chat_rows(8)
        rows = rows + [dict(rows[0]), dict(rows[1])]
        self.mem.messages = rows
        self.run_digest()
        self.assertEqual(len(self.written), 1)
        # 去重后 8 行 → 转写里不该出现重复的同一句
        self.assertEqual(self.last_prompt.count("第 0 句聊天内容"), 1)

    def test_system_rows_and_empty_lines_skipped(self) -> None:
        rows = self.chat_rows(6)
        rows.append({"role": "system", "content": "系统提示", "created_at": now_ts()})
        rows.append({"role": "user", "content": "   ", "created_at": now_ts()})
        self.mem.messages = rows
        self.run_digest()
        self.assertNotIn("系统提示", self.last_prompt)
        self.assertEqual(len(self.written), 1)

    def test_non_lover_profile_is_skipped(self) -> None:
        self.plugin.db.update_profile(UID, relation="普通")
        self.mem.messages = self.chat_rows(8)
        self.run_digest()
        self.assertEqual(self.mem.calls, [])
        self.assertEqual(self.written, [])
        # 没人生成过 → guard 落库，别每 5 分钟重跑
        self.assertEqual(self.plugin.db.kv_get("daily_digest:2026-01-02"), "2026-01-02")

    def test_summary_under_eight_chars_counts_as_failure(self) -> None:
        async def short(umo, system, prompt):
            return "好。"

        self.plugin.llm.chat_raw = short
        self.mem.messages = self.chat_rows(8)
        self.run_digest()
        self.assertEqual(self.written, [])
        self.assertEqual(self.plugin.db.kv_get("daily_digest_tries:2026-01-02"), 1)


if __name__ == "__main__":
    unittest.main()
