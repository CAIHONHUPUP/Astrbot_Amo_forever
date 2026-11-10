# -*- coding: utf-8 -*-
"""amo_social 覆盖面补充：关系网/称呼/群聊引用/社交打扰/账号合并。

只测不需要网络与模型调用的逻辑；涉及 llm 的 `_auto_learn` 用假 llm 喂固定事实。
时间相关一律传固定 ts 或 now_ts() 的偏移，不依赖真实当前时间。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import astrbot_stub  # noqa: E402

astrbot_stub.install()

from astrbot.api.message_components import At, Plain, Reply  # noqa: E402

import amo_social  # noqa: E402
from amo_db import AmoDB  # noqa: E402
from amo_message import MessageMixin  # noqa: E402
from amo_shared import now_ts  # noqa: E402
from amo_social import SocialMixin  # noqa: E402

BOUND = (
    (SocialMixin, (
        "_uid_alias_mapping", "_canonical_uid", "_merge_alias_profiles", "_is_admin",
        "_learn", "_register_lover", "_is_registered_lover", "_restore_lover_relation",
        "_lover_aliases", "_learn_alias", "_ctx_remember", "_group_roster",
        "_group_roster_text", "_group_speaker_count", "_should_quote_group",
        "_quote_allowed", "_install_qq_quote_guard", "_install_lark_quote_guard",
        "_learn_relations", "_relation_network_text", "_disturb_category",
        "_disturb_active", "_tone_with_continuity", "_apply_disturbance",
        "_disturb_pressure", "_mark_bot_initiated", "_recent_bot_initiated",
        "_should_disturb", "_sediment_relations", "_decay_hate_relations",
        "_auto_learn", "_purge_profile_kv",
    )),
    (MessageMixin, ("_recent",)),
)


class FakeEvent:
    def __init__(self, text="", sender_id="1", self_id="999", private=False,
                 group_id="", platform="aiocqhttp", message=None, sender_name="张三",
                 umo=None):
        self.message_str = text
        self._sender_id = sender_id
        self._self_id = self_id
        self._private = private
        self._group_id = group_id
        self._platform = platform
        self._sender_name = sender_name
        if umo is None:
            umo = ("aiocqhttp:FriendMessage:" + sender_id if private
                   else "aiocqhttp:GroupMessage:" + group_id)
        self.unified_msg_origin = umo
        self.message_obj = types.SimpleNamespace(message=message or [], message_id="m1")

    def is_private_chat(self):
        return self._private

    def get_sender_id(self):
        return self._sender_id

    def get_sender_name(self):
        return self._sender_name

    def get_self_id(self):
        return self._self_id

    def get_group_id(self):
        return self._group_id

    def get_platform_name(self):
        return self._platform

    def __getattr__(self, name):
        raise AttributeError(name)


class FakeState:
    def __init__(self):
        self.nudged = []
        self.observed = []
        self.worldview = {"city": "东莞"}
        self.activity = {"category": "work", "place": "东莞·商场·餐厅"}
        self.snapshot_data = {"activity": {"category": "work"}}

    def observe(self, text):
        self.observed.append(text)

    def nudge(self, **kwargs):
        self.nudged.append(kwargs)

    def snapshot(self):
        return self.snapshot_data

    def current_activity(self):
        return self.activity


class FakePlugin:
    def __init__(self, tmp, **cfg):
        self.config = {"uid_merge_enabled": True}
        self.config.update(cfg)
        self.db = AmoDB(tmp)
        self.db.init()
        self.admin_uids = set()
        self.state = FakeState()
        self.heartflow = None
        self.context = None
        self.bot_name = "大肥鱼"
        self.bot_aliases = ["小鱼"]
        self.CONTEXT_BUFFER_LIMIT = 60
        self._uid_alias_cache_key = None
        self._uid_alias_map = {}
        self._admin_cache = {}
        self._ctx_buffer = {}
        self._ctx_hydrated = set()
        self._group_times = {}
        self._last_group = ""
        self._last_umo = ""
        self._disturb_until = {}
        self._disturb_last = {}
        self._disturb_cooldown = {}
        self._disturb_reset_at = {}
        self._last_affect = {}
        self._bot_initiated = {}
        self._hub = None
        self._mem = None
        self._store = None
        self.data_calls = []
        self.data_raise = False
        self.relations_pushed = []
        self.learned = []
        self.data_bot_id = "bot"
        for owner, names in BOUND:
            for name in names:
                setattr(self, name, types.MethodType(getattr(owner, name), self))

    # ---- 其他 mixin / main.py 里的接线（只做记录用） ----
    def _memory_hub(self):
        return self._hub

    def _data_mem(self):
        return self._mem

    def _data_store(self):
        return self._store

    def _data_bot_id(self):
        return self.data_bot_id

    async def _data_call(self, name, *args, **kwargs):
        self.data_calls.append((name, args, kwargs))
        if self.data_raise:
            raise RuntimeError("终端不可用")
        return True

    async def _push_relation_to_data(self, a_uid, b_uid, relation, note=""):
        self.relations_pushed.append((a_uid, b_uid, relation, note))

    def _record_channel(self, uid, umo, platform):
        if not uid:
            return
        data = dict(self.db.kv_get("channels:" + str(uid), {}) or {})
        data[str(platform)] = {"umo": umo, "ts": now_ts()}
        self.db.kv_set("channels:" + str(uid), data)

    def _platform_of(self, event=None):
        return "aiocqhttp"

    def _event_message_id(self, event):
        return "m1"

    def cfg_str(self, key, default=""):
        return str(self.config.get(key, default))

    def cfg_int(self, key, default=0):
        return int(self.config.get(key, default))

    def cfg_float(self, key, default=0.0):
        return float(self.config.get(key, default))

    def cfg_bool(self, key, default=False):
        return bool(self.config.get(key, default))


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="amo-soc-")
        self._saved = {}
        for name in ("astrbot.core.utils", "astrbot.core.utils.astrbot_path"):
            self._saved[name] = sys.modules.get(name)
            module = types.ModuleType(name)
            module.__path__ = []
            sys.modules[name] = module
        path_module = types.ModuleType("astrbot.core.utils.astrbot_path")
        path_module.get_astrbot_data_path = lambda: self.tmp
        sys.modules["astrbot.core.utils.astrbot_path"] = path_module
        self.plugin = FakePlugin(self.tmp)
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        try:
            self.plugin.db.conn.close()
        except Exception:
            pass
        for name, module in self._saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def profile(self, uid, **fields):
        self.plugin.db.touch_profile(uid, fields.pop("name", ""), "", "", "", False)
        if fields:
            self.plugin.db.update_profile(uid, **fields)
        return self.plugin.db.get_profile(uid)

    def write_map_file(self, data, raw=None):
        path = os.path.join(os.path.dirname(self.plugin.db.path), "uid_map.json")
        with open(path, "w", encoding="utf-8-sig") as fh:
            fh.write(raw if raw is not None else json.dumps(data))
        return path


def install_module(name, **attrs):
    """把一个假模块（含所有父包）塞进 sys.modules。"""
    parts = name.split(".")
    for index in range(1, len(parts) + 1):
        sub = ".".join(parts[:index])
        module = sys.modules.get(sub)
        if module is None:
            module = types.ModuleType(sub)
            module.__path__ = []
            sys.modules[sub] = module
    module = sys.modules[name]
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


# ---------------------------------------------------------------------------
# 引用守卫：模块不存在时要静默跳过（必须最先跑，否则模块已被装进 sys.modules）
# ---------------------------------------------------------------------------
class AQuoteGuardMissingTests(Base):
    def test_qq_guard_without_module_is_noop(self) -> None:
        self.plugin._install_qq_quote_guard()
        self.assertNotIn("astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event",
                         sys.modules)

    def test_lark_guard_without_module_is_noop(self) -> None:
        self.plugin._install_lark_quote_guard()
        self.assertNotIn("astrbot.core.platform.sources.lark.lark_event", sys.modules)


# ---------------------------------------------------------------------------
# uid 映射 / 账号合并
# ---------------------------------------------------------------------------
class AliasMappingTests(Base):
    def test_chained_alias_and_self_map(self) -> None:
        self.plugin.config["uid_alias_map"] = json.dumps({"a": "b", "b": "c", "x": "x"})
        mapping = self.plugin._uid_alias_mapping()
        self.assertEqual(mapping, {"a": "c", "b": "c"})
        self.assertIs(self.plugin._uid_alias_mapping(), mapping, "同样内容应命中缓存")

    def test_bad_config_json_falls_back_to_empty(self) -> None:
        self.plugin.config["uid_alias_map"] = "{坏的 json"
        self.assertEqual(self.plugin._uid_alias_mapping(), {})

    def test_bad_map_file_falls_back_to_empty(self) -> None:
        self.write_map_file(None, raw="{不是 json")
        self.assertEqual(self.plugin._uid_alias_mapping(), {})

    def test_config_wins_over_file(self) -> None:
        self.plugin.config["uid_alias_map"] = json.dumps({"a": "c"})
        self.write_map_file({"a": "b", "d": "e"})
        mapping = self.plugin._uid_alias_mapping()
        self.assertEqual(mapping, {"a": "c", "d": "e"})

    def test_empty_values_dropped(self) -> None:
        self.plugin.config["uid_alias_map"] = json.dumps({"a": "", "b": None})
        self.assertEqual(self.plugin._uid_alias_mapping(), {})

    def test_cfg_error_still_reads_file(self) -> None:
        self.write_map_file({"ou_x": "302578963"})
        self.plugin._uid_alias_cache_key = "stale"
        self.plugin.cfg_str = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("配置挂了"))
        mapping = self.plugin._uid_alias_mapping()
        self.assertEqual(mapping.get("ou_x"), "302578963")


class CanonicalUidTests(Base):
    def test_maps_alias(self) -> None:
        self.plugin.config["uid_alias_map"] = json.dumps({"ou_x": "302578963"})
        self.assertEqual(self.plugin._canonical_uid(FakeEvent(sender_id="ou_x")),
                         "302578963")

    def test_disabled_keeps_original(self) -> None:
        self.plugin.config["uid_merge_enabled"] = False
        self.plugin.config["uid_alias_map"] = json.dumps({"ou_x": "302578963"})
        self.assertEqual(self.plugin._canonical_uid(FakeEvent(sender_id="ou_x")), "ou_x")

    def test_bad_event_returns_empty(self) -> None:
        class Boom:
            def get_sender_id(self):
                raise RuntimeError("没有 sender")

        self.assertEqual(self.plugin._canonical_uid(Boom()), "")


class MergeAliasTests(Base):
    def test_merge_moves_old_profile_once(self) -> None:
        self.profile("ou_x", name="旧号")
        self.plugin.config["uid_alias_map"] = json.dumps({"ou_x": "302578963"})
        self.plugin._merge_alias_profiles()
        self.assertEqual(self.plugin.db.get_profile("ou_x"), {})
        merged = self.plugin.db.get_profile("302578963")
        self.assertEqual(merged.get("name"), "旧号")
        self.assertTrue(self.plugin.db.kv_get("uid_alias_merged_signature"))
        self.plugin._merge_alias_profiles()  # 同一签名不再重复跑
        self.assertEqual(self.plugin.db.get_profile("302578963").get("name"), "旧号")

    def test_merge_disabled(self) -> None:
        self.profile("ou_x", name="旧号")
        self.plugin.config["uid_merge_enabled"] = False
        self.plugin.config["uid_alias_map"] = json.dumps({"ou_x": "302578963"})
        self.plugin._merge_alias_profiles()
        self.assertTrue(self.plugin.db.get_profile("ou_x"))
        self.assertIsNone(self.plugin.db.kv_get("uid_alias_merged_signature"))

    def test_merge_without_mapping(self) -> None:
        self.plugin._merge_alias_profiles()
        self.assertIsNone(self.plugin.db.kv_get("uid_alias_merged_signature"))

    def test_merge_failure_does_not_mark_signature(self) -> None:
        self.plugin.config["uid_alias_map"] = json.dumps({"a": "b"})
        with mock.patch.object(amo_social, "merge_uid_alias_data",
                               side_effect=RuntimeError("合并挂了")):
            self.plugin._merge_alias_profiles()
        self.assertIsNone(self.plugin.db.kv_get("uid_alias_merged_signature"))


class AdminTests(Base):
    def test_admin_uid(self) -> None:
        self.plugin.admin_uids = {"302578963"}
        self.assertTrue(self.plugin._is_admin(FakeEvent(sender_id="302578963")))

    def test_config_string_cached(self) -> None:
        class Context:
            calls = 0

            def get_config(self, umo=None):
                Context.calls += 1
                return {"admins_id": "1, 2"}

        self.plugin.context = Context()
        event = FakeEvent(sender_id="2", umo="qq:1")
        self.assertTrue(self.plugin._is_admin(event))
        self.assertTrue(self.plugin._is_admin(event))
        self.assertEqual(Context.calls, 1)

    def test_cache_expires_after_60s(self) -> None:
        class Context:
            calls = 0

            def get_config(self, umo=None):
                Context.calls += 1
                return {"admins_id": ["2"]}

        self.plugin.context = Context()
        event = FakeEvent(sender_id="2", umo="qq:1")
        self.plugin._admin_cache["qq:1"] = (now_ts() - 120, {"2"})
        self.assertTrue(self.plugin._is_admin(event))
        self.assertEqual(Context.calls, 1)

    def test_context_error_is_false(self) -> None:
        class Boom:
            def get_config(self, umo=None):
                raise RuntimeError("配置挂了")

        self.plugin.context = Boom()
        self.assertFalse(self.plugin._is_admin(FakeEvent(sender_id="1", umo="qq:1")))

    def test_missing_umo_uses_empty_key(self) -> None:
        class Odd:
            def get_sender_id(self):
                return "9"

            @property
            def unified_msg_origin(self):
                raise AttributeError("没有 umo")

        self.assertFalse(self.plugin._is_admin(Odd()))


# ---------------------------------------------------------------------------
# 学会话 / 恋人 / 称呼
# ---------------------------------------------------------------------------
class LearnTests(Base):
    def _run(self, event, text):
        asyncio.run(self.plugin._learn(event, text))

    def test_private_learn_updates_profile(self) -> None:
        event = FakeEvent(text="今天很开心，谢谢你", private=True)
        self._run(event, event.message_str)
        profile = self.plugin.db.get_profile("1")
        self.assertEqual(profile.get("affection"), 12)
        self.assertEqual(profile.get("private_umo"), event.unified_msg_origin)
        self.assertEqual(self.plugin.state.observed, ["今天很开心，谢谢你"])
        rows = self.plugin._ctx_buffer[event.unified_msg_origin]
        self.assertEqual(rows[-1]["role"], "user")
        self.assertEqual(rows[-1]["content"], "今天很开心，谢谢你")
        self.assertEqual(self.plugin.db.kv_get("channels:1")["aiocqhttp"]["umo"],
                         event.unified_msg_origin)
        self.assertEqual(self.plugin._last_umo, event.unified_msg_origin)
        self.assertEqual(self.plugin.data_calls[0][0], "add_message")

    def test_birthday_is_parsed(self) -> None:
        event = FakeEvent(text="我的生日是11月7号", private=True)
        self._run(event, event.message_str)
        self.assertEqual(self.plugin.db.get_profile("1").get("birthday"), "11-07")

    def test_insult_drops_affection_and_relation(self) -> None:
        self.profile("1", name="张三", relation="熟识")
        event = FakeEvent(text="你这个废物", private=True)
        self._run(event, event.message_str)
        profile = self.plugin.db.get_profile("1")
        self.assertEqual(profile.get("affection"), 8)
        self.assertEqual(profile.get("relation"), "抵触")

    def test_familiar_threshold(self) -> None:
        self.plugin.config["familiar_msg_count"] = 1
        self.profile("1", name="张三")
        event = FakeEvent(text="在吗", private=True)
        self._run(event, event.message_str)
        self.assertEqual(self.plugin.db.get_profile("1").get("relation"), "熟识")

    def test_admin_profile_is_upgraded(self) -> None:
        self.profile("1", name="张三")
        self.plugin.admin_uids = {"1"}
        event = FakeEvent(text="在吗", private=True)
        self._run(event, event.message_str)
        self.assertEqual(self.plugin.db.get_profile("1").get("is_admin"), 1)

    def test_group_learning_records_group(self) -> None:
        event = FakeEvent(text="群里好热闹", group_id="g1")
        self._run(event, event.message_str)
        self.assertEqual(self.plugin._last_group, "g1")
        self.assertEqual(len(self.plugin._group_times["g1"]), 1)

    def test_local_cache_writes_message(self) -> None:
        self.plugin.config["local_chat_cache"] = True
        event = FakeEvent(text="记一下这句", private=True)
        self._run(event, event.message_str)
        rows = self.plugin.db.recent_messages(event.unified_msg_origin, 10)
        self.assertEqual([row["content"] for row in rows], ["记一下这句"])

    def test_data_call_failure_is_swallowed(self) -> None:
        self.plugin.data_raise = True
        event = FakeEvent(text="终端挂了也要回", private=True)
        self._run(event, event.message_str)
        self.assertEqual(self.plugin.db.get_profile("1").get("msg_count"), 1)

    def test_auto_relation_hook_called(self) -> None:
        calls = []

        async def fake_learn_relations(event, text, uid):
            calls.append((text, uid))

        self.plugin._learn_relations = fake_learn_relations
        event = FakeEvent(text="小明是我同事", private=True)
        self._run(event, event.message_str)
        self.assertEqual(calls, [("小明是我同事", "1")])


class LoverTests(Base):
    def test_register_and_check(self) -> None:
        self.assertFalse(self.plugin._is_registered_lover(""))
        self.assertFalse(self.plugin._is_registered_lover("u1"))
        self.plugin._register_lover("u1")
        self.assertTrue(self.plugin._is_registered_lover("u1"))

    def test_profile_relation_registers(self) -> None:
        self.profile("u2", relation="相恋")
        self.assertTrue(self.plugin._is_registered_lover("u2"))
        self.assertTrue(self.plugin.db.kv_get("lover_uid_u2"))

    def test_restore_lover_relation(self) -> None:
        self.profile("u3", relation="抵触")
        self.plugin._register_lover("u3")
        self.plugin._restore_lover_relation("u3")
        self.assertEqual(self.plugin.db.get_profile("u3").get("relation"), "相恋")
        self.profile("u4", relation="抵触")
        self.plugin._restore_lover_relation("u4")
        self.assertEqual(self.plugin.db.get_profile("u4").get("relation"), "抵触")

    def test_lover_aliases(self) -> None:
        self.profile("u1", name="阿明", relation="相恋", alias="宝贝；亲爱的")
        self.profile("u2", name="小张")
        self.plugin._register_lover("u2")
        self.profile("u3", name="路人")
        aliases = self.plugin._lover_aliases()
        self.assertEqual(aliases.get("宝贝"), "u1")
        self.assertEqual(aliases.get("亲爱的"), "u1")
        self.assertEqual(aliases.get("小张"), "u2")
        self.assertNotIn("路人", aliases)


class LearnAliasTests(Base):
    def test_direct_alias_appends(self) -> None:
        self.profile("1", name="张三", alias="")
        event = FakeEvent(text="以后叫我小鱼", private=True)
        self.plugin._learn_alias(event, event.message_str, "1",
                                 self.plugin.db.get_profile("1"))
        self.assertEqual(self.plugin.db.get_profile("1").get("alias"), "小鱼")
        event2 = FakeEvent(text="叫我阿鱼", private=True)
        self.plugin._learn_alias(event2, event2.message_str, "1",
                                 self.plugin.db.get_profile("1"))
        self.assertEqual(self.plugin.db.get_profile("1").get("alias"), "小鱼；阿鱼")

    def test_blocked_word_not_learned(self) -> None:
        self.profile("1", name="张三")
        event = FakeEvent(text="叫我干嘛", private=True)
        self.plugin._learn_alias(event, event.message_str, "1",
                                 self.plugin.db.get_profile("1"))
        self.assertEqual(self.plugin.db.get_profile("1").get("alias") or "", "")

    def test_suffix_is_part_of_alias(self) -> None:
        # 源码第一条正则会把「就行」一起吞进称呼，这里锁住当前真实行为
        self.profile("1", name="张三")
        event = FakeEvent(text="叫我阿明就行", private=True)
        self.plugin._learn_alias(event, event.message_str, "1",
                                 self.plugin.db.get_profile("1"))
        self.assertEqual(self.plugin.db.get_profile("1").get("alias"), "阿明就行")

    def test_at_target_alias(self) -> None:
        event = FakeEvent(text="以后喊他阿明", message=[At(qq="222")],
                          sender_id="1", group_id="g1")
        self.plugin._learn_alias(event, event.message_str, "1",
                                 self.plugin.db.get_profile("1"))
        self.assertEqual(self.plugin.db.get_profile("222").get("alias"), "阿明")

    def test_at_all_and_self_ignored(self) -> None:
        event = FakeEvent(text="以后喊他阿明", message=[At(qq="all"), At(qq="999")],
                          sender_id="1", group_id="g1", self_id="999")
        self.plugin._learn_alias(event, event.message_str, "1",
                                 self.plugin.db.get_profile("1"))
        self.assertEqual(self.plugin.db.get_profile("all"), {})
        self.assertEqual(self.plugin.db.get_profile("999"), {})

    def test_only_last_at_wins(self) -> None:
        event = FakeEvent(text="以后喊他阿明", message=[At(qq="222"), At(qq="333")],
                          sender_id="1", group_id="g1")
        self.plugin._learn_alias(event, event.message_str, "1",
                                 self.plugin.db.get_profile("1"))
        self.assertEqual(self.plugin.db.get_profile("222").get("alias") or "", "")
        self.assertEqual(self.plugin.db.get_profile("333").get("alias"), "阿明")

    def test_plain_short_name_needs_three_times(self) -> None:
        self.profile("444", name="阿四")
        event = FakeEvent(text="出来玩", message=[At(qq="444")], sender_id="1",
                          group_id="g1")
        for _ in range(2):
            self.plugin._learn_alias(event, event.message_str, "1",
                                     self.plugin.db.get_profile("1"))
        self.assertEqual(self.plugin.db.get_profile("444").get("alias") or "", "")
        self.plugin._learn_alias(event, event.message_str, "1",
                                 self.plugin.db.get_profile("1"))
        self.assertEqual(self.plugin.db.get_profile("444").get("alias"), "出来玩")

    def test_missing_message_obj_is_tolerated(self) -> None:
        self.profile("1", name="张三")
        event = FakeEvent(text="以后叫我小鱼", private=True)
        del event.message_obj
        self.plugin._learn_alias(event, event.message_str, "1",
                                 self.plugin.db.get_profile("1"))
        self.assertEqual(self.plugin.db.get_profile("1").get("alias"), "小鱼")


class CtxRememberTests(Base):
    def test_empty_input_ignored(self) -> None:
        self.plugin._ctx_remember("", "1", "张三", "user", "你好")
        self.plugin._ctx_remember("umo", "1", "张三", "user", "   ")
        self.assertEqual(self.plugin._ctx_buffer, {})

    def test_rows_and_roles(self) -> None:
        self.plugin._ctx_remember("umo", "1", "张三", "user", "早")
        self.plugin._ctx_remember("umo", "bot", "大肥鱼", "bot", "早呀")
        rows = self.plugin._ctx_buffer["umo"]
        self.assertEqual([row["role"] for row in rows], ["user", "bot"])
        self.assertEqual(rows[0]["content"], "早")

    def test_limit_trims_oldest(self) -> None:
        self.plugin.CONTEXT_BUFFER_LIMIT = 2
        for index in range(3):
            self.plugin._ctx_remember("umo", "1", "张三", "user", "第%d句" % index)
        contents = [row["content"] for row in self.plugin._ctx_buffer["umo"]]
        self.assertEqual(contents, ["第1句", "第2句"])

    def test_hub_failure_does_not_lose_buffer(self) -> None:
        class BoomHub:
            class buffer:
                @staticmethod
                def add(*args, **kwargs):
                    raise RuntimeError("hub 挂了")

            @staticmethod
            def next_turn():
                raise RuntimeError("hub 挂了")

        self.plugin._hub = BoomHub()
        self.plugin._ctx_remember("umo", "1", "张三", "user", "还在吗")
        self.assertEqual(self.plugin._ctx_buffer["umo"][0]["content"], "还在吗")


# ---------------------------------------------------------------------------
# 群聊名单 / 发言人数 / 引用
# ---------------------------------------------------------------------------
class GroupRosterTests(Base):
    def setUp(self) -> None:
        super().setUp()
        self.umo = "aiocqhttp:GroupMessage:g1"
        self.profile("u1", name="阿明", alias="小鱼", relation="相恋")
        self.profile("u2", name="小张")
        self.plugin.db.conn.execute("UPDATE profiles SET msg_count=2 WHERE uid='u1'")
        self.plugin.db.conn.commit()
        for uid, name, role, text in (
            ("u1", "阿明", "user", "第一句"),
            ("bot", "大肥鱼", "bot", "她说的"),
            ("u2", "小张", "user", "第二句"),
            ("u1", "阿明", "user", "第三句"),
        ):
            self.plugin.db.add_message(self.umo, uid, name, role, text)

    def test_roster_dedup_and_current_first(self) -> None:
        roster = self.plugin._group_roster(self.umo, current_uid="u2")
        self.assertEqual([item["uid"] for item in roster], ["u2", "u1"])
        self.assertEqual(roster[0]["name"], "小张")
        self.assertTrue(roster[0]["current"])
        self.assertEqual(roster[1]["name"], "小鱼")
        self.assertEqual(roster[1]["relation"], "相恋")
        self.assertEqual(roster[1]["msg_count"], 2)

    def test_roster_limit(self) -> None:
        roster = self.plugin._group_roster(self.umo, limit=1)
        self.assertEqual(len(roster), 1)

    def test_roster_recent_error(self) -> None:
        self.plugin._recent = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("读不到"))
        self.assertEqual(self.plugin._group_roster(self.umo), [])

    def test_roster_text_levels(self) -> None:
        self.plugin.db.conn.execute("UPDATE profiles SET msg_count=200 WHERE uid='u1'")
        self.plugin.db.conn.execute("UPDATE profiles SET msg_count=30 WHERE uid='u2'")
        self.plugin.db.conn.commit()
        text = self.plugin._group_roster_text(self.umo, current_uid="u2")
        self.assertIn("很熟", text)
        self.assertIn("熟识", text)
        self.assertIn("（现在这句就是ta说的）", text)

    def test_roster_text_beginner_and_stranger(self) -> None:
        self.plugin.db.conn.execute("UPDATE profiles SET msg_count=1 WHERE uid='u1'")
        self.plugin.db.conn.execute("UPDATE profiles SET msg_count=0 WHERE uid='u2'")
        self.plugin.db.conn.commit()
        text = self.plugin._group_roster_text(self.umo)
        self.assertIn("刚认识", text)
        self.assertIn("陌生", text)

    def test_roster_text_empty(self) -> None:
        self.assertEqual(self.plugin._group_roster_text("aiocqhttp:GroupMessage:empty"), "")


class GroupSpeakerTests(Base):
    def setUp(self) -> None:
        super().setUp()
        self.umo = "aiocqhttp:GroupMessage:g1"

    def _insert(self, uid, created_at, role="user"):
        self.plugin.db.conn.execute(
            "INSERT INTO messages(umo, uid, name, role, content, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (self.umo, uid, uid, role, "x", created_at),
        )
        self.plugin.db.conn.commit()

    def test_counts_recent_distinct_speakers(self) -> None:
        now = now_ts()
        self._insert("u1", now - 10)
        self._insert("u1", now - 20)
        self._insert("u2", now - 30)
        self._insert("u3", now - 3600)
        self._insert("u4", now - 5, role="bot")
        self.assertEqual(self.plugin._group_speaker_count(self.umo), 2)

    def test_recent_error_returns_zero(self) -> None:
        self.plugin._recent = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("读不到"))
        self.assertEqual(self.plugin._group_speaker_count(self.umo), 0)


class QuoteTests(Base):
    def setUp(self) -> None:
        super().setUp()
        self.umo = "aiocqhttp:GroupMessage:g1"

    def test_threshold_zero_disables(self) -> None:
        self.plugin.config["quote_group_speaker_threshold"] = 0
        self.assertFalse(self.plugin._should_quote_group(self.umo))

    def test_few_speakers_no_quote(self) -> None:
        self.plugin.config["quote_group_speaker_threshold"] = 3
        self.plugin._group_speaker_count = lambda *a, **k: 2
        self.assertFalse(self.plugin._should_quote_group(self.umo))

    def test_probability_zero_and_one(self) -> None:
        self.plugin.config["quote_group_speaker_threshold"] = 1
        self.plugin._group_speaker_count = lambda *a, **k: 5
        self.plugin.config["quote_group_probability"] = 0
        self.assertFalse(self.plugin._should_quote_group(self.umo))
        self.plugin.config["quote_group_probability"] = 1
        self.assertTrue(self.plugin._should_quote_group(self.umo))

    def test_probability_roll(self) -> None:
        self.plugin.config["quote_group_speaker_threshold"] = 1
        self.plugin._group_speaker_count = lambda *a, **k: 5
        self.plugin.config["quote_group_probability"] = 0.5
        with mock.patch.object(amo_social.random, "random", return_value=0.2):
            self.assertTrue(self.plugin._should_quote_group(self.umo))
        with mock.patch.object(amo_social.random, "random", return_value=0.8):
            self.assertFalse(self.plugin._should_quote_group(self.umo))

    def test_speaker_count_error_is_false(self) -> None:
        self.plugin._group_speaker_count = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("读不到"))
        self.assertFalse(self.plugin._should_quote_group(self.umo))

    def test_quote_allowed_rules(self) -> None:
        self.assertFalse(self.plugin._quote_allowed("lark:FriendMessage:ou_x"))
        self.assertFalse(self.plugin._quote_allowed(self.umo, group=False))
        self.assertFalse(self.plugin._quote_allowed("aiocqhttp:FriendMessage:1", group=True))
        self.plugin._should_quote_group = lambda umo: True
        self.assertTrue(self.plugin._quote_allowed(self.umo))

    def test_quote_allowed_exception_false(self) -> None:
        self.plugin._should_quote_group = lambda umo: (_ for _ in ()).throw(
            RuntimeError("炸了"))
        self.assertFalse(self.plugin._quote_allowed(self.umo))


class QQQuoteGuardTests(Base):
    def _install(self):
        calls = []

        class AiocqhttpMessageEvent:
            async def send(self, message):
                calls.append(message.chain)

        install_module(
            "astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event",
            AiocqhttpMessageEvent=AiocqhttpMessageEvent,
        )
        return AiocqhttpMessageEvent, calls

    def test_private_chain_drops_reply(self) -> None:
        event_cls, calls = self._install()
        self.plugin._install_qq_quote_guard()
        self.assertTrue(getattr(event_cls, "_amo_quote_guard", False))

        class Ev:
            def get_group_id(self):
                return ""

        message = types.SimpleNamespace(chain=[Reply(id="m9"), Plain("在吗")])
        asyncio.run(event_cls.send(Ev(), message))
        self.assertEqual([type(comp).__name__ for comp in message.chain], ["Plain"])
        self.assertEqual(len(calls), 1)

    def test_group_chain_keeps_reply(self) -> None:
        event_cls, _ = self._install()
        self.plugin._install_qq_quote_guard()

        class Ev:
            def get_group_id(self):
                return "g1"

        message = types.SimpleNamespace(chain=[Reply(id="m9"), Plain("在吗")])
        asyncio.run(event_cls.send(Ev(), message))
        self.assertEqual([type(comp).__name__ for comp in message.chain],
                         ["Reply", "Plain"])

    def test_group_id_error_still_sends(self) -> None:
        event_cls, calls = self._install()
        self.plugin._install_qq_quote_guard()

        class Ev:
            def get_group_id(self):
                raise RuntimeError("拿不到群号")

        message = types.SimpleNamespace(chain=[Reply(id="m9"), Plain("在吗")])
        asyncio.run(event_cls.send(Ev(), message))
        self.assertEqual(len(calls), 1)


class LarkQuoteGuardTests(Base):
    def _install(self, fake_base=None):
        calls = []

        class FakeLark:
            @classmethod
            async def send_message_chain(cls, message, bot, **kwargs):
                calls.append(kwargs)

        install_module(
            "astrbot.core.platform.sources.lark.lark_event",
            LarkMessageEvent=FakeLark,
        )
        base_calls = []

        class FakeBase:
            @staticmethod
            async def send(event, message):
                base_calls.append(message)

        self.base = FakeBase
        return FakeLark, calls, base_calls

    def _event(self, private=True, chain=None, sender="ou_user", group="",
               message_id="m1"):
        class Message:
            def __init__(self):
                self.chain = list(chain or [])
                self.message_id = message_id
                self.type = types.SimpleNamespace(value="text")

        class Ev:
            message_obj = Message()
            bot = object()

            def is_private_chat(self):
                return private

            def get_sender_id(self):
                return sender

            def get_group_id(self):
                return group

        return Ev()

    def test_private_reply_is_stripped(self) -> None:
        fake_lark, calls, base_calls = self._install()
        event = self._event(private=True, chain=[Reply(id="m9"), Plain("在吗")])
        with mock.patch.object(amo_social, "AstrMessageEvent", self.base):
            self.plugin._install_lark_quote_guard()
            self.assertTrue(getattr(fake_lark, "_amo_quote_guard", False))
            asyncio.run(fake_lark.send(event, event.message_obj))
        self.assertEqual([type(comp).__name__ for comp in event.message_obj.chain],
                         ["Plain"])
        self.assertEqual(calls[0]["receive_id"], "ou_user")
        self.assertEqual(calls[0]["receive_id_type"], "open_id")
        self.assertNotIn("reply_message_id", calls[0])
        self.assertEqual(len(base_calls), 1)

    def test_group_keeps_reply(self) -> None:
        fake_lark, calls, _ = self._install()
        event = self._event(private=False, chain=[Reply(id="m9"), Plain("在吗")],
                            group="oc_chat")
        with mock.patch.object(amo_social, "AstrMessageEvent", self.base):
            self.plugin._install_lark_quote_guard()
            asyncio.run(fake_lark.send(event, event.message_obj))
        self.assertEqual(calls[0]["reply_message_id"], "m1")

    def test_private_without_reply_sends_plain(self) -> None:
        fake_lark, calls, _ = self._install()
        event = self._event(private=True, chain=[Plain("在吗")])
        with mock.patch.object(amo_social, "AstrMessageEvent", self.base):
            self.plugin._install_lark_quote_guard()
            asyncio.run(fake_lark.send(event, event.message_obj))
        self.assertEqual(calls[0]["receive_id"], "ou_user")
        self.assertNotIn("reply_message_id", calls[0])

    def test_private_check_error_treated_as_group(self) -> None:
        fake_lark, calls, _ = self._install()

        class Ev:
            class message_obj:
                chain = [Reply(id="m9")]
                message_id = "m1"
                type = types.SimpleNamespace(value="text")

            bot = object()

            def is_private_chat(self):
                raise RuntimeError("拿不到会话类型")

            def get_sender_id(self):
                return "ou_user"

            def get_group_id(self):
                return "oc_chat"

        with mock.patch.object(amo_social, "AstrMessageEvent", self.base):
            self.plugin._install_lark_quote_guard()
            asyncio.run(fake_lark.send(Ev(), Ev.message_obj))
        self.assertEqual(calls[0]["reply_message_id"], "m1")

    def test_chain_error_means_no_reply(self) -> None:
        fake_lark, calls, _ = self._install()

        class Message:
            message_id = "m1"
            type = types.SimpleNamespace(value="text")

            @property
            def chain(self):
                raise RuntimeError("链坏了")

            @chain.setter
            def chain(self, value):
                pass

        class Ev:
            message_obj = Message()
            bot = object()

            def is_private_chat(self):
                return False

            def get_sender_id(self):
                return "ou_user"

            def get_group_id(self):
                return "oc_chat"

        with mock.patch.object(amo_social, "AstrMessageEvent", self.base):
            self.plugin._install_lark_quote_guard()
            asyncio.run(fake_lark.send(Ev(), Ev.message_obj))
        self.assertNotIn("reply_message_id", calls[0])

    def test_plain_send_falla_back_to_reply(self) -> None:
        state = {"first": True}

        class FakeLark:
            calls = []

            @classmethod
            async def send_message_chain(cls, message, bot, **kwargs):
                cls.calls.append(kwargs)
                if "reply_message_id" not in kwargs:
                    raise RuntimeError("open_id 被拒")

        install_module(
            "astrbot.core.platform.sources.lark.lark_event",
            LarkMessageEvent=FakeLark,
        )

        class FakeBase:
            @staticmethod
            async def send(event, message):
                return None

        event = self._event(private=True, chain=[Plain("在吗")])
        with mock.patch.object(amo_social, "AstrMessageEvent", FakeBase):
            self.plugin._install_lark_quote_guard()
            asyncio.run(FakeLark.send(event, event.message_obj))
        self.assertEqual(len(FakeLark.calls), 2)
        self.assertNotIn("reply_message_id", FakeLark.calls[0])
        self.assertEqual(FakeLark.calls[1]["reply_message_id"], "m1")
        del state

    def test_reply_send_error_propagates(self) -> None:
        class FakeLark:
            @classmethod
            async def send_message_chain(cls, message, bot, **kwargs):
                raise RuntimeError("发送失败")

        install_module(
            "astrbot.core.platform.sources.lark.lark_event",
            LarkMessageEvent=FakeLark,
        )

        class FakeBase:
            @staticmethod
            async def send(event, message):
                return None

        event = self._event(private=False, chain=[Reply(id="m9")], group="oc_chat")
        with mock.patch.object(amo_social, "AstrMessageEvent", FakeBase):
            with mock.patch.object(amo_social.logger, "warning"):
                self.plugin._install_lark_quote_guard()
                with self.assertRaises(RuntimeError):
                    asyncio.run(FakeLark.send(event, event.message_obj))


# ---------------------------------------------------------------------------
# 关系学习 / 关系网
# ---------------------------------------------------------------------------
class LearnRelationsTests(Base):
    def test_learns_relation_from_statement(self) -> None:
        self.profile("222", name="小明")
        event = FakeEvent(text="小明是我同事", private=True)
        asyncio.run(self.plugin._learn_relations(event, event.message_str, "1"))
        edges = {tuple(sorted([row["a_uid"], row["b_uid"]])): row
                 for row in self.plugin.db.list_relations()}
        edge = edges[("1", "222")]
        self.assertEqual(edge["relation"], "同事")
        self.assertTrue(edge["note"].startswith("对话："))
        self.assertEqual(self.plugin.relations_pushed,
                         [("1", "222", "同事", edge["note"])])

    def test_no_relation_statement(self) -> None:
        self.profile("222", name="小明")
        event = FakeEvent(text="今天好热")
        asyncio.run(self.plugin._learn_relations(event, event.message_str, "1"))
        self.assertEqual(self.plugin.db.list_relations(), [])

    def test_empty_text(self) -> None:
        asyncio.run(self.plugin._learn_relations(FakeEvent(), "", "1"))
        self.assertEqual(self.plugin.db.list_relations(), [])

    def test_ambiguous_name_is_skipped(self) -> None:
        self.profile("222", name="小明")
        self.profile("333", name="小明")
        event = FakeEvent(text="小明是我同事", private=True)
        asyncio.run(self.plugin._learn_relations(event, event.message_str, "1"))
        self.assertEqual(self.plugin.db.list_relations(), [])

    def test_manual_relation_not_overwritten(self) -> None:
        self.profile("222", name="小明")
        self.plugin.db.upsert_relation("1", "222", "同事", "手动：面板设的")
        asyncio.run(self.plugin._learn_relations(FakeEvent(text="小明是我朋友"),
                                                 "小明是我朋友", "1"))
        edge = self.plugin.db.list_relations()[0]
        self.assertEqual(edge["note"], "手动：面板设的")
        self.assertEqual(edge["relation"], "同事")

    def test_parse_error_is_swallowed(self) -> None:
        with mock.patch.object(amo_social, "parse_relations",
                               side_effect=RuntimeError("解析挂了")):
            asyncio.run(self.plugin._learn_relations(FakeEvent(text="小明是我同事"),
                                                     "小明是我同事", "1"))
        self.assertEqual(self.plugin.db.list_relations(), [])

    def test_profile_read_error_is_swallowed(self) -> None:
        self.plugin.db.list_profiles = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("读不到档案"))
        asyncio.run(self.plugin._learn_relations(FakeEvent(text="小明是我同事"),
                                                 "小明是我同事", "1"))
        self.assertEqual(self.plugin.db.list_relations(), [])

    def test_relation_read_error_falls_back(self) -> None:
        self.profile("222", name="小明")
        self.plugin.db.list_relations = lambda: (_ for _ in ()).throw(
            RuntimeError("读不到关系"))
        asyncio.run(self.plugin._learn_relations(FakeEvent(text="小明是我同事"),
                                                 "小明是我同事", "1"))
        self.plugin.db.list_relations = AmoDB.list_relations.__get__(self.plugin.db)
        self.assertEqual(len(self.plugin.db.list_relations()), 1)


class RelationNetworkTests(Base):
    def test_empty(self) -> None:
        self.assertEqual(self.plugin._relation_network_text("u1"), "")

    def test_stranger_only_is_hidden(self) -> None:
        self.plugin.db.upsert_relation("u1", "u2", "陌生人", "自动：在列表里")
        self.assertEqual(self.plugin._relation_network_text("u1"), "")

    def test_names_and_relation(self) -> None:
        self.profile("u1", name="阿明", alias="小鱼")
        self.profile("u2", name="小张", alias="阿张")
        self.plugin.db.upsert_relation("u1", "u2", "朋友", "自动：累计 3 条")
        text = self.plugin._relation_network_text("u1")
        self.assertIn("小鱼和阿张是朋友", text)

    def test_fallback_without_rank_edges(self) -> None:
        self.plugin.db.upsert_relation("u1", "u2", "朋友")
        self.plugin.db.upsert_relation("u2", "u3", "熟人")
        with mock.patch.object(amo_social, "_rank_edges", None):
            text = self.plugin._relation_network_text("u1")
        self.assertIn("u1和u2是朋友", text)
        self.assertIn("u2和u3是熟人", text)

    def test_bot_name_and_uid_fallback(self) -> None:
        self.plugin.bot_name = ""
        self.plugin.db.upsert_relation("u1", "u2", "朋友")
        self.plugin.db.list_profiles = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("读不到档案"))
        text = self.plugin._relation_network_text("u1")
        self.assertIn("u1和u2是朋友", text)

    def test_many_edges_capped(self) -> None:
        for index in range(45):
            self.plugin.db.upsert_relation("u1", "n%d" % index, "朋友")
        lines = self.plugin._relation_network_text("u1").splitlines()
        self.assertLessEqual(len(lines), 12)
        self.assertTrue(lines)

    def test_relation_read_error_returns_empty(self) -> None:
        self.plugin.db.list_relations = lambda: (_ for _ in ()).throw(
            RuntimeError("读不到关系"))
        self.assertEqual(self.plugin._relation_network_text("u1"), "")


# ---------------------------------------------------------------------------
# 打扰 / 情绪惯性
# ---------------------------------------------------------------------------
class DisturbTests(Base):
    def test_category(self) -> None:
        self.assertTrue(self.plugin._disturb_category(
            {"activity": {"category": "sleep"}}))
        self.assertTrue(self.plugin._disturb_category(
            {"activity": {"category": "study"}}))
        self.assertFalse(self.plugin._disturb_category(
            {"activity": {"category": "meal"}}))
        self.assertFalse(self.plugin._disturb_category({}))

    def test_active_window(self) -> None:
        self.plugin._disturb_until["u"] = now_ts() + 100
        self.assertTrue(self.plugin._disturb_active("u"))
        self.plugin._disturb_until["u"] = now_ts() - 100
        self.assertFalse(self.plugin._disturb_active("u"))

    def test_tone_adds_disturb_warning_once(self) -> None:
        self.plugin._disturb_until["u"] = now_ts() + 100
        tone = self.plugin._tone_with_continuity("u", "语气自然")
        self.assertIn("不要一秒变甜蜜", tone)
        self.assertEqual(tone.count("不要一秒变甜蜜"), 1)
        again = self.plugin._tone_with_continuity("u", tone)
        self.assertEqual(again.count("不要一秒变甜蜜"), 1)

    def test_tone_keeps_anger_continuity(self) -> None:
        self.plugin._last_affect["u"] = (now_ts() - 60, "你现在很烦躁")
        tone = self.plugin._tone_with_continuity("u", "语气自然")
        self.assertIn("慢慢缓和", tone)

    def test_tone_old_affect_expires(self) -> None:
        self.plugin._last_affect["u"] = (now_ts() - 5000, "你现在很烦躁")
        self.assertNotIn("慢慢缓和", self.plugin._tone_with_continuity("u", "语气自然"))

    def test_apply_disturbance_default_penalty(self) -> None:
        self.plugin._apply_disturbance("u")
        self.assertGreater(self.plugin._disturb_until["u"], now_ts())
        # now_ts() 是浮点秒，两次调用之间会差几微秒，按 1 秒粒度比
        self.assertAlmostEqual(self.plugin._disturb_cooldown["u"] - now_ts(), 120, delta=1)
        self.assertEqual(self.plugin.state.nudged, [
            {"生气": 6, "郁闷": 3, "疲惫": 3, "开心": -2},
        ])

    def test_apply_disturbance_once_per_minute(self) -> None:
        self.plugin._apply_disturbance("u")
        self.plugin._apply_disturbance("u")
        self.assertEqual(len(self.plugin.state.nudged), 1)

    def test_apply_disturbance_custom_penalty(self) -> None:
        self.plugin.config["disturb_mood_penalty"] = 3
        self.plugin.config["disturb_tone_seconds"] = 1
        self.plugin._apply_disturbance("u")
        self.assertEqual(self.plugin.state.nudged[0],
                         {"生气": 3, "郁闷": 1, "疲惫": 1, "开心": -1})
        self.assertAlmostEqual(self.plugin._disturb_until["u"] - now_ts(), 30, delta=1)


class DisturbPressureTests(Base):
    def setUp(self) -> None:
        super().setUp()
        self.umo = "aiocqhttp:GroupMessage:g1"

    def _add(self, uid, role, text, created_at=None):
        created_at = now_ts() if created_at is None else created_at
        self.plugin.db.conn.execute(
            "INSERT INTO messages(umo, uid, name, role, content, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (self.umo, uid, uid, role, text, created_at),
        )
        self.plugin.db.conn.commit()

    def test_private_counts_before_bot(self) -> None:
        self._add("bot", "bot", "她说的")
        self._add("u1", "user", "一")
        self._add("u1", "user", "二")
        self.assertEqual(self.plugin._disturb_pressure(self.umo, "u1"), 2)

    def test_old_messages_ignored(self) -> None:
        self._add("u1", "user", "很久以前", created_at=now_ts() - 3600)
        self._add("u1", "user", "刚刚")
        self.plugin.config["disturb_window_minutes"] = 10
        self.assertEqual(self.plugin._disturb_pressure(self.umo, "u1"), 1)

    def test_group_mentions_count(self) -> None:
        self._add("u2", "user", "大肥鱼在吗")
        self._add("u1", "user", "小鱼也来看看")
        self.assertEqual(self.plugin._disturb_pressure(self.umo, "u1", group=True), 2)

    def test_recent_error_returns_zero(self) -> None:
        self.plugin._recent = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("读不到"))
        self.assertEqual(self.plugin._disturb_pressure(self.umo, "u1"), 0)


class BotInitiatedTests(Base):
    def test_mark_and_check(self) -> None:
        self.plugin._disturb_until["u"] = now_ts() + 100
        self.plugin._mark_bot_initiated("u")
        self.assertTrue(self.plugin._recent_bot_initiated("u"))
        self.assertEqual(self.plugin._disturb_until["u"], 0)
        self.assertIn("主动发起", self.plugin._last_affect["u"][1])

    def test_expired(self) -> None:
        self.plugin._bot_initiated["u"] = now_ts() - 7200
        self.assertFalse(self.plugin._recent_bot_initiated("u"))
        self.assertFalse(self.plugin._recent_bot_initiated("u", seconds=10))

    def test_should_disturb_rules(self) -> None:
        snap = {"activity": {"category": "work"}}
        self.plugin._disturb_pressure = lambda *a, **k: 5
        self.assertTrue(self.plugin._should_disturb(snap, "u", "1"))
        self.plugin.config["disturb_reply_enabled"] = False
        self.assertFalse(self.plugin._should_disturb(snap, "u", "1"))
        self.plugin.config.pop("disturb_reply_enabled")
        self.plugin._mark_bot_initiated("u")
        self.assertFalse(self.plugin._should_disturb(snap, "u", "1"))
        self.plugin._bot_initiated.clear()
        self.assertFalse(self.plugin._should_disturb(
            {"activity": {"category": "meal"}}, "u", "1"))
        self.plugin._disturb_cooldown["u"] = now_ts() + 100
        self.assertFalse(self.plugin._should_disturb(snap, "u", "1"))
        self.plugin._disturb_cooldown.clear()
        self.plugin._disturb_pressure = lambda *a, **k: 1
        self.assertFalse(self.plugin._should_disturb(snap, "u", "1"))


# ---------------------------------------------------------------------------
# 关系沉淀 / 仇恨衰减 / 自动学习 / 清理
# ---------------------------------------------------------------------------
class SedimentTests(Base):
    def setUp(self) -> None:
        super().setUp()
        self.umo = "aiocqhttp:FriendMessage:u1"

    def _messages(self, uid, count, start, span_days=2.0):
        step = span_days * 86400 / max(1, count - 1)
        for index in range(count):
            self.plugin.db.conn.execute(
                "INSERT INTO messages(umo, uid, name, role, content, created_at) "
                "VALUES(?,?,?,?,?,?)",
                (self.umo, uid, uid, "user", "第%d句" % index, start + index * step),
            )
        self.plugin.db.conn.commit()

    def test_plan_none_returns(self) -> None:
        with mock.patch.object(amo_social, "plan_relation_edges", None):
            asyncio.run(self.plugin._sediment_relations())
        self.assertEqual(self.plugin.db.list_relations(), [])

    def test_sediment_writes_bot_edges(self) -> None:
        self.profile("u1", name="阿明", alias="小鱼")
        self.profile("u2", name="只见过")
        self._messages("u1", 20, now_ts() - 2 * 86400)
        asyncio.run(self.plugin._sediment_relations())
        edges = {tuple(sorted([row["a_uid"], row["b_uid"]])): row
                 for row in self.plugin.db.list_relations()}
        self.assertEqual(edges[("bot", "u1")]["relation"], "熟人")
        self.assertTrue(edges[("bot", "u1")]["note"].startswith("自动："))
        self.assertEqual(edges[("bot", "u2")]["relation"], "陌生人")
        self.assertEqual(len(self.plugin.relations_pushed), 2)

    def test_stranger_edges_can_be_disabled(self) -> None:
        self.profile("u1", name="阿明")
        self.profile("u2", name="只见过")
        self.plugin.config["relation_stranger_edges"] = False
        self._messages("u1", 20, now_ts() - 2 * 86400)
        asyncio.run(self.plugin._sediment_relations())
        edges = [tuple(sorted([row["a_uid"], row["b_uid"]]))
                 for row in self.plugin.db.list_relations()]
        self.assertEqual(edges, [("bot", "u1")])

    def test_infer_edges_from_friend(self) -> None:
        self.profile("u1", name="阿明", alias="小鱼")
        self.profile("u2", name="小张")
        self.plugin.config["relation_stranger_edges"] = False
        self.plugin.db.upsert_relation("u1", "u2", "闺蜜", "手动")
        self._messages("u1", 20, now_ts() - 2 * 86400)
        asyncio.run(self.plugin._sediment_relations())
        edge = [row for row in self.plugin.db.list_relations()
                if {row["a_uid"], row["b_uid"]} == {"bot", "u2"}][0]
        self.assertEqual(edge["relation"], "朋友")
        self.assertIn("小鱼", edge["note"])

    def test_no_stats_no_writes(self) -> None:
        asyncio.run(self.plugin._sediment_relations())
        self.assertEqual(self.plugin.db.list_relations(), [])

    def test_stats_error_returns(self) -> None:
        class BoomDB:
            def interaction_stats(self, days):
                raise RuntimeError("统计挂了")

        self.plugin.db = BoomDB()
        asyncio.run(self.plugin._sediment_relations())

    def test_relation_read_error_returns(self) -> None:
        self.profile("u1", name="阿明")
        self._messages("u1", 20, now_ts() - 2 * 86400)
        self.plugin.db.list_relations = lambda: (_ for _ in ()).throw(
            RuntimeError("读不到关系"))
        asyncio.run(self.plugin._sediment_relations())

    def test_plan_error_returns(self) -> None:
        self.profile("u1", name="阿明")
        self._messages("u1", 20, now_ts() - 2 * 86400)
        with mock.patch.object(amo_social, "plan_relation_edges",
                               side_effect=RuntimeError("算不出来")):
            asyncio.run(self.plugin._sediment_relations())
        self.assertEqual(self.plugin.db.list_relations(), [])


class DecayHateTests(Base):
    def test_old_hate_becomes_guarded(self) -> None:
        self.profile("u1", relation="仇恨")
        self.profile("u2", relation="仇恨")
        self.plugin.db.conn.execute(
            "UPDATE profiles SET relation_at=? WHERE uid='u1'", (now_ts() - 8 * 86400,))
        self.plugin.db.conn.commit()
        self.plugin._decay_hate_relations()
        self.assertEqual(self.plugin.db.get_profile("u1").get("relation"), "抵触")
        self.assertEqual(self.plugin.db.get_profile("u2").get("relation"), "仇恨")

    def test_db_error_is_swallowed(self) -> None:
        class BoomDB:
            @property
            def conn(self):
                raise RuntimeError("库挂了")

        self.plugin.db = BoomDB()
        self.plugin._decay_hate_relations()


class AutoLearnTests(Base):
    def setUp(self) -> None:
        super().setUp()
        self.written = []
        self.write_ok = True
        self.fact_lines = []
        self.rows = []
        self.plugin._recent_by_uid = self._recent
        self.plugin._write_memory_checked = self._write

    async def _recent(self, uid, limit=20, umo=""):
        return self.rows

    async def _write(self, uid, content, kind, tier):
        self.written.append((uid, content, kind, tier))
        return self.write_ok

    def test_no_active_users(self) -> None:
        asyncio.run(self.plugin._auto_learn())
        self.assertEqual(self.written, [])

    def test_user_without_private_umo_skipped(self) -> None:
        self.plugin.db.add_message("g1", "u1", "阿明", "user", "群里的话")
        self.rows = [{"role": "user", "content": "群里的话", "umo": "g1"}]
        self.written = []
        self.write_ok = True
        self.plugin.llm = types.SimpleNamespace()
        asyncio.run(self.plugin._auto_learn())
        self.assertEqual(self.written, [])

    def test_interval_not_elapsed(self) -> None:
        self.profile("u1", name="阿明")
        self.plugin.db.update_profile("u1", name="阿明")
        self.plugin.db.conn.execute(
            "UPDATE profiles SET private_umo='qq:1' WHERE uid='u1'")
        self.plugin.db.conn.commit()
        self.plugin.db.add_message("qq:1", "u1", "阿明", "user", "刚聊过")
        self.plugin.db.kv_set("auto_learn_u1", now_ts())
        self.rows = [{"role": "user", "content": "刚聊过", "umo": "qq:1"}]
        self.written = []
        self.write_ok = True
        self.plugin.llm = types.SimpleNamespace()
        asyncio.run(self.plugin._auto_learn())
        self.assertEqual(self.written, [])

    def _setup_user(self):
        self.profile("u1", name="阿明")
        self.plugin.db.conn.execute(
            "UPDATE profiles SET private_umo='qq:1' WHERE uid='u1'")
        self.plugin.db.conn.commit()
        self.plugin.db.add_message("qq:1", "u1", "阿明", "user", "我喜欢猫")
        self.rows = [
            {"role": "user", "content": "我喜欢猫", "umo": "qq:1"},
            {"role": "bot", "content": "我也喜欢", "umo": "qq:1"},
            {"role": "summary", "content": "摘要", "umo": "qq:1"},
            {"role": "user", "content": "别处的话", "umo": "other"},
        ]
        self.written = []
        self.write_ok = True
        self.plugin.llm = types.SimpleNamespace(
            extract_facts=self._facts)

    async def _facts(self, umo, name, lines):
        self.fact_lines = list(lines)
        return [{"content": "他喜欢猫", "kind": "fact", "tier": 1}]

    def test_facts_written_and_marked(self) -> None:
        self._setup_user()
        asyncio.run(self.plugin._auto_learn())
        self.assertEqual(self.written, [("u1", "他喜欢猫", "fact", 1)])
        self.assertTrue(self.plugin.db.kv_get("auto_learn_u1"))
        self.assertEqual(self.fact_lines, ["[他] 我喜欢猫", "[我] 我也喜欢"])

    def test_write_failure_keeps_unmarked(self) -> None:
        self._setup_user()
        self.write_ok = False
        asyncio.run(self.plugin._auto_learn())
        self.assertFalse(self.plugin.db.kv_get("auto_learn_u1"))

    def test_no_lines_skips(self) -> None:
        self._setup_user()
        self.rows = [{"role": "summary", "content": "摘要", "umo": "qq:1"}]
        asyncio.run(self.plugin._auto_learn())
        self.assertEqual(self.written, [])
        self.assertFalse(self.plugin.db.kv_get("auto_learn_u1"))

    def test_extract_error_is_swallowed(self) -> None:
        self._setup_user()
        self.plugin.llm = types.SimpleNamespace(
            extract_facts=lambda *a, **k: (_ for _ in ()).throw(
                RuntimeError("模型挂了")))
        asyncio.run(self.plugin._auto_learn())
        self.assertFalse(self.plugin.db.kv_get("auto_learn_u1"))

    def test_active_users_error_returns(self) -> None:
        class BoomDB:
            def active_users(self, since, limit=2):
                raise RuntimeError("读不到活跃用户")

        self.plugin.db = BoomDB()
        self.written = []
        asyncio.run(self.plugin._auto_learn())
        self.assertEqual(self.written, [])


class PurgeProfileKvTests(Base):
    def test_removes_only_uid_keys(self) -> None:
        self.plugin.db.kv_set("channels:u1", {"qq": 1})
        self.plugin.db.kv_set("lover_uid_u1", True)
        self.plugin.db.kv_set("ritual_2026_u1_morning", "x")
        self.plugin.db.kv_set("channels:u2", {"qq": 1})
        self.plugin.db.kv_set("other_u1", "keep")
        removed = self.plugin._purge_profile_kv("u1")
        self.assertEqual(removed, 3)
        remaining = [row["key"] for row in
                     self.plugin.db.conn.execute("SELECT key FROM kv").fetchall()]
        self.assertEqual(sorted(remaining), ["channels:u2", "other_u1"])

    def test_nothing_matches(self) -> None:
        self.assertEqual(self.plugin._purge_profile_kv("nobody"), 0)

    def test_query_error_returns_zero(self) -> None:
        class BoomDB:
            class conn:
                @staticmethod
                def execute(*args, **kwargs):
                    raise RuntimeError("库挂了")

        self.plugin.db = BoomDB()
        self.assertEqual(self.plugin._purge_profile_kv("u1"), 0)


if __name__ == "__main__":
    unittest.main()
