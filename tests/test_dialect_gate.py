# -*- coding: utf-8 -*-
"""方言开关的回归测试。

三件事：
1. 方言选择里选「普通话」= 彻底关掉方言（就算 `dialect_enabled` 还是 true）；
2. 关掉时不再检索方言知识库（不查、不注入，省一次 embedding 和一段提示词）；
3. 开着的时候行为不变（该查还查）。

做法：把 `main.py` 里的 `_dialect_active()` / `_dialect_style()` / `_dialect_kb_context()`
从源码抠出来执行，喂一个假 self。
"""

from __future__ import annotations

import ast
import asyncio
import os
import types
import unittest

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(PLUGIN, "main.py")
SRC = open(MAIN, encoding="utf-8").read()


def module_ns():
    """把 _dialect_style 依赖的模块级常量和 dialect_for_city 一起带上。"""
    tree = ast.parse(SRC)
    ns = {"logger": types.SimpleNamespace(debug=lambda *a, **k: None, warning=lambda *a, **k: None)}
    wanted_consts = {"CITY_DIALECT_RULES", "DIALECT_REGIONS", "DIALECT_SAMPLES"}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(name in wanted_consts for name in names):
                exec(compile(ast.Module([node], []), "<const>", "exec"), ns)
        elif isinstance(node, ast.FunctionDef) and node.name == "dialect_for_city":
            exec(compile(ast.Module([node], []), "<fn>", "exec"), ns)
    return ns


def load_method(name):
    tree = ast.parse(SRC)
    ns = module_ns()
    for item in ast.walk(tree):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name:
            exec(compile(ast.get_source_segment(SRC, item), "<" + name + ">", "exec"), ns)
            return ns[name]
    raise SystemExit("main.py 里找不到 " + name)


ACTIVE = load_method("_dialect_active")
STYLE = load_method("_dialect_style")
KB_CONTEXT = load_method("_dialect_kb_context")


class ExplodingKB:
    """一碰就报错：用来证明"关掉方言后根本没去查知识库"。"""

    def __init__(self):
        self.touched = 0

    async def get_kb_by_name(self, name):
        self.touched += 1
        raise AssertionError("关掉方言后不该检索方言库")


class SilentKB:
    def __init__(self):
        self.touched = 0

    async def get_kb_by_name(self, name):
        self.touched += 1
        return None


class FakeSelf:
    """够 `_dialect_active` / `_dialect_style` / `_dialect_kb_context` 用的最小假体。"""

    _dialect_active = ACTIVE
    _dialect_style = STYLE

    def __init__(self, enabled=True, style="", manager=None, city=""):
        self.enabled = enabled
        self.style = style
        self.city = city
        self.state = types.SimpleNamespace(worldview={"city": city} if city else {})
        self.context = types.SimpleNamespace(kb_manager=manager)

    def cfg_bool(self, key, default=False):
        if key == "dialect_enabled":
            return self.enabled
        return default

    def cfg_str(self, key, default=""):
        if key == "dialect_style":
            return self.style
        return default

    def _dialect_kb_name(self):
        style = self._dialect_style().strip()
        base = "陪伴方言库"
        return base + "-" + style if style else base


class ActiveFlagTests(unittest.TestCase):
    def test_plain_mandarin_means_off(self):
        self.assertFalse(FakeSelf(enabled=True, style="普通话")._dialect_active())

    def test_dialect_on(self):
        self.assertTrue(FakeSelf(enabled=True, style="广东话")._dialect_active())

    def test_master_switch_off(self):
        self.assertFalse(FakeSelf(enabled=False, style="广东话")._dialect_active())

    def test_default_auto_follows_city(self):
        mine = FakeSelf(enabled=True, style="", city="东莞")
        self.assertTrue(mine._dialect_active())
        self.assertEqual(mine._dialect_style(), "广东话")

    def test_auto_keyword_is_not_a_style(self):
        mine = FakeSelf(enabled=True, style="自动", city="东莞")
        self.assertEqual(mine._dialect_style(), "广东话")
        self.assertTrue(mine._dialect_active())


class KbGateTests(unittest.TestCase):
    def test_plain_mandarin_never_touches_kb(self):
        kb = ExplodingKB()
        out = asyncio.run(KB_CONTEXT(FakeSelf(enabled=True, style="普通话", manager=kb), "今天好热啊"))
        self.assertEqual(out, "")
        self.assertEqual(kb.touched, 0, "普通话不该碰知识库")

    def test_switch_off_never_touches_kb(self):
        kb = ExplodingKB()
        asyncio.run(KB_CONTEXT(FakeSelf(enabled=False, style="广东话", manager=kb), "x"))
        self.assertEqual(kb.touched, 0)

    def test_dialect_on_still_queries(self):
        kb = SilentKB()
        asyncio.run(KB_CONTEXT(FakeSelf(enabled=True, style="广东话", manager=kb), "今天好热啊"))
        self.assertGreaterEqual(kb.touched, 1, "开着的时候仍要检索")


    def test_plain_mandarin_never_builds_kb(self):
        kb = ExplodingKB()
        ensure = load_method("_ensure_dialect_kb")
        out = asyncio.run(ensure(FakeSelf(enabled=True, style="普通话", manager=kb)))
        self.assertIsNone(out)
        self.assertEqual(kb.touched, 0, "普通话不该去建/同步方言库")

class WiringTests(unittest.TestCase):
    """静态检查：面板和保存接口这两处别被改回去。"""

    def test_config_save_allows_dialect_style(self):
        self.assertIn('key == "dialect_style"', SRC, "config_save 必须放行 dialect_style")

    def test_panel_has_mandarin_option(self):
        with open(os.path.join(PLUGIN, "views", "dashboard", "index.html"), encoding="utf-8") as stream:
            html = stream.read()
        self.assertIn('<option value="普通话">', html)
        self.assertIn('dialect_enabled: false', html, "选普通话时要顺手关掉方言开关")
        self.assertIn('create_dialect_kb: true', html, "选回方言时要把方言库开关恢复")


if __name__ == "__main__":
    unittest.main()
