# -*- coding: utf-8 -*-
"""`amo_api.py`（面板 / HTTP 接口层）的单元测试。

这一层几乎全是「读 query/body → 调 self.db / self.state → 返回 dict」的接线代码，
以前完全没有测试（覆盖率 17%）。这里用假 request / 假 context / 假插件把正常路径、
参数缺失、数据库没连上（记忆终端没装）、保存失败这些分支都跑一遍；能用真 AmoDB
的地方就用真库，断言写库效果，而不是只断言「没抛异常」。
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import types
import unittest
from datetime import date, datetime
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import astrbot_stub  # noqa: E402

astrbot_stub.install()

import main as amo_main  # noqa: E402
import amo_api  # noqa: E402
import amo_city_index  # noqa: E402
from amo_db import AmoDB  # noqa: E402
from amo_shared import PLUGIN_NAME  # noqa: E402


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 假对象
# ---------------------------------------------------------------------------

class FakeHeaders(dict):
    def get(self, key, default=None):
        for name, value in self.items():
            if name.lower() == str(key).lower():
                return value
        return default


class FakeRequest:
    """AstrBot 的 web_request：query 给 GET，json()/get_json() 给 POST body。"""

    def __init__(self, method="POST", headers=None, query=None, body=None,
                 json_error=None):
        self.method = method
        self.headers = FakeHeaders(headers or {})
        self.query = dict(query or {})
        self._body = body
        self._json_error = json_error

    async def json(self, default=None):
        if self._json_error is not None:
            raise self._json_error
        if self._body is not None:
            return self._body
        return default if default is not None else {}

    async def get_json(self, silent=True):
        if self._json_error is not None:
            raise self._json_error
        return self._body if self._body is not None else {}


class FakeConfig(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.saved = 0
        self.save_error = None

    def save_config(self):
        if self.save_error is not None:
            raise self.save_error
        self.saved += 1
        return True


class FakeStar:
    def __init__(self, mem):
        self.star_cls = types.SimpleNamespace(mem=mem)


class FakeContext:
    """只提供 ApiMixin / DataSyncMixin 会用到的那几个口子。"""

    def __init__(self, data_mem=None):
        self.routes = []
        self.registered_web_apis = []
        self._data_mem = data_mem

    def register_web_api(self, route, handler, methods, desc):
        self.routes.append((route, handler, methods, desc))
        self.registered_web_apis.append((route, handler, methods, desc))

    def get_registered_star(self, name):
        if self._data_mem is None:
            return None
        return FakeStar(self._data_mem)

    def get_all_stars(self):
        return []


class FakeMem:
    """「想记」(Astr_Amo_data) 的 mem 门面。"""

    def __init__(self, rows=None):
        self.calls = []
        self.rows = list(rows or [])
        self.delete_ok = True
        self.save_profile_result = True
        self.person = {}

    async def list_memories(self, bot_id, uid, size):
        self.calls.append(("list_memories", bot_id, uid, size))
        return [dict(row) for row in self.rows]

    async def recall(self, bot_id, uid, keyword, size, *rest):
        self.calls.append(("recall", bot_id, uid, keyword, size))
        return [dict(row) for row in self.rows]

    async def save_profile(self, *args, **kwargs):
        self.calls.append(("save_profile",) + tuple(args) + (dict(kwargs),))
        return {"uid": args[1]} if self.save_profile_result else None

    async def save_relation(self, *args):
        self.calls.append(("save_relation",) + tuple(args))
        return True

    async def delete_relation(self, *args):
        self.calls.append(("delete_relation",) + tuple(args))
        return True

    async def delete_memory(self, bot_id, memory_id):
        self.calls.append(("delete_memory", bot_id, memory_id))
        return self.delete_ok

    async def person_context(self, bot_id, platform, uid, limit):
        self.calls.append(("person_context", bot_id, platform, uid, limit))
        return dict(self.person)


class FakeGift:
    def __init__(self, panel=None, removed=0, purge_error=None, panel_error=None):
        self.panel = panel or {"enabled": True, "wishes": [], "gifts": []}
        self.removed = removed
        self.purge_error = purge_error
        self.panel_error = panel_error
        self.purged = []

    def purge_user(self, uid, umos):
        self.purged.append((uid, set(umos)))
        if self.purge_error is not None:
            raise self.purge_error
        return self.removed

    def panel_data(self):
        if self.panel_error is not None:
            raise self.panel_error
        return dict(self.panel)


class FakeState:
    def __init__(self):
        self.weather = {}
        self.weather_brief_text = "东莞 · 多云 · 23℃"
        self.mood = {}
        self.saved = 0
        self.snapshot_value = {"mood": {}}
        self.worldview = {"city": "东莞"}
        self.worldview_result = {"city": "深圳", "regenerated": True}
        self.schedule = [{"start": "10:00", "end": "11:00", "activity": "开会"}]
        self.schedule_tree_value = {"years": [{"year": 2024, "months": []}]}
        self.current_value = {"activity": "开会"}
        self.context_value = {"city": "东莞"}
        self.expand_result = {"detail": "在开周会"}
        self.calls = []
        self.refresh_error = None

    def weather_brief(self):
        return self.weather_brief_text

    async def refresh_weather(self, force=False):
        self.calls.append(("refresh_weather", force))
        if self.refresh_error is not None:
            raise self.refresh_error
        self.weather = {"now": {"text": "多云"}}
        return self.weather

    async def ensure_schedule(self, umo, force=False):
        self.calls.append(("ensure_schedule", umo, force))
        return [dict(item) for item in self.schedule]

    def _hourly_schedule(self, items):
        self.calls.append(("_hourly_schedule", tuple(items)))
        return [dict(item) for item in items]

    def schedule_tree(self, day):
        self.calls.append(("schedule_tree", day))
        return self.schedule_tree_value

    def current_activity(self):
        return self.current_value

    def schedule_context(self, day):
        return self.context_value

    async def expand_hour(self, day, item, items, force=False):
        self.calls.append(("expand_hour", day, dict(item), tuple(items), force))
        return dict(self.expand_result)

    async def ensure_worldview(self, umo, force=False):
        self.calls.append(("ensure_worldview", umo, force))
        if force:
            self.worldview = dict(self.worldview_result)
        return self.worldview

    def save(self):
        self.saved += 1

    def snapshot(self):
        self.snapshot_value = {"mood": dict(self.mood), "saved": self.saved}
        return dict(self.snapshot_value)


class FakePlugin(amo_api.ApiMixin):
    """只提供接口层真正会碰的字段；helper 尽量复用真实实现。"""

    SENSITIVE_KEYS = {"hefeng_key", "deepseek_api_key"}
    DATA_PLUGIN_NAMES = amo_main.HumanCorePlugin.DATA_PLUGIN_NAMES

    def __init__(self, root, data_mem=None, config=None):
        self.plugin_dir = ROOT
        self.name = PLUGIN_NAME
        self.bot_name = "大肥鱼"
        self.config = config if config is not None else FakeConfig()
        self.context = FakeContext(data_mem)
        self.state = FakeState()
        self.db = AmoDB(root)
        self.db.init()
        self._last_umo = "aiocqhttp:private:302578963"
        self._last_reply_at = {}
        self.gift = None
        self.ready_calls = 0
        self.apply_calls = 0
        self.diary_dir = os.path.join(root, "diary")
        self.diary_text = "今天去了趟超市，买了他爱吃的橙子。"
        self.external_write_ok = True
        self.external_writes = []
        self.send_ok = True
        self.sent = []
        self.dialect_kb = object()
        self.scenic_kb = object()
        self.dialect_style_value = ""
        self.dialect_rows_value = [1, 2, 3]
        # 用量 / 供应商
        self.usage_prices_value = {"hit_peak": 1.0}
        self.usage_day_start = 1000.0
        self.balance_value = {"ok": True, "balance": "12.30"}
        self.provider_items = [
            {"id": "p1", "model": "m1"},
            {"id": "p2", "model": "m2"},
        ]
        self.judge_provider = "p1"
        self.using_provider = "p2"
        self.balance_map = [{"id": "p1", "ok": True, "balance": "3.00"}]
        self.balance_queries = []

    # ---- 生命周期 ----
    async def _ensure_ready(self):
        self.ready_calls += 1

    async def _apply_runtime_config(self):
        self.apply_calls += 1

    # ---- 日记 / 语种 / 景区库 ----
    def _diary_dir(self):
        return self.diary_dir

    async def _generate_daily_diary(self, day):
        return self.diary_text

    async def _ensure_dialect_kb(self):
        return self.dialect_kb

    async def _ensure_scenic_kb(self):
        return self.scenic_kb

    def _dialect_style(self):
        return str(self.config.get("dialect_style") or "")

    def _dialect_region(self):
        return "广东"

    def _dialect_rows(self):
        return list(self.dialect_rows_value)

    def _dialect_kb_name(self):
        return "陪伴方言库-广东话"

    def _scenic_kb_name(self):
        return "景区库"

    # ---- 用量 / 供应商 ----
    def _usage_db_path(self):
        return os.path.join(ROOT, "data_v4.db")

    def _usage_prices(self):
        return dict(self.usage_prices_value)

    def _usage_start_of_today(self):
        return self.usage_day_start

    async def _balance_cached(self):
        return dict(self.balance_value)

    async def _provider_balances_cached(self, providers):
        self.balance_queries.append([dict(item) for item in providers])
        return [dict(item) for item in self.balance_map]

    def _provider_inventory(self):
        return [dict(item) for item in self.provider_items]

    def _judge_provider_id(self):
        return self.judge_provider

    def _using_provider_id(self):
        return self.using_provider

    # ---- 记忆写入 / 发送 ----
    def _external_memory_write(self, uid, content, kind="fact", tier=1):
        self.external_writes.append((uid, content, kind, tier))
        return self.external_write_ok

    async def _send_to_umo(self, umo, text, quote_id=None, group=False):
        self.sent.append((umo, text))
        return self.send_ok

    # ---- 面板状态 ----
    async def _status_data(self):
        return {
            "dominant": "开心",
            "mood": {"开心": 80},
            "activity": {"activity": "上班"},
            "health": {"status": "健康"},
            "period": {"phase": "经期", "day": 2},
            "weather_text": "多云 23℃",
            "config": {"auto_active_msg": True},
            "threshold": 0.5,
            "counts": {"profiles": 1},
        }


# helper 优先用真实实现：解析 query/body、配置 schema、记忆桥、城市表、路由注册
for _name in (
    "_q", "_q_int", "_body",
    "cfg", "cfg_bool", "cfg_int", "cfg_float", "cfg_str",
    "_schema_map", "_config_schema_items",
    "_purge_profile_kv", "_register_lover",
    "_data_plugin", "_data_mem", "_data_store", "_data_call", "_data_bot_id",
    "_data_mem_list", "_all_memories", "_push_relation_to_data",
    "_push_profile_to_data",
    "_city_module", "_city_lookup",
    "_safe_register", "_web_guard",
):
    setattr(FakePlugin, _name, getattr(amo_main.HumanCorePlugin, _name))

FakePlugin._coerce_config_value = staticmethod(amo_main.HumanCorePlugin._coerce_config_value)
FakePlugin._mask_secret = staticmethod(amo_main.HumanCorePlugin._mask_secret)
FakePlugin._star_instance = staticmethod(amo_main.HumanCorePlugin._star_instance)


# ---------------------------------------------------------------------------
# 基类
# ---------------------------------------------------------------------------

class ApiTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="amo-api-")
        self._saved_modules = {}
        for name in ("astrbot.core.utils", "astrbot.core.utils.astrbot_path"):
            self._saved_modules[name] = sys.modules.get(name)
            module = types.ModuleType(name)
            module.__path__ = []
            sys.modules[name] = module
        path_module = types.ModuleType("astrbot.core.utils.astrbot_path")
        path_module.get_astrbot_data_path = lambda: self.tmp
        sys.modules["astrbot.core.utils.astrbot_path"] = path_module

        self._orig_main_request = amo_main.web_request
        self._orig_api_request = amo_api.web_request
        self.request = FakeRequest()
        self._apply_request()

        self.plugin = self.make_plugin()

    def make_plugin(self, data_mem=None, config=None):
        return FakePlugin(self.tmp, data_mem=data_mem, config=config)

    def tearDown(self):
        try:
            self.plugin.db.conn.close()
        except Exception:
            pass
        amo_main.web_request = self._orig_main_request
        amo_api.web_request = self._orig_api_request
        for name, module in self._saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    # ---- 请求 / 调用 ----
    def set_request(self, method="POST", headers=None, query=None, body=None,
                    json_error=None):
        self.request = FakeRequest(method=method, headers=headers, query=query,
                                   body=body, json_error=json_error)
        self._apply_request()

    def _apply_request(self):
        amo_main.web_request = self.request
        amo_api.web_request = self.request

    def api(self, name, *args, **kwargs):
        return run(getattr(self.plugin, name)(*args, **kwargs))


# ---------------------------------------------------------------------------
# 路由注册 / 写操作守卫
# ---------------------------------------------------------------------------

class RegistrationTests(ApiTestBase):
    def test_registers_all_prefixes_and_cleans_stale_routes(self):
        context = self.plugin.context
        context.registered_web_apis = [
            ("/Astrbot_Amo_forever/status", object(), ["GET"], "/status"),
            ("/build4/status", object(), ["GET"], "/status"),
            ("get_status", object(), ["GET"], "/get_status"),
            ("refresh_status", object(), ["GET"], "/refresh_status"),
            ("/other/plugin/x", object(), ["GET"], "/x"),
        ]

        self.plugin._register_web_apis()

        routes = [item[0] for item in context.registered_web_apis]
        # 旧实例/旧版本残留的、指向已关闭连接的路由必须清掉
        self.assertNotIn("get_status", routes)
        self.assertNotIn("refresh_status", routes)
        self.assertEqual(routes.count("/Astrbot_Amo_forever/status"), 1)
        self.assertEqual(routes.count("/build4/status"), 1)
        # 别人的路由不能动
        self.assertIn("/other/plugin/x", routes)
        # 三个真实前缀都注册了一遍（"build4" 只是测试环境残留的历史别名，不在源码前缀表里）
        for prefix in ("Astrbot_Amo_forever",
                       "astrbot_plugin_Astrbot_Amo_forever",
                       "astrbot_plugin_amo_forever"):
            self.assertIn("/%s/status" % prefix, routes)
            self.assertIn("/%s/config/save" % prefix, routes)
        # 写路由只注册 POST
        methods = [item[2] for item in context.registered_web_apis
                   if item[0] == "/Astrbot_Amo_forever/config/save"]
        self.assertEqual(methods, [["POST"]])
        # 3 个前缀 × 59 条接口（外加别人的路由，数量不写死成 4 倍）
        self.assertGreaterEqual(len(routes), 3 * 59)

    def test_registry_access_failure_does_not_block_registration(self):
        class _BoomRegistryContext:
            def __init__(self):
                self.routes = []

            @property
            def registered_web_apis(self):
                raise RuntimeError("registry boom")

            def register_web_api(self, *args):
                self.routes.append(args)

            def get_registered_star(self, name):
                return None

            def get_all_stars(self):
                return []

        self.plugin.context = _BoomRegistryContext()
        self.plugin._register_web_apis()
        # 取不到 router 里的旧路由也不影响注册；前缀个数随插件目录名变
        # （CI 检出目录叫 Astrbot_Amo_forever 是 3 个，本地叫 build4 会多一个）。
        # 接口条数会随功能增长（照片功能后 59→72），所以验「每个前缀条数一致 + 不少于 59」，
        # 不要再写死 % 59。
        by_prefix = {}
        for item in self.plugin.context.routes:
            prefix = str(item[0]).split("/")[1]
            by_prefix[prefix] = by_prefix.get(prefix, 0) + 1
        self.assertGreaterEqual(len(by_prefix), 3)
        self.assertEqual(len(set(by_prefix.values())), 1, by_prefix)
        self.assertGreaterEqual(min(by_prefix.values()), 59)


class WebGuardTests(ApiTestBase):
    def _guard(self, handler, is_write=True):
        return run(self.plugin._web_guard(handler, is_write=is_write)())

    def test_forwarded_host_allows_origin_mismatch(self):
        called = []

        async def handler():
            called.append(True)
            return {"code": 0}

        self.set_request(method="POST", headers={
            "origin": "https://bot.example.com",
            "host": "127.0.0.1:6185",
            "x-forwarded-host": "bot.example.com, proxy.internal",
        })
        self.assertEqual(self._guard(handler), {"code": 0})
        self.assertEqual(called, [True])

    def test_unknown_origin_is_rejected(self):
        called = []

        async def handler():
            called.append(True)
            return {"code": 0}

        self.set_request(method="POST", headers={
            "origin": "https://evil.example",
            "host": "127.0.0.1:6185",
        })
        result = self._guard(handler)
        self.assertEqual(result["code"], 403)
        self.assertEqual(result["msg"], "拒绝来源不一致的请求")
        self.assertEqual(called, [])


# ---------------------------------------------------------------------------
# 面板聚合接口
# ---------------------------------------------------------------------------

class DispatchTests(ApiTestBase):
    MAPPING = [
        ("", "api_get_status"),
        ("status", "api_get_status"),
        ("get_status", "api_get_status"),
        ("profiles", "api_profiles"),
        ("profile_list", "api_profiles"),
        ("profile/delete", "api_profile_delete"),
        ("delete_profile", "api_profile_delete"),
        ("profile_save", "api_profile_save"),
        ("save_profile", "api_profile_save"),
        ("memories", "api_memories"),
        ("memory_list", "api_memories"),
        ("memory_add", "api_memory_add"),
        ("add_memory", "api_memory_add"),
        ("memory_delete", "api_memory_delete"),
        ("delete_memory", "api_memory_delete"),
        ("mood_update", "api_mood_update"),
        ("update_mood", "api_mood_update"),
        ("schedule", "api_schedule"),
        ("scenic_kb_regen", "api_scenic_kb_regen"),
        ("regen_scenic_kb", "api_scenic_kb_regen"),
        ("kb_regen", "api_kb_regen"),
        ("regen_kb", "api_kb_regen"),
        ("dialect_kb_regen", "api_kb_regen"),
        ("schedule_regen", "api_schedule_regen"),
        ("regen_schedule", "api_schedule_regen"),
        ("weather", "api_weather"),
        ("weather_refresh", "api_weather"),
        ("refresh_weather", "api_weather"),
        ("worldview", "api_worldview"),
        ("worldview_regen", "api_worldview_regen"),
        ("regen_worldview", "api_worldview_regen"),
        ("say", "api_say"),
        ("send", "api_say"),
        ("refresh_status", "api_refresh_status"),
        ("refresh", "api_refresh_status"),
        ("get_profile", "api_get_profile"),
        ("profile", "api_get_profile"),
    ]

    def _install_stubs(self):
        calls = []
        api_names = sorted({target for _action, target in self.MAPPING})

        def make(name):
            async def stub(*args, **kwargs):
                calls.append(name)
                return {"code": 0, "from": name}

            return stub

        for name in api_names:
            setattr(self.plugin, name, make(name))
        return calls

    def test_dispatch_maps_every_action(self):
        calls = self._install_stubs()
        for action, expected in self.MAPPING:
            calls.clear()
            result = run(self.plugin.api_dispatch(action))
            self.assertEqual(result.get("from"), expected, action)
            self.assertEqual(calls, [expected], action)
        self.assertGreaterEqual(self.plugin.ready_calls, len(self.MAPPING))

    def test_dispatch_unknown_and_exception(self):
        result = run(self.plugin.api_dispatch("no_such_api"))
        self.assertEqual(result["code"], 1)
        self.assertEqual(result["msg"], "未知接口：no_such_api")

        async def boom(*args, **kwargs):
            raise RuntimeError("库没连上")

        self.plugin.api_profiles = boom
        result = run(self.plugin.api_dispatch("profiles"))
        self.assertEqual(result["code"], 1)
        self.assertIn("库没连上", result["msg"])


class PanelStatusTests(ApiTestBase):
    def test_status_wraps_status_data(self):
        result = self.api("api_status")
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["data"]["weather_text"], "多云 23℃")
        self.assertEqual(result["data"]["counts"], {"profiles": 1})

    def test_get_status_formats_fields(self):
        result = self.api("api_get_status")
        data = result["data"]
        self.assertEqual(data["mood"], "开心（{'开心': 80}）")
        self.assertEqual(data["schedule"], "上班")
        self.assertEqual(data["health"], "健康")
        self.assertEqual(data["period"], "经期 第2天")
        self.assertEqual(data["weather"], "多云 23℃")
        self.assertEqual(data["threshold"], 0.5)
        self.assertEqual(data["counts"], {"profiles": 1})

    def test_providers_marks_judge_and_using(self):
        result = self.api("api_providers")
        items = result["data"]["items"]
        self.assertEqual(len(items), 2)
        self.assertTrue(items[0]["judge"])
        self.assertFalse(items[0]["using"])
        self.assertFalse(items[1]["judge"])
        self.assertTrue(items[1]["using"])

    def test_providers_without_ids(self):
        self.plugin.judge_provider = ""
        self.plugin.using_provider = ""
        items = self.api("api_providers")["data"]["items"]
        self.assertEqual([item["judge"] for item in items], [False, False])
        self.assertEqual([item["using"] for item in items], [False, False])

    def test_balance_returns_cached_payload(self):
        self.assertEqual(self.api("api_balance"),
                         {"code": 0, "data": {"ok": True, "balance": "12.30"}})


class UsageTests(ApiTestBase):
    def _patch_usage(self, calls):
        def fake_summarize(db_path, start):
            calls.append((db_path, start))
            return {
                "calls": 2,
                "input_miss": 100,
                "input_cached": 50,
                "output": 30,
                "by_model": [{"model": "m1", "input_miss": 100,
                              "input_cached": 50, "output": 30,
                              "calls": 2, "cost": 1.5}],
            }

        def fake_cost(usage, prices):
            return 0.5 * int(usage.get("calls") or 0)

        return mock.patch.multiple(
            amo_api,
            summarize_token_usage=mock.Mock(side_effect=fake_summarize),
            usage_cost=mock.Mock(side_effect=fake_cost),
        )

    def test_usage_builds_today_week_total_and_provider_rows(self):
        calls = []
        with self._patch_usage(calls):
            result = self.api("api_usage")
        data = result["data"]
        self.assertTrue(data["enabled"])
        self.assertEqual(data["currency"], "元")
        self.assertEqual(data["prices"], {"hit_peak": 1.0})
        # 三个窗口：今天 / 最近 7 天 / 全部
        self.assertEqual([start for _path, start in calls],
                         [1000.0, 1000.0 - 6 * 86400, None])
        self.assertEqual(data["today"]["cost"], 1.0)
        self.assertIn("week", data)
        self.assertIn("total", data)
        self.assertEqual(data["balance"], {"ok": True, "balance": "12.30"})

        providers = data["providers"]
        first, second = providers[0], providers[1]
        self.assertTrue(first["judge"])
        self.assertFalse(first["using"])
        self.assertEqual(first["today_tokens"], 180)
        self.assertEqual(first["today_calls"], 2)
        self.assertEqual(first["today_cost"], 1.5)
        self.assertEqual(first["balance"], {"id": "p1", "ok": True, "balance": "3.00"})
        self.assertEqual(second["today_tokens"], 0)
        self.assertEqual(second["balance"],
                         {"ok": False, "error": "未配置密钥或地址"})
        self.assertEqual(self.plugin.balance_queries[0][0]["id"], "p1")

    def test_usage_disabled_returns_early(self):
        self.plugin.config["usage_stats_enabled"] = False
        calls = []
        with self._patch_usage(calls):
            result = self.api("api_usage")
        self.assertEqual(result, {"code": 0, "data": {"enabled": False}})
        self.assertEqual(calls, [])

    def test_usage_balance_switches(self):
        self.plugin.config["deepseek_balance_enabled"] = False
        calls = []
        with self._patch_usage(calls):
            data = self.api("api_usage")["data"]
        self.assertEqual(data["balance"], {"ok": False, "error": "余额查询已关闭"})
        self.assertEqual(
            [item["balance"] for item in data["providers"]],
            [{"ok": False, "error": "余额查询已关闭"}] * 2,
        )

        self.plugin.config["deepseek_balance_enabled"] = True
        self.plugin.config["usage_balance_enabled"] = False
        calls = []
        with self._patch_usage(calls):
            data = self.api("api_usage")["data"]
        self.assertEqual(data["balance"], {"ok": True, "balance": "12.30"})
        self.assertEqual(
            [item["balance"] for item in data["providers"]],
            [{"ok": False, "error": "余额查询已关闭"}] * 2,
        )


# ---------------------------------------------------------------------------
# 配置读写
# ---------------------------------------------------------------------------

class ConfigTests(ApiTestBase):
    def test_config_exposes_schema_and_masks_secrets(self):
        self.plugin.config = FakeConfig({
            "bot_name": "大肥鱼",
            "hefeng_key": "0123456789abcdef",
        })
        result = self.api("api_config")
        items = {item["key"]: item for item in result["data"]["items"]}
        self.assertGreater(len(items), 20)
        self.assertEqual(items["bot_name"]["group"], "基础")
        self.assertEqual(items["bot_name"]["value"], "大肥鱼")
        secret = items["hefeng_key"]
        self.assertTrue(secret["sensitive"])
        self.assertTrue(secret["configured"])
        self.assertEqual(secret["value"], "0123********cdef")
        self.assertIn("心流", {item["group"] for item in items.values()})

    def test_config_save_coerces_and_skips(self):
        config = FakeConfig({
            "bot_name": "旧名",
            "hefeng_key": "0123456789abcdef",
            "period_days": 3,
        })
        self.plugin.config = config
        self.set_request(body={"changes": {
            "bot_name": "新名",
            "period_days": "7",
            "usage_stats_enabled": "true",
            "dialect_style": "广东话",
            "unknown_key_xyz": "x",
            "hefeng_key": "0123********cdef",
        }})

        result = self.api("api_config_save")

        self.assertEqual(result["code"], 0)
        self.assertEqual(result["data"]["saved"], {
            "bot_name": "新名",
            "period_days": 7,
            "usage_stats_enabled": True,
            "dialect_style": "广东话",
        })
        self.assertEqual(config["bot_name"], "新名")
        self.assertEqual(config["period_days"], 7)
        self.assertIs(config["usage_stats_enabled"], True)
        self.assertNotIn("unknown_key_xyz", config)
        # 面板回传打码串时不能把真 key 覆盖掉
        self.assertEqual(config["hefeng_key"], "0123456789abcdef")
        self.assertEqual(config.saved, 1)
        self.assertEqual(self.plugin.apply_calls, 1)

    def test_config_save_flat_body_and_invalid_values(self):
        config = FakeConfig({"bot_name": "旧名", "period_days": 3})
        self.plugin.config = config
        self.set_request(body={"bot_name": "扁平", "period_days": "abc"})
        result = self.api("api_config_save")
        self.assertEqual(result["data"]["saved"], {"bot_name": "扁平"})
        self.assertEqual(result["code"], 0)

    def test_config_save_apply_failure_still_saves(self):
        config = FakeConfig({})
        self.plugin.config = config

        async def boom():
            raise RuntimeError("心流启动失败")

        self.plugin._apply_runtime_config = boom
        self.set_request(body={"changes": {"bot_name": "小鱼"}})
        result = self.api("api_config_save")
        self.assertEqual(result["code"], 0)
        self.assertEqual(config["bot_name"], "小鱼")

    def test_config_save_persist_failure_returns_error(self):
        config = FakeConfig({})
        config.save_error = RuntimeError("磁盘只读")
        self.plugin.config = config
        self.set_request(body={"changes": {"bot_name": "小鱼"}})
        result = self.api("api_config_save")
        self.assertEqual(result["code"], 1)
        self.assertIn("保存配置失败", result["msg"])
        self.assertIn("磁盘只读", result["msg"])
        self.assertEqual(config.saved, 0)

    def test_config_save_empty_secret_and_empty_changes(self):
        config = FakeConfig({"hefeng_key": "0123456789abcdef"})
        self.plugin.config = config
        self.set_request(body={"changes": {"hefeng_key": ""}})
        result = self.api("api_config_save")
        self.assertEqual(result["data"]["saved"], {})
        self.assertEqual(config.saved, 0)
        self.assertEqual(config["hefeng_key"], "0123456789abcdef")


# ---------------------------------------------------------------------------
# 天气 / 城市
# ---------------------------------------------------------------------------

class WeatherCityTests(ApiTestBase):
    def test_weather_brief_refreshes_when_empty(self):
        self.plugin.config = FakeConfig({
            "weather_city": "101281601",
            "weather_city_name": "东莞",
        })
        result = self.api("api_weather_brief")
        self.assertEqual(result["data"]["city"], "101281601")
        self.assertEqual(result["data"]["city_name"], "东莞")
        self.assertEqual(result["data"]["weather"], "东莞 · 多云 · 23℃")
        self.assertEqual(self.plugin.state.calls, [("refresh_weather", False)])

    def test_weather_brief_uses_cache_when_present(self):
        self.plugin.state.weather = {"now": {"text": "晴"}}
        self.api("api_weather_brief")
        self.assertEqual(self.plugin.state.calls, [])

    def test_weather_brief_swallows_refresh_error(self):
        self.plugin.state.refresh_error = RuntimeError("和风超时")
        result = self.api("api_weather_brief")
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["data"]["weather"], "东莞 · 多云 · 23℃")

    def test_city_search_reads_query_then_body(self):
        result = self.api("api_city_search")
        self.assertEqual(result, {"code": 0, "data": {"items": [], "query": ""}})

        self.set_request(query={"q": "东莞"})
        result = self.api("api_city_search")
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["data"]["query"], "东莞")
        self.assertTrue(result["data"]["items"])
        self.assertTrue(all("name" in item for item in result["data"]["items"]))

        self.set_request(body={"q": "深圳"})
        result = self.api("api_city_search")
        self.assertEqual(result["data"]["query"], "深圳")

    def test_city_search_missing_module_and_broken_table(self):
        self.plugin._city_module = lambda: None
        self.set_request(query={"q": "东莞"})
        self.assertEqual(self.api("api_city_search")["code"], 1)

        fake = types.SimpleNamespace(
            search_city=lambda q, limit: (_ for _ in ()).throw(RuntimeError("表坏了")))
        self.plugin._city_module = lambda: fake
        result = self.api("api_city_search")
        self.assertEqual(result["code"], 1)
        self.assertIn("城市表读取失败", result["msg"])

    def test_city_set_missing_text(self):
        result = self.api("api_city_set")
        self.assertEqual(result["code"], 1)
        self.assertEqual(result["msg"], "请填写城市名")

    def test_city_set_unknown_city(self):
        self.plugin._city_lookup = lambda text: None
        self.set_request(body={"city": "不存在的地方"})
        result = self.api("api_city_set")
        self.assertEqual(result["code"], 1)
        self.assertIn("没找到「不存在的地方」", result["msg"])

    def test_city_set_updates_config_and_refreshes(self):
        self.plugin.config = FakeConfig({"weather_city": "", "weather_city_name": ""})
        hit = amo_city_index.resolve_city("东莞")
        self.set_request(body={"city": "东莞"})
        result = self.api("api_city_set")
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["data"]["id"], hit["id"])
        self.assertEqual(result["data"]["name"], hit["name"])
        self.assertEqual(result["data"]["weather"], {"now": {"text": "多云"}})
        self.assertEqual(self.plugin.config["weather_city"], hit["id"])
        self.assertEqual(self.plugin.config["weather_city_name"], hit["name"])
        self.assertEqual(self.plugin.config.saved, 1)
        self.assertIn(("refresh_weather", True), self.plugin.state.calls)

    def test_city_set_same_city_reuses_cache(self):
        hit = amo_city_index.resolve_city("东莞")
        self.plugin.config = FakeConfig({
            "weather_city": hit["id"], "weather_city_name": hit["name"]})
        self.plugin.state.weather = {"now": {"text": "晴"}}
        self.set_request(body={"city": "东莞"})
        result = self.api("api_city_set")
        self.assertEqual(result["data"]["weather"], {"now": {"text": "晴"}})
        self.assertEqual(self.plugin.config.saved, 0)
        self.assertEqual(self.plugin.state.calls, [])

    def test_city_set_keep_name_and_save_failure(self):
        self.plugin.config = FakeConfig({"weather_city": "", "weather_city_name": "旧名"})
        self.set_request(body={"city": "东莞", "keep_name": 1})
        self.api("api_city_set")
        self.assertEqual(self.plugin.config["weather_city_name"], "旧名")

        self.plugin.config.save_error = RuntimeError("只读")
        self.plugin.config["weather_city"] = ""
        self.set_request(body={"city": "东莞"})
        result = self.api("api_city_set")
        self.assertEqual(result["code"], 1)
        self.assertIn("保存配置失败", result["msg"])

    def test_city_set_refresh_error_returns_empty_weather(self):
        self.plugin.config = FakeConfig({"weather_city": "", "weather_city_name": ""})
        self.plugin.state.refresh_error = RuntimeError("和风超时")
        self.set_request(body={"city": "东莞"})
        result = self.api("api_city_set")
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["data"]["weather"], {})


# ---------------------------------------------------------------------------
# 画像 / 关系
# ---------------------------------------------------------------------------

class ProfileTests(ApiTestBase):
    def _seed_profiles(self):
        for uid, name in (("u1", "甲"), ("u2", "乙"), ("u3", "丙")):
            self.plugin.db.touch_profile(uid, name, "qq", "qq:private:" + uid, "", True)

    def test_profiles_sync(self):
        self._seed_profiles()
        result = self.api("api_profiles_sync")
        self.assertEqual(result["data"]["synced"], 0)
        self.assertEqual(len(result["data"]["profiles"]), 3)
        self.assertIn("不再从记忆插件同步", result["msg"])

    def test_profiles_uses_query_and_body(self):
        self._seed_profiles()
        self.set_request(query={"q": "u", "limit": "1"})
        self.assertEqual(len(self.api("api_profiles")["data"]), 1)

        self.set_request(body={"q": "u2", "limit": "10"})
        rows = self.api("api_profiles")["data"]
        self.assertEqual([row["uid"] for row in rows], ["u2"])

    def test_get_profile_by_uid_and_first(self):
        self._seed_profiles()
        self.plugin.db.update_profile("u1", relation="相恋")
        flags = []
        async def fake_all(uid, keyword="", limit=50):
            flags.append((uid, keyword, limit))
            return [{"content": "记得"}, {"content": "两件"}]
        self.plugin._all_memories = fake_all

        self.set_request(body={"uid": "u1"})
        result = self.api("api_get_profile")
        self.assertEqual(result["data"]["relation"], "相恋")
        self.assertEqual(result["data"]["mem_count"], 2)
        self.assertEqual(result["data"]["profile"]["uid"], "u1")

        self.set_request()
        result = self.api("api_get_profile")
        self.assertIn(result["data"]["profile"]["uid"], {"u1", "u2", "u3"})

        self.set_request(query={"uid": "u2"})
        result = self.api("api_get_profile")
        self.assertEqual(result["data"]["profile"]["uid"], "u2")

    def test_profile_save_creates_and_normalizes(self):
        self._seed_profiles()
        mem = FakeMem()
        self.plugin.context = FakeContext(mem)
        self.set_request(body={
            "uid": "u9",
            "name": "小鱼",
            "alias": "鱼",
            "birthday": "1990-5-6",
            "relation": "相恋",
            "notes": "杭州来的",
            "affection": "150",
        })
        result = self.api("api_profile_save")
        self.assertEqual(result["code"], 0)
        profile = result["data"]
        self.assertEqual(profile["name"], "小鱼")
        self.assertEqual(profile["alias"], "鱼")
        self.assertEqual(profile["birthday"], "05-06")
        self.assertEqual(profile["relation"], "相恋")
        self.assertEqual(profile["affection"], 100)
        self.assertEqual(profile["notes"], "杭州来的")
        # 相恋要登记 lover，才不会被当成普通朋友
        self.assertTrue(self.plugin.db.kv_get("lover_uid_u9"))
        # 画像要推给想记
        pushes = [call for call in mem.calls if call[0] == "save_profile"]
        self.assertEqual(len(pushes), 1)
        self.assertEqual(pushes[0][1], "大肥鱼")
        self.assertEqual(pushes[0][2], "u9")

    def test_profile_save_negative_affection_and_existing(self):
        self._seed_profiles()
        self.set_request(body={"uid": "u1", "affection": "-5"})
        result = self.api("api_profile_save")
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["data"]["affection"], 0)
        self.assertEqual(len(self.plugin.db.list_profiles(limit=50)), 3)

    def test_profile_save_validation_errors(self):
        self.set_request(body={"name": "没有 uid"})
        self.assertEqual(self.api("api_profile_save")["code"], 1)

        self.set_request(body={"uid": "u1", "relation": "亲戚"})
        result = self.api("api_profile_save")
        self.assertEqual(result["code"], 1)
        self.assertIn("关系只能是", result["msg"])

        self.set_request(body={"uid": "u1", "birthday": "5/6"})
        result = self.api("api_profile_save")
        self.assertEqual(result["code"], 1)
        self.assertIn("生日格式", result["msg"])
        self.assertEqual(self.plugin.db.get_profile("u1"), {})

    def test_profile_save_push_failure_is_swallowed(self):
        async def boom(*args, **kwargs):
            raise RuntimeError("想记没装")

        self.plugin._push_profile_to_data = boom
        self.set_request(body={"uid": "u8", "name": "阿八"})
        result = self.api("api_profile_save")
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["data"]["name"], "阿八")

    def test_profile_links(self):
        self.set_request()
        self.assertEqual(self.api("api_profile_links")["data"]["links"], [])

        self.set_request(body={"uid": "u1"})
        self.assertEqual(self.api("api_profile_links")["data"]["links"], [])

        mem = FakeMem()
        mem.person = {"links": [
            {"platform": "qq", "label": "QQ", "uid": "302578963", "name": "他"},
            {"platform": "lark", "uid": "ou_x"},
        ]}
        self.plugin.context = FakeContext(mem)
        result = self.api("api_profile_links")
        self.assertEqual(result["data"]["links"], [
            {"platform": "qq", "label": "QQ", "uid": "302578963", "name": "他"},
            {"platform": "lark", "label": "lark", "uid": "ou_x", "name": ""},
        ])
        self.assertEqual(mem.calls[0][0], "person_context")
        self.assertEqual(mem.calls[0][2], "aiocqhttp")

    def test_profile_links_without_person_context(self):
        mem = types.SimpleNamespace()
        self.plugin.context = FakeContext(mem)
        self.set_request(body={"uid": "u1"})
        self.assertEqual(self.api("api_profile_links")["data"]["links"], [])

    def test_profile_delete_cleans_everything(self):
        db = self.plugin.db
        self.plugin.db.touch_profile("u1", "甲", "qq", "qq:private:u1", "", True)
        db.conn.execute("UPDATE profiles SET last_group=? WHERE uid=?", ("qq:group:g1", "u1"))
        db.conn.commit()
        db.touch_profile("u2", "乙", "qq", "qq:private:u2", "", True)
        db.upsert_relation("u1", "u2", "相恋", "恋人")
        db.upsert_relation("u2", "u3", "朋友", "")
        for uid, role in (("u1", "user"), ("u1", "bot"), ("u2", "user")):
            db.conn.execute(
                "INSERT INTO messages(umo, uid, name, role, content, created_at) "
                "VALUES(?,?,?,?,?,?)",
                ("qq:private:u1", uid, "", role, "hi", 1.0),
            )
        db.conn.execute(
            "INSERT INTO proactive_log(uid, kind, content, created) VALUES(?,?,?,?)",
            ("u1", "daily", "在吗", 1.0),
        )
        db.conn.commit()
        db.kv_set("channels:u1", {"lark": {"umo": "lark:private:u1", "ts": 1}})
        db.kv_set("lover_uid_u1", True)
        db.kv_set("ritual_morning_u1_x", 1)
        db.kv_set("channels:u2", {"qq": {"umo": "qq:private:u2", "ts": 1}})

        gift = FakeGift(removed=2)
        self.plugin.gift = gift
        self.plugin._last_umo = "lark:private:u1"
        self.plugin._last_reply_at = {"lark:private:u1": 1.0, "other": 2.0}

        self.set_request(body={"uid": "u1", "confirm": "1"})
        result = self.api("api_profile_delete")

        self.assertEqual(result["code"], 0)
        counts = result["data"]["counts"]
        self.assertEqual(counts["profiles"], 1)
        self.assertEqual(counts["messages"], 2)
        self.assertEqual(counts["proactive_log"], 1)
        self.assertEqual(counts["relation_network"], 1)
        self.assertEqual(counts["kv"], 3)
        self.assertEqual(counts["gifts"], 2)
        self.assertEqual(result["data"]["uid"], "u1")

        self.assertEqual(db.get_profile("u1"), {})
        left = db.conn.execute(
            "SELECT COUNT(*) AS c FROM messages WHERE uid='u1'").fetchone()["c"]
        self.assertEqual(left, 0)
        self.assertEqual(db.conn.execute(
            "SELECT COUNT(*) AS c FROM proactive_log WHERE uid='u1'").fetchone()["c"], 0)
        self.assertEqual(len(db.list_relations()), 1)
        self.assertIsNone(db.kv_get("channels:u1"))
        self.assertIsNone(db.kv_get("lover_uid_u1"))
        self.assertIsNone(db.kv_get("ritual_morning_u1_x"))
        self.assertIsNotNone(db.kv_get("channels:u2"))
        self.assertEqual(self.plugin._last_umo, "")
        self.assertNotIn("lark:private:u1", self.plugin._last_reply_at)
        self.assertEqual(gift.purged[0][0], "u1")
        self.assertEqual(gift.purged[0][1],
                         {"qq:private:u1", "qq:group:g1", "lark:private:u1"})

    def test_profile_delete_requires_uid_and_confirm(self):
        self.set_request(body={})
        result = self.api("api_profile_delete")
        self.assertEqual(result["code"], 1)
        self.assertEqual(result["msg"], "缺少 uid")

        self.set_request(body={"uid": "u1"})
        result = self.api("api_profile_delete")
        self.assertEqual(result["code"], 1)
        self.assertIn("confirm=1", result["msg"])

    def test_profile_delete_gift_failure_is_swallowed(self):
        self.plugin.db.touch_profile("u1", "甲", "qq", "qq:private:u1", "", True)
        self.plugin.gift = FakeGift(purge_error=RuntimeError("礼物文件坏了"))
        self.set_request(body={"uid": "u1", "confirm": "yes"})
        result = self.api("api_profile_delete")
        self.assertEqual(result["code"], 0)
        self.assertNotIn("gifts", result["data"]["counts"])


class RelationTests(ApiTestBase):
    def _seed(self):
        self.plugin.db.touch_profile("u1", "甲", "qq", "", "", True)
        self.plugin.db.touch_profile("u2", "乙", "qq", "", "", True)
        self.plugin.db.upsert_relation("u1", "u2", "朋友", "一起打游戏")

    def test_relations_maps_names(self):
        self._seed()
        result = self.api("api_relations")
        edges = result["data"]["edges"]
        self.assertEqual(edges[0]["a_name"], "甲")
        self.assertEqual(edges[0]["b_name"], "乙")
        self.assertIn("家人", result["data"]["relations"])

    def test_relation_save_validation_and_success(self):
        self._seed()
        mem = FakeMem()
        self.plugin.context = FakeContext(mem)

        self.set_request(body={"a_uid": "u1", "b_uid": "u1"})
        self.assertEqual(self.api("api_relation_save")["code"], 1)

        self.set_request(body={"a_uid": "u1", "b_uid": "u2", "relation": "亲戚"})
        result = self.api("api_relation_save")
        self.assertEqual(result["code"], 1)
        self.assertIn("关系类型无效", result["msg"])

        self.set_request(body={"a_uid": "u1", "b_uid": "u3",
                               "relation": "同事", "note": "同公司"})
        result = self.api("api_relation_save")
        self.assertEqual(result["code"], 0)
        pairs = {(edge["a_uid"], edge["b_uid"]): edge
                 for edge in result["data"]["edges"]}
        self.assertEqual(pairs[("u1", "u3")]["relation"], "同事")
        self.assertEqual(pairs[("u1", "u3")]["note"], "同公司")
        self.assertIn(("save_relation", "大肥鱼", "u1", "u3", "同事", "同公司"), mem.calls)

    def test_relation_save_push_failure_is_swallowed(self):
        async def boom(*args, **kwargs):
            raise RuntimeError("想记没装")

        self.plugin._push_relation_to_data = boom
        self.set_request(body={"a_uid": "u1", "b_uid": "u4", "relation": "朋友"})
        result = self.api("api_relation_save")
        self.assertEqual(result["code"], 0)
        self.assertTrue(any(edge["b_uid"] == "u4" for edge in result["data"]["edges"]))

    def test_relation_delete(self):
        self._seed()
        mem = FakeMem()
        self.plugin.context = FakeContext(mem)

        self.set_request(body={"a_uid": "u1"})
        self.assertEqual(self.api("api_relation_delete")["code"], 1)

        self.set_request(body={"a_uid": "u1", "b_uid": "u2"})
        result = self.api("api_relation_delete")
        self.assertEqual(result["code"], 0)
        # 真实关系边删掉了；画像里的 relation 字段还会补一条面板用的展示边
        edges = result["data"]["edges"]
        self.assertEqual([edge for edge in edges if edge.get("note") != "画像：关系字段"], [])
        self.assertEqual({edge["b_uid"] for edge in edges}, {"u1", "u2"})
        self.assertIn(("delete_relation", "大肥鱼", "u1", "u2"), mem.calls)


# ---------------------------------------------------------------------------
# 记忆面板
# ---------------------------------------------------------------------------

class MemoryTests(ApiTestBase):
    def test_memories_requires_uid(self):
        result = self.api("api_memories")
        self.assertEqual(result["code"], 1)
        self.assertEqual(result["msg"], "uid 不能为空")

    def test_memories_lists_and_limits(self):
        rows = [{"content": "记忆%d" % index} for index in range(5)]
        mem = FakeMem(rows)
        self.plugin.context = FakeContext(mem)
        self.set_request(query={"uid": "u1", "limit": "2"})
        result = self.api("api_memories")
        self.assertEqual(len(result["data"]), 2)
        self.assertEqual(mem.calls[0][0], "list_memories")
        self.assertEqual(mem.calls[0][2], "u1")

        self.set_request(query={"uid": "u1", "q": "记忆", "limit": "0"})
        result = self.api("api_memories")
        self.assertEqual(len(result["data"]), 1)  # limit 0 也至少给 1 条
        self.assertEqual(mem.calls[-1][0], "recall")
        self.assertEqual(mem.calls[-1][3], "记忆")

    def test_memories_without_data_plugin(self):
        self.set_request(body={"uid": "u1"})
        self.assertEqual(self.api("api_memories"), {"code": 0, "data": []})

    def test_memory_add(self):
        self.set_request(body={"uid": "u1"})
        self.assertEqual(self.api("api_memory_add")["code"], 1)

        self.set_request(body={"uid": "u1", "content": "他爱吃橙子", "tier": "2"})
        result = self.api("api_memory_add")
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["msg"], "已写入记忆终端")
        self.assertEqual(self.plugin.external_writes,
                         [("u1", "他爱吃橙子", "manual", 2)])

        self.plugin.external_write_ok = False
        result = self.api("api_memory_add")
        self.assertEqual(result["code"], 1)
        self.assertIn("没有可写入的记忆终端", result["msg"])

    def test_memory_delete(self):
        self.set_request(body={})
        result = self.api("api_memory_delete")
        self.assertEqual(result["code"], 1)
        self.assertIn("记忆由记忆终端保存", result["msg"])

        mem = FakeMem()
        self.plugin.context = FakeContext(mem)
        self.set_request(body={"id": "12"})
        result = self.api("api_memory_delete")
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["msg"], "已删除")
        self.assertIn(("delete_memory", "大肥鱼", 12), mem.calls)

        mem.delete_ok = False
        result = self.api("api_memory_delete")
        self.assertEqual(result["code"], 1)

    def test_chat_history(self):
        db = self.plugin.db
        db.touch_profile("u1", "甲", "qq", "qq:private:u1", "", True)
        for content, role in (("在吗", "user"), ("在呢", "bot")):
            db.conn.execute(
                "INSERT INTO messages(umo, uid, name, role, content, created_at) "
                "VALUES(?,?,?,?,?,?)",
                ("qq:private:u1", "u1", "", role, content, 1.0),
            )
        db.conn.commit()

        self.set_request()
        self.assertEqual(self.api("api_chat_history")["code"], 1)

        mem = FakeMem([{"content": "记得"}])
        self.plugin.context = FakeContext(mem)
        self.set_request(query={"uid": "u1", "limit": "10"})
        result = self.api("api_chat_history")
        self.assertEqual([row["content"] for row in result["data"]["chat"]],
                         ["在吗", "在呢"])
        self.assertEqual(result["data"]["memories"], [{"content": "记得"}])


# ---------------------------------------------------------------------------
# 心情 / 日程 / 天气 / 世界观 / 礼物 / 知识库
# ---------------------------------------------------------------------------

class StateApiTests(ApiTestBase):
    def test_mood_update_clamps_and_saves(self):
        self.set_request(body={"mood": {"开心": 150, "平静": -3, "生气": "不是数字"}})
        result = self.api("api_mood_update")
        self.assertEqual(result["code"], 0)
        self.assertEqual(self.plugin.state.mood["开心"], 100.0)
        self.assertEqual(self.plugin.state.mood["平静"], 0.0)
        self.assertNotIn("生气", self.plugin.state.mood)
        self.assertEqual(self.plugin.state.saved, 1)
        self.assertEqual(result["data"]["mood"], self.plugin.state.mood)

        # 不套 "mood" 键、直接平铺也认
        self.set_request(body={"开心": 20})
        self.api("api_mood_update")
        self.assertEqual(self.plugin.state.mood["开心"], 20.0)

    def test_schedule_today_and_other_day(self):
        with mock.patch.object(amo_api, "today_str", lambda: "2024-05-06"):
            result = self.api("api_schedule")
            data = result["data"]
            self.assertEqual(data["day"], "2024-05-06")
            self.assertEqual(data["items"], self.plugin.state.schedule)
            self.assertEqual(data["current"], {"activity": "开会"})
            self.assertIn(("ensure_schedule", self.plugin._last_umo, False),
                          self.plugin.state.calls)

            self.plugin.db.conn.execute(
                "INSERT OR REPLACE INTO schedule(day, items, updated) VALUES(?,?,?)",
                ("2000-01-02", '[{"start": "09:00", "end": "10:00", "activity": "早饭"}]', 1.0),
            )
            self.plugin.db.conn.commit()
            self.set_request(body={"date": "2000-01-02"})
            data = self.api("api_schedule")["data"]
        self.assertEqual(data["day"], "2000-01-02")
        self.assertEqual(data["meta"]["date"], "2000-01-02")
        self.assertEqual(data["items"][0]["activity"], "早饭")
        self.assertIn(("_hourly_schedule", (
            {"start": "09:00", "end": "10:00", "activity": "早饭"},)),
            self.plugin.state.calls)

    def test_schedule_detail_validates_start(self):
        self.set_request(body={"start": "abc"})
        result = self.api("api_schedule_detail")
        self.assertEqual(result["code"], 1)
        self.assertIn("start 需要 HH:MM", result["msg"])

        self.set_request(body={"start": "09"})
        result = self.api("api_schedule_detail")
        self.assertEqual(result["code"], 1)
        self.assertIn("09:00", result["msg"])

    def test_schedule_detail_expands_hour(self):
        with mock.patch.object(amo_api, "today_str", lambda: "2024-05-06"):
            self.set_request(body={"start": "10", "force": "yes"})
            result = self.api("api_schedule_detail")
        self.assertEqual(result["code"], 0)
        data = result["data"]
        self.assertEqual(data["day"], "2024-05-06")
        self.assertEqual(data["start"], "10:00")
        self.assertEqual(data["end"], "11:00")
        self.assertEqual(data["detail"], "在开周会")
        expand = [call for call in self.plugin.state.calls if call[0] == "expand_hour"][0]
        self.assertEqual(expand[1], "2024-05-06")
        self.assertEqual(expand[3][0]["start"], "10:00")
        self.assertTrue(expand[4])

    def test_schedule_detail_clamps_hour(self):
        self.plugin.state.schedule = []
        self.set_request(body={"start": "99"})
        result = self.api("api_schedule_detail")
        self.assertEqual(result["code"], 1)
        self.assertIn("23:00", result["msg"])

    def test_schedule_regen_forces(self):
        result = self.api("api_schedule_regen")
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["data"], self.plugin.state.schedule)
        self.assertIn(("ensure_schedule", self.plugin._last_umo, True),
                      self.plugin.state.calls)

    def test_weather_and_worldview(self):
        result = self.api("api_weather")
        self.assertEqual(result["data"], {"now": {"text": "多云"}})
        self.assertIn(("refresh_weather", True), self.plugin.state.calls)

        result = self.api("api_worldview")
        self.assertEqual(result["data"], {"city": "东莞"})
        self.assertIn(("ensure_worldview", self.plugin._last_umo, False),
                      self.plugin.state.calls)

        result = self.api("api_worldview_regen")
        self.assertEqual(result["data"], {"city": "深圳", "regenerated": True})
        self.assertIn(("ensure_worldview", self.plugin._last_umo, True),
                      self.plugin.state.calls)

    def test_refresh_status_throttles_and_reports_failure(self):
        clock = {"now": 1000.0}
        with mock.patch.object(amo_api, "now_ts", lambda: clock["now"]):
            result = self.api("api_refresh_status")
            self.assertEqual(result["code"], 0)
            self.assertEqual(result["msg"], "刷新成功")
            self.assertIn(("refresh_weather", True), self.plugin.state.calls)

            result = self.api("api_refresh_status")
            self.assertEqual(result["code"], 0)
            self.assertTrue(result["data"]["throttled"])
            self.assertIn("刚刚刷新过", result["msg"])

            self.plugin._refresh_status_at = 0
            clock["now"] = 2000.0
            self.plugin.state.refresh_error = RuntimeError("和风 500")
            result = self.api("api_refresh_status")
        self.assertEqual(result["code"], 1)
        self.assertIn("刷新失败", result["msg"])
        self.assertIn("和风 500", result["msg"])

    def test_gift_panel(self):
        self.assertEqual(self.api("api_gift")["data"],
                         {"enabled": False, "wishes": [], "gifts": []})

        self.plugin.gift = FakeGift(panel={"enabled": True, "wishes": ["围巾"],
                                           "gifts": [{"name": "围巾"}]})
        self.assertEqual(self.api("api_gift")["data"]["wishes"], ["围巾"])

        self.plugin.gift = FakeGift(panel_error=RuntimeError("礼物文件坏了"))
        self.assertEqual(self.api("api_gift")["data"]["enabled"], False)

    def test_kb_regen_and_scenic_kb_regen(self):
        self.plugin.config = FakeConfig({"dialect_style": ""})
        self.set_request(body={"dialect_style": "广东话"})
        result = self.api("api_kb_regen")
        self.assertEqual(result["code"], 0)
        self.assertIn("陪伴方言库-广东话", result["msg"])
        self.assertEqual(self.plugin.config["dialect_style"], "广东话")
        self.assertEqual(self.plugin.config.saved, 1)

        self.plugin.dialect_kb = None
        result = self.api("api_kb_regen")
        self.assertEqual(result["code"], 1)
        self.assertIn("知识库创建失败", result["msg"])

        result = self.api("api_scenic_kb_regen")
        self.assertEqual(result["code"], 0)
        self.assertIn("景区知识库已就绪", result["msg"])

        self.plugin.scenic_kb = None
        result = self.api("api_scenic_kb_regen")
        self.assertEqual(result["code"], 1)
        self.assertIn("景区知识库创建失败", result["msg"])

    def test_kb_regen_reads_broken_body(self):
        async def boom():
            raise RuntimeError("请求体坏了")

        self.plugin._body = boom
        self.plugin.config = FakeConfig({"dialect_style": "贵州话"})
        result = self.api("api_kb_regen")
        self.assertEqual(result["code"], 0)
        self.assertEqual(self.plugin.config["dialect_style"], "贵州话")


class SayTests(ApiTestBase):
    def setUp(self):
        super().setUp()
        self.plugin.db.touch_profile("u1", "甲", "qq", "qq:private:u1", "", True)

    def test_say_validates_arguments(self):
        self.set_request(body={})
        self.assertEqual(self.api("api_say")["code"], 1)

        self.plugin._last_umo = ""
        self.set_request(body={"text": "在吗"})
        result = self.api("api_say")
        self.assertEqual(result["code"], 1)
        self.assertEqual(result["msg"], "没有可发送的会话")

        self.plugin._last_umo = "aiocqhttp:private:302578963"
        self.set_request(body={"text": "在吗", "umo": "qq:private:unknown"})
        result = self.api("api_say")
        self.assertEqual(result["code"], 1)
        self.assertEqual(result["msg"], "umo 不在已知会话内")

    def test_say_sends_to_known_umo(self):
        self.set_request(body={"text": "在吗", "umo": "qq:private:u1"})
        result = self.api("api_say")
        self.assertEqual(result, {"code": 0, "msg": "已发送"})
        self.assertEqual(self.plugin.sent, [("qq:private:u1", "在吗")])

        self.plugin.send_ok = False
        result = self.api("api_say")
        self.assertEqual(result["code"], 1)
        self.assertEqual(result["msg"], "发送失败")

    def test_say_falls_back_to_last_umo(self):
        self.plugin._last_umo = "qq:private:u1"
        self.set_request(body={"text": "到家了"})
        result = self.api("api_say")
        self.assertEqual(result["code"], 0)
        self.assertEqual(self.plugin.sent, [("qq:private:u1", "到家了")])

    def test_say_swallows_profile_read_failure(self):
        def boom(*args, **kwargs):
            raise RuntimeError("库锁住了")

        self.plugin.db.list_profiles = boom
        self.set_request(body={"text": "在吗", "umo": "qq:private:u1"})
        result = self.api("api_say")
        self.assertEqual(result["code"], 1)
        self.assertEqual(result["msg"], "umo 不在已知会话内")


# ---------------------------------------------------------------------------
# 日记
# ---------------------------------------------------------------------------

class DiaryTests(ApiTestBase):
    def test_diary_import_validates_path(self):
        self.set_request(body={})
        self.assertEqual(self.api("api_diary_import")["msg"], "缺少文件夹路径")

        self.set_request(body={"path": "C:"})
        self.assertEqual(self.api("api_diary_import")["msg"], "别整盘导入，请选具体文件夹")

        with mock.patch.object(amo_api, "_diary_import_folder", None):
            self.set_request(body={"path": os.path.join(self.tmp, "x")})
            result = self.api("api_diary_import")
        self.assertEqual(result["code"], 1)
        self.assertEqual(result["msg"], "日记模块未加载")

    def test_diary_import_copies_folder(self):
        source = os.path.join(self.tmp, "old-diary")
        os.makedirs(source)
        with open(os.path.join(source, "我的日记2024年05月06日.txt"),
                  "w", encoding="utf-8") as handle:
            handle.write("旧日记正文")
        self.set_request(body={"path": source})
        result = self.api("api_diary_import")
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["data"]["copied"], 1)
        self.assertTrue(os.path.isfile(
            os.path.join(self.diary_path("2024-05-06"))))

    def test_diary_import_failure_result(self):
        with mock.patch.object(amo_api, "_diary_import_folder",
                               lambda src, root: {"ok": False, "error": "文件夹不存在"}):
            self.set_request(body={"path": os.path.join(self.tmp, "missing")})
            result = self.api("api_diary_import")
        self.assertEqual(result["code"], 1)
        self.assertEqual(result["msg"], "文件夹不存在")

    def diary_path(self, day):
        path = amo_api._diary_write(self.plugin.diary_dir,
                                    amo_api._diary_parse_day(day), "占位")
        return path

    def test_diary_tree_and_read(self):
        self.diary_path("2024-05-06")
        result = self.api("api_diary_tree")
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["data"]["total"], 1)

        self.set_request(body={"date": "2024-05-06"})
        result = self.api("api_diary_read")
        self.assertEqual(result["data"]["date"], "2024-05-06")
        self.assertIn("占位", result["data"]["text"])

        self.set_request(body={"date": "不是日期"})
        result = self.api("api_diary_read")
        self.assertEqual(result["code"], 1)
        self.assertIn("YYYY-MM-DD", result["msg"])

        with mock.patch.object(amo_api, "_diary_tree", None):
            result = self.api("api_diary_tree")
        self.assertEqual(result["code"], 1)
        self.assertEqual(result["msg"], "日记模块未加载")

    def test_diary_write_with_date(self):
        self.set_request(body={"date": "2024-05-06"})
        result = self.api("api_diary_write")
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["data"]["date"], "2024-05-06")
        self.assertEqual(result["data"]["text"], self.plugin.diary_text)
        self.assertTrue(os.path.isfile(result["data"]["path"]))
        self.assertEqual(
            self.plugin.db.kv_get("diary_written:2024-05-06"),
            result["data"]["path"],
        )

    def test_diary_write_defaults_to_yesterday(self):
        with mock.patch.object(amo_api, "_now",
                               lambda: datetime(2024, 5, 7, 12, 0, 0)):
            result = self.api("api_diary_write")
        self.assertEqual(result["data"]["date"], "2024-05-06")

    def test_diary_write_empty_text_and_write_failure(self):
        self.plugin.diary_text = ""
        self.set_request(body={"date": "2024-05-06"})
        result = self.api("api_diary_write")
        self.assertEqual(result["code"], 1)
        self.assertIn("日记生成失败", result["msg"])

        self.plugin.diary_text = "今天很开心。"
        with mock.patch.object(amo_api, "_diary_write",
                               side_effect=OSError("磁盘满了")):
            result = self.api("api_diary_write")
        self.assertEqual(result["code"], 1)
        self.assertIn("写入失败", result["msg"])

    def test_diary_write_kv_failure_is_swallowed(self):
        self.set_request(body={"date": "2024-05-06"})

        def boom(*args, **kwargs):
            raise RuntimeError("kv 锁住了")

        self.plugin.db.kv_set = boom
        result = self.api("api_diary_write")
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["data"]["date"], "2024-05-06")

    def test_diary_open_creates_folder(self):
        self.set_request()
        result = self.api("api_diary_open")
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["data"]["root"], self.plugin.diary_dir)
        self.assertTrue(os.path.isdir(self.plugin.diary_dir))

    def test_diary_open_makedirs_failure(self):
        blocker = os.path.join(self.tmp, "blocker")
        with open(blocker, "w", encoding="utf-8") as handle:
            handle.write("file")
        self.plugin.diary_dir = blocker
        self.set_request()
        result = self.api("api_diary_open")
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["data"]["root"], blocker)
        self.assertFalse(result["data"]["opened"])

    @unittest.skipUnless(os.name == "nt", "os.startfile 只有 Windows 有")
    def test_diary_open_calls_startfile_on_windows(self):
        self.set_request()
        started = []
        with mock.patch.object(amo_api.os, "startfile",
                               lambda path: started.append(path), create=True):
            result = self.api("api_diary_open")
        self.assertTrue(result["data"]["opened"])
        self.assertEqual(started, [self.plugin.diary_dir])


if __name__ == "__main__":
    unittest.main()
