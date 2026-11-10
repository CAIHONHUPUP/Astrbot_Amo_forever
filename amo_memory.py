# -*- coding: utf-8 -*-
"""MemoryMixin：从 main.py 拆出的 mixin，由 HumanCorePlugin 组合使用。"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3

try:
    from .amo_observability import note as _note_swallowed
except ImportError:
    from amo_observability import note as _note_swallowed

try:
    from .clock import from_timestamp as _clock_from_ts
except ImportError:
    from clock import from_timestamp as _clock_from_ts

try:
    from .amo_shared import (
        INTERNAL_RELATION_NODES, PLUGIN_NAME, _looks_like_time_query, _now, _render_time_block, logger, now_ts, overlap, to_float, to_int, tokens,
    )
except ImportError:  # 直接按文件加载时
    from amo_shared import (
        INTERNAL_RELATION_NODES, PLUGIN_NAME, _looks_like_time_query, _now, _render_time_block, logger, now_ts, overlap, to_float, to_int, tokens,
    )


class MemoryMixin:
    @staticmethod
    def _memcomp_db_path(plugin):
        service = getattr(plugin, "service", None)
        store = getattr(service, "store", None)
        path = getattr(store, "db_path", None)
        if path and os.path.isfile(str(path)):
            return str(path)
        data_dir = getattr(service, "data_dir", None) or getattr(plugin, "data_dir", None)
        if data_dir:
            candidate = os.path.join(str(data_dir), "memory_companion.db")
            if os.path.isfile(candidate):
                return candidate
        return ""

    def _memcomp_rows(self, sql, params=()):
        path = self._memcomp_db_path(self._companion_plugin())
        if not path:
            return []
        conn = None
        try:
            from urllib.parse import quote
            try:
                conn = sqlite3.connect(
                    "file:" + quote(path) + "?mode=ro",
                    uri=True,
                    timeout=2.0,
                )
            except Exception as _amo_exc:
                _note_swallowed("amo_memory.HumanCorePlugin._memcomp_rows", _amo_exc)
                conn = sqlite3.connect(path, timeout=2.0)
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(sql, params).fetchall()]
        except Exception as exc:
            logger.debug("[amo] 读取 Memory Companion 数据库失败: %s" % exc)
            return []
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception as _amo_exc:
                    _note_swallowed("amo_memory.HumanCorePlugin._memcomp_rows", _amo_exc)

    def _memcomp_name_maps(self, plugin=None):
        """从 identities/profile/证据里建立 person_id -> 名字 的自动映射。"""
        plugin = plugin or self._companion_plugin()
        by_uid = {}
        by_key = {}
        evidence_map = {}
        try:
            rows = self._memcomp_rows(
                "SELECT entity_id, display_name, profile FROM identities "
                "WHERE entity_kind='user' AND entity_id!=''"
            )
            for row in rows:
                uid = str(row.get("entity_id") or "").strip()
                name = str(row.get("display_name") or "").strip()
                if uid and name:
                    by_uid[uid] = name
                try:
                    profile = json.loads(row.get("profile") or "{}")
                except Exception as _amo_exc:
                    _note_swallowed("amo_memory.HumanCorePlugin._memcomp_name_maps", _amo_exc)
                    profile = {}
                if not isinstance(profile, dict):
                    continue
                for key in ("display_name", "name", "nickname"):
                    if not name and profile.get(key):
                        name = str(profile.get(key)).strip()
                if name:
                    for key in ("person_id", "resolved_identity_key", "identity_key"):
                        value = str(profile.get(key) or "").strip()
                        if value:
                            by_key[value] = name
        except Exception as exc:
            logger.debug("[amo] 建立身份名字映射失败: %s" % exc)
        try:
            rows = self._memcomp_rows(
                "SELECT e.person_id, t.subject_id, i.display_name "
                "FROM portrait_evidence e "
                "LEFT JOIN timeline t ON t.message_id=e.message_id "
                "LEFT JOIN identities i ON i.entity_id=t.subject_id "
                "WHERE e.person_id!='' AND i.display_name!=''"
            )
            for row in rows:
                pid = str(row.get("person_id") or "").strip()
                name = str(row.get("display_name") or "").strip()
                if pid and name:
                    evidence_map.setdefault(pid, name)
        except Exception as exc:
            logger.debug("[amo] 建立证据名字映射失败: %s" % exc)
        return {"by_uid": by_uid, "by_key": by_key, "evidence": evidence_map}

    def _memcomp_person_name(self, person_id, identity_key="", maps=None):
        """按 画像事实 -> 身份键 -> 身份表 -> 证据 的顺序自动取名字。"""
        maps = maps or self._memcomp_name_maps()
        rows = self._memcomp_rows(
            "SELECT dimension, claim_summary FROM portrait_facts "
            "WHERE person_id=? AND status='active' "
            "ORDER BY confidence DESC, updated_at DESC LIMIT 40",
            (str(person_id),),
        )
        name_dims = {
            "name", "display_name", "nickname", "preferred_address",
            "用户别名", "称呼", "昵称", "姓名", "名字",
        }
        patterns = (
            r"(?:名字|姓名|昵称|称呼|别名)(?:是|叫|为|：|:)\s*([^\s，。；;,.!?！？]{1,20})",
            r"(?:叫我|叫做|名为)\s*([^\s，。；;,.!?！？]{1,20})",
        )
        for row in rows:
            dimension = str(row.get("dimension") or "").strip().lower()
            claim = re.sub(r"\s+", " ", str(row.get("claim_summary") or "")).strip()
            if not claim:
                continue
            if dimension in name_dims:
                text = claim
                for pattern in patterns:
                    match = re.search(pattern, text)
                    if match:
                        text = match.group(1)
                        break
                text = text.strip("「」“”\"' ")
                if 1 <= len(text) <= 20:
                    return text
            for pattern in patterns:
                match = re.search(pattern, claim)
                if match:
                    text = match.group(1).strip("「」“”\"' ")
                    if 1 <= len(text) <= 20:
                        return text
        for candidate in (str(identity_key or "").strip(), str(person_id)):
            if candidate and maps.get("by_key", {}).get(candidate):
                return maps["by_key"][candidate]
        if maps.get("by_uid", {}).get(str(person_id)):
            return maps["by_uid"][str(person_id)]
        if maps.get("evidence", {}).get(str(person_id)):
            return maps["evidence"][str(person_id)]
        return ""

    def _memcomp_profile_rows(self, plugin=None):
        """以 portrait_facts 为准：只有真正有画像事实的人才是用户画像。"""
        plugin = plugin or self._companion_plugin()
        if not self._is_memory_companion(plugin):
            return []
        rows = self._memcomp_rows(
            "SELECT person_id, resolved_identity_key, 0 AS fact_count FROM portrait_people "
            "WHERE profile_status='active' AND person_id!='' "
            "ORDER BY updated_at DESC"
        )
        maps = self._memcomp_name_maps(plugin)
        items = []
        for row in rows:
            uid = str(row.get("person_id") or "").strip()
            if not uid:
                continue
            name = self._memcomp_person_name(
                uid, str(row.get("resolved_identity_key") or ""), maps
            )
            items.append({
                "uid": uid,
                "name": name or ("画像 " + uid[-6:]),
                "count": to_int(row.get("fact_count"), 0),
                "source": "portrait_people",
            })
        if items:
            return items
        # 老库没有 portrait_facts 时，退回 identities，但只取真实用户/有资料者。
        user_roles = (
            "conversation_partner", "external_memory_owner", "user", "admin",
            "member", "friend", "owner", "lover", "partner",
        )
        placeholders = ",".join("?" for _ in user_roles)
        rows = self._memcomp_rows(
            "SELECT entity_id, display_name, profile FROM identities "
            "WHERE entity_kind='user' AND entity_id!='' "
            "AND LOWER(COALESCE(role,'')) IN (" + placeholders + ") "
            "AND COALESCE(profile,'') NOT IN ('', '{}', 'null')",
            user_roles,
        )
        items = []
        for row in rows:
            uid = str(row.get("entity_id") or "").strip()
            if not uid:
                continue
            name = str(row.get("display_name") or "").strip()
            if not name:
                try:
                    parsed = json.loads(row.get("profile") or "{}")
                    if isinstance(parsed, dict):
                        name = str(parsed.get("name") or parsed.get("nickname") or "").strip()
                except Exception as _amo_exc:
                    _note_swallowed("amo_memory.HumanCorePlugin._memcomp_profile_rows", _amo_exc)
            items.append({"uid": uid, "name": name, "count": 0, "source": "identities"})
        return items

    def _memcomp_profile_uids(self, plugin=None):
        plugin = plugin or self._companion_plugin()
        return {row["uid"] for row in self._memcomp_profile_rows(plugin)}

    def _memcomp_user_count(self, plugin=None):
        plugin = plugin or self._companion_plugin()
        if not self._is_memory_companion(plugin):
            return 0
        return len(self._memcomp_profile_rows(plugin))

    def _memcomp_memories(self, uid, keyword="", limit=50):
        plugin = self._companion_plugin()
        if not self._is_memory_companion(plugin):
            return []
        rows = self._memcomp_rows(
            "SELECT claim_summary, dimension, confidence, created_at, updated_at "
            "FROM portrait_facts WHERE person_id=? AND status='active' "
            "ORDER BY confidence DESC, updated_at DESC LIMIT ?",
            (str(uid), max(1, min(100, to_int(limit, 50)))),
        )
        items = []
        for row in rows:
            content = re.sub(r"\s+", " ", str(row.get("claim_summary") or "")).strip()
            if len(content) < 2:
                continue
            if keyword and str(keyword).lower() not in content.lower():
                continue
            confidence = to_float(row.get("confidence"), 0.5)
            items.append({
                "content": content[:500],
                "tier": 2 if confidence >= 0.8 else (1 if confidence >= 0.55 else 0),
                "kind": "memory_companion",
                "source": "memory_companion",
                "memory_type": row.get("dimension", "profile"),
                "created_at": row.get("created_at", ""),
                "hits": 0,
                "expires_at": None,
            })
        if items:
            return items
        # 兼容旧库：没有 portrait_facts 时，只返回画像类 memory_type。
        sql = (
            "SELECT content, importance, memory_type, created_at, updated_at "
            "FROM memories WHERE (subject_id=? OR object_id=?) AND content!='' "
            "AND lifecycle NOT IN ('deleted','archived','quarantined') "
            "AND memory_type IN ('user_profile','user_preference','relationship_claim','user_habit') "
        )
        params = [str(uid), str(uid)]
        if keyword:
            sql += "AND content LIKE ? "
            params.append("%" + str(keyword) + "%")
        sql += "ORDER BY importance DESC, updated_at DESC LIMIT ?"
        params.append(max(1, min(100, to_int(limit, 50))))
        for row in self._memcomp_rows(sql, tuple(params)):
            content = re.sub(r"\s+", " ", str(row.get("content") or "")).strip()
            if len(content) < 2:
                continue
            importance = to_float(row.get("importance"), 0.3)
            items.append({
                "content": content[:500],
                "tier": 2 if importance >= 0.72 else (1 if importance >= 0.42 else 0),
                "kind": "memory_companion",
                "source": "memory_companion",
                "memory_type": row.get("memory_type", ""),
                "created_at": row.get("created_at", ""),
                "hits": 0,
                "expires_at": None,
            })
        return items

    @staticmethod
    def _star_instance(meta):
        """AstrBot 不同版本把实例放在 star_cls / instance / star 上，挨个试。"""
        if meta is None:
            return None
        for attr in ("star_cls", "instance", "star", "plugin"):
            value = getattr(meta, attr, None)
            if value is not None and hasattr(value, "mem"):
                return value
        return None

    def _data_plugin(self):
        """找「我想永远记住你」插件实例；没装就返回 None。"""
        try:
            for name in self.DATA_PLUGIN_NAMES:
                star = self._star_instance(self.context.get_registered_star(name))
                if star is not None:
                    return star
        except Exception as _amo_exc:
            _note_swallowed("amo_memory.HumanCorePlugin._data_plugin", _amo_exc)
        try:
            for meta in self.context.get_all_stars():
                marker = (getattr(meta, "name", "") or "") + " " + (getattr(meta, "module_path", "") or "")
                star = self._star_instance(meta)
                if star is not None and "amo_data" in marker.lower():
                    return star
        except Exception as _amo_exc:
            _note_swallowed("amo_memory.HumanCorePlugin._data_plugin", _amo_exc)
        return None

    def _data_mem(self):
        plugin = self._data_plugin()
        return getattr(plugin, "mem", None) if plugin is not None else None

    def _normalize_memories(self, rows):
        """把各家插件返回的记忆统一成 {content, tier, name, kind, ...}。"""
        items = []
        for row in rows or []:
            if isinstance(row, dict):
                content = str(row.get("content") or row.get("memory") or "").strip()
                importance = to_float(row.get("importance"), 0.5)
                name = str(row.get("name") or row.get("who") or "").strip()
                kind = str(row.get("kind") or row.get("memory_type") or "fact")
                created_at = row.get("created_at", 0)
            else:
                memory = getattr(row, "memory", None) or row
                content = str(getattr(memory, "content", "") or "").strip()
                importance = to_float(getattr(memory, "importance", 0.5), 0.5)
                name = str(getattr(memory, "name", "") or "").strip()
                kind = str(getattr(memory, "memory_type", "") or "fact")
                created_at = getattr(memory, "created_at", 0)
            if len(content) < 2:
                continue
            items.append({
                "content": content[:500],
                "tier": 2 if importance >= 0.72 else (1 if importance >= 0.42 else 0),
                "importance": importance,
                "kind": kind,
                "name": name,
                "source": "hub",
                "created_at": created_at,
                "hits": 0,
                "expires_at": None,
            })
        return items

    def _data_store(self):
        """兜底：直接拿数据插件的 DataStore（mem 门面缺失/旧版时用）。"""
        plugin = self._data_plugin()
        return getattr(plugin, "store", None) if plugin is not None else None

    def _data_connected(self):
        """数据插件此刻在不在：只看内存里的插件表，不读库、不联网。"""
        plugin = self._data_plugin()
        if plugin is None:
            return False
        return getattr(plugin, "mem", None) is not None or getattr(plugin, "store", None) is not None

    def _data_bot_id(self):
        return str(self.cfg_str("data_bot_id", "") or self.bot_name or "default")

    async def _data_call(self, name, *args, **kwargs):
        mem = self._data_mem()
        func = getattr(mem, name, None) if mem is not None else None
        if not callable(func):
            # 旧版/半装的数据插件可能只暴露 store 门面（mem 上没有同名方法）。
            # 以前这里直接 return None，聊天记录会一句都不进终端，表现就是「她失忆」。
            store = self._data_store()
            func = getattr(store, name, None) if store is not None else None
            if not callable(func):
                return None
        try:
            return await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=max(1.0, self.cfg_float("data_call_timeout_seconds", 15.0)),
            )
        except asyncio.TimeoutError:
            logger.warning("[amo] 数据插件 %s 调用超时，先跳过（不影响这轮回复）" % name)
            return None
        except TypeError:
            # 数据插件是旧版（还没有 platform / message_id 参数）时退一步，别把聊天记录整个丢掉
            trimmed = {k: v for k, v in kwargs.items() if k not in ("platform", "message_id")}
            if trimmed != kwargs:
                try:
                    return await func(*args, **trimmed)
                except Exception as exc:
                    logger.debug("[amo] 数据插件 %s 调用失败: %s" % (name, exc))
                    return None
            logger.debug("[amo] 数据插件 %s 参数不匹配" % name)
            return None
        except Exception as exc:
            logger.debug("[amo] 数据插件 %s 调用失败: %s" % (name, exc))
            return None

    async def _push_profile_to_data(self, uid, profile=None, platform=""):
        """把本地画像推给数据插件（名字/称呼/关系/备注），顺带记下平台身份。

        返回“是否真的写进去了”：数据插件没装、旧版没有 platform 参数、或者内部报错，
        都会返回 False，调用方好统计失败条数，不再假装成功。
        """
        if not uid:
            return False
        profile = profile or self.db.get_profile(uid) or {}
        name = str(profile.get("name") or "")
        # 本地画像自己记着这个人是哪个平台的，补推时别把飞书用户错标成 QQ
        platform = str(platform or profile.get("platform") or "").strip().lower()
        fields = {
            "name": name,
            "alias": str(profile.get("alias") or ""),
            "relation": str(profile.get("relation") or ""),
            "remark": str(profile.get("notes") or ""),
        }
        mem = self._data_mem()
        save = getattr(mem, "save_profile", None) if mem is not None else None
        result = None
        if callable(save):
            # 直接调一次，异常不再被 _data_call 吞掉，好定位到底哪一步失败
            try:
                result = await save(self._data_bot_id(), str(uid), platform=platform, **fields)
            except TypeError:
                # 旧版数据插件没有 platform 参数
                try:
                    result = await save(self._data_bot_id(), str(uid), **fields)
                except Exception as exc:
                    _note_swallowed("amo_memory.HumanCorePlugin._push_profile_to_data", exc)
                    self._log_push_failure(uid, exc)
                    result = None
            except Exception as exc:
                _note_swallowed("amo_memory.HumanCorePlugin._push_profile_to_data", exc)
                self._log_push_failure(uid, exc)
                result = None
        if isinstance(result, dict) and result.get("uid"):
            return True
        if result:
            return True
        # 兜底：mem 门面不可用时，直接写数据插件的 DataStore（老版本只有 store）
        store = self._data_store()
        saver = getattr(store, "save_profile", None)
        if not callable(saver):
            return False
        try:
            raw = await asyncio.to_thread(
                lambda: saver(self._data_bot_id(), str(uid), **fields)
            )
        except Exception as exc:
            _note_swallowed("amo_memory.HumanCorePlugin._push_profile_to_data", exc)
            self._log_push_failure(uid, exc)
            return False
        return bool(raw and (not isinstance(raw, dict) or raw.get("uid")))

    def _log_push_failure(self, uid, exc):
        """同一次同步里最多打 3 条 warning，避免刷屏。"""
        count = to_int(getattr(self, "_push_fail_count", 0))
        self._push_fail_count = count + 1
        if count < 3:
            logger.warning(
                "[amo] 推送画像 %s 失败: %s: %s" % (uid, type(exc).__name__, exc)
            )

    async def _sync_relations_from_data(self):
        """把记忆终端里的关系网拉回本地（面板改过的也能生效，不用重启）。"""
        try:
            rows = await self._data_call("list_relations", self._data_bot_id())
        except Exception as _amo_exc:
            _note_swallowed("amo_memory.HumanCorePlugin._sync_relations_from_data", _amo_exc)
            return 0
        if rows is None:
            # 终端不可用时不要动本地，避免把关系网清空
            return 0
        remote = set()
        count = 0
        for edge in rows:
            a_uid = str(edge.get("a_uid") or "")
            b_uid = str(edge.get("b_uid") or "")
            if not a_uid or not b_uid:
                continue
            if a_uid in INTERNAL_RELATION_NODES or b_uid in INTERNAL_RELATION_NODES:
                # 老版本可能推过 bot 边：不参与比较，也不动本地
                continue
            remote.add(tuple(sorted([a_uid, b_uid])))
            try:
                self.db.upsert_relation(a_uid, b_uid, edge.get("relation") or "朋友", edge.get("note") or "")
                count += 1
            except Exception as _amo_exc:
                _note_swallowed("amo_memory.HumanCorePlugin._sync_relations_from_data", _amo_exc)
                continue
        # 面板上删掉的关系，本地也同步删掉（终端为准）；
        # 终端返回空、或远端的边比本地还少时都不删——那多半是换库/重装/恢复残缺备份，
        # 照删一次就能把本地关系网清空（之后还得靠聊天慢慢沉淀）。
        try:
            local_rows = self.db.list_relations()
        except Exception as _amo_exc:
            _note_swallowed("amo_memory.HumanCorePlugin._sync_relations_from_data", _amo_exc)
            local_rows = []
        # bot/self 边推不到远端，比较前先排掉：不然远端永远"比本地少"，
        # 这条 warning 会每轮都响，而且下面"终端删了本地也删"永远不会执行。
        local_rows = [
            item for item in local_rows
            if str(item.get("a_uid") or "") not in INTERNAL_RELATION_NODES
            and str(item.get("b_uid") or "") not in INTERNAL_RELATION_NODES
        ]
        if not remote or len(remote) < len(local_rows):
            if remote:
                logger.warning(
                    "[amo] 关系网不同步：远端 %d 条 < 本地 %d 条，先不删本地"
                    % (len(remote), len(local_rows))
                )
            return count
        try:
            for item in local_rows:
                pair = tuple(sorted([str(item.get("a_uid") or ""), str(item.get("b_uid") or "")]))
                if pair not in remote:
                    self.db.delete_relation(pair[0], pair[1])
        except Exception as _amo_exc:
            _note_swallowed("amo_memory.HumanCorePlugin._sync_relations_from_data", _amo_exc)
        return count

    async def _sync_profiles_to_data(self):
        """把本地画像补齐到数据插件：缺的补、改过的重推。不依赖一次性迁移标记。

        之前迁移是一次性的，标记写早了就永远是 0；这里改成每次都对一遍，
        而且推完再查一次条数，日志里能直接看到到底写进去没有。
        """
        mem = self._data_mem()
        store = self._data_store()
        if mem is None and store is None:
            return 0
        bot_id = self._data_bot_id()
        try:
            local = self.db.list_profiles(limit=500) or []
        except Exception as exc:
            logger.warning("[amo] 读本地画像失败: %s" % exc)
            return 0
        try:
            remote_rows = await self._data_call("list_profiles", bot_id, "", 500) or []
        except Exception as _amo_exc:
            _note_swallowed("amo_memory.HumanCorePlugin._sync_profiles_to_data", _amo_exc)
            remote_rows = []
        if not remote_rows:
            # mem 门面不可用的旧版：直接读 DataStore
            lister = getattr(self._data_store(), "list_profiles", None)
            if callable(lister):
                try:
                    remote_rows = await asyncio.to_thread(lambda: lister(bot_id, "", 500)) or []
                except Exception as _amo_exc:
                    _note_swallowed("amo_memory.HumanCorePlugin._sync_profiles_to_data", _amo_exc)
                    remote_rows = []
        self._push_fail_count = 0
        remote = {}
        for row in remote_rows:
            if not isinstance(row, dict):
                continue
            uid = str(row.get("uid") or "")
            if uid:
                remote[uid] = row
        pushed = 0
        failed = 0
        pulled = 0
        for profile in local:
            if not isinstance(profile, dict):
                continue
            uid = str(profile.get("uid") or "")
            if not uid:
                continue
            name = str(profile.get("name") or "")
            alias = str(profile.get("alias") or "")
            relation = str(profile.get("relation") or "")
            remark = str(profile.get("notes") or "")
            old = remote.get(uid)
            if old is not None:
                if (
                    str(old.get("name") or "") == name
                    and str(old.get("alias") or "") == alias
                    and str(old.get("relation") or "") == relation
                    and str(old.get("remark") or "") == remark
                ):
                    continue
                # 数据插件里更新过（面板手动改了名字/关系）就以远端为准，拉回本地。
                # 比较基准是 profile_updated_at（本地手动改画像的时间），不是 last_seen：
                # last_seen 每收一条消息都会刷新，拿它比会把面板改动永远判成「更旧」。
                remote_at = to_float(old.get("updated_at"), 0)
                local_at = to_float(profile.get("profile_updated_at"), 0)
                if remote_at and remote_at > local_at:
                    if self._apply_remote_profile(uid, old, profile):
                        pulled += 1
                    continue
            try:
                ok = await self._push_profile_to_data(uid, profile)
            except Exception as exc:
                logger.warning("[amo] 推送画像 %s 异常: %s: %s" % (uid, type(exc).__name__, exc))
                ok = False
            if ok:
                pushed += 1
            else:
                failed += 1
        # 推完再查一次，拿到“真的写进去了多少条”
        after = []
        try:
            after = await self._data_call("list_profiles", bot_id, "", 500) or []
        except Exception as _amo_exc:
            _note_swallowed("amo_memory.HumanCorePlugin._sync_profiles_to_data", _amo_exc)
            after = []
        if not after:
            lister = getattr(self._data_store(), "list_profiles", None)
            if callable(lister):
                try:
                    after = await asyncio.to_thread(lambda: lister(bot_id, "", 500)) or []
                except Exception as _amo_exc:
                    _note_swallowed("amo_memory.HumanCorePlugin._sync_profiles_to_data", _amo_exc)
                    after = []
        total = max(len(after), len(remote))
        message = (
            "[amo] 画像同步：本地 %d 条 / 数据插件 %d 条，本次补推 %d 条，拉回 %d 条，失败 %d 条"
            % (len(local), total, pushed, pulled, failed)
        )
        if failed:
            logger.warning(message)
            if failed >= len(local) and local:
                logger.warning(
                    "[amo] 画像一条都没写进去：先确认 Astr_Amo_data 已启用且版本 >= 2.0.4"
                )
        elif pushed or not getattr(self, "_profile_sync_logged", False):
            self._profile_sync_logged = True
            logger.info(message)
        else:
            logger.debug(message)
        return pushed

    def _apply_remote_profile(self, uid, remote_row, local_profile):
        """把数据插件面板改过的画像字段拉回本地（不标记成本地手动修改）。"""
        fields = {}
        for src, dst in (("name", "name"), ("alias", "alias"), ("relation", "relation"), ("remark", "notes")):
            value = str(remote_row.get(src) or "").strip()
            if value and value != str(local_profile.get(dst) or "").strip():
                fields[dst] = value
        if not fields:
            return False
        try:
            self.db.update_profile(uid, mark_local=False, **fields)
        except Exception as exc:
            logger.warning("[amo] 拉回画像 %s 失败: %s" % (uid, exc))
            return False
        logger.info("[amo] 画像从数据插件拉回：%s %s" % (uid, ",".join(fields.keys())))
        return True

    async def _time_recall_context(self, event, uid):
        """按时间回看：他问"昨天下午/前天/上周三"时，去记忆终端取那段时间的聊天。"""
        if not self.cfg_bool("time_recall_enabled", True):
            return ""
        text = str(getattr(event, "message_str", "") or "")
        if not _looks_like_time_query(text):
            return ""
        mem = self._data_mem()
        if mem is None or not callable(getattr(mem, "recall_messages", None)):
            return ""
        try:
            umo = str(getattr(event, "unified_msg_origin", "") or "")
            # 配 0 / 负数时以前会「请求 4 条、只渲染 1 条」，两边都按同一档位收敛
            limit = max(1, min(40, self.cfg_int("time_recall_limit", 6)))
            # 私聊：不传 uid。recall_messages 按 uid 过滤后只剩「他」说的话，她的回复全被滤掉，
            # 块里就成了「他：是啊 / 自己煮的 / 厉害吧」这种碎片；umo 已经把范围限在这一个
            # 1:1 会话，双方的话都要，不会串到别人。
            # 群聊：**仍然要按 uid**，否则会把群里其他人的话也拉进【按时间回看】。
            try:
                private = bool(event.is_private_chat())
            except Exception as _amo_exc:
                _note_swallowed("amo_memory.HumanCorePlugin._time_recall_context", _amo_exc)
                private = True
            if private:
                # 跨平台：同一个人在 QQ / 飞书两边说过的话都要算进「昨天聊了什么」，
                # 否则飞书说的「今天吃面」在 QQ 上问就等于没说过。
                profile = self.db.get_profile(uid) or {}
                umos = self._ritual_umos(profile)[:3] or [umo]
                gathered = []
                label = ""
                for one_umo in umos:
                    result = await self._data_call(
                        "recall_messages", self._data_bot_id(), query=text,
                        umo=one_umo, limit=min(limit * 2, 40),
                    )
                    if not isinstance(result, dict):
                        continue
                    label = label or str(result.get("label") or "")
                    gathered.extend(result.get("messages") or [])
                seen = set()
                merged = []
                for row in sorted(gathered, key=lambda r: to_int(r.get("created_at"), 0)):
                    key = (to_int(row.get("created_at"), 0), str(row.get("content") or "")[:80])
                    if key in seen:
                        continue
                    seen.add(key)
                    merged.append(row)
                result = {"label": label, "messages": merged} if merged else {}
            else:
                result = await self._data_call(
                    "recall_messages", self._data_bot_id(), query=text, umo=umo,
                    uid=str(uid), limit=min(limit * 2, 40),
                )
        except Exception as exc:
            logger.debug("[amo] 时间回看失败: %s" % exc)
            return ""
        if not isinstance(result, dict):
            return ""
        messages = result.get("messages") or []
        label = str(result.get("label") or "")
        if not label:
            return ""
        return _render_time_block(label, messages, max_lines=max(1, int(limit)))

    async def _cross_platform_context(self, event, uid):
        """同一个人的其他平台（QQ / 飞书）说过什么，拼成一段给提示词用。"""
        mem = self._data_mem()
        if mem is None or not uid:
            return ""
        platform = self._platform_of(event)
        try:
            # 两个平台共用一个近聊池：只要 6 条的话，他在这头连聊几句就把另一头挤没了。
            detail = await self._data_call("person_context", self._data_bot_id(), platform, str(uid), 24)
        except Exception as _amo_exc:
            _note_swallowed("amo_memory.HumanCorePlugin._cross_platform_context", _amo_exc)
            return ""
        if not detail:
            return ""
        others = [
            item for item in (detail.get("others") or [])
            if str(item.get("uid") or "") and str(item.get("uid")) != str(uid)
        ]
        recent = detail.get("recent") or []
        lines = []
        if others:
            labels = []
            for item in others:
                labels.append("%s（%s）" % (item.get("label") or item.get("platform"), item.get("uid")))
            lines.append(
                "【跨平台】这个人在 " + "、".join(labels) + " 也是同一个人；"
                "不管他在哪个平台说话，都是同一个人在跟你聊。"
            )
        other_lines = []
        my_lines = []
        for item in recent:
            item_platform = str(item.get("platform") or "")
            if item_platform and item_platform == str(platform):
                # 本平台的近聊已经在 _recent() 里，不重复
                continue
            if not item_platform and str(item.get("uid") or "") == str(uid):
                continue
            text = str(item.get("content") or "").strip().replace("\n", " ")
            if not text:
                continue
            label = item.get("label") or item.get("platform") or "别的平台"
            line = "· [%s] %s" % (label, text[:120])
            if str(item.get("role") or "") == "bot":
                # 她自己说的：只留最近两句，够判断「另一边已经改口了」
                my_lines.append(line)
                continue
            other_lines.append(line)
        if other_lines:
            # 约定最新在尾部，取尾部而不是开头，免得喂最旧的几句
            lines.append("他在别的平台最近说过：\n" + "\n".join(other_lines[-6:]))
            lines.append(
                "这些事他已经在别的平台说过了，不要当成没说过、也不要再问一遍；"
                "不要把平台名、编号念出来。"
            )
        if my_lines:
            lines.append("你自己在别的平台最近说过：\n" + "\n".join(my_lines[-2:]))
            lines.append(
                "这些是你自己说的，不是他说的；别复述、别重复，"
                "和现在对不上就以【正在】为准，自然改口。"
            )
        return "\n".join(lines)

    async def _push_relation_to_data(self, a_uid, b_uid, relation, note=""):
        # "bot"/"self" 是插件内部标识，不是真实人物：写进记忆终端会让关系图多出一个
        # 叫 bot 的节点，所以只推真实的人与人之间的关系。
        if str(a_uid) in INTERNAL_RELATION_NODES or str(b_uid) in INTERNAL_RELATION_NODES:
            return
        await self._data_call(
            "save_relation", self._data_bot_id(), str(a_uid), str(b_uid),
            str(relation or "朋友"), str(note or ""),
        )

    async def _data_mem_list(self, uid, keyword="", limit=50):
        """面板记忆页：直接列出记忆终端里的条目。"""
        mem = self._data_mem()
        if mem is None or not uid:
            return []
        size = max(1, min(200, to_int(limit, 50)))
        try:
            if keyword:
                recall = getattr(mem, "recall", None)
                rows = await recall(self._data_bot_id(), str(uid), str(keyword), size, "", "") if callable(recall) else []
            else:
                lister = getattr(mem, "list_memories", None)
                rows = await lister(self._data_bot_id(), str(uid), size) if callable(lister) else []
        except Exception as exc:
            logger.debug("[amo] 读取记忆终端失败: %s" % exc)
            return []
        return [dict(row) for row in (rows or []) if isinstance(row, dict)]

    async def _push_cache_to_data(self, key, value):
        await self._data_call("cache_set", self._data_bot_id(), str(key), value)

    async def _sync_with_data_plugin(self):
        """启动时双向同步：首次把本地画像/关系/日程缓存推过去，之后以插件为准补齐本地。

        数据插件（Astr_Amo_data）可能比 amo 后加载，所以允许重试：
        - 本实例只成功同步一次（_data_synced），之后所有调用直接返回，不重复推送；
        - 启动、on_astrbot_loaded、后台 tick 三处可能同时来，用锁串行，避免重复迁移。
        """
        if self._data_synced:
            return
        async with self._data_sync_lock:
            if self._data_synced:
                return
            await self._sync_with_data_plugin_once()

    async def _sync_with_data_plugin_once(self):
        """真正干活的同步；没找到数据插件就只记一笔、安排 60 秒后的一次提醒。"""
        mem = self._data_mem()
        if mem is None and self._data_store() is None:
            self._note_data_missing()
            return
        if not self._data_found_logged:
            self._data_found_logged = True
            logger.info("[amo] 已连接数据插件 Astr_Amo_data，开始同步")
        bot_id = self._data_bot_id()
        marker = "data_plugin_migrated_" + bot_id
        migrated = bool(self.db.kv_get(marker, False))
        if not migrated:
            pushed = {"relations": 0, "cache": 0}
            try:
                for edge in self.db.list_relations():
                    await self._push_relation_to_data(
                        edge.get("a_uid"), edge.get("b_uid"),
                        edge.get("relation"), edge.get("note"),
                    )
                    pushed["relations"] += 1
            except Exception as exc:
                logger.debug("[amo] 关系网迁移失败: %s" % exc)
            for key in ("schedule", "schedule_ctx", "schedule_profile", "worldview"):
                try:
                    value = self.db.kv_get(key, None)
                    if value:
                        await self._push_cache_to_data(key, value)
                        pushed["cache"] += 1
                except Exception as _amo_exc:
                    _note_swallowed("amo_memory.HumanCorePlugin._sync_with_data_plugin_once", _amo_exc)
            self.db.kv_set(marker, True)
            logger.info("[amo] 已把关系网/日程缓存迁移到「我想永远记住你」：%s" % pushed)
        # 画像每次都对齐（不看一次性标记）：缺的补、改过的重推
        try:
            await self._sync_profiles_to_data()
        except Exception as exc:
            logger.warning("[amo] 画像同步失败: %s" % exc)
        # 插件里有、本地没有的，补回本地
        try:
            rows = await self._data_call("list_relations", bot_id) or []
            for edge in rows:
                try:
                    self.db.upsert_relation(
                        edge.get("a_uid"), edge.get("b_uid"),
                        edge.get("relation") or "朋友", edge.get("note") or "",
                    )
                except Exception as _amo_exc:
                    _note_swallowed("amo_memory.HumanCorePlugin._sync_with_data_plugin_once", _amo_exc)
                    continue
        except Exception as exc:
            logger.debug("[amo] 拉取关系网失败: %s" % exc)
        try:
            rows = await self._data_call("list_profiles", bot_id, "", 500) or []
            for row in rows:
                uid = str(row.get("uid") or "")
                if not uid:
                    continue
                local = self.db.get_profile(uid) or {}
                if not local:
                    self.db.touch_profile(uid, str(row.get("name") or ""), "", "", "", True)
                    local = self.db.get_profile(uid) or {}
                # 只有数据插件里的这条更新（面板改过）才覆盖本地，否则以本地为准，
                # 免得上一条自动改名被旧值顶回去、来回打架。
                try:
                    remote_at = to_float(row.get("updated_at"), 0)
                    local_at = to_float(local.get("profile_updated_at"), 0)
                except Exception as _amo_exc:
                    _note_swallowed("amo_memory.HumanCorePlugin._sync_with_data_plugin_once", _amo_exc)
                    remote_at = local_at = 0
                if remote_at and remote_at <= local_at:
                    continue
                self._apply_remote_profile(uid, row, local)
        except Exception as exc:
            logger.debug("[amo] 拉取画像失败: %s" % exc)
        # 日程/世界观缓存：本地空的才用插件的
        for key, attr in (("schedule", "schedule"), ("schedule_ctx", "schedule_ctx"),
                          ("schedule_profile", "schedule_profile"), ("worldview", "worldview")):
            try:
                local = self.db.kv_get(key, None)
                if local:
                    continue
                value = await self._data_call("cache_get", bot_id, key)
                if value:
                    self.db.kv_set(key, value)
                    if self.state is not None:
                        setattr(self.state, attr, value)
            except Exception as _amo_exc:
                _note_swallowed("amo_memory.HumanCorePlugin._sync_with_data_plugin_once", _amo_exc)
                continue
        # 到这里才算这次启动真的同步完了：以后不再探测、不再重复推
        self._data_synced = True
        self._data_missing_logged = False

    def _memcomp_all_memories(self, uid, keyword="", limit=50):
        """完整记忆：不限制 memory_type，用于“查看记忆”和召回。"""
        plugin = self._companion_plugin()
        if not self._is_memory_companion(plugin):
            return []
        sql = (
            "SELECT content, importance, memory_type, created_at, updated_at "
            "FROM memories WHERE (subject_id=? OR object_id=?) AND content!='' "
            "AND lifecycle NOT IN ('deleted','archived','quarantined') "
        )
        params = [str(uid), str(uid)]
        if keyword:
            sql += "AND content LIKE ? "
            params.append("%" + str(keyword) + "%")
        sql += "ORDER BY importance DESC, updated_at DESC LIMIT ?"
        params.append(max(1, min(100, to_int(limit, 50))))
        items = []
        for row in self._memcomp_rows(sql, tuple(params)):
            content = re.sub(r"\s+", " ", str(row.get("content") or "")).strip()
            if len(content) < 2:
                continue
            importance = to_float(row.get("importance"), 0.3)
            items.append({
                "content": content[:500],
                "tier": 2 if importance >= 0.72 else (1 if importance >= 0.42 else 0),
                "kind": "memory_companion",
                "source": "memory_companion",
                "memory_type": row.get("memory_type", ""),
                "created_at": row.get("created_at", ""),
                "hits": 0,
                "expires_at": None,
            })
        return items

    @staticmethod
    def _angel_component(plugin, name):
        ctx = getattr(plugin, "plugin_context", None)
        if ctx is not None and hasattr(ctx, "get_component"):
            try:
                value = ctx.get_component(name)
                if value is not None:
                    return value
            except Exception as _amo_exc:
                _note_swallowed("amo_memory.HumanCorePlugin._angel_component", _amo_exc)
        if name == "memory_store":
            return getattr(plugin, "memory_store", None)
        if name == "memory_sql_manager":
            return getattr(plugin, "memory_sql_manager", None)
        return None

    def _angel_records(self, plugin=None):
        plugin = plugin or self._companion_plugin()
        if not self._is_angel_memory(plugin):
            return []
        store = self._angel_component(plugin, "memory_store")
        method = getattr(store, "list_records", None)
        if not callable(method):
            return []
        try:
            return list(method(None, all_scopes=True) or [])
        except Exception as exc:
            logger.debug("[amo] 读取 Angel Memory 记录失败: %s" % exc)
            return []

    def _angel_ledger_users(self, plugin=None):
        plugin = plugin or self._companion_plugin()
        if not self._is_angel_memory(plugin):
            return []
        ledger = self._angel_component(plugin, "memory_sql_manager")
        method = getattr(ledger, "list_ledger_users", None)
        if not callable(method):
            return []
        try:
            return list(method() or [])
        except Exception as exc:
            logger.debug("[amo] 读取 Angel Memory 用户账本失败: %s" % exc)
            return []

    @staticmethod
    def _angel_tags(record):
        tags = (record or {}).get("tags") or []
        if isinstance(tags, str):
            tags = [item.strip() for item in tags.split(",")]
        return [str(item).strip() for item in tags if str(item).strip()]

    def _angel_known_ids(self, plugin=None):
        return {
            str(item.get("user_id") or "").strip()
            for item in self._angel_ledger_users(plugin)
            if isinstance(item, dict) and str(item.get("user_id") or "").strip()
        }

    @staticmethod
    def _angel_is_id(tag, known_ids=None):
        text = str(tag or "").strip()
        if not text:
            return False
        if known_ids and text in known_ids:
            return True
        if len(text) <= 5 or any("\u4e00" <= char <= "\u9fff" for char in text):
            return False
        if any(char.isspace() for char in text):
            return False
        return not text.replace("-", "").replace("_", "").isalpha()

    def _angel_uid_tags(self, tags, known_ids=None):
        normalized = [str(item).strip() for item in (tags or []) if str(item).strip()]
        if known_ids:
            hits = [item for item in normalized if item in known_ids]
            if hits:
                return hits
        return [item for item in normalized if self._angel_is_id(item, known_ids)]

    def _angel_profile_records(self, plugin=None):
        """Angel 的用户画像只取带画像属性标签的记录，不把普通记忆里的群/机器人 ID 当用户。"""
        plugin = plugin or self._companion_plugin()
        if not self._is_angel_memory(plugin):
            return []
        result = []
        for record in self._angel_records(plugin):
            tags = self._angel_tags(record)
            if any(tag in self.ANGEL_ATTRIBUTE_TAGS for tag in tags):
                result.append(record)
        return result

    def _angel_user_count(self, plugin=None):
        plugin = plugin or self._companion_plugin()
        if not self._is_angel_memory(plugin):
            return 0
        known = self._angel_known_ids(plugin)
        users = set()
        for record in self._angel_profile_records(plugin):
            users.update(self._angel_uid_tags(self._angel_tags(record), known))
        return len(users)

    def _sync_angel_profiles(self, only_uid=""):
        plugin = self._companion_plugin()
        if not self._is_angel_memory(plugin):
            return 0
        known = self._angel_known_ids(plugin)
        buckets = {}
        for record in self._angel_profile_records(plugin):
            tags = self._angel_tags(record)
            uids = self._angel_uid_tags(tags, known)
            if not uids:
                continue
            nickname = ""
            for tag in tags:
                if tag in known or self._angel_is_id(tag, known):
                    continue
                if tag in self.ANGEL_ATTRIBUTE_TAGS:
                    continue
                nickname = tag
                break
            for uid in uids:
                bucket = buckets.setdefault(uid, {"name": "", "count": 0})
                bucket["count"] += 1
                if nickname and not bucket["name"]:
                    bucket["name"] = nickname
        # 账本只用来补昵称，不单独创建画像；Angel 自己也是按画像记录展示用户。
        ledger_names = {}
        for row in self._angel_ledger_users(plugin):
            if isinstance(row, dict) and str(row.get("user_id") or "").strip():
                ledger_names[str(row["user_id"])] = str(row.get("nickname") or "")
        for uid, bucket in buckets.items():
            if not bucket.get("name") and ledger_names.get(uid):
                bucket["name"] = ledger_names[uid]
        if not only_uid:
            self._cleanup_auto_profiles("angel_memory", buckets.keys())
        synced = 0
        for uid, bucket in buckets.items():
            if only_uid and uid != str(only_uid):
                continue
            profile = self.db.get_profile(uid) or {}
            if not profile:
                self.db.touch_profile(uid, bucket.get("name") or uid, "angel_memory", "", "", False)
                profile = self.db.get_profile(uid) or {}
            fields = {}
            name = str(bucket.get("name") or "").strip()
            if name and (not profile.get("name") or str(profile.get("name")) == uid):
                fields["name"] = name[:60]
            if not profile.get("notes") and bucket.get("count"):
                fields["notes"] = ("Angel Memory：%d 条记忆" % bucket["count"])[:100]
            if fields:
                self.db.update_profile(uid, **fields)
            synced += 1
        return synced

    def _sync_angel_profile(self, uid, force=False):
        plugin = self._companion_plugin()
        if not self._is_angel_memory(plugin):
            return
        uid = str(uid)
        if not force:
            key = "angel_profile_sync_" + uid
            if now_ts() - to_float(self.db.kv_get(key, 0)) < 600:
                return
            self.db.kv_set(key, now_ts())
        self._sync_angel_profiles(only_uid=uid)

    def _angel_memories(self, uid, keyword="", limit=50):
        plugin = self._companion_plugin()
        if not self._is_angel_memory(plugin):
            return []
        known = self._angel_known_ids(plugin)
        items = []
        for record in self._angel_profile_records(plugin):
            tags = self._angel_tags(record)
            if str(uid) not in self._angel_uid_tags(tags, known):
                continue
            content = str(record.get("judgment") or record.get("reasoning") or "").strip()
            content = re.sub(r"\s+", " ", content)
            if len(content) < 2:
                continue
            if keyword and str(keyword).lower() not in content.lower():
                continue
            state = record.get("state") if isinstance(record.get("state"), dict) else {}
            strength = to_int(state.get("strength"), 1)
            pinned = bool(state.get("pinned", False))
            items.append({
                "content": content[:500],
                "tier": 2 if pinned or strength >= 3 else (1 if strength >= 2 else 0),
                "kind": "angel_memory",
                "source": "angel_memory",
                "memory_type": "angel",
                "created_at": record.get("created_at_us") or record.get("created_at") or "",
                "hits": 0,
                "expires_at": None,
            })
            if len(items) >= max(1, min(100, to_int(limit, 50))):
                break
        return items

    def _angel_all_memories(self, uid, keyword="", limit=50):
        """天使之魂完整记忆，不限制画像标签。"""
        plugin = self._companion_plugin()
        if not self._is_angel_memory(plugin):
            return []
        known = self._angel_known_ids(plugin)
        items = []
        for record in self._angel_records(plugin):
            tags = self._angel_tags(record)
            if str(uid) not in self._angel_uid_tags(tags, known):
                continue
            content = str(record.get("judgment") or record.get("reasoning") or "").strip()
            content = re.sub(r"\s+", " ", content)
            if len(content) < 2:
                continue
            if keyword and str(keyword).lower() not in content.lower():
                continue
            state = record.get("state") if isinstance(record.get("state"), dict) else {}
            strength = to_int(state.get("strength"), 1)
            pinned = bool(state.get("pinned", False))
            items.append({
                "content": content[:500],
                "tier": 2 if pinned or strength >= 3 else (1 if strength >= 2 else 0),
                "kind": "angel_memory",
                "source": "angel_memory",
                "memory_type": "angel",
                "created_at": record.get("created_at_us") or record.get("created_at") or "",
                "hits": 0,
                "expires_at": None,
            })
            if len(items) >= max(1, min(100, to_int(limit, 50))):
                break
        return items

    def _livingmem_db_path(self):
        """找 livingmemory 的库；路径不写死，跟着 AstrBot 的数据目录走。"""
        candidates = []
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path
            candidates.append(os.path.join(str(get_astrbot_data_path()), "plugin_data",
                                           "astrbot_plugin_livingmemory", "livingmemory.db"))
        except Exception as _amo_exc:
            _note_swallowed("amo_memory.HumanCorePlugin._livingmem_db_path", _amo_exc)
        own = getattr(self, "plugin_dir", "") or ""
        if own:
            candidates.append(os.path.join(os.path.dirname(os.path.dirname(own)),
                                           "astrbot_plugin_livingmemory", "livingmemory.db"))
        for path in candidates:
            if path and os.path.isfile(str(path)):
                return str(path)
        return ""

    def _livingmem_active(self):
        """livingmemory 现在算不算记忆源：启用着，或者用户明确选了它。"""
        selected = self.cfg_str("companion_memory_plugin_name", "").strip().lower()
        explicit = selected not in ("", "auto", "automatic", "自动")
        if explicit and selected != "astrbot_plugin_livingmemory":
            return False
        try:
            meta = self.context.get_registered_star("astrbot_plugin_livingmemory")
            if meta is not None and not bool(getattr(meta, "activated", True)):
                return False
        except Exception as _amo_exc:
            _note_swallowed("amo_memory.HumanCorePlugin._livingmem_active", _amo_exc)
        return bool(self._livingmem_db_path())

    def _livingmem_stats(self):
        """livingmemory 有没有数据、大概几个人（面板候选用）。"""
        if not self._livingmem_db_path():
            return False, 0
        rows = self._livingmem_rows("SELECT COUNT(*) AS n FROM documents")
        total = int(rows[0]["n"]) if rows else 0
        if not total:
            return False, 0
        owners = set()
        try:
            for row in self._livingmem_rows("SELECT metadata FROM documents LIMIT 500"):
                meta = json.loads(row.get("metadata") or "{}")
                for item in meta.get("participant_uids") or []:
                    owners.add(str(item))
        except Exception as _amo_exc:
            _note_swallowed("amo_memory.HumanCorePlugin._livingmem_stats", _amo_exc)
            owners = set()
        return True, max(len(owners), 1)

    def _livingmem_rows(self, sql, params=()):
        path = self._livingmem_db_path()
        if not path:
            return []
        conn = None
        try:
            from urllib.parse import quote
            conn = sqlite3.connect("file:" + quote(path) + "?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(sql, params).fetchall()]
        except Exception as exc:
            logger.debug("[amo] 读取 livingmemory 失败: %s" % exc)
            return []
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception as _amo_exc:
                _note_swallowed("amo_memory.HumanCorePlugin._livingmem_rows", _amo_exc)

    def _livingmem_owner_ids(self, uid=""):
        """认哪些 ID 算同一个人：当前 uid + 配置里的别名（跨平台用）。"""
        ids = {str(uid or "").strip()}
        raw = str(self.cfg_str("livingmemory_owner_ids", "") or "").replace("，", ",")
        for item in raw.split(","):
            item = item.strip()
            if item:
                ids.add(item)
        ids.discard("")
        return ids

    def _livingmem_owned(self, metadata, uid):
        """这段记忆是不是这个人这边的。

        livingmemory 写进 documents 的归属可能是任何一种平台 ID（如飞书 openid），
        不一定是 amo 里的 canonical uid；所以按“uid + 配置别名”的交集判断。
        没有归属信息时按“自己的”处理（单用户部署最常见）。
        """
        ids = self._livingmem_owner_ids(uid)
        try:
            meta = json.loads(metadata or "{}")
        except Exception as _amo_exc:
            _note_swallowed("amo_memory.HumanCorePlugin._livingmem_owned", _amo_exc)
            meta = {}
        owners = {str(x) for x in (meta.get("participant_uids") or [])}
        for item in meta.get("participant_identities") or []:
            if isinstance(item, dict) and item.get("sender_id"):
                owners.add(str(item["sender_id"]))
        if not owners:
            return True
        return bool(ids & owners)

    @staticmethod
    def _livingmem_like_escape(text):
        """LIKE 里的 % 和 _ 要转义，否则用户搜个下划线就变成通配符。"""
        return str(text or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def _livingmem_all_memories(self, uid, keyword="", limit=50):
        """livingmemory 的 documents：每条是一段对话摘要。

        排序规则：
          - 有关键词：命中次数多的优先，其次重要度高、其次新；
          - 没关键词：按重要度、再按时间倒序。
        和 memory_companion 那条“importance DESC, updated_at DESC”的风格保持一致。
        """
        if not self._livingmem_db_path():
            return []
        cap = max(1, min(100, int(limit or 50)))
        keyword = str(keyword or "").strip()[:100]
        sql = (
            "SELECT text, created_at, metadata, "
            "COALESCE(json_extract(metadata, '$.importance'), 0) AS imp, id "
            "FROM documents WHERE text != ''"
        )
        params = []
        if keyword:
            sql += " AND text LIKE ? ESCAPE '\\'"
            params.append("%" + self._livingmem_like_escape(keyword) + "%")
        sql += " ORDER BY imp DESC, id DESC LIMIT ?"
        params.append(max(cap * 5, 50) if keyword else cap)
        rows = self._livingmem_rows(sql, tuple(params))

        uid_s = str(uid or "")
        items = []
        for row in rows:
            content = re.sub(r"\\s+", " ", str(row.get("text") or "")).strip()
            if len(content) < 2:
                continue
            if not self._livingmem_owned(row.get("metadata"), uid_s):
                continue
            hits = content.lower().count(keyword.lower()) if keyword else 0
            items.append({
                "content": content[:500],
                "tier": 1,
                "kind": "livingmemory",
                "source": "livingmemory",
                "memory_type": "episodic",
                "created_at": row.get("created_at") or "",
                "hits": hits,
                "expires_at": None,
            })

        if keyword:
            items.sort(key=lambda x: (x["hits"], x["created_at"] or ""), reverse=True)
        return items[:cap]

    def _external_all_memories_legacy(self, uid, query="", limit=50):
        """给 prompt 注入用的版本：故意不读 livingmemory。

        livingmemory 自己会把检索结果注入 prompt（BM25+向量+图），
        这里再读一遍会重复；它只负责写入和注入，amo 只负责面板展示。
        """
        items = []
        plugin = self._companion_plugin()
        if plugin is None:
            return items
        try:
            if self._is_memory_companion(plugin):
                items.extend(self._memcomp_all_memories(uid, query, limit))
            elif self._is_angel_memory(plugin):
                items.extend(self._angel_all_memories(uid, query, limit))
            else:
                items.extend(self._companion_memories(uid, query))
        except Exception as exc:
            logger.debug("[amo] 外部完整记忆读取失败(legacy): %s" % exc)
        return items

    def _external_all_memories(self, uid, query="", limit=50):
        """只读地从已安装记忆插件取完整记忆，不创建画像。"""
        items = []
        if self._livingmem_active():
            living = self._livingmem_all_memories(uid, query, limit)
            if living:
                return living
        plugin = self._companion_plugin()
        if plugin is None:
            return items
        try:
            if self._is_memory_companion(plugin):
                items.extend(self._memcomp_all_memories(uid, query, limit))
            elif self._is_angel_memory(plugin):
                items.extend(self._angel_all_memories(uid, query, limit))
            else:
                items.extend(self._companion_memories(uid, query))
        except Exception as exc:
            logger.debug("[amo] 外部完整记忆读取失败: %s" % exc)
        return items

    def _external_profile_memories(self, uid, name="", alias="", limit=200):
        """按 UID 或名字/称呼从已安装记忆插件取完整记忆；只读，不建画像。"""
        if self._livingmem_active():
            living = self._livingmem_all_memories(uid, "", limit)
            if living:
                return living
        plugin = self._companion_plugin()
        if plugin is None:
            return []
        items = []
        names = [str(name or "").strip(), str(alias or "").strip()]
        names = [item for item in names if item]
        try:
            if self._is_memory_companion(plugin):
                items.extend(self._memcomp_all_memories(uid, "", limit))
                if not items and names:
                    sql = (
                        "SELECT content, importance, memory_type, created_at, updated_at "
                        "FROM memories WHERE content!='' "
                        "AND lifecycle NOT IN ('deleted','archived','quarantined') "
                        "AND (" + " OR ".join("content LIKE ?" for _ in names) + ") "
                        "ORDER BY importance DESC, updated_at DESC LIMIT ?"
                    )
                    params = ["%" + item + "%" for item in names] + [max(1, min(100, limit))]
                    for row in self._memcomp_rows(sql, tuple(params)):
                        content = re.sub(r"\s+", " ", str(row.get("content") or "")).strip()
                        if len(content) < 2:
                            continue
                        importance = to_float(row.get("importance"), 0.3)
                        items.append({
                            "content": content[:500],
                            "tier": 2 if importance >= 0.72 else (1 if importance >= 0.42 else 0),
                            "kind": "memory_companion",
                            "source": "memory_companion",
                            "created_at": row.get("created_at", ""),
                        })
            elif self._is_angel_memory(plugin):
                items.extend(self._angel_all_memories(uid, "", limit))
                if not items and names:
                    for record in self._angel_records(plugin):
                        tags = self._angel_tags(record)
                        content = str(record.get("judgment") or record.get("reasoning") or "")
                        haystack = content + " " + " ".join(tags)
                        if not any(item in haystack for item in names):
                            continue
                        content = re.sub(r"\s+", " ", content).strip()
                        if len(content) >= 2:
                            items.append({
                                "content": content[:500],
                                "tier": 1,
                                "kind": "angel_memory",
                                "source": "angel_memory",
                                "created_at": record.get("created_at_us") or record.get("created_at") or "",
                            })
                        if len(items) >= limit:
                            break
            else:
                items.extend(self._companion_memories(uid, ""))
                if not items and names:
                    data = getattr(plugin, "data", None)
                    users = data.get("users") if isinstance(data, dict) else None
                    if isinstance(users, dict):
                        for other_uid, user in users.items():
                            if not isinstance(user, dict):
                                continue
                            values = [user.get("name"), user.get("nickname"), user.get("display_name")]
                            values += list(user.get("aliases") or []) if isinstance(user.get("aliases"), list) else []
                            if any(item and item in " ".join(str(v or "") for v in values) for item in names):
                                try:
                                    items.extend(self._companion_memories(str(other_uid), ""))
                                except Exception as _amo_exc:
                                    _note_swallowed("amo_memory.HumanCorePlugin._external_profile_memories", _amo_exc)
        except Exception as exc:
            logger.debug("[amo] 外部画像记忆读取失败: %s" % exc)
        unique = []
        seen = set()
        for item in items:
            key = re.sub(r"\s+", "", str(item.get("content") or "")).lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(item)
        return unique[:max(1, min(500, limit))]

    def _companion_plugin_meta(self):
        """优先用配置的插件名；留空或找不到时从已安装插件里自动检测。"""
        name = self.cfg_str("companion_memory_plugin_name", "").strip()
        if name and name.lower() not in ("auto", "automatic", "自动"):
            try:
                meta = self.context.get_registered_star(name)
                if meta and getattr(meta, "star_cls", None) is not None:
                    return meta
            except Exception as _amo_exc:
                _note_swallowed("amo_memory.HumanCorePlugin._companion_plugin_meta", _amo_exc)
        candidates = []
        try:
            for meta in self.context.get_all_stars():
                if getattr(meta, "name", None) == PLUGIN_NAME:
                    continue
                plugin = getattr(meta, "star_cls", None)
                if plugin is None:
                    continue
                data = getattr(plugin, "data", None)
                users = data.get("users") if isinstance(data, dict) else None
                marker = (
                    (getattr(meta, "name", "") or "") + " "
                    + (getattr(meta, "module_path", "") or "")
                ).lower()
                score = 0
                if "livingmemory" in marker:
                    # 只有真的启用着才给最高权重；停用时让位给别的已激活记忆插件
                    score += 12 if bool(getattr(meta, "activated", False)) else 3
                if bool(getattr(meta, "activated", False)):
                    score += 2
                if "private_companion" in marker:
                    score += 5
                if "memory" in marker:
                    score += 1
                if getattr(plugin, "memory_companion", None) is not None:
                    score += 6
                if self._is_angel_memory(plugin):
                    score += 7
                if isinstance(users, dict) and users:
                    sample = next((item for item in users.values() if isinstance(item, dict)), {})
                    if isinstance(sample.get("companion_memory"), dict):
                        score += 4
                    if "relationship_score" in sample:
                        score += 2
                    if isinstance(sample.get("important_memories"), list):
                        score += 1
                    score += 1
                if score:
                    candidates.append((score, meta))
        except Exception as _amo_exc:
            _note_swallowed("amo_memory.HumanCorePlugin._companion_plugin_meta", _amo_exc)
        candidates.sort(key=lambda pair: -pair[0])
        return candidates[0][1] if candidates else None

    def _companion_plugin(self):
        meta = self._companion_plugin_meta()
        return getattr(meta, "star_cls", None) if meta else None

    def _companion_candidates(self):
        items = []
        try:
            for meta in self.context.get_all_stars():
                if getattr(meta, "name", None) == PLUGIN_NAME:
                    continue
                plugin = getattr(meta, "star_cls", None)
                data = getattr(plugin, "data", None) if plugin is not None else None
                users = data.get("users") if isinstance(data, dict) else None
                count = len(users) if isinstance(users, dict) else 0
                ready = False
                marker = (
                    (getattr(meta, "name", "") or "") + " "
                    + (getattr(meta, "module_path", "") or "")
                ).lower()
                if isinstance(users, dict) and users:
                    sample = next((item for item in users.values() if isinstance(item, dict)), {})
                    ready = isinstance(sample, dict) and (
                        isinstance(sample.get("companion_memory"), dict)
                        or "relationship_score" in sample
                        or isinstance(sample.get("important_memories"), list)
                    )
                if plugin is not None and self._is_memory_companion(plugin):
                    ready = True
                    count = self._memcomp_user_count(plugin)
                if plugin is not None and self._is_angel_memory(plugin):
                    ready = True
                    count = self._angel_user_count(plugin)
                if "livingmemory" in marker:
                    lm_ready, lm_count = self._livingmem_stats()
                    if lm_ready:
                        ready = True
                        count = lm_count
                if not ready and plugin is not None:
                    # 市面上记忆类插件很多：只要有检索接口或 users 里的记忆结构，就当作可用
                    ready = self._looks_like_memory_plugin(plugin, users)
                items.append({
                    "name": str(getattr(meta, "name", "") or ""),
                    "display_name": str(getattr(meta, "display_name", "") or getattr(meta, "name", "") or ""),
                    "version": str(getattr(meta, "version", "") or ""),
                    "users": count,
                    "ready": ready,
                    "activated": bool(getattr(meta, "activated", False)),
                    "reserved": bool(getattr(meta, "reserved", False)),
                })
        except Exception as _amo_exc:
            _note_swallowed("amo_memory.HumanCorePlugin._companion_candidates", _amo_exc)
        items.sort(key=lambda item: (not item["ready"], -item["users"], item["name"]))
        return items

    @staticmethod
    def _companion_pick_profile(mapping, uid):
        if not isinstance(mapping, dict):
            return {}
        direct = mapping.get(str(uid))
        if isinstance(direct, dict):
            return direct
        for key, value in mapping.items():
            if not isinstance(value, dict):
                continue
            subject = (
                value.get("user_id") or value.get("member_id")
                or value.get("identity_subject_id") or key
            )
            if str(subject) == str(uid):
                return value
        return {}

    def _companion_memories(self, uid, query=""):
        """只读地从挂载插件的 data 中提取用户记忆。"""
        plugin = self._companion_plugin()
        if plugin is None:
            return []
        data = getattr(plugin, "data", None)
        if not isinstance(data, dict):
            return []

        user = self._companion_pick_profile(data.get("users"), uid)
        items = []
        seen = set()

        def add(content, tier=1, weight=1):
            text = re.sub(r"\s+", " ", str(content or "")).strip()
            if len(text) < 2:
                return
            key = re.sub(r"[\s，。！？!?、；;：:]+", "", text).lower()
            if not key or key in seen:
                return
            seen.add(key)
            items.append({
                "content": text[:240],
                "tier": max(0, min(2, to_int(tier, 1))),
                "kind": "companion",
                "source": "companion",
                "weight": to_int(weight, 1),
                "hits": 0,
                "expires_at": None,
            })

        memory = user.get("companion_memory") if isinstance(user, dict) else None
        if isinstance(memory, dict):
            raw_items = memory.get("items")
            if isinstance(raw_items, list):
                for raw in raw_items:
                    if not isinstance(raw, dict):
                        continue
                    weight = to_int(raw.get("weight"), 1)
                    add(
                        raw.get("text"),
                        2 if weight >= 3 else (1 if weight >= 2 else 0),
                        weight,
                    )
            if self.cfg_bool("companion_memory_include_profile", True):
                profile = memory.get("profile")
                if isinstance(profile, dict):
                    labels = (
                        ("strong_memories", "强记忆", 2),
                        ("boundaries", "边界", 2),
                        ("speaking_style", "表达习惯", 1),
                        ("weak_preferences", "偏好", 1),
                        ("interests", "兴趣", 1),
                    )
                    for key, label, tier in labels:
                        value = profile.get(key)
                        values = value if isinstance(value, list) else ([value] if value else [])
                        for entry in values[:6]:
                            if isinstance(entry, dict):
                                entry = entry.get("text") or entry.get("content") or ""
                            add(str(label) + "：" + str(entry), tier, 2 if tier >= 2 else 1)

        if self.cfg_bool("companion_memory_include_important", True):
            important = []
            if isinstance(user, dict) and isinstance(user.get("important_memories"), list):
                important.extend(user.get("important_memories") or [])
            worldbook = data.get("worldbook_member_profiles")
            wb_profile = self._companion_pick_profile(worldbook, uid)
            if isinstance(wb_profile.get("important_memories"), list):
                important.extend(wb_profile.get("important_memories") or [])
            for entry in important:
                if isinstance(entry, dict):
                    add(entry.get("content") or entry.get("text"), 2, 3)
                elif isinstance(entry, str):
                    add(entry, 2, 3)

        if not items:
            return []
        query_tokens = tokens(query)
        for item in items:
            item["_score"] = overlap(query_tokens, tokens(item["content"])) + 0.08 * to_int(item.get("weight"))
        items.sort(key=lambda item: (-item["_score"], -to_int(item.get("weight")), -len(item["content"])))
        for item in items:
            item.pop("_score", None)
        # 挂载插件的记忆不做条数限制：返回插件里有的全部，注入时再按 memory_recall_limit 截断
        return items[:500]

    def _companion_user_record(self, uid):
        plugin = self._companion_plugin()
        if plugin is None:
            return {}
        data = getattr(plugin, "data", None)
        if not isinstance(data, dict):
            return {}
        return self._companion_pick_profile(data.get("users"), uid)

    @staticmethod
    def _map_companion_relation(user):
        """把陪伴插件的关系分数/阶段映射到本插件的关系；不会自动到“相恋”。"""
        if not isinstance(user, dict):
            return "普通"
        score = to_int(user.get("relationship_score"), 0)
        stage = str(user.get("relationship_phase_key") or user.get("relationship_stage") or "").lower()
        role = str(user.get("relationship_role") or "").lower()
        if "hatred" in stage or "enemy" in role or score <= -60:
            return "仇恨"
        if "distant" in stage or "rival" in role or score < 0:
            return "抵触"
        if "close" in stage or score >= 40:
            return "熟识"
        if "familiar" in stage or score >= 15:
            return "熟识"
        return "普通"

    def _sync_companion_profile(self, uid, force=False):
        """从陪伴插件的用户数据补全本插件画像（只补空字段，不覆盖手动关系）。"""
        if not force and not self.cfg_bool("companion_profile_sync", True):
            return
        uid = str(uid)
        if not force:
            key = "companion_profile_sync_" + uid
            if now_ts() - to_float(self.db.kv_get(key, 0)) < 600:
                return
            self.db.kv_set(key, now_ts())
        user = self._companion_user_record(uid)
        if not user:
            return
        profile = self.db.get_profile(uid)
        name = str(
            user.get("name") or user.get("nickname")
            or user.get("display_name") or ""
        ).strip()
        if not profile:
            self.db.touch_profile(uid, name or uid, "companion", "", "", False)
            profile = self.db.get_profile(uid)
        if not profile:
            return
        fields = {}
        if name and (not profile.get("name") or str(profile.get("name")) == uid):
            fields["name"] = name[:60]
        birthday = str(user.get("birthday") or "").strip()
        if birthday and not profile.get("birthday"):
            fields["birthday"] = birthday[:20]
        relation = self._map_companion_relation(user)
        if relation != "普通" and profile.get("relation", "普通") == "普通":
            fields["relation"] = relation
        if fields:
            self.db.update_profile(uid, **fields)

    async def _recall(self, uid, text, event=None):
        """记忆只来自「记忆终端」（Astr_Amo_data）；没装才退回外挂记忆插件。

        陪伴自己不存记忆：读也只读记忆终端，读不到再退旧的插件库。
        """
        limit = max(1, min(50, self.cfg_int("memory_recall_limit", 6)))
        if self.cfg_str("context_style", "lean").strip().lower() == "lean" and event is not None:
            try:
                if not event.is_private_chat():
                    limit = min(limit, 4)
            except Exception as _amo_exc:
                _note_swallowed("amo_memory.HumanCorePlugin._recall", _amo_exc)
        memories = []
        hub = self._memory_hub()
        if hub is not None:
            try:
                private = True
                try:
                    private = bool(event.is_private_chat()) if event is not None else True
                except Exception as _amo_exc:
                    _note_swallowed("amo_memory.HumanCorePlugin._recall", _amo_exc)
                    private = True
                if not private and len(str(text or "").strip()) <= 3:
                    limit = min(limit, 2)   # 群聊短消息只补 2 条，避免一句“猫”塞满提示词
                if hub.should_recall(text, private):
                    scope = "private"
                    group_id = ""
                    if event is not None and not private:
                        scope = "group"
                        try:
                            group_id = str(event.get_group_id() or "")
                        except Exception as _amo_exc:
                            _note_swallowed("amo_memory.HumanCorePlugin._recall", _amo_exc)
                            group_id = ""
                    memories = await hub.recall(uid, text, limit, scope, group_id)
            except Exception as exc:
                logger.debug("[amo] 能力层召回失败: %s" % exc)
                memories = []
        if not memories:
            try:
                memories = await self._data_memory_recall(uid, text, limit, event)
            except Exception as exc:
                logger.debug("[amo] 记忆终端召回异常: %s" % exc)
        if not memories:
            memories = await self._external_memory_recall(event, text, limit)
        if not memories:
            memories = self._external_memory_fallback(uid, text, limit)

        unique = []
        seen = set()
        for item in memories:
            content = str(item.get("content", "")).strip()
            key = re.sub(r"[\s，。！？!?、；;：:]+", "", content).lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(item)
        memories = unique[:max(1, self.cfg_int("memory_recall_limit", 6))]
        if not memories:
            return [], ""
        lines = []
        for item in memories:
            source = str(item.get("source") or "")
            if source == "amo_data":
                label = "记忆"
            elif source == "companion":
                label = "陪伴记忆"
            else:
                tier = to_int(item.get("tier"))
                label = "珍贵" if tier >= 2 else ("重要" if tier == 1 else "普通")
            who = str(item.get("name") or "").strip()
            prefix = (who + "：") if (who and source in ("hub", "amo_data")) else ""
            # 老记忆里常有"今天/昨晚/刚才"这种相对说法：注入时补一个记录日期，
            # 免得她把 11-04 的事当成"昨晚"（用户反馈过一次）。
            body = str(item.get("content", ""))
            rel_words = ("今天", "今晚", "昨天", "昨晚", "刚才", "刚刚", "前天", "这会儿", "这两天")
            created = to_int(item.get("created_at"))
            if created and any(w in body for w in rel_words):
                try:
                    day = _clock_from_ts(created)
                    if day.strftime("%Y-%m-%d") != _now().strftime("%Y-%m-%d"):
                        body = "（记于 %s）%s" % (day.strftime("%m-%d"), body)
                except Exception as _amo_exc:
                    _note_swallowed("amo_memory.HumanCorePlugin._recall", _amo_exc)
            # 记忆都是“关于他”的：没名字的统一补「他：」，避免模型把「脸疼」当成自己的感受
            if not prefix and not body.startswith(("他", "她", "用户")):
                prefix = "他："
            lines.append("· " + prefix + body + "（" + label + "）")
        if lines:
            lines.append("（记忆里出现的『今天/昨晚/刚才』是当时记下的说法，不是现在；对不上就以他刚说的为准。）")
        text = "\n".join(lines)
        budget = self.cfg_int("memory_inject_max_chars", 1200)
        if budget > 0 and len(text) > budget:
            text = text[:budget]
            if "\n" in text:
                text = text.rsplit("\n", 1)[0]
        return memories, text
