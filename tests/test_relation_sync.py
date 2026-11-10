# -*- coding: utf-8 -*-
"""关系网同步的回归：bot/self 边推不到记忆终端，比较条数时不能再把它算进"本地"。

2026-11-09 的现象：本地 3 条（含 2 条 bot 边）、远端 1 条 →
每 10 分钟一条「关系网不同步：远端 1 条 < 本地 3 条，先不删本地」，
而且"面板删了本地也删"那段因为提前 return 永远跑不到。
"""

import asyncio
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import astrbot_stub  # noqa: E402

astrbot_stub.install()

import main as amo_main  # noqa: E402
import amo_memory_data  # noqa: E402
import amo_shared  # noqa: E402


def edge(a, b, relation="朋友", note=""):
    return {"a_uid": a, "b_uid": b, "relation": relation, "note": note}


class _Recorder:
    def __init__(self):
        self.warnings = []
        self.info = []

    def warning(self, msg, *args, **kwargs):
        self.warnings.append(str(msg))

    def info(self, msg, *args, **kwargs):
        self.info.append(str(msg))

    def debug(self, msg, *args, **kwargs):
        pass

    def error(self, msg, *args, **kwargs):
        pass


class _FakeDB:
    def __init__(self, rows):
        self.rows = [dict(r) for r in rows]
        self.deleted = []
        self.upserted = []

    def list_relations(self):
        return [dict(r) for r in self.rows]

    def upsert_relation(self, a_uid, b_uid, relation, note=""):
        self.upserted.append((str(a_uid), str(b_uid), str(relation)))
        return True

    def delete_relation(self, a_uid, b_uid):
        self.deleted.append((str(a_uid), str(b_uid)))
        return True


class _FakePlugin:
    def __init__(self, local_rows, remote_rows):
        self.db = _FakeDB(local_rows)
        self.remote = remote_rows

    async def _data_call(self, name, *args, **kwargs):
        self.assert_name = name
        if self.remote is None:
            return None
        return [dict(r) for r in self.remote]

    def _data_bot_id(self):
        return "大肥鱼"


def run_sync(plugin):
    return asyncio.run(amo_main.HumanCorePlugin._sync_relations_from_data(plugin))


class RelationSyncTests(unittest.TestCase):
    def setUp(self):
        self.recorder = _Recorder()
        self._old_logger = amo_memory_data.logger
        amo_memory_data.logger = self.recorder

    def tearDown(self):
        amo_memory_data.logger = self._old_logger

    def test_bot_edges_do_not_trigger_warning(self):
        """本机真实形状：本地 3 条（2 条 bot 边），远端 1 条真人边。"""
        plugin = _FakePlugin(
            [edge("302578963", "470488586", "相恋"),
             edge("302578963", "bot", "熟人"),
             edge("470488586", "bot", "朋友")],
            [edge("302578963", "470488586", "相恋")],
        )
        count = run_sync(plugin)

        self.assertEqual(count, 1)
        self.assertEqual(self.recorder.warnings, [])
        self.assertEqual(plugin.db.deleted, [])
        # 三条本地边一条都不能丢
        self.assertEqual(len(plugin.db.list_relations()), 3)

    def test_bot_edges_on_remote_side_ignored(self):
        plugin = _FakePlugin(
            [edge("A", "B"), edge("A", "bot"), edge("B", "bot")],
            [edge("A", "B"), edge("B", "bot")],
        )
        run_sync(plugin)
        self.assertEqual(self.recorder.warnings, [])
        self.assertEqual(plugin.db.deleted, [])

    def test_warning_still_fires_for_real_decrease(self):
        """真的少了一条真人边（换库/残缺备份）时，保护逻辑还得在。"""
        plugin = _FakePlugin(
            [edge("A", "B"), edge("A", "C"), edge("A", "bot")],
            [edge("A", "B")],
        )
        run_sync(plugin)
        self.assertEqual(len(self.recorder.warnings), 1)
        self.assertIn("关系网不同步", self.recorder.warnings[0])
        self.assertEqual(plugin.db.deleted, [])

    def test_remote_deletion_propagates(self):
        """远端和本地真人边条数相等时，本地独有的那条要被删掉。"""
        plugin = _FakePlugin(
            [edge("A", "B"), edge("A", "C"), edge("A", "bot")],
            [edge("A", "B"), edge("A", "D")],
        )
        run_sync(plugin)
        self.assertEqual(plugin.db.deleted, [("A", "C")])
        self.assertNotIn(("A", "bot"), plugin.db.deleted)
        self.assertEqual(self.recorder.warnings, [])

    def test_empty_remote_keeps_local(self):
        plugin = _FakePlugin([edge("A", "B")], [])
        run_sync(plugin)
        self.assertEqual(plugin.db.deleted, [])
        self.assertEqual(self.recorder.warnings, [])

    def test_none_remote_keeps_local(self):
        plugin = _FakePlugin([edge("A", "B")], None)
        self.assertEqual(run_sync(plugin), 0)
        self.assertEqual(plugin.db.deleted, [])


class InternalNodeConstantTests(unittest.TestCase):
    def test_push_uses_same_nodes(self):
        """推送过滤和同步过滤必须用同一个常量，不然两边又会脱节。"""
        self.assertEqual(tuple(amo_shared.INTERNAL_RELATION_NODES), ("bot", "self"))


if __name__ == "__main__":
    unittest.main()
