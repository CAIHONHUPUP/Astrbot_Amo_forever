# -*- coding: utf-8 -*-
"""方言开关：dialect_enabled=false 时，连方言知识库都不该查。

行为测试：把 main.py 里的 `_dialect_kb_context()` 从源码抠出来执行，
假的 self 里放一个"一碰就会炸"的 kb_manager——关掉方言时它不该被碰。
"""

from __future__ import annotations

import ast
import asyncio
import os
import sys
import textwrap
import types
import unittest

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(PLUGIN, "main.py")


def load_method():
    src = open(MAIN, encoding="utf-8").read()
    tree = ast.parse(src)
    node = None
    for item in ast.walk(tree):
        if isinstance(item, ast.AsyncFunctionDef) and item.name == "_dialect_kb_context":
            node = item
            break
    if node is None:
        raise SystemExit("main.py 里找不到 _dialect_kb_context")
    body = textwrap.dedent(ast.get_source_segment(src, node))
    ns = {"logger": types.SimpleNamespace(debug=lambda *a, **k: None)}
    exec(compile(body, "<_dialect_kb_context>", "exec"), ns)
    return ns["_dialect_kb_context"]


class ExplodingKB:
    """被调用就报错，用来证明"关掉方言后根本没去查知识库"。"""

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
    def __init__(self, enabled, manager):
        self.enabled = enabled
        self.context = types.SimpleNamespace(kb_manager=manager)

    def cfg_bool(self, key, default=False):
        if key == "dialect_enabled":
            return self.enabled
        return default

    def _dialect_kb_name(self):
        return "陪伴方言库-广东话"


class DialectGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.method = staticmethod(load_method())

    def test_disabled_never_touches_kb(self):
        kb = ExplodingKB()
        out = asyncio.run(self.method(FakeSelf(False, kb), "今天好热啊"))
        self.assertEqual(out, "")
        self.assertEqual(kb.touched, 0, "关掉方言后不该碰知识库")

    def test_disabled_without_manager_is_safe(self):
        self.assertEqual(asyncio.run(self.method(FakeSelf(False, None), "x")), "")

    def test_enabled_still_queries(self):
        kb = SilentKB()
        self.assertEqual(asyncio.run(self.method(FakeSelf(True, kb), "今天好热啊")), "")
        self.assertGreaterEqual(kb.touched, 1, "开着的时候仍要检索一次")


if __name__ == "__main__":
    unittest.main()
