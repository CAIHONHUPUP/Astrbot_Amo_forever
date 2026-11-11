# -*- coding: utf-8 -*-
"""`amo_image_common`：照片 / 画图两个引擎的公共层。

这些函数以前在两个引擎里各写一份（有的还漂移过），所以这里既测行为，
也加一条源码守卫，防止有人再往引擎里抄一份。
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import astrbot_stub  # noqa: E402

astrbot_stub.install()

import amo_image_common as C  # noqa: E402
import amo_observability as OBS  # noqa: E402
import draw_engine as DE  # noqa: E402
import photo_engine as PE  # noqa: E402
import test_draw_engine as DT  # noqa: E402
import test_photo_engine as PT  # noqa: E402


class CleanPlaceTests(unittest.TestCase):
    def test_desk_becomes_home(self):
        self.assertEqual(C.clean_place("他桌面上"), "家里")
        self.assertEqual(C.clean_place("她的床边"), "家里")

    def test_plain_place_is_kept(self):
        self.assertEqual(C.clean_place("西湖"), "西湖")
        self.assertEqual(C.clean_place(""), "")

    def test_long_place_is_truncated(self):
        self.assertEqual(C.clean_place("东莞" * 20), ("东莞" * 20)[: C.PLACE_MAX_CHARS])

    def test_both_engines_share_one_implementation(self):
        # 以前 photo 截断、draw 不截断，现在必须是同一个结果
        sample = "东莞" * 20
        self.assertEqual(DE.DrawEngine._clean_place(sample), PE.PhotoEngine._clean_place(sample))


class CfgTests(unittest.TestCase):
    class Plugin:
        def __init__(self, values, boom=False):
            self.values = values
            self.boom = boom

        def _read(self, key, default):
            if self.boom:
                raise RuntimeError("配置坏了")
            return self.values.get(key, default)

        def cfg_bool(self, key, default=False):
            return self._read(key, default)

        def cfg_int(self, key, default=0):
            return self._read(key, default)

        def cfg_float(self, key, default=0.0):
            return self._read(key, default)

        def cfg_str(self, key, default=""):
            return self._read(key, default)

    def test_types(self):
        plugin = self.Plugin({"b": 1, "i": "12", "f": "1.5", "s": 3})
        self.assertIs(C.cfg(plugin, "b", False, bool), True)
        self.assertEqual(C.cfg(plugin, "i", 0, int), 12)
        self.assertEqual(C.cfg(plugin, "f", 0.0, float), 1.5)
        self.assertEqual(C.cfg(plugin, "s", "", str), "3")

    def test_bad_values_fall_back(self):
        plugin = self.Plugin({"i": "不是数字", "f": "x", "b": "yes"})
        self.assertEqual(C.cfg(plugin, "i", 7, int), 7)
        self.assertEqual(C.cfg(plugin, "f", 2.0, float), 2.0)
        self.assertIs(C.cfg(plugin, "b", False, bool), True)  # "yes" 也是真
        self.assertEqual(C.cfg(plugin, "missing", 5, int), 5)

    def test_reader_exception_is_counted_not_raised(self):
        OBS.reset()
        plugin = self.Plugin({}, boom=True)
        self.assertEqual(C.cfg(plugin, "photo_daily_cap", 4, int, "test.cfg"), 4)
        self.assertEqual(OBS.snapshot().get("test.cfg"), 1)

    def test_plugin_without_reader_returns_default(self):
        self.assertEqual(C.cfg(object(), "k", 9, int), 9)


class SpawnTests(unittest.TestCase):
    def test_uses_plugin_spawn(self):
        plugin = mock.Mock()
        plugin._spawn.return_value = "task"
        coro = asyncio.sleep(0)
        try:
            self.assertEqual(C.spawn(plugin, coro), "task")
        finally:
            coro.close()

    def test_plugin_spawn_returning_none_means_failed(self):
        plugin = mock.Mock()
        plugin._spawn.return_value = None

        async def noop():
            return 1

        coro = noop()
        self.assertIsNone(C.spawn(plugin, coro))
        coro.close()

    def test_falls_back_to_create_task(self):
        class NoSpawn:
            pass

        async def main():
            task = C.spawn(NoSpawn(), asyncio.sleep(0))
            self.assertIsInstance(task, asyncio.Task)
            await task

        asyncio.run(main())


class FindOmniTests(unittest.TestCase):
    class Holder:
        _omni = None
        _omni_checked = 0.0

    class Plugin:
        def __init__(self, instance):
            self.calls = 0
            self.instance = instance
            self.context = self

        def get_registered_star(self, name):
            self.calls += 1
            if self.instance is None:
                return None

            class Meta:
                star_cls = self.instance

            return Meta()

    def test_finds_and_caches(self):
        instance = type("Omni", (), {"generate_images_for_plugin": lambda self, **kw: None})()
        plugin = self.Plugin(instance)
        holder = self.Holder()
        self.assertIs(C.find_omni(plugin, holder), instance)
        self.assertIs(C.find_omni(plugin, holder), instance)
        self.assertEqual(plugin.calls, 1)  # 第二次走缓存

    def test_missing_plugin_returns_none(self):
        holder = self.Holder()
        self.assertIsNone(C.find_omni(self.Plugin(None), holder))

    def test_context_without_getter_is_safe(self):
        holder = self.Holder()
        self.assertIsNone(C.find_omni(object(), holder))


class ImageComponentTests(unittest.TestCase):
    def test_data_url_wins(self):
        component = C.image_component({"data_url": "data:image/png;base64,AAA", "file_path": "x.png"})
        self.assertIsNotNone(component)
        self.assertIn("base64://", component.file)

    def test_file_path(self):
        component = C.image_component({"file_path": "C:/tmp/a.png"})
        self.assertIsNotNone(component)

    def test_url(self):
        component = C.image_component({"url": "https://example.com/a.png"})
        self.assertIsNotNone(component)

    def test_nothing_usable(self):
        self.assertIsNone(C.image_component({}))
        self.assertIsNone(C.image_component(None))


class PersonaConfigTests(unittest.TestCase):
    def test_payload_uses_its_own_schema_keys(self):
        raw = {"persona_config": {"persona_ref_images": [], "profiles": [{"id": "default"}]},
               "providers": []}
        omni = type("Omni", (), {"raw_config": raw})()
        payload = C.persona_config_payload(omni, ["a.png", "b.png"])
        persona = payload["persona_config"]
        self.assertEqual(persona["persona_ref_images"], ["a.png", "b.png"])
        self.assertEqual(persona["persona_ref_image"], "a.png")  # 单个键必须是字符串
        self.assertEqual(persona["profiles"][0]["persona_ref_images"], ["a.png", "b.png"])
        # 不能改到对方原本的对象
        self.assertEqual(raw["persona_config"]["persona_ref_images"], [])

    def test_payload_without_raw_config(self):
        omni = type("Omni", (), {})()
        self.assertIsNone(C.persona_config_payload(omni, ["a.png"]))


class ApplyPersonaTests(unittest.TestCase):
    class OmniWithEntry:
        def __init__(self):
            self.raw_config = {"persona_config": {"profiles": []}}
            self.applied = []
            self.persisted = 0
            self.synced = 0

        def _apply_runtime_config(self, payload):
            self.applied.append(payload)

        def _persist_config(self):
            self.persisted += 1

        def _safe_update_context_config(self):
            self.synced += 1

    def test_goes_through_its_own_entry(self):
        omni = self.OmniWithEntry()
        self.assertTrue(C.apply_persona_config(omni, ["a.png"]))
        self.assertEqual(len(omni.applied), 1)
        self.assertEqual(omni.applied[0]["persona_config"]["persona_ref_images"], ["a.png"])
        self.assertEqual(omni.persisted, 1)
        self.assertEqual(omni.synced, 1)

    def test_falls_back_to_memory_only(self):
        """没有配置入口时只改内存，绝不自己去写文件。"""
        class Cfg:
            persona_ref_image = ""
            persona_ref_images = []
            personas = []

        omni = type("Omni", (), {"plugin_config": Cfg()})()
        with mock.patch("builtins.open", side_effect=AssertionError("不该写文件")):
            self.assertTrue(C.apply_persona_config(omni, ["a.png"]))
        self.assertEqual(omni.plugin_config.persona_ref_images, ["a.png"])
        self.assertEqual(omni.plugin_config.persona_ref_image, "a.png")

    def test_apply_failure_degrades_to_memory(self):
        class Broken(self.OmniWithEntry):
            def _apply_runtime_config(self, payload):
                raise RuntimeError("它的配置坏了")

        omni = Broken()
        omni.plugin_config = type("Cfg", (), {"persona_ref_image": "", "persona_ref_images": [],
                                              "personas": []})()
        self.assertTrue(C.apply_persona_config(omni, ["a.png"]))
        self.assertEqual(omni.plugin_config.persona_ref_images, ["a.png"])


class SyncRefsTests(unittest.TestCase):
    def test_photo_sync_uses_public_entry(self):
        engine, plugin = PT.engine_for()
        omni = ApplyPersonaTests.OmniWithEntry()
        engine._omni = omni
        engine._omni_checked = 10 ** 9  # 不再重新找实例
        with mock.patch("builtins.open", side_effect=AssertionError("不该写万象画卷的配置文件")):
            engine._sync_omni_refs()
        self.assertEqual(len(omni.applied), 1)

    def test_sync_without_omni_is_noop(self):
        engine, _ = PT.engine_for()
        engine._omni = None
        engine._omni_checked = 10 ** 9
        engine._sync_omni_refs()  # 不抛就算过

    def test_engines_no_longer_write_omni_config_files(self):
        """守卫：以前直接 open/dump 万象画卷的 json，现在必须走它的配置入口。"""
        source = open(os.path.join(ROOT, "photo_engine.py"), encoding="utf-8").read()
        self.assertNotIn("_omni_native_config", source)   # 计算对方配置文件路径的那段已删
        self.assertNotIn("json.dump(", source)            # 不再自己拼 json 落盘
        self.assertIn("apply_persona_config(", source)    # 改为走对方的配置入口


class DrawIntegrationTests(unittest.TestCase):
    def test_draw_engine_still_uses_shared_helpers(self):
        engine, plugin = DT.engine_for()
        # 公共层拿到的是插件 context 里那个万象画卷实例
        self.assertIs(engine._find_omni(), plugin.context.omni)
        self.assertEqual(engine._cfg_int("draw_max_per_day", 10),
                         int(plugin.config.get("draw_max_per_day", 10)))

    def test_draw_image_component_delegates(self):
        self.assertIsNone(DE.DrawEngine._image_component({}))
        self.assertIsNotNone(DE.DrawEngine._image_component({"file_path": "C:/tmp/a.png"}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
