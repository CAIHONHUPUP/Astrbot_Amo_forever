# -*- coding: utf-8 -*-
"""
我想永远陪着你 / 我想永远陪伴你 5.4.2
一个尽量“像人”的 AstrBot 智械人类核心：
生理期 / 九维心情 / 世界观与日程 / 天气 / 健康 / 群聊插话阈值 /
私聊判定 / 主动私聊 / 长期记忆与遗忘 / 防抖 / 分段与打字延迟 / 引用回复 / AI 润色
"""

from __future__ import annotations
try:
    from .amo_observability import note as _note_swallowed
except ImportError:  # 直接按文件加载时
    from amo_observability import note as _note_swallowed
try:
    from .amo_observability import snapshot as _swallowed_snapshot
except ImportError:  # 直接按文件加载时
    from amo_observability import snapshot as _swallowed_snapshot

import asyncio
import inspect
import json
import math
import os
import random
import re
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta

# 统一时区：容器/服务器常在 UTC 跑，直接取服务器本地时间会把北京时间 10 点算成凌晨 2 点
# （「大晚上的」就是这么来的）。clock.now() 返回目标时区下的 naive 本地时间，
# 和原来的用法完全兼容。
try:
    from .clock import (
        now as _clock_now,
        from_timestamp as _clock_from_ts,
        configure as _clock_configure,
        current_name as _clock_name,
    )
except Exception:
    try:
        from clock import (
            now as _clock_now,
            from_timestamp as _clock_from_ts,
            configure as _clock_configure,
            current_name as _clock_name,
        )
    except Exception:
        def _clock_now(*args, **kwargs):
            return datetime.now()

        def _clock_from_ts(ts, *args, **kwargs):
            return datetime.fromtimestamp(float(ts or 0))

        def _clock_configure(*args, **kwargs):
            return ""

        def _clock_name(*args, **kwargs):
            return ""


# ---- 拆分后的模块（main 只做组装）----
try:
    from .amo_shared import (
        _now,
        Comp,
        logger,
        AstrMessageEvent,
        filter,
        Context,
        Star,
        MessageChain,
        web_request,
        HeartflowEngine,
        SegmentEngine,
        parse_weather_daily,
        is_weather_query,
        GiftEngine,
        _pg_analyze_rows,
        _pg_compose_task,
        _pg_near_duplicate,
        _looks_like_time_query,
        _render_time_block,
        _DIARY_WRITTEN,
        _DIARY_SHOW,
        _diary_pick_hints,
        _ms_should_archive,
        _ms_transcript,
        _ms_build_prompt,
        _ms_build_content,
        _wander_assess,
        _wander_ask_limit,
        _wander_agree,
        _wander_question,
        _follow_invite,
        _follow_refuse,
        _wander_refuse,
        _wander_follow_agree_text,
        _follow_block,
        _wander_offer_block,
        _wander_pick,
        _wander_plan_text,
        _wander_solo_agree_text,
        _wander_solo_block,
        _wander_solo_refuse_text,
        _wander_trip_days,
        _wander_want,
        render_recent_block,
        first_person_experience,
        attribution_leak,
        leak_tokens,
        strip_brushoff,
        parse_relations,
        _CITY_DEFAULT,
        _city_detect,
        _city_block,
        _city_travel_block,
        _city_travel_events,
        _city_travel_to_events,
        _city_pick_spots,
        _rank_edges,
        plan_relation_edges,
        ScheduleEngine,
        PLUGIN_NAME,
        LEGACY_DEFAULT_ADMIN,
        RELATIONS,
        DIALECT_SAMPLES,
        dialect_for_city,
        DIALECT_FALLBACK_ROWS,
        DIALECT_REGIONS,
        SCHEDULE_VERSION,
        MOOD_KEYS,
        SICK_STATUSES,
        MOOD_BASE,
        STYLE_HINTS,
        INTERNAL_RELATION_NODES,
        now_ts,
        day_meta,
        lark_quote_kwargs,
        today_str,
        other_platform_bot_lines,
        schedule_category_mood,
        weekday_cn,
        clamp,
        to_int,
        to_float,
        truncate,
        md5_int,
        parse_hhmm,
        minutes_now,
        in_minute_range,
        quiet_now,
        looks_like_plain_command,
        has_question,
        sentiment,
        tokens,
        overlap,
        json_extract_list,
        json_extract,
        strip_chat_format,
        clean_reply,
        looks_like_ai_admission,
        looks_like_defensive_reply,
        looks_like_model_leak,
        typing_delay_ms,
        USAGE_DEFAULT_PRICES,
        fetch_provider_balance,
        fetch_deepseek_balance,
        merge_uid_alias_data,
    )
    from .amo_api import ApiMixin
    from .amo_proactive import ProactiveMixin
    from .amo_schedule import ScheduleMixin
    from .amo_llm import LlmMixin
except ImportError:  # 直接按文件加载时
    from amo_shared import (
        _now,
        Comp,
        logger,
        AstrMessageEvent,
        filter,
        Context,
        Star,
        MessageChain,
        web_request,
        HeartflowEngine,
        SegmentEngine,
        parse_weather_daily,
        is_weather_query,
        GiftEngine,
        _pg_analyze_rows,
        _pg_compose_task,
        _pg_near_duplicate,
        _looks_like_time_query,
        _render_time_block,
        _DIARY_WRITTEN,
        _DIARY_SHOW,
        _diary_pick_hints,
        _ms_should_archive,
        _ms_transcript,
        _ms_build_prompt,
        _ms_build_content,
        _wander_assess,
        _wander_ask_limit,
        _wander_agree,
        _wander_question,
        _follow_invite,
        _follow_refuse,
        _wander_refuse,
        _wander_follow_agree_text,
        _follow_block,
        _wander_offer_block,
        _wander_pick,
        _wander_plan_text,
        _wander_solo_agree_text,
        _wander_solo_block,
        _wander_solo_refuse_text,
        _wander_trip_days,
        _wander_want,
        render_recent_block,
        first_person_experience,
        attribution_leak,
        leak_tokens,
        strip_brushoff,
        parse_relations,
        _CITY_DEFAULT,
        _city_detect,
        _city_block,
        _city_travel_block,
        _city_travel_events,
        _city_travel_to_events,
        _city_pick_spots,
        _rank_edges,
        plan_relation_edges,
        ScheduleEngine,
        PLUGIN_NAME,
        LEGACY_DEFAULT_ADMIN,
        RELATIONS,
        DIALECT_SAMPLES,
        dialect_for_city,
        DIALECT_FALLBACK_ROWS,
        DIALECT_REGIONS,
        SCHEDULE_VERSION,
        MOOD_KEYS,
        SICK_STATUSES,
        MOOD_BASE,
        STYLE_HINTS,
        INTERNAL_RELATION_NODES,
        now_ts,
        day_meta,
        lark_quote_kwargs,
        today_str,
        other_platform_bot_lines,
        schedule_category_mood,
        weekday_cn,
        clamp,
        to_int,
        to_float,
        truncate,
        md5_int,
        parse_hhmm,
        minutes_now,
        in_minute_range,
        quiet_now,
        looks_like_plain_command,
        has_question,
        sentiment,
        tokens,
        overlap,
        json_extract_list,
        json_extract,
        strip_chat_format,
        clean_reply,
        looks_like_ai_admission,
        looks_like_defensive_reply,
        looks_like_model_leak,
        typing_delay_ms,
        USAGE_DEFAULT_PRICES,
        fetch_provider_balance,
        fetch_deepseek_balance,
        merge_uid_alias_data,
    )
    from amo_api import ApiMixin
    from amo_proactive import ProactiveMixin
    from amo_schedule import ScheduleMixin
    from amo_llm import LlmMixin

PLUGIN_VERSION = "6.6.8"

class AmoDB:
    def __init__(self, plugin_dir):
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path
            data_dir = os.path.join(get_astrbot_data_path(), "plugin_data", PLUGIN_NAME)
        except Exception as _amo_exc:
            _note_swallowed("main.AmoDB.__init__", _amo_exc)
            data_dir = os.path.join(plugin_dir, "data")
        try:
            os.makedirs(data_dir, exist_ok=True)
        except Exception as _amo_exc:
            _note_swallowed("main.AmoDB.__init__", _amo_exc)
            data_dir = plugin_dir
        self.path = os.path.join(data_dir, "amo_forever.db")
        # 4.0.0 起插件标识为 Astrbot_Amo_forever。
        # 4.0.6 保持新标识，并把 3.x 的 amo_forever 旧数据迁移到新目录。
        try:
            import shutil as _shutil
            data_root = get_astrbot_data_path()
            legacy_paths = [
                os.path.join(data_root, "plugin_data", "amo_forever", "amo_forever.db"),
                os.path.join(data_root, "plugin_data", "astrbot_plugin_amo_forever", "amo_forever.db"),
            ]
            current_size = os.path.getsize(self.path) if os.path.exists(self.path) else 0
            if current_size < 4096:
                for legacy_path in legacy_paths:
                    if not os.path.exists(legacy_path) or os.path.getsize(legacy_path) < 4096:
                        continue
                    if os.path.exists(self.path):
                        _shutil.copy2(self.path, self.path + ".bak-4.0.6")
                    for suffix in ("-wal", "-shm", "-journal"):
                        stale = self.path + suffix
                        if os.path.exists(stale):
                            try:
                                os.remove(stale)
                            except Exception as _amo_exc:
                                _note_swallowed("main.AmoDB.__init__", _amo_exc)
                    _shutil.copy2(legacy_path, self.path)
                    for suffix in ("-wal", "-shm"):
                        source = legacy_path + suffix
                        if os.path.exists(source):
                            _shutil.copy2(source, self.path + suffix)
                    logger.info("[amo] 已迁移旧版 amo_forever 数据: %s -> %s" % (legacy_path, self.path))
                    logger.info("[amo] 升级提示：插件标识保持 Astrbot_Amo_forever；旧 amo_forever 数据已迁移到新目录，配置文件也会自动合并。")
                    break
        except Exception as exc:
            logger.warning("[amo] 旧版 amo_forever 数据迁移失败: %s" % exc)
        self.lock = threading.RLock()
        self._conn = None
        self._open()

    def _open(self):
        with self.lock:
            self._open_unlocked()

    def _open_unlocked(self):
        """打开（或重新打开）连接。

        插件重载时 AstrBot 可能先调用旧实例的 terminate()，而旧实例注册的
        Web API 仍然存在；这里保证连接被关闭后下一次访问会自动重开，避免
        "Cannot operate on a closed database"。
        """
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=15)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
        except Exception as _amo_exc:
            _note_swallowed("main.AmoDB._open_unlocked", _amo_exc)

    @property
    def conn(self):
        # Web 协程 + 后台 _tick + _ensure_ready 可能同时进来；不加锁会各自 connect，
        # 后一个覆盖前一个，先前的连接泄漏，PRAGMA journal_mode=WAL 还可能出现 database is locked。
        if self._conn is None:
            with self.lock:
                if self._conn is None:
                    self._open()
        return self._conn

    def init(self):
        with self.lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    uid TEXT PRIMARY KEY,
                    name TEXT DEFAULT '',
                    alias TEXT DEFAULT '',
                    birthday TEXT DEFAULT '',
                    relation TEXT DEFAULT '普通',
                    affection INTEGER DEFAULT 10,
                    notes TEXT DEFAULT '',
                    platform TEXT DEFAULT '',
                    private_umo TEXT DEFAULT '',
                    last_group TEXT DEFAULT '',
                    first_seen REAL DEFAULT 0,
                    last_seen REAL DEFAULT 0,
                    msg_count INTEGER DEFAULT 0,
                    last_proactive REAL DEFAULT 0,
                    proactive_day TEXT DEFAULT '',
                    proactive_count INTEGER DEFAULT 0,
                    relation_at REAL DEFAULT 0,
                    is_admin INTEGER DEFAULT 0,
                    profile_updated_at REAL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    umo TEXT DEFAULT '',
                    uid TEXT DEFAULT '',
                    name TEXT DEFAULT '',
                    role TEXT DEFAULT 'user',
                    content TEXT DEFAULT '',
                    created_at REAL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_msg_umo ON messages(umo);
                CREATE TABLE IF NOT EXISTS kv (
                    key TEXT PRIMARY KEY,
                    value TEXT DEFAULT '',
                    updated REAL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS schedule (
                    day TEXT PRIMARY KEY,
                    items TEXT DEFAULT '[]',
                    updated REAL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS schedule_diary (
                    day TEXT DEFAULT '',
                    hour TEXT DEFAULT '',
                    text TEXT DEFAULT '',
                    updated REAL DEFAULT 0,
                    PRIMARY KEY(day, hour)
                );
                CREATE TABLE IF NOT EXISTS proactive_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid TEXT DEFAULT '',
                    kind TEXT DEFAULT '',
                    content TEXT DEFAULT '',
                    created REAL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS dialects (
                    term TEXT PRIMARY KEY,
                    meaning TEXT DEFAULT '',
                    region TEXT DEFAULT '',
                    example TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS relation_network (
                    a_uid TEXT NOT NULL,
                    b_uid TEXT NOT NULL,
                    relation TEXT DEFAULT '朋友',
                    note TEXT DEFAULT '',
                    updated_at REAL DEFAULT 0,
                    PRIMARY KEY(a_uid, b_uid)
                );
                """
            )
            self.conn.commit()
            self._seed_dialects()
            self._migrate_legacy()
            try:
                cols = {row[1] for row in self.conn.execute("PRAGMA table_info(profiles)").fetchall()}
                if "relation_at" not in cols:
                    self.conn.execute("ALTER TABLE profiles ADD COLUMN relation_at REAL DEFAULT 0")
                    self.conn.execute("UPDATE profiles SET relation_at=last_seen WHERE relation_at=0")
                    self.conn.commit()
                if "profile_updated_at" not in cols:
                    # 画像最后一次「本地手动修改」的时间：面板/命令改画像才更新，
                    # 收消息刷新 last_seen 不算，否则面板改完聊一句就被本地旧值覆盖。
                    self.conn.execute("ALTER TABLE profiles ADD COLUMN profile_updated_at REAL DEFAULT 0")
                    self.conn.commit()
            except Exception as _amo_exc:
                _note_swallowed("main.AmoDB.init", _amo_exc)

    def _migrate_legacy(self):
        try:
            has_old = self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='user_status'"
            ).fetchone()
            if has_old:
                rows = self.conn.execute(
                    "SELECT uid, relation, mem_count FROM user_status"
                ).fetchall()
                for row in rows:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO profiles(uid, relation, msg_count, first_seen, last_seen) "
                        "VALUES(?,?,?,?,?)",
                        (row["uid"], row["relation"] or "普通", row["mem_count"] or 0, now_ts(), now_ts()),
                    )
            self.conn.commit()
        except Exception as exc:
            logger.debug("[amo] 旧数据迁移跳过: %s" % exc)

    def close(self):
        with self.lock:
            if self._conn is None:
                return
            try:
                self._conn.commit()
            except Exception as _amo_exc:
                _note_swallowed("main.AmoDB.close", _amo_exc)
            try:
                self._conn.close()
            except Exception as _amo_exc:
                _note_swallowed("main.AmoDB.close", _amo_exc)
            self._conn = None

    # ---------- KV ----------
    def kv_get(self, key, default=None):
        with self.lock:
            row = self.conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except Exception as _amo_exc:
            _note_swallowed("main.AmoDB.kv_get", _amo_exc)
            return default

    def kv_set(self, key, value):
        with self.lock:
            self.conn.execute(
                "INSERT INTO kv(key, value, updated) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated=excluded.updated",
                (key, json.dumps(value, ensure_ascii=False), now_ts()),
            )
            self.conn.commit()

    # ---------- 档案 ----------
    def get_profile(self, uid):
        with self.lock:
            row = self.conn.execute("SELECT * FROM profiles WHERE uid=?", (str(uid),)).fetchone()
        return dict(row) if row else {}

    def touch_profile(self, uid, name, platform, umo, group_id, private):
        uid = str(uid)
        name = name or ""
        now = now_ts()
        with self.lock:
            row = self.conn.execute("SELECT * FROM profiles WHERE uid=?", (uid,)).fetchone()
            if row is None:
                self.conn.execute(
                    "INSERT INTO profiles(uid, name, platform, private_umo, last_group, "
                    "first_seen, last_seen, msg_count) VALUES(?,?,?,?,?,?,?,1)",
                    (uid, name, platform or "", umo if private else "",
                     umo if not private else "", now, now),
                )
            else:
                updates = ["last_seen=?", "msg_count=msg_count+1"]
                values = [now]
                if name and not row["name"]:
                    updates.append("name=?")
                    values.append(name)
                if private:
                    updates.append("private_umo=?")
                    values.append(umo)
                elif group_id:
                    updates.append("last_group=?")
                    values.append(umo)
                values.append(uid)
                self.conn.execute(
                    "UPDATE profiles SET " + ", ".join(updates) + " WHERE uid=?", values
                )
            self.conn.commit()
            row = self.conn.execute("SELECT * FROM profiles WHERE uid=?", (uid,)).fetchone()
        return dict(row) if row else {}

    def update_profile(self, uid, mark_local=True, **fields):
        allowed = ("name", "alias", "birthday", "relation", "notes",
                   "affection", "is_admin")
        updates = []
        values = []
        for key, value in fields.items():
            if key in allowed:
                updates.append(key + "=?")
                values.append(value)
        if "relation" in fields:
            updates.append("relation_at=?")
            values.append(now_ts())
        if mark_local:
            updates.append("profile_updated_at=?")
            values.append(now_ts())
        if not updates:
            return False
        values.append(str(uid))
        with self.lock:
            self.conn.execute(
                "UPDATE profiles SET " + ", ".join(updates) + " WHERE uid=?", values
            )
            self.conn.commit()
        return True

    def delete_profile(self, uid):
        with self.lock:
            self.conn.execute("DELETE FROM profiles WHERE uid=?", (str(uid),))
            self.conn.commit()

    def list_profiles(self, keyword="", limit=100):
        limit = max(1, min(int(limit), 500))
        with self.lock:
            if keyword:
                like = "%" + str(keyword) + "%"
                rows = self.conn.execute(
                    "SELECT * FROM profiles WHERE uid LIKE ? OR name LIKE ? OR alias LIKE ? "
                    "ORDER BY last_seen DESC LIMIT ?",
                    (like, like, like, limit),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT * FROM profiles ORDER BY last_seen DESC LIMIT ?", (limit,)
                ).fetchall()
        return [dict(row) for row in rows]

    def _seed_dialects(self):
        rows = [
            ("么子", "什么", "贵州·土家族地区", "你在搞么子？"),
            ("哪门", "怎么", "贵州·土家族地区", "哪门搞的？"),
            ("要得", "好的", "贵州·土家族地区", "要得，没问题"),
            ("晓得", "知道", "贵州·土家族地区", "我晓得了"),
            ("恰饭", "吃饭", "贵州·土家族地区", "走，恰饭去"),
            ("莫", "不要", "贵州·土家族地区", "你莫急"),
            ("屋头", "家里", "贵州·土家族地区", "在屋头"),
            ("落雨", "下雨", "贵州·土家族地区", "外头落雨了"),
            ("安逸", "舒服", "贵州·土家族地区", "好安逸"),
            ("拐哒", "糟糕", "贵州·土家族地区", "拐哒，忘了"),
            ("摆龙门阵", "聊天", "贵州·土家族地区", "来摆龙门阵"),
            ("崽崽", "小孩", "贵州·土家族地区", "那个崽崽"),
            ("老汉", "父亲", "贵州·土家族地区", "我老汉"),
            ("堂客", "妻子", "贵州·土家族地区", "他堂客"),
            ("哈戳戳", "傻乎乎", "贵州·土家族地区", "你哈戳戳的"),
            ("扯皮", "吵架", "贵州·土家族地区", "莫扯皮"),
            ("逗是", "就是", "贵州·土家族地区", "逗是这么回事"),
            ("热和", "暖和", "贵州·土家族地区", "屋里热和"),
            ("搞么子", "干什么", "贵州·土家族地区", "你搞么子"),
            ("巴适", "舒服", "贵州·土家族地区", "巴适得很"),
            ("啷个", "怎么", "贵州·土家族地区", "啷个办嘛"),
            ("哪样", "什么", "贵州·土家族地区", "你要哪样"),
            ("为哪样", "为什么", "贵州·土家族地区", "你为哪样不吃饭"),
            ("恁个", "这么", "贵州·土家族地区", "恁个热"),
            ("恁么", "那么", "贵州·土家族地区", "恁么远"),
            ("等哈", "等一下", "贵州·土家族地区", "等哈我"),
            ("一哈", "一下", "贵州·土家族地区", "看一哈"),
            ("哈哈儿", "一会儿", "贵州·土家族地区", "哈哈儿就来"),
            ("将才", "刚才", "贵州·土家族地区", "将才说的"),
            ("这哈", "现在", "贵州·土家族地区", "这哈忙"),
            ("那哈", "那时候", "贵州·土家族地区", "那哈还小"),
            ("哪哈", "什么时候", "贵州·土家族地区", "你哪哈来"),
            ("好久", "多久", "贵州·土家族地区", "等了好久"),
            ("清早", "早晨", "贵州·土家族地区", "清早八晨"),
            ("晌午", "中午", "贵州·土家族地区", "晌午吃饭"),
            ("黑了", "晚上", "贵州·土家族地区", "黑了再说"),
            ("昨儿个", "昨天", "贵州·土家族地区", "昨儿个下雨"),
            ("今儿个", "今天", "贵州·土家族地区", "今儿个赶场"),
            ("明儿个", "明天", "贵州·土家族地区", "明儿个去"),
            ("赶场", "赶集", "贵州·土家族地区", "去镇上赶场"),
            ("吃酒", "参加酒席", "贵州·土家族地区", "明天去吃酒"),
            ("坐席", "入席", "贵州·土家族地区", "快坐席"),
            ("背篓", "竹背篓", "贵州·土家族地区", "背个背篓"),
            ("山卡卡", "山沟里", "贵州·土家族地区", "山卡卡里头"),
            ("坝子", "平地", "贵州·土家族地区", "坝子上晒谷"),
            ("坎坎", "台阶或坎", "贵州·土家族地区", "小心坎坎"),
            ("岩脚", "山岩下", "贵州·土家族地区", "在岩脚歇气"),
            ("河沟", "小河", "贵州·土家族地区", "河沟里摸鱼"),
            ("扯火闪", "闪电", "贵州·土家族地区", "天边扯火闪"),
            ("雪米子", "小冰粒", "贵州·土家族地区", "下雪米子了"),
            ("凌冰", "冰", "贵州·土家族地区", "路上结凌冰"),
            ("太阳坝", "向阳的地方", "贵州·土家族地区", "去太阳坝坐"),
            ("阴凉坝", "阴凉处", "贵州·土家族地区", "树脚阴凉坝"),
            ("热天", "夏天", "贵州·土家族地区", "热天莫出门"),
            ("冷天", "冬天", "贵州·土家族地区", "冷天烤火"),
            ("莫慌", "别急", "贵州·土家族地区", "莫慌，慢慢来"),
            ("慢点", "慢一点", "贵州·土家族地区", "你慢点走"),
            ("归一", "完成、结束", "贵州·土家族地区", "事情搞归一了"),
            ("刹角", "收尾、结束", "贵州·土家族地区", "今天刹角了"),
            ("杀割", "结束", "贵州·土家族地区", "饭吃杀割了"),
            ("架势", "开始、用力", "贵州·土家族地区", "架势干"),
            ("稀罕", "喜欢、少见", "贵州·土家族地区", "我不稀罕"),
            ("撇脱", "干脆、简单", "贵州·土家族地区", "撇脱点"),
            ("巴心巴肠", "一心一意", "贵州·土家族地区", "巴心巴肠对你"),
            ("焦人", "让人着急", "贵州·土家族地区", "这事焦人"),
            ("恼火", "难受、麻烦", "贵州·土家族地区", "心头恼火"),
            ("造孽", "可怜", "贵州·土家族地区", "这娃儿造孽"),
            ("舒气", "整洁、清爽", "贵州·土家族地区", "屋头收拾得舒气"),
            ("冰凊", "冰凉", "贵州·土家族地区", "水冰凊"),
            ("嘎公", "外公", "贵州·土家族地区", "我嘎公"),
            ("嘎婆", "外婆", "贵州·土家族地区", "我嘎婆"),
            ("舅公", "舅爷", "贵州·土家族地区", "舅公来了"),
            ("舅婆", "舅奶", "贵州·土家族地区", "舅婆做饭"),
            ("幺爸", "最小的叔叔", "贵州·土家族地区", "幺爸在家"),
            ("幺妈", "最小的婶婶", "贵州·土家族地区", "幺妈来了"),
            ("嬢嬢", "阿姨", "贵州·土家族地区", "嬢嬢好"),
            ("老表", "表亲或哥们", "贵州·土家族地区", "老表，走哪去"),
            ("家门", "同姓、本家", "贵州·土家族地区", "我们是家门"),
            ("老庚", "同岁好友", "贵州·土家族地区", "他是我老庚"),
            ("娃儿", "孩子", "贵州·土家族地区", "这个娃儿乖"),
            ("妹崽", "女孩", "贵州·土家族地区", "那个妹崽"),
            ("男娃儿", "男孩", "贵州·土家族地区", "男娃儿调皮"),
            ("吃莽莽", "吃饭，哄小孩说法", "贵州·土家族地区", "走，吃莽莽"),
            ("嘎嘎", "肉，儿语", "贵州·土家族地区", "要吃嘎嘎"),
            ("粑粑", "饼、糍粑", "贵州·土家族地区", "烤粑粑"),
            ("折耳根", "鱼腥草", "贵州·土家族地区", "凉拌折耳根"),
            ("酸汤", "酸汤", "贵州·土家族地区", "酸汤鱼"),
            ("糟辣椒", "糟辣椒", "贵州·土家族地区", "糟辣椒炒肉"),
            ("油茶", "油茶", "贵州·土家族地区", "喝碗油茶"),
            ("洋芋", "土豆", "贵州·土家族地区", "烤洋芋"),
            ("苞谷", "玉米", "贵州·土家族地区", "掰苞谷"),
            ("红苕", "红薯", "贵州·土家族地区", "烤红苕"),
            ("海椒", "辣椒", "贵州·土家族地区", "海椒面"),
            ("盐须", "香菜", "贵州·土家族地区", "放点盐须"),
            ("鬼火戳", "生气、窝火", "贵州·土家族地区", "鬼火戳得很"),
            ("毛焦火辣", "焦急", "贵州·土家族地区", "等得毛焦火辣"),
            ("扯把子", "开玩笑", "贵州·土家族地区", "你莫扯把子"),
            ("冲壳子", "吹牛", "贵州·土家族地区", "又冲壳子"),
            ("摆闲条", "闲聊", "贵州·土家族地区", "来摆闲条"),
            ("装莽", "装傻", "贵州·土家族地区", "你莫装莽"),
            ("千翻", "调皮", "贵州·土家族地区", "这娃儿千翻"),
            ("费头子", "调皮鬼", "贵州·土家族地区", "这个费头子"),
            ("猴跳跳", "顽皮好动", "贵州·土家族地区", "猴跳跳的"),
            ("落教", "懂事", "贵州·土家族地区", "这娃儿落教"),
            ("不落教", "不懂事", "贵州·土家族地区", "你莫不落教"),
            ("弯酸", "刁难、挖苦", "贵州·土家族地区", "莫弯酸人"),
            ("洗刷", "数落", "贵州·土家族地区", "又洗刷我"),
            ("日诀", "骂", "贵州·土家族地区", "莫日诀人"),
            ("割孽", "吵架、打架", "贵州·土家族地区", "两个人割孽"),
            ("扯筋", "扯皮", "贵州·土家族地区", "莫扯筋"),
            ("咋整", "怎么办", "东北", "咋整啊"),
            ("得瑟", "显摆", "东北", "别得瑟"),
            ("忽悠", "骗", "东北", "别忽悠我"),
            ("埋汰", "脏、讽刺", "东北", "别埋汰人"),
            ("唠嗑", "聊天", "东北", "来唠嗑"),
            ("嘎哈", "干什么", "东北", "你嘎哈呢"),
            ("老铁", "哥们", "东北", "老铁没毛病"),
            ("贼拉", "非常", "东北", "贼拉冷"),
            ("稀罕", "喜欢", "东北", "我稀罕你"),
            ("麻溜", "快点", "东北", "麻溜的"),
            ("嘚吧", "唠叨", "东北", "别嘚吧了"),
            ("秃噜", "滑脱、说漏", "东北", "别秃噜了"),
            ("稀碎", "碎得很", "东北", "摔稀碎"),
            ("吭哧", "磨蹭", "东北", "别吭哧了"),
            ("瓜娃子", "傻孩子", "四川", "你个瓜娃子"),
            ("雄起", "加油", "四川", "雄起"),
            ("莫得", "没有", "四川", "莫得问题"),
            ("撇脱", "干脆、利落", "四川", "撇脱点"),
            ("巴心不得", "求之不得", "四川", "我巴心不得"),
            ("耍朋友", "谈恋爱", "四川", "耍朋友没"),
            ("搞快些", "快点", "四川", "搞快些"),
            ("啷个办", "怎么办", "四川", "啷个办嘛"),
            ("唔该", "谢谢、劳驾", "广东", "唔该晒"),
            ("多谢", "谢谢", "广东", "多谢你"),
            ("食饭", "吃饭", "广东", "去食饭"),
            ("饮茶", "喝茶", "广东", "去饮茶"),
            ("靓仔", "帅哥", "广东", "靓仔"),
            ("靓女", "美女", "广东", "靓女"),
            ("点解", "为什么", "广东", "点解啊"),
            ("冇", "没有", "广东", "冇问题"),
            ("得闲", "有空", "广东", "得闲饮茶"),
            ("搞掂", "搞定", "广东", "搞掂啦"),
            ("早唞", "晚安", "广东", "早唞"),
            ("好正", "很棒", "广东", "好正"),
            ("唔使", "不用", "广东", "唔使客气"),
            ("酱紫", "这样", "台湾", "酱紫啊"),
            ("机车", "麻烦、烦人", "台湾", "很机车"),
            ("很瞎", "离谱", "台湾", "很瞎"),
            ("阿嬷", "奶奶", "台湾", "阿嬷"),
            ("蛮", "很", "台湾", "蛮好的"),
            ("超赞", "非常棒", "台湾", "超赞"),
            ("拍谢", "不好意思", "台湾", "拍谢啦"),
            ("古早", "传统、旧时", "台湾", "古早味"),
            ("龟毛", "挑剔", "台湾", "别龟毛"),
            ("嘛呢", "干什么", "天津", "嘛呢"),
            ("介", "这", "天津", "介是嘛"),
            ("倍儿", "非常", "天津", "倍儿好"),
            ("哏儿", "有趣", "天津", "真哏儿"),
            ("腻歪", "腻烦、黏人", "天津", "别腻歪"),
            ("得嘞", "好的", "天津", "得嘞"),
            ("幺蛾子", "麻烦", "天津", "出幺蛾子"),
            ("耐人", "招人喜欢", "天津", "真耐人"),
            ("走鸡", "事情办砸", "天津", "走鸡了"),
            ("各色", "特别、难相处", "天津", "真各色"),
            ("弄啥嘞", "干什么", "河南", "你弄啥嘞"),
            ("中", "好", "河南", "中，就这么办"),
            ("得劲", "舒服", "河南", "真得劲"),
            ("木有", "没有", "河南", "木有事"),
            ("恁", "你", "河南", "恁吃饭没"),
            ("俺", "我", "河南", "俺知道了"),
            ("嘟囔", "嘀咕", "河南", "别嘟囔"),
            ("夜儿个", "昨天", "河南", "夜儿个下雨"),
            ("咋着", "怎么了", "河南", "咋着了"),
            ("中不中", "行不行", "河南", "中不中"),
            ("喝汤", "吃晚饭", "河南", "喝汤没"),
            ("阿拉", "我、我们", "上海", "阿拉晓得"),
            ("侬", "你", "上海", "侬好"),
            ("哪能", "怎么", "上海", "哪能办"),
            ("结棍", "厉害", "上海", "侬结棍"),
            ("老灵", "很好", "上海", "老灵额"),
            ("白相", "玩", "上海", "出去白相"),
            ("适意", "舒服", "上海", "适意"),
            ("勿", "不", "上海", "勿晓得"),
            ("谢谢侬", "谢谢你", "上海", "谢谢侬"),
            ("辰光", "时候", "上海", "啥辰光"),
            ("困觉", "睡觉", "上海", "去困觉"),
            ("覅", "不要", "上海", "覅去"),
        ]
        with self.lock:
            for term, meaning, region, example in rows:
                self.conn.execute(
                    "INSERT OR IGNORE INTO dialects(term, meaning, region, example) VALUES(?,?,?,?)",
                    (term, meaning, region, example),
                )
            self.conn.commit()

    def list_dialects(self):
        with self.lock:
            rows = self.conn.execute("SELECT * FROM dialects").fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _relation_pair(a_uid, b_uid):
        a, b = str(a_uid or "").strip(), str(b_uid or "").strip()
        return (a, b) if a <= b else (b, a)

    def list_relations(self):
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM relation_network ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def relations_for(self, uid):
        uid = str(uid or "")
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM relation_network WHERE a_uid=? OR b_uid=? ORDER BY updated_at DESC",
                (uid, uid),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_relation(self, a_uid, b_uid, relation, note=""):
        a, b = self._relation_pair(a_uid, b_uid)
        if not a or not b or a == b:
            return False
        with self.lock:
            self.conn.execute(
                "INSERT INTO relation_network(a_uid, b_uid, relation, note, updated_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(a_uid, b_uid) DO UPDATE SET "
                "relation=excluded.relation, note=excluded.note, updated_at=excluded.updated_at",
                (a, b, str(relation or "朋友"), str(note or "")[:200], now_ts()),
            )
            self.conn.commit()
        return True

    def delete_relation(self, a_uid, b_uid):
        a, b = self._relation_pair(a_uid, b_uid)
        with self.lock:
            cursor = self.conn.execute(
                "DELETE FROM relation_network WHERE a_uid=? AND b_uid=?", (a, b)
            )
            self.conn.commit()
            return cursor.rowcount > 0

    def proactive_profiles(self, limit=30):
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM profiles WHERE private_umo != '' AND relation NOT IN ('仇恨','抵触') "
                "ORDER BY last_proactive ASC LIMIT ?", (int(limit),)
            ).fetchall()
        return [dict(row) for row in rows]

    def bump_proactive(self, uid):
        today = today_str()
        with self.lock:
            row = self.conn.execute(
                "SELECT proactive_day, proactive_count FROM profiles WHERE uid=?", (str(uid),)
            ).fetchone()
            if not row:
                return
            count = int(row["proactive_count"] or 0) + 1
            if row["proactive_day"] != today:
                count = 1
            self.conn.execute(
                "UPDATE profiles SET last_proactive=?, proactive_day=?, proactive_count=? WHERE uid=?",
                (now_ts(), today, count, str(uid)),
            )
            self.conn.commit()

    def log_proactive(self, uid, kind, content):
        with self.lock:
            self.conn.execute(
                "INSERT INTO proactive_log(uid, kind, content, created) VALUES(?,?,?,?)",
                (str(uid), kind, content, now_ts()),
            )
            self.conn.commit()

    # ---------- 消息 ----------
    def add_message(self, umo, uid, name, role, content):
        content = str(content or "").strip()
        if not content:
            return
        with self.lock:
            self.conn.execute(
                "INSERT INTO messages(umo, uid, name, role, content, created_at) VALUES(?,?,?,?,?,?)",
                (str(umo), str(uid), str(name or ""), role, content, now_ts()),
            )
            self.conn.commit()

    def recent_messages(self, umo, limit=10):
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM messages WHERE umo=? ORDER BY id DESC LIMIT ?",
                (str(umo), int(limit)),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def messages_by_uid(self, uid, limit=20):
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM messages WHERE uid=? ORDER BY id DESC LIMIT ?",
                (str(uid), int(limit)),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def chat_history(self, uid, limit=200):
        """按用户参与过的 umo 取原始聊天记录（本人 + 机器人），不是摘要记忆。"""
        uid = str(uid)
        limit = max(1, min(2000, int(limit or 200)))
        with self.lock:
            rows = self.conn.execute(
                "SELECT DISTINCT umo FROM messages WHERE uid=? AND umo!=''",
                (uid,),
            ).fetchall()
            umos = [str(row["umo"]) for row in rows if str(row["umo"] or "")]
            if not umos:
                rows = self.conn.execute(
                    "SELECT * FROM messages WHERE uid=? ORDER BY id DESC LIMIT ?",
                    (uid, limit),
                ).fetchall()
            else:
                placeholders = ",".join("?" for _ in umos)
                params = umos + [uid, limit]
                rows = self.conn.execute(
                    "SELECT * FROM messages WHERE umo IN (" + placeholders + ") "
                    "AND (uid=? OR role='bot') ORDER BY id DESC LIMIT ?",
                    params,
                ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def interaction_stats(self, days=30):
        """按 uid 统计真实互动量（只算用户自己说的话），给关系沉淀用。

        ``days <= 0`` 表示统计全部历史，这样很早以前聊过的人也会被记进关系网。
        """
        days = int(days or 0)
        cutoff = 0 if days <= 0 else now_ts() - days * 86400
        with self.lock:
            rows = self.conn.execute(
                "SELECT uid, MAX(name) AS name, COUNT(*) AS c, MIN(created_at) AS f, MAX(created_at) AS l "
                "FROM messages WHERE role='user' AND uid!='' AND uid!='bot' AND created_at>=? "
                "GROUP BY uid ORDER BY c DESC LIMIT 1000",
                (cutoff,),
            ).fetchall()
        return [dict(row) for row in rows]

    def active_users(self, since, limit=2):
        with self.lock:
            rows = self.conn.execute(
                "SELECT uid, name, COUNT(*) AS c FROM messages WHERE role='user' AND created_at>? "
                "GROUP BY uid ORDER BY c DESC LIMIT ?", (float(since), int(limit))
            ).fetchall()
        return [dict(row) for row in rows]

    def purge_messages(self, days=14):
        with self.lock:
            self.conn.execute("DELETE FROM messages WHERE created_at<?",
                              (now_ts() - max(1, int(days)) * 86400,))
            self.conn.commit()

    # ---------- 日程 ----------
    def save_schedule(self, day, items):
        with self.lock:
            self.conn.execute(
                "INSERT INTO schedule(day, items, updated) VALUES(?,?,?) "
                "ON CONFLICT(day) DO UPDATE SET items=excluded.items, updated=excluded.updated",
                (str(day), json.dumps(items, ensure_ascii=False), now_ts()),
            )
            self.conn.commit()

    def fade_schedules(self, days=7):
        """7~14 天前的日程去掉细节，只保留每小时骨架。"""
        cutoff = (_now().date() - timedelta(days=max(1, int(days)))).isoformat()
        with self.lock:
            rows = self.conn.execute(
                "SELECT day, items FROM schedule WHERE day < ?", (cutoff,)
            ).fetchall()
            for row in rows:
                try:
                    items = json.loads(row["items"])
                except Exception as _amo_exc:
                    _note_swallowed("main.AmoDB.fade_schedules", _amo_exc)
                    continue
                if not isinstance(items, list):
                    continue
                for item in items:
                    if isinstance(item, dict):
                        item.pop("detail", None)
                self.conn.execute(
                    "UPDATE schedule SET items=? WHERE day=?",
                    (json.dumps(items, ensure_ascii=False), row["day"]),
                )
            self.conn.commit()

    def purge_schedules(self, days=14):
        cutoff = (_now().date() - timedelta(days=max(1, int(days)))).isoformat()
        with self.lock:
            self.conn.execute("DELETE FROM schedule WHERE day < ?", (cutoff,))
            self.conn.commit()

    def get_schedule(self, day):
        with self.lock:
            row = self.conn.execute("SELECT items FROM schedule WHERE day=?", (str(day),)).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["items"])
        except Exception as _amo_exc:
            _note_swallowed("main.AmoDB.get_schedule", _amo_exc)
            return None

    def get_diary(self, day, hour):
        with self.lock:
            row = self.conn.execute(
                "SELECT text FROM schedule_diary WHERE day=? AND hour=?",
                (str(day), str(hour)),
            ).fetchone()
        return str(row["text"] or "") if row else ""

    def save_diary(self, day, hour, text):
        with self.lock:
            self.conn.execute(
                "INSERT INTO schedule_diary(day, hour, text, updated) VALUES(?,?,?,?) "
                "ON CONFLICT(day, hour) DO UPDATE SET text=excluded.text, updated=excluded.updated",
                (str(day), str(hour), str(text or ""), now_ts()),
            )
            self.conn.commit()

    def clear_diaries(self, day):
        with self.lock:
            self.conn.execute("DELETE FROM schedule_diary WHERE day=?", (str(day),))
            self.conn.commit()

    def clear_diaries_from(self, day, hour):
        """只清某个小时及以后的小日记（换城覆盖日程时用，过去的留着）。"""
        with self.lock:
            self.conn.execute(
                "DELETE FROM schedule_diary WHERE day=? AND hour>=?", (str(day), str(hour))
            )
            self.conn.commit()

    def purge_diaries(self, days=30):
        cutoff = (_now().date() - timedelta(days=max(1, int(days)))).isoformat()
        with self.lock:
            self.conn.execute("DELETE FROM schedule_diary WHERE day < ?", (cutoff,))
            self.conn.commit()

    # ---------- 统计 ----------
    def counts(self):
        with self.lock:
            profiles = self.conn.execute("SELECT COUNT(*) AS c FROM profiles").fetchone()["c"]
            memories = 0
            messages = self.conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"]
        return {"profiles": profiles, "memories": memories, "messages": messages}


# ---------------------------------------------------------------------------
# 状态：九维心情 / 生理期 / 健康 / 天气 / 世界观 / 日程
# ---------------------------------------------------------------------------

class HumanState:
    def __init__(self, plugin):
        self.p = plugin
        self.db = plugin.db
        saved_mood = self.db.kv_get("mood", {}) or {}
        self.mood = {key: clamp(saved_mood.get(key, MOOD_BASE[key])) for key in MOOD_KEYS}
        self.mood_ts = to_float(self.db.kv_get("mood_ts", now_ts()), now_ts())
        config_start = self.p.cfg_str("period_start", "").strip()
        seen = self.db.kv_get("period_config_seen", "")
        stored = self.db.kv_get("period_start", "")
        if config_start and config_start != seen:
            try:
                date.fromisoformat(config_start)
                stored = config_start
                self.db.kv_set("period_config_seen", config_start)
            except Exception as _amo_exc:
                _note_swallowed("main.HumanState.__init__", _amo_exc)
        self.period_start = stored or (_now().date() - timedelta(days=10)).isoformat()
        self.health = self.db.kv_get("health", {}) or {
            "status": "健康", "since": now_ts(), "until": 0, "note": ""
        }
        self.weather = self.db.kv_get("weather", {}) or {}
        self.worldview = self.db.kv_get("worldview", {}) or {}
        self.schedule = self.db.kv_get("schedule", {}) or {}
        self.schedule_ctx = self.db.kv_get("schedule_ctx", {}) or {}
        if not isinstance(self.schedule_ctx, dict):
            self.schedule_ctx = {}
        self.schedule_profile = self.db.kv_get("schedule_profile", {}) or {}
        if not isinstance(self.schedule_profile, dict):
            self.schedule_profile = {}
        self.engine = None
        if ScheduleEngine is not None:
            try:
                self.engine = ScheduleEngine(self)
            except Exception as exc:
                logger.warning("[amo] 日程引擎初始化失败: %s" % exc)
        self.last_daily = self.db.kv_get("last_daily", "")
        self.last_health_roll = self.db.kv_get("last_health_roll", "")

    # ---------- 心情 ----------
    def save_mood(self):
        self.db.kv_set("mood", {key: round(value, 2) for key, value in self.mood.items()})
        self.db.kv_set("mood_ts", self.mood_ts)

    def save(self):
        self.save_mood()
        self.db.kv_set("period_start", self.period_start)
        self.db.kv_set("health", self.health)
        self.db.kv_set("last_daily", self.last_daily)
        self.db.kv_set("last_health_roll", self.last_health_roll)

    def nudge(self, **deltas):
        for key, value in deltas.items():
            if key in self.mood:
                self.mood[key] = clamp(self.mood[key] + value)
        self.mood_ts = now_ts()
        self.save_mood()

    def decay_mood(self):
        now = now_ts()
        hours = max(0.0, (now - self.mood_ts) / 3600.0)
        if hours <= 0:
            return
        # 连续衰减：约 45 分钟向基础值回落一半，不再要求隔 9 分钟才衰减一次。
        rate = min(0.85, 1.0 - math.exp(-hours / 0.75))
        for key in MOOD_KEYS:
            self.mood[key] = self.mood[key] + (MOOD_BASE[key] - self.mood[key]) * rate
        self.mood_ts = now
        self.save_mood()

    def dominant_mood(self):
        return max(MOOD_KEYS, key=lambda key: self.mood[key])

    def mood_score(self):
        m = self.mood
        positive = (m["开心"] + m["兴奋"] + m["平静"] + m["依恋"]) / 4.0
        negative = (m["郁闷"] + m["疲惫"] + m["生气"] + m["暴躁"] + m["委屈"] + m["焦虑"]) / 6.0
        return clamp(50 + (positive - negative) * 0.8)

    def mood_text(self):
        parts = [key + str(int(round(value))) for key, value in self.mood.items()]
        return " ".join(parts) + "（整体偏" + self.dominant_mood() + "）"

    def observe(self, text):
        senti = sentiment(text)
        if re.search(r"(对不起|抱歉|我错了|别生气|不生气|哄你|哄哄|原谅我)", text or ""):
            # 恋人或普通人的道歉都要能真正降温，不能“道歉也没用”。
            self.nudge(生气=-18, 暴躁=-10, 委屈=-6, 郁闷=-3, 开心=4, 依恋=2)
        elif senti["insult"] or senti["angry"] >= 2:
            self.nudge(生气=9, 暴躁=5, 开心=-8, 委屈=5)
        elif senti["sad"]:
            self.nudge(郁闷=8, 委屈=7, 开心=-4)
        elif senti["aff"]:
            self.nudge(开心=10, 依恋=12, 生气=-5, 暴躁=-3)
        elif senti["pos"]:
            self.nudge(开心=6, 平静=2, 生气=-2)
        elif senti["neg"]:
            self.nudge(郁闷=4, 疲惫=2)
        else:
            self.nudge(平静=1)
        hour = _now().hour
        if 0 <= hour < 6:
            self.nudge(疲惫=3, 平静=2)
        elif 6 <= hour < 9:
            self.nudge(疲惫=-1, 开心=1)
        elif 22 <= hour < 24:
            self.nudge(疲惫=2, 依恋=2)

    # ---------- 生理期 ----------
    def period_info(self):
        if not self.p.cfg_bool("enable_period_simulate", True):
            return {
                "day": 0, "phase": "非生理期", "tone": "", "pain": 0,
                "reply_mult": 1.0, "days_to_next": 0,
                "cycle_days": self.p.cfg_int("period_cycle_days", 28),
                "bleed_days": 0, "next_start": "",
            }
        try:
            start = date.fromisoformat(str(self.period_start))
        except Exception as _amo_exc:
            _note_swallowed("main.HumanState.period_info", _amo_exc)
            start = _now().date() - timedelta(days=10)
            self.period_start = start.isoformat()
        cycle_days = max(10, self.p.cfg_int("period_cycle_days", 28))
        bleed_days = max(1, min(self.p.cfg_int("period_days", 5), cycle_days - 6))
        day = (_now().date() - start).days % cycle_days + 1
        ovulation_day = max(bleed_days + 1, min(cycle_days - 1, self.p.cfg_int("period_ovulation_day", 14)))
        ovulation_window = max(1, min(9, self.p.cfg_int("period_ovulation_window", 3)))
        ovulation_start = max(bleed_days + 1, ovulation_day - (ovulation_window - 1) // 2)
        ovulation_end = min(cycle_days - 1, ovulation_start + ovulation_window - 1)
        if day <= bleed_days:
            phase = "月经期"
            tone = self.p.cfg_str("period_menstrual_tone", "身体沉沉的，容易累，也更容易委屈")
            pain = min(9, 5 + max(0, bleed_days + 1 - day))
            reply_mult = 0.8
        elif day < ovulation_start:
            phase = "卵泡期"
            tone = self.p.cfg_str("period_follicular_tone", "身体轻快，心情慢慢变好")
            pain = 1
            reply_mult = 1.05
        elif day <= ovulation_end:
            phase = "排卵期"
            tone = self.p.cfg_str("period_ovulatory_tone", "精力最好，也更想和人说话")
            pain = 0
            reply_mult = 1.12
        else:
            phase = "黄体期"
            tone = self.p.cfg_str("period_luteal_tone", "容易烦躁、敏感，想要被哄")
            pain = 3
            reply_mult = 0.88
        pain = max(0, min(10, pain + (md5_int(str(start) + str(day)) % 3) - 1))
        if phase == "月经期":
            phase_day = day
        elif phase == "卵泡期":
            phase_day = day - bleed_days
        elif phase == "排卵期":
            phase_day = day - ovulation_start + 1
        else:
            phase_day = day - ovulation_end
        return {
            "day": day, "phase": phase, "phase_day": max(1, phase_day),
            "tone": tone, "pain": pain,
            "reply_mult": reply_mult, "days_to_next": cycle_days - day + 1,
            "cycle_days": cycle_days, "bleed_days": bleed_days,
            "ovulation_day": ovulation_day, "ovulation_window": ovulation_window,
            "next_start": (_now().date() + timedelta(days=cycle_days - day + 1)).isoformat(),
        }

    def set_period_start(self, value):
        try:
            parsed = date.fromisoformat(str(value))
        except Exception as _amo_exc:
            _note_swallowed("main.HumanState.set_period_start", _amo_exc)
            return False
        self.period_start = parsed.isoformat()
        self.db.kv_set("period_start", self.period_start)
        self.db.kv_set("period_config_seen", self.p.cfg_str("period_start", ""))
        return True

    # ---------- 健康 ----------
    def health_info(self):
        status = self.health.get("status", "健康")
        until = to_float(self.health.get("until", 0))
        if status != "健康" and until and now_ts() >= until:
            self.health = {"status": "健康", "since": now_ts(), "until": 0, "note": ""}
            self.db.kv_set("health", self.health)
            status = "健康"
        return {
            "status": status,
            "since": to_float(self.health.get("since", 0)),
            "until": to_float(self.health.get("until", 0)),
            "note": self.health.get("note", ""),
            # 「疲惫」只是累，不是病：以前 status != 健康 全算 sick，于是休息日
            # 排成「吃药、量体温、捂汗」的病号一天。
            "sick": status in SICK_STATUSES,
        }

    def set_health(self, status, hours=24, note=""):
        if status == "健康":
            self.health = {"status": "健康", "since": now_ts(), "until": 0, "note": ""}
        else:
            self.health = {
                "status": status, "since": now_ts(),
                "until": now_ts() + max(1, hours) * 3600, "note": note,
            }
        self.db.kv_set("health", self.health)

    def roll_health(self):
        if not self.p.cfg_bool("enable_sick_random", True):
            return
        now = now_ts()
        if self.health.get("status") != "健康" and to_float(self.health.get("until", 0)) <= now:
            self.health = {"status": "健康", "since": now, "until": 0, "note": ""}
            self.db.kv_set("health", self.health)
        if self.last_health_roll == today_str():
            return
        self.last_health_roll = today_str()
        self.db.kv_set("last_health_roll", self.last_health_roll)
        if self.health.get("status") != "健康":
            return
        prob = self.p.cfg_float("sick_prob", 0.02)
        weather = self.weather or {}
        if weather.get("tag") in ("rain", "storm", "snow"):
            prob += 0.03
        if to_float(weather.get("temp", 20), 20) < 8:
            prob += 0.02
        if self.period_info()["phase"] == "月经期":
            prob += 0.02
        if self.mood.get("疲惫", 0) > 65:
            prob += 0.02
        if random.random() >= prob:
            return
        status = random.choice(["轻微不适", "感冒", "低烧", "疲惫"])
        hours = {"轻微不适": 12, "感冒": 48, "低烧": 24, "疲惫": 10}[status]
        note = {
            "轻微不适": "有点不舒服，说不上哪里难受",
            "感冒": "鼻子堵堵的，头有点沉",
            "低烧": "身上发烫，没什么力气",
            "疲惫": "没由来的累，只想躺着",
        }[status]
        self.health = {"status": status, "since": now, "until": now + hours * 3600, "note": note}
        self.db.kv_set("health", self.health)

    # ---------- 天气 ----------
    @staticmethod
    def _weather_base_url(value, default=""):
        """和风 Host 兼容：允许只填域名（自动补 https://），也允许带路径。"""
        text = str(value or default or "").strip().rstrip("/")
        if not text:
            return ""
        if not text.startswith(("http://", "https://")):
            text = "https://" + text
        return text

    @staticmethod
    def _weather_tag(text):
        if any(word in text for word in ("雷", "暴雨")):
            return "storm"
        if "雪" in text:
            return "snow"
        if "雨" in text:
            return "rain"
        if "晴" in text:
            return "clear"
        if "阴" in text:
            return "overcast"
        if "雾" in text or "霾" in text:
            return "fog"
        return "cloud"

    def _simulate_weather(self):
        month = _now().date().month
        rng = random.Random(md5_int(today_str() + str(_now().hour)))
        if month in (12, 1, 2):
            choices = [("晴", "clear"), ("多云", "cloud"), ("阴", "overcast"),
                       ("小雪", "snow"), ("小雨", "rain")]
            base_temp = 7
        elif month in (6, 7, 8):
            choices = [("晴", "clear"), ("多云", "cloud"), ("雷阵雨", "storm"),
                       ("阵雨", "rain"), ("阴", "overcast")]
            base_temp = 29
        else:
            choices = [("晴", "clear"), ("多云", "cloud"), ("小雨", "rain"),
                       ("阴", "overcast")]
            base_temp = 19
        text, tag = rng.choice(choices)
        temp = base_temp + rng.randint(-4, 4)
        city = (
            self.p.cfg_str("weather_city", "").strip()
            or str((getattr(self, "schedule_profile", {}) or {}).get("city") or "").strip()
            or "贵阳"
        )
        return {
            # 存显示名，refresh_weather 的缓存签名才比得上（weather_city 可能是数字 ID）
            "city": (self.p.cfg_str("weather_city_name", "") or "").strip() or city,
            "text": text, "tag": tag, "temp": temp,
            "humidity": rng.randint(40, 90),
            "wind": random.choice(["东风", "南风", "西北风", "微风"]) + str(rng.randint(1, 4)) + "级",
            "ts": now_ts(), "source": "simulate", "ok": True, "error": "",
            "key_set": bool(self.p.cfg_str("hefeng_key", "")),
            "host": self.p.cfg_str("weather_host", ""),
        }

    async def _qweather_payload(self, response, label):
        try:
            text = await response.text()
        except Exception as exc:
            logger.warning("[amo] 和风天气 %s 读取响应失败: %s" % (label, exc))
            return {}
        if not str(text or "").strip():
            logger.warning("[amo] 和风天气 %s 返回空响应 HTTP %s" % (label, getattr(response, "status", "?")))
            return {}
        try:
            payload = json.loads(text)
        except Exception:
            logger.warning(
                "[amo] 和风天气 %s 返回非 JSON HTTP %s: %s"
                % (label, getattr(response, "status", "?"), str(text)[:160])
            )
            return {}
        if not isinstance(payload, dict):
            logger.warning("[amo] 和风天气 %s 返回格式异常: %s" % (label, type(payload).__name__))
            return {}
        code = str(payload.get("code") or "")
        status = to_int(getattr(response, "status", 0), 0)
        if status >= 400 or (code and code != "200"):
            logger.warning(
                "[amo] 和风天气 %s HTTP %s code=%s: %s"
                % (label, status, code or "?", str(payload)[:200])
            )
        return payload

    async def _qweather_get(self, url, params):
        """和风请求：用系统网络栈（线程里 urllib），避免 aiohttp 在部分环境超时。"""
        import urllib.parse
        import urllib.request

        key = self.p.cfg_str("hefeng_key", "")
        query = dict(params or {})
        query["key"] = key
        full = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(query)

        def _do():
            req = urllib.request.Request(
                full, headers={"X-QW-Api-Key": key, "Accept-Encoding": "identity"}
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                raw = resp.read()
            if raw[:2] == b"\x1f\x8b":
                import gzip
                raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8"))

        return await asyncio.to_thread(_do)

    def _location_of(self, city):
        """中文城市名换成 LocationID；数字/坐标/空值原样返回。

        注意：这两个取天气的方法在 HumanState 上，不能调插件的 `_city_lookup`，
        所以直接用离线表模块的纯函数，模块不在就原样交给上层。
        """
        try:
            try:
                from .amo_city_index import city_location
            except Exception as _amo_exc:
                _note_swallowed("main.HumanState._location_of", _amo_exc)
                from amo_city_index import city_location
            return city_location(city)
        except Exception as exc:
            logger.debug("[amo] 城市名解析失败: %s" % exc)
            return str(city or "").strip()

    async def _fetch_qweather(self, key, city):
        host = self._weather_base_url(self.p.cfg_str("weather_host", ""))
        if not host:
            return None
        legacy_hosts = {"https://devapi.qweather.com", "https://api.qweather.com"}
        if host in legacy_hosts:
            logger.warning("[amo] 和风天气公共 API 域名已停服，请在配置里填写控制台的 API Host")
        geo_raw = self._weather_base_url(self.p.cfg_str("weather_geo_host", ""))
        if geo_raw:
            geo_base = geo_raw
            if geo_base.endswith("/city/lookup"):
                geo_base = geo_base[: -len("/city/lookup")]
            if not geo_base.endswith(("/geo/v2", "/v2")):
                geo_base += "/geo/v2"
        else:
            geo_base = host + "/geo/v2"
        location = self._location_of(city)
        try:
            # 坐标（经度,纬度）和风直接吃，别再去 GeoAPI 换 ID（那会 403）
            if not location.isdigit() and "," not in location:
                geo = await self._qweather_get(
                    geo_base + "/city/lookup", {"location": location, "number": 1}
                )
                if str(geo.get("code") or "") != "200" or not isinstance(geo.get("location"), list):
                    return None
                first = geo["location"][0] if geo["location"] else None
                if not isinstance(first, dict) or not first.get("id"):
                    return None
                location = str(first["id"])
            data = await self._qweather_get(host + "/v7/weather/now", {"location": location})
            if not isinstance(data, dict) or str(data.get("code") or "") != "200":
                logger.warning("[amo] 和风天气 now 返回异常: %s" % str(data)[:160])
                return None
            now = data.get("now")
            if not isinstance(now, dict):
                logger.warning("[amo] 和风天气 now 字段缺失或格式异常")
                return None
            text = str(now.get("text") or "多云")
            city_name = (self.p.cfg_str("weather_city_name", "") or "").strip() or city
            return {
                "city": city_name, "text": text, "tag": self._weather_tag(text),
                "temp": to_int(now.get("temp")), "humidity": to_int(now.get("humidity")),
                "wind": str(now.get("windDir", "")) + str(now.get("windScale", "")) + "级",
                "ts": now_ts(), "source": "qweather", "ok": True, "error": "",
                "key_set": True,
                "host": host,
            }
        except Exception as exc:
            logger.warning("[amo] 和风天气接口失败: %s %r" % (type(exc).__name__, exc))
            return None

    async def _fetch_qweather_daily(self, key, city, days=3, fresh=False):
        """明天/后天的预报；缓存 3 小时，避免后台循环反复打接口。

        fresh=True 跳过缓存：晚上发预警前要拿最新的一份，早上判断的那份不算数。
        """
        cache = self.db.kv_get("weather_daily", {}) or {}
        city = str(city or "").strip()
        if (
            not fresh
            and isinstance(cache, dict)
            and cache.get("ts")
            and now_ts() - to_float(cache.get("ts"), 0) < 3 * 3600
            and str(cache.get("city") or "") == city
            and to_int(cache.get("days")) == int(days)
        ):
            items = cache.get("items")
            return items if isinstance(items, list) else []
        host = self._weather_base_url(self.p.cfg_str("weather_host", ""))
        if not host:
            return []
        geo_raw = self._weather_base_url(self.p.cfg_str("weather_geo_host", ""))
        if geo_raw:
            geo_base = geo_raw
            if geo_base.endswith("/city/lookup"):
                geo_base = geo_base[: -len("/city/lookup")]
            if not geo_base.endswith(("/geo/v2", "/v2")):
                geo_base += "/geo/v2"
        else:
            geo_base = host + "/geo/v2"
        location = self._location_of(city)
        try:
            # 坐标（经度,纬度）和风直接吃，别再去 GeoAPI 换 ID（那会 403）
            if not location.isdigit() and "," not in location:
                geo = await self._qweather_get(
                    geo_base + "/city/lookup", {"location": location, "number": 1}
                )
                if str(geo.get("code") or "") != "200" or not isinstance(geo.get("location"), list):
                    return []
                first = geo["location"][0] if geo["location"] else None
                if not isinstance(first, dict) or not first.get("id"):
                    return []
                location = str(first["id"])
            data = await self._qweather_get(host + "/v7/weather/%dd" % int(days), {"location": location})
            if not isinstance(data, dict) or str(data.get("code") or "") != "200":
                logger.warning("[amo] 和风天气预报返回异常: %s" % str(data)[:160])
                return []
            items = parse_weather_daily(data)
        except Exception as exc:
            logger.warning("[amo] 和风天气预报接口失败: %s %r" % (type(exc).__name__, exc))
            return []
        self.db.kv_set("weather_daily", {"ts": now_ts(), "city": city, "days": int(days), "items": items})
        return items

    async def refresh_weather(self, force=False):
        try:
            self.p._reload_config_if_changed()
        except Exception as _amo_exc:
            _note_swallowed("main.HumanState.refresh_weather", _amo_exc)
        try:
            self.p._sync_weather_city_config()
        except Exception as _amo_exc:
            _note_swallowed("main.HumanState.refresh_weather", _amo_exc)
        current = self.weather or {}
        key = self.p.cfg_str("hefeng_key", "")
        city = (
            self.p.cfg_str("weather_city", "").strip()
            or str((getattr(self, "schedule_profile", {}) or {}).get("city") or "").strip()
            or "贵阳"
        )
        host = self.p.cfg_str("weather_host", "")
        # 配置里的城市/Key/Host 变了就必须重取，不能继续用旧缓存。
        # 比较用显示名：weather_city 可能是数字 LocationID，缓存里存的却是「东莞」这种名字，
        # 拿数字去比永远不相等 → 每次轮询都强制重取天气（30 秒一次，免费额度会被打光）。
        city_label = (self.p.cfg_str("weather_city_name", "") or "").strip() or city
        current_signature = (current.get("city"), bool(current.get("key_set")), current.get("host"))
        desired_signature = (city_label, bool(key), host)
        if current_signature != desired_signature:
            force = True
        if not force and current.get("ts") and now_ts() - current["ts"] < 1800:
            return current
        # 刚刷过就别再打接口（双击「设置」、面板刷新和后台 tick 撞车）
        if force and current.get("ts") and now_ts() - to_float(current["ts"], 0) < 3:
            return current
        old_tag = current.get("tag")
        data = None
        if key:
            data = await self._fetch_qweather(key, city)
        if not data:
            data = self._simulate_weather()
        self.weather = data
        self.db.kv_set("weather", data)
        if data.get("tag") != old_tag:
            if data.get("tag") in ("rain", "storm", "snow"):
                self.nudge(郁闷=2, 平静=2)
            elif data.get("tag") == "clear":
                self.nudge(开心=2)
        return data

    def weather_text(self):
        weather = self.weather or {}
        if not weather:
            return "还不知道天气"
        return "%s %s %s℃ 湿度%s%% %s" % (
            weather.get("city", ""), weather.get("text", ""),
            weather.get("temp", ""), weather.get("humidity", ""), weather.get("wind", ""),
        )

    def weather_brief(self):
        """面板用的一行天气摘要（只读缓存，不请求和风）。"""
        weather = self.weather or {}
        if not weather:
            return {}
        return {
            "city": str(weather.get("city") or ""),
            "text": str(weather.get("text") or ""),
            "temp": weather.get("temp"),
            "humidity": weather.get("humidity"),
            "wind": str(weather.get("wind") or ""),
            "tag": str(weather.get("tag") or ""),
            "source": str(weather.get("source") or ""),
            "ts": to_float(weather.get("ts"), 0),
        }

    # ---------- 世界观 ----------
    def _fallback_world(self):
        return {
            "name": self.p.persona_name or self.p.cfg_str("bot_name", "") or "陪伴",
            "age": 22,
            "city": (
                self.p.cfg_str("weather_city_name", "").strip()
                or self.p.cfg_str("weather_city", "").strip()
                or str((getattr(self, "schedule_profile", {}) or {}).get("city") or "").strip()
                or "贵阳"
            ),
            "occupation": "普通上班族",
            "workplace": "公司",
            "personality": "温柔、敏感，偶尔有点小脾气",
            "hobbies": ["听歌", "散步", "喝奶茶"],
            "daily_life": "一个人在城市里上班、生活，会为小事开心，也会有力气用光的时候。",
            "world_rules": "这是一个普通的现代都市，没有超能力；角色要上班、吃饭、睡觉，也会生病和情绪低落。",
            "summary": "一个在城市里认真生活的普通女孩。",
            "_ts": now_ts(),
        }

    async def ensure_worldview(self, umo, force=False):
        if not force and self.worldview and now_ts() - to_float(self.worldview.get("_ts")) < 7 * 86400:
            return self.worldview
        persona = await self.p.llm.persona(umo)
        data = await self.p.llm.gen_worldview(umo, persona)
        if not data:
            data = self._fallback_world()
        name = await self.p._persona_name_for(umo)
        if name:
            data["name"] = name
        data["_ts"] = now_ts()
        self.worldview = data
        self.db.kv_set("worldview", data)
        if name:
            self.p.persona_name = name
            self.p.bot_name = name
        elif data.get("name") and self.p.cfg_str("bot_name", ""):
            self.p.bot_name = data["name"]
        return data

    def worldview_text(self):
        world = self.worldview or {}
        if not world:
            return "还没有生成世界观。"
        hobbies = world.get("hobbies") or []
        if isinstance(hobbies, list):
            hobbies = "、".join([str(item) for item in hobbies])
        return "\n".join([
            "名字：%s" % world.get("name", ""),
            "年龄：%s" % world.get("age", ""),
            "城市：%s" % world.get("city", ""),
            "职业：%s" % world.get("occupation", ""),
            "任职：%s" % world.get("workplace", ""),
            "性格：%s" % world.get("personality", ""),
            "爱好：%s" % hobbies,
            "日常：%s" % world.get("daily_life", ""),
            "规则：%s" % world.get("world_rules", ""),
        ])

    # ---------- 日程（主干生成 + 动态展开） ----------
    @staticmethod
    def _hourly_schedule(items):
        """把任意日程整理成 24 条整点日程；最后一条固定 23:00-24:00。"""
        valid = [item for item in (items or []) if isinstance(item, dict) and item.get("start")]
        valid.sort(key=lambda item: parse_hhmm(item.get("start")))
        result = []
        for hour in range(24):
            start_min = hour * 60
            found = None
            for item in valid:
                begin = parse_hhmm(item.get("start"))
                finish = parse_hhmm(item.get("end")) or (begin + 60)
                if begin <= start_min < finish:
                    found = item
                    break
            entry = {
                "start": "%02d:00" % hour,
                "end": "24:00" if hour == 23 else "%02d:00" % (hour + 1),
                "activity": "睡觉" if hour < 7 or hour >= 23 else "休息",
                "place": "家",
                "category": "sleep" if hour < 7 or hour >= 23 else "rest",
            }
            if found:
                entry.update({
                    "activity": found.get("activity", "休息"),
                    "place": found.get("place", "家"),
                    "category": found.get("category", "rest"),
                })
                for key in ("zone", "transit", "vehicle", "detail", "spot",
                            "event", "mood", "mood_valence"):
                    if found.get(key) not in (None, "", 0):
                        entry[key] = found.get(key)
                if isinstance(found.get("effects"), dict):
                    entry["effects"] = found.get("effects")
                if found.get("soothe"):
                    entry["soothe"] = True
            result.append(entry)
        return result

    @staticmethod
    def _fmt_minutes(value):
        value = max(0, min(24 * 60, int(value)))
        if value >= 24 * 60:
            return "24:00"
        return "%02d:%02d" % (value // 60, value % 60)

    def schedule_tree(self, day=None):
        """一级 4 段、二级每小时；不再生成三级 10 分钟。"""
        day = str(day or today_str())
        hourly = self._hourly_schedule(self.schedule.get(day) or self.db.get_schedule(day) or [])
        now_min = minutes_now()
        is_today = day == today_str()
        blocks = [
            {"start": "00:00", "end": "06:00", "title": "深夜"},
            {"start": "06:00", "end": "12:00", "title": "上午"},
            {"start": "12:00", "end": "18:00", "title": "中午"},
            {"start": "18:00", "end": "24:00", "title": "晚上"},
        ]
        for block in blocks:
            bstart = parse_hhmm(block["start"])
            bend = 24 * 60 if block["end"] == "24:00" else parse_hhmm(block["end"])
            children = []
            for item in hourly:
                start = max(bstart, parse_hhmm(item.get("start")))
                end = min(bend, parse_hhmm(item.get("end")))
                if start >= end:
                    continue
                hour = {
                    "start": self._fmt_minutes(start),
                    "end": self._fmt_minutes(end),
                    "activity": item.get("activity", "休息"),
                    "place": item.get("place", "家"),
                    "category": item.get("category", "rest"),
                    "zone": item.get("zone", ""),
                    "transit": item.get("transit", ""),
                    "vehicle": item.get("vehicle", ""),
                    "detail": item.get("detail", ""),
                    "event": item.get("event", ""),
                    "mood": item.get("mood", ""),
                    "current": bool(is_today and start <= now_min < end),
                }
                children.append(hour)
            block["date"] = day
            block["children"] = children
            block["current"] = any(child["current"] for child in children)
            if children:
                if all(item.get("category") == "sleep" for item in children):
                    block["activity"] = "睡觉"
                elif any(item.get("category") in ("play", "social") for item in children):
                    block["activity"] = "出去玩"
                elif any(item.get("category") == "work" for item in children):
                    block["activity"] = "上班"
                elif any(item.get("category") == "commute" for item in children):
                    block["activity"] = "回家"
                elif any(item.get("category") == "meal" for item in children):
                    block["activity"] = "吃饭"
                elif any(item.get("category") == "rest" for item in children):
                    block["activity"] = "休息"
                else:
                    block["activity"] = children[0].get("activity") or "休息"
                block["place"] = children[0].get("place") or ""
        return blocks

    @staticmethod
    def _cover_schedule(items):
        """兼容旧数据：补上 00:00 到第一条安排之间的睡眠段。"""
        if not isinstance(items, list) or not items:
            return items
        valid = [item for item in items if isinstance(item, dict) and item.get("start")]
        if not valid:
            return items
        ordered = sorted(valid, key=lambda item: parse_hhmm(item.get("start")))
        first_start = ordered[0].get("start", "00:00")
        if parse_hhmm(first_start) > 0:
            ordered.insert(0, {
                "start": "00:00", "end": first_start,
                "activity": "睡觉", "place": "家", "category": "sleep", "zone": "home",
            })
        return ordered

    def _emergency_schedule(self):
        """新引擎不可用时的最小兜底，保证 24 小时闭环、不瞬移。"""
        profile = getattr(self, "schedule_profile", {}) or {}
        home = self.p.cfg_str("schedule_home", "") or profile.get("home") or "家"
        office = self.p.cfg_str("schedule_workplace", "") or profile.get("workplace") or "公司"
        items = []
        for hour in range(24):
            if hour < 7 or hour >= 23:
                activity, place, zone, category = "睡觉", home, "home", "sleep"
            elif hour < 8:
                activity, place, zone, category = "起床洗漱", home, "home", "life"
            elif hour < 9:
                activity, place, zone, category = "通勤去公司", "路上", "road", "commute"
            elif hour < 12:
                activity, place, zone, category = "上班", office, "office", "work"
            elif hour < 13:
                activity, place, zone, category = "吃午饭", office + "附近", "restaurant", "meal"
            elif hour < 14:
                activity, place, zone, category = "午休", office, "office", "rest"
            elif hour < 18:
                activity, place, zone, category = "上班", office, "office", "work"
            elif hour < 19:
                activity, place, zone, category = "下班回家", "路上", "road", "commute"
            elif hour < 20:
                activity, place, zone, category = "吃晚饭", home, "home", "meal"
            elif hour < 22:
                activity, place, zone, category = "休息", home, "home", "rest"
            else:
                activity, place, zone, category = "洗澡护肤", home, "home", "life"
            items.append({
                "start": "%02d:00" % hour,
                "end": "24:00" if hour == 23 else "%02d:00" % (hour + 1),
                "activity": activity, "place": place, "zone": zone,
                "category": category,
            })
        return items

    async def ensure_schedule(self, umo, force=False):
        """每天只生成一次主干；点击二级卡片时再动态生成这一小时的日记。"""
        today = today_str()
        meta = day_meta(today)
        existing = None if force else self.schedule.get(today)
        context = self.schedule_ctx.get(today) or {}
        version_ok = (
            self.db.kv_get("schedule_version", "") == SCHEDULE_VERSION
            and isinstance(context, dict)
            and context.get("version") == "backbone-v5"
        )
        if existing and version_ok and not force:
            hourly = self._hourly_schedule(existing)
            if hourly != existing:
                self.schedule[today] = hourly
                self.db.kv_set("schedule", self.schedule)
                self.db.save_schedule(today, hourly)
            return hourly
        world = await self.ensure_worldview(umo)
        persona = ""
        try:
            if self.p.llm is not None:
                persona = await self.p.llm.persona(umo)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanState.ensure_schedule", _amo_exc)
            persona = ""
        if self.engine is not None:
            try:
                self.schedule_profile = self.engine.resolve_profile(world, persona, seed=today)
            except Exception as exc:
                logger.debug("[amo] 角色位置解析失败: %s" % exc)
        weather = await self.refresh_weather()
        try:
            self.roll_health()
        except Exception as _amo_exc:
            _note_swallowed("main.HumanState.ensure_schedule", _amo_exc)
        period = self.period_info()
        health = self.health_info()
        context = None
        items = None
        if self.engine is not None:
            try:
                context = self.engine.build_context(
                    today, meta, weather, world, self.mood, period, health,
                    persona=persona, salt=str(now_ts()) if force else "",
                )
                self.schedule_profile = context.get("profile") or self.schedule_profile
                items = self.engine.build_skeleton(context)
                try:
                    items = await self.engine.enrich(umo, context, items, self.p.llm)
                except Exception as exc:
                    logger.debug("[amo] 日程主干文案润色失败，保留骨架: %s" % exc)
            except Exception as exc:
                logger.warning("[amo] 日程主干生成失败，使用兜底: %s" % exc)
                items = None
        if not items:
            profile = getattr(self, "schedule_profile", {}) or {}
            fallback_city = (
                self.p.cfg_str("schedule_city", "").strip()
                or str(profile.get("city") or "").strip()
                or str((weather or {}).get("city") or "").strip()
                or "贵阳"
            )
            context = context or {
                "version": "backbone-v5",
                "day": today,
                "meta": meta,
                "weather": weather,
                "world": world,
                "city": fallback_city,
                "home": self.p.cfg_str("schedule_home", "") or profile.get("home") or "家",
                "workplace": self.p.cfg_str("schedule_workplace", "") or profile.get("workplace") or "公司",
                "car": profile.get("car") or "",
                "mood": dict(self.mood),
                "period": period,
                "health": health,
                "event": {"kind": "none"},
                "scenic": None,
                "profile": profile,
                "location": fallback_city,
                "good_weather": True,
                "yesterday": self.engine.yesterday_summary(today) if self.engine is not None else {},
            }
            items = self._emergency_schedule()
        items = self._hourly_schedule(items)
        self.schedule[today] = items
        if context:
            context["version"] = "backbone-v5"
            context["day"] = today
            self.schedule_ctx[today] = context
            self.db.kv_set("schedule_ctx", self.schedule_ctx)
        self.db.kv_set("schedule_version", SCHEDULE_VERSION)
        self.db.kv_set("schedule", self.schedule)
        self.db.save_schedule(today, items)
        if force:
            try:
                self.db.clear_diaries(today)
            except Exception as _amo_exc:
                _note_swallowed("main.HumanState.ensure_schedule", _amo_exc)
        cutoff = (_now().date() - timedelta(days=14)).isoformat()
        for day in list(self.schedule.keys()):
            if day < cutoff:
                self.schedule.pop(day, None)
                self.schedule_ctx.pop(day, None)
        self.db.kv_set("schedule_ctx", self.schedule_ctx)
        logger.info("[amo] 生成日程主干 %s：%s" % (
            today, (context or {}).get("event", {}).get("kind", "none"),
        ))
        try:
            travel = self.db.kv_get("travel", {}) or {}
            if isinstance(travel, dict) and str(travel.get("city") or "").strip():
                city = str(travel["city"])
                start_day = str(travel.get("start_day") or "")
                today = today_str()
                if start_day and today < start_day:
                    pass
                elif today == start_day and travel.get("phase") == "journey":
                    try:
                        start_hour = int(travel.get("start_hour") or 9)
                    except (TypeError, ValueError):
                        start_hour = 9
                    rows = [x for x in (travel.get("spots") or []) if isinstance(x, dict)]
                    self.apply_follow_start(city, start_hour, rows, keep_past=False)
                    self.db.kv_set("his_city", city)
                    if travel.get("id"):
                        try:
                            await self.p._switch_weather_city({
                                "id": str(travel["id"]), "name": city,
                            })
                        except Exception as exc:
                            logger.debug("[amo] 跟随天气切换失败: %s" % exc)
                    travel["phase"] = "touring"
                    self.db.kv_set("travel", travel)
                else:
                    self.apply_travel_overlay(city)
                    self._log_follow_day(city, today)
        except Exception as exc:
            logger.debug("[amo] 出行日程覆盖失败: %s" % exc)
        try:
            trip = self.db.kv_get("wander_trip", {}) or {}
            if isinstance(trip, dict) and trip.get("city"):
                city = str(trip["city"])
                start_day = str(trip.get("day") or "")
                ret_day = str(trip.get("return_day") or start_day)
                today = today_str()
                if start_day and today < start_day:
                    pass
                elif today == start_day:
                    self.apply_travel_overlay(city)
                    trip["phase"] = "applied"
                    self.db.kv_set("wander_trip", trip)
                    self._log_solo_day(city, today)
                    if trip.get("id"):
                        try:
                            await self.p._switch_weather_city({
                                "id": str(trip["id"]), "name": city,
                            })
                        except Exception as exc:
                            logger.debug("[amo] 旅游天气切换失败: %s" % exc)
                elif start_day < today < ret_day:
                    self.apply_travel_overlay(city)
                    self._log_solo_day(city, today)
                elif today == ret_day:
                    until = int(trip.get("return_hour") or 12)
                    self.apply_return_overlay(city, until)
                    self._log_solo_day(city, today)
                    if _now().hour >= until:
                        his = str(self.db.kv_get("his_city", "") or "").strip() or _CITY_DEFAULT
                        hit = self.p._city_lookup(his)
                        if hit:
                            try:
                                await self.p._switch_weather_city(hit)
                            except Exception as _amo_exc:
                                _note_swallowed("main.HumanState.ensure_schedule", _amo_exc)
                elif today > ret_day:
                    self.db.kv_set("wander_trip", {})
                    his = str(self.db.kv_get("his_city", "") or "").strip() or _CITY_DEFAULT
                    hit = self.p._city_lookup(his)
                    if hit:
                        try:
                            await self.p._switch_weather_city(hit)
                        except Exception as _amo_exc:
                            _note_swallowed("main.HumanState.ensure_schedule", _amo_exc)
                    self.apply_travel_overlay(his)
                    try:
                        rows = self.db.list_profiles(limit=1) or []
                        uid = str((rows[0] or {}).get("uid") or "") if rows else ""
                        if uid:
                            self.p._external_memory_write(
                                uid, "她 %s 从 %s 旅游回来了" % (today, city), "event", 1,
                            )
                    except Exception as exc:
                        logger.debug("[amo] 回来记忆失败: %s" % exc)
        except Exception as exc:
            logger.debug("[amo] 旅游行程推进失败: %s" % exc)
        return items

    def _log_solo_day(self, city, day):
        """旅游每天记一条（日记用）；同一天只记一次。"""
        try:
            log = self.db.kv_get("travel_log", []) or []
            if not isinstance(log, list):
                log = []
            if any(
                isinstance(x, dict) and x.get("day") == day and x.get("solo") and not x.get("back")
                for x in log
            ):
                return
            log.append({"day": day, "hour": "09:00", "city": city, "solo": True})
            self.db.kv_set("travel_log", log[-10:])
        except Exception as _amo_exc:
            _note_swallowed("main.HumanState._log_solo_day", _amo_exc)

    def apply_follow_start(self, city, start_hour=9, spots=None, keep_past=True):
        """跟去他那边的出发日：起床 → 出门坐车约 2 小时 → 到达 → 旅游。"""
        name = str(city or "").strip()
        if not name:
            return False
        if not self.p.cfg_bool("city_travel_schedule", True):
            return False
        today = today_str()
        try:
            start = max(0, min(21, int(start_hour or 9)))
        except (TypeError, ValueError):
            start = 9
        existing = self.schedule.get(today) or self.db.get_schedule(today) or []
        keep = []
        if keep_past:
            for item in existing:
                try:
                    hour = int(str(item.get("start") or "0")[:2])
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanState.apply_follow_start", _amo_exc)
                    hour = 0
                if hour < start:
                    keep.append(item)
        items = _city_travel_to_events(
            name, start, spots=spots, weekday=_now().date().weekday() < 5, seed=today,
        )
        if keep_past:
            items = [x for x in items if int(str(x.get("start") or "0")[:2]) >= start]
        merged = keep + items
        if not merged:
            return False
        self.schedule[today] = merged
        self.db.save_schedule(today, merged)
        self.db.kv_set("schedule", self.schedule)
        try:
            ctx = dict(self.schedule_ctx.get(today) or {})
            if ctx:
                ctx["city"] = name
                ctx["location"] = name
                ctx["home"] = "他桌面上"
                ctx["workplace"] = "（在去" + name + "的路上）"
                self.schedule_ctx[today] = ctx
                self.db.kv_set("schedule_ctx", self.schedule_ctx)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanState.apply_follow_start", _amo_exc)
        try:
            if keep_past:
                self.db.clear_diaries_from(today, "%02d:00" % start)
            else:
                self.db.clear_diaries(today)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanState.apply_follow_start", _amo_exc)
        logger.info("[amo] 出发日日程：%s 点坐车去 %s" % (start, name))
        return True

    def _log_follow_day(self, city, day):
        """跟他旅游的每一天记一条（日记用）；同一天只记一次。"""
        try:
            log = self.db.kv_get("travel_log", []) or []
            if not isinstance(log, list):
                log = []
            if any(
                isinstance(x, dict) and x.get("day") == day and x.get("city") == city
                and not x.get("solo") and not x.get("back") and not x.get("journey")
                for x in log
            ):
                return
            log.append({"day": day, "hour": "09:00", "city": city})
            self.db.kv_set("travel_log", log[-10:])
        except Exception as _amo_exc:
            _note_swallowed("main.HumanState._log_follow_day", _amo_exc)

    def apply_return_overlay(self, city, until_hour=12):
        """旅游最后一天：0 点到 until_hour 在旅游城市，之后回家。"""
        name = str(city or "").strip()
        if not name:
            return False
        try:
            until = max(0, min(23, int(until_hour or 12)))
        except (TypeError, ValueError):
            until = 12
        today = today_str()
        spots = []
        try:
            spots = _city_pick_spots(self.p.scenic_spots(), name, today)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanState.apply_return_overlay", _amo_exc)
            spots = []
        his = str(self.db.kv_get("his_city", "") or "").strip() or _CITY_DEFAULT
        items = _city_travel_events(name, 0, spots=spots, until_hour=until)
        items += _city_travel_events(his, until, home=True)
        if not items:
            return False
        self.schedule[today] = items
        self.db.save_schedule(today, items)
        self.db.kv_set("schedule", self.schedule)
        try:
            self.db.clear_diaries(today)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanState.apply_return_overlay", _amo_exc)
        logger.info("[amo] 旅游最后一天：%s 点前在 %s，之后回家" % (until, name))
        return True

    def apply_travel_overlay(self, city=None):
        """出行覆盖层：把今天剩下的日程换成「跟他一起在 X」（已过去的时段不动）。

        只在换城时调用；写库 + 清掉今天剩余时段的小日记，让它们按新日程重算。
        """
        travel = self.db.kv_get("travel", {}) or {}
        name = str(city or (travel.get("city") if isinstance(travel, dict) else "") or "").strip()
        if not name:
            return False
        if not self.p.cfg_bool("city_travel_schedule", True):
            return False
        today = today_str()
        from_hour = _now().hour
        home = name == _CITY_DEFAULT
        existing = self.schedule.get(today) or self.db.get_schedule(today) or []
        if not existing:
            from_hour = 0
        if home and from_hour >= 22:
            logger.info("[amo] 超过 22 点才回去，今晚住酒店，今天日程不再改")
            return False
        keep = []
        for item in existing:
            try:
                hour = int(str(item.get("start") or "0")[:2])
            except Exception as _amo_exc:
                _note_swallowed("main.HumanState.apply_travel_overlay", _amo_exc)
                hour = 0
            if hour < from_hour:
                keep.append(item)
        spots = []
        if not home:
            try:
                spots = _city_pick_spots(self.p.scenic_spots(), name, today)
            except Exception as exc:
                logger.debug("[amo] 出行景点挑选失败: %s" % exc)
        merged = keep + _city_travel_events(
            name, from_hour, home=home, weekday=_now().date().weekday() < 5, spots=spots,
        )
        if not merged:
            return False
        self.schedule[today] = merged
        self.db.save_schedule(today, merged)
        self.db.kv_set("schedule", self.schedule)
        try:
            ctx = dict(self.schedule_ctx.get(today) or {})
            if ctx:
                ctx["city"] = name
                ctx["location"] = name
                if home:
                    ctx["home"] = "他桌面上"
                    ctx["workplace"] = str((self.schedule_profile or {}).get("workplace") or "")
                    ctx.pop("scenic", None)
                else:
                    ctx["home"] = name + "·酒店房间"
                    ctx["workplace"] = "（旅游中，不上班）"
                    if spots:
                        ctx["scenic"] = spots[0]
                self.schedule_ctx[today] = ctx
                self.db.kv_set("schedule_ctx", self.schedule_ctx)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanState.apply_travel_overlay", _amo_exc)
        try:
            self.db.clear_diaries_from(today, "%02d:00" % from_hour)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanState.apply_travel_overlay", _amo_exc)
        logger.info("[amo] 出行日程已写入：%s 起在 %s%s" % (
            "%02d:00" % from_hour, name, "（回家）" if home else "",
        ))
        return True

    def schedule_context(self, day=None):
        day = str(day or today_str())
        context = self.schedule_ctx.get(day) or {}
        if isinstance(context, dict):
            return context
        return {}

    def _minimal_context(self, day):
        try:
            meta = day_meta(day)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanState._minimal_context", _amo_exc)
            meta = day_meta()
        profile = getattr(self, "schedule_profile", {}) or {}
        city = (
            self.p.cfg_str("schedule_city", "").strip()
            or str(profile.get("city") or "").strip()
            or str((self.weather or {}).get("city") or "").strip()
            or "贵阳"
        )
        return {
            "version": "backbone-v5",
            "day": day,
            "meta": meta,
            "weather": self.weather or {},
            "world": self.worldview or {},
            "city": city,
            "home": self.p.cfg_str("schedule_home", "") or profile.get("home") or "家",
            "workplace": self.p.cfg_str("schedule_workplace", "") or profile.get("workplace") or "公司",
            "car": profile.get("car") or "",
            "mood": dict(self.mood),
            "period": self.period_info(),
            "health": self.health_info(),
            "event": {"kind": "none"},
            "scenic": None,
            "profile": profile,
            "location": city,
            "good_weather": True,
            "yesterday": self.engine.yesterday_summary(day) if self.engine is not None else {},
        }

    async def expand_hour(self, day, item, items=None, force=False):
        """点击二级卡片时，实时生成这一小时的第一人称小日记。"""
        day = str(day or today_str())
        item = dict(item or {})
        items = items or self._hourly_schedule(self.schedule.get(day) or [])
        start = item.get("start") or ""
        if not start:
            return {"diary": "", "mood": "平静", "place": "", "activity": ""}
        if not force:
            cached = self.db.get_diary(day, start)
            if cached:
                return {
                    "diary": cached,
                    "mood": item.get("mood") or "平静",
                    "place": item.get("place") or "",
                    "activity": item.get("activity") or "",
                    "cached": True,
                }
        context = self.schedule_context(day)
        if not context:
            context = self._minimal_context(day)
        else:
            context = dict(context)
            context["mood"] = dict(self.mood)
            context["health"] = self.health_info()
            context["period"] = self.period_info()
            if self.weather:
                context["weather"] = self.weather
        index = 0
        for position, entry in enumerate(items):
            if entry.get("start") == start:
                index = position
                break
        prev_item = items[index - 1] if index > 0 else None
        next_item = items[index + 1] if index + 1 < len(items) else None
        prev_diary = ""
        if prev_item is not None:
            try:
                prev_diary = self.db.get_diary(day, str(prev_item.get("start") or ""))
            except Exception as _amo_exc:
                _note_swallowed("main.HumanState.expand_hour", _amo_exc)
                prev_diary = ""
        result = {"diary": "", "mood": item.get("mood") or "平静",
                  "place": item.get("place") or "", "activity": item.get("activity") or ""}
        if self.engine is not None:
            try:
                result.update(await self.engine.generate_diary(
                    self.p._last_umo, context, item, prev_item, next_item, self.p.llm,
                    prev_diary=prev_diary,
                ))
            except Exception as exc:
                logger.warning("[amo] 动态日记生成失败: %s" % exc)
        if not result.get("diary") and self.engine is not None:
            result["diary"] = self.engine.fallback_diary(context, item, prev_item)
        if not result.get("diary"):
            result["diary"] = "这小时我在%s，%s，心情%s。" % (
                item.get("place") or "家", item.get("activity") or "待着",
                item.get("mood") or "平静",
            )
        self.db.save_diary(day, start, result["diary"])
        return result

    def apply_schedule_events(self):
        """当前小时的日程事件只触发一次，避免每轮都扣心情。"""
        item = self.current_activity()
        effects = item.get("effects") if isinstance(item.get("effects"), dict) else {}
        ctx = self.schedule_context(today_str())
        key = "schedule_event_%s_%s_%s" % (
            today_str(), item.get("start", ""), ctx.get("seed", ""),
        )
        if self.db.kv_get(key, False):
            return
        applied = False
        clean = {}
        for mood_key, delta in effects.items():
            if mood_key in MOOD_KEYS:
                try:
                    clean[mood_key] = float(delta)
                    applied = True
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanState.apply_schedule_events", _amo_exc)
                    continue
        if not applied:
            # 日常活动也要影响真实心情：上班会累、逛街会开心、睡觉回血。
            # CATEGORY_MOOD 是日程内部用的「每小时」增量，真实心情每轮都会向基准
            # 回落，所以乘一个增益（schedule_mood_gain，默认 3）才看得出来。
            try:
                gain = max(0.0, self.p.cfg_float("schedule_mood_gain", 3.0))
            except Exception as _amo_exc:
                _note_swallowed("main.HumanState.apply_schedule_events", _amo_exc)
                gain = 3.0
            category = str(item.get("category") or "")
            for mood_key, delta in (schedule_category_mood().get(category) or {}).items():
                if mood_key not in MOOD_KEYS:
                    continue
                try:
                    clean[mood_key] = float(delta) * gain
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanState.apply_schedule_events", _amo_exc)
                    continue
            applied = bool(clean)
        if clean:
            self.nudge(**clean)
        # 兼容旧版日程里用 detail 标记的事件链。
        detail = str(item.get("detail") or "")
        if not applied and detail:
            legacy = {
                "熬夜": {"疲惫": 7, "暴躁": 3, "开心": -3},
                "精神恍惚": {"疲惫": 5, "焦虑": 5},
                "老板": {"生气": 8, "委屈": 8, "郁闷": 6, "暴躁": 4},
                "扣工资": {"郁闷": 8, "生气": 6},
                "同事闹脾气": {"生气": 5, "委屈": 3},
                "同事聊天": {"开心": 3, "平静": 2},
            }
            for word, deltas in legacy.items():
                if word in detail:
                    self.nudge(**deltas)
                    applied = True
                    break
        self.db.kv_set(key, True)

    def current_activity(self):
        items = self.schedule.get(today_str()) or []
        current = minutes_now()
        for item in items:
            if in_minute_range(current, parse_hhmm(item.get("start")), parse_hhmm(item.get("end"))):
                return dict(item)
        hour = _now().hour
        if hour < 6:
            return {"start": "00:00", "end": "06:00", "activity": "睡觉", "place": "家", "category": "sleep"}
        if hour < 9:
            return {"start": "07:00", "end": "09:00", "activity": "起床收拾", "place": "家", "category": "life"}
        if hour < 12:
            return {"start": "09:00", "end": "12:00", "activity": "上班", "place": "公司", "category": "work"}
        if hour < 14:
            return {"start": "12:00", "end": "14:00", "activity": "吃午饭", "place": "公司附近", "category": "meal"}
        if hour < 18:
            return {"start": "14:00", "end": "18:00", "activity": "上班", "place": "公司", "category": "work"}
        if hour < 20:
            return {"start": "18:00", "end": "20:00", "activity": "吃晚饭", "place": "家", "category": "meal"}
        if hour < 23:
            return {"start": "20:00", "end": "23:00", "activity": "休息", "place": "家", "category": "rest"}
        return {"start": "23:00", "end": "24:00", "activity": "准备睡觉", "place": "家", "category": "sleep"}

    @staticmethod
    def busy_level(activity):
        category = (activity or {}).get("category", "rest")
        if category == "sleep":
            return 1.0
        if category in ("work", "study"):
            return 0.75
        if category == "commute":
            return 0.6
        if category == "meal":
            return 0.3
        return 0.1

    # ---------- 汇总 ----------
    def snapshot(self):
        period = self.period_info()
        health = self.health_info()
        activity = self.current_activity()
        weather = self.weather or {}
        return {
            "date": today_str(),
            "weekday": weekday_cn(),
            "time": _now().strftime("%H:%M"),
            "datetime_text": "%s 星期%s %s" % (today_str(), weekday_cn(), _now().strftime("%H:%M")),
            "mood": {key: round(value, 1) for key, value in self.mood.items()},
            "dominant": self.dominant_mood(),
            "mood_score": self.mood_score(),
            "period": period,
            "health": health,
            "weather": weather,
            "weather_text": self.weather_text(),
            "activity": activity,
            "busy": self.busy_level(activity),
            "schedule": self.schedule.get(today_str()) or [],
        }

    def prompt_text(self, snap=None, with_activity=False):
        snap = snap or self.snapshot()
        activity = snap["activity"]
        lines = [
            "现在是 %s。" % snap["datetime_text"],
            "心情：%s" % self.mood_text(),
            "生理期：%s第%d天，%s。" % (
                snap["period"]["phase"], snap["period"]["day"], snap["period"]["tone"]
            ),
            "身体：%s%s。" % (
                snap["health"]["status"],
                ("（" + snap["health"]["note"] + "）") if snap["health"].get("note") else "",
            ),
            "天气：%s。" % snap["weather_text"],
        ]
        if with_activity:
            # 只有被问到「你在干嘛/在哪」时才给活动，避免她张口就报行程
            lines.append(
                "（内在状态，仅供自洽，不是话题）你此刻在%s（%s）。"
                % (activity.get("activity", "休息"), activity.get("place", "家"))
            )
        return "\n".join(lines)

    def tone_text(self, snap=None, relation="普通"):
        snap = snap or self.snapshot()
        mood = snap["mood"]
        if relation == "相恋" and (mood["暴躁"] >= 60 or mood["生气"] >= 62):
            tone = (
                "你在生对方的气，但你是他的恋人：会抱怨、闹别扭、说反话、要哄，"
                "语气带一点委屈，不会像对普通人那样冷怼、赶人或人身攻击；可以嘴硬，但不要真的伤人。"
            )
        elif mood["暴躁"] >= 60:
            tone = "你现在很暴躁，说话冲、短、带刺，一点就着，但不要真正辱骂。"
        elif mood["生气"] >= 62:
            tone = "你现在很烦躁，说话冲、短、带刺，容易不耐烦，但不要辱骂。"
        elif mood["委屈"] >= 60:
            tone = "你现在很委屈，语气软软的，会撒娇，想被哄。"
        elif mood["开心"] >= 65 or mood["兴奋"] >= 65:
            tone = "你现在心情很好，语气轻快，会用语气词和感叹号。"
        elif mood["郁闷"] >= 60:
            tone = "你现在有点低落，说话安静、句子短。"
        elif mood["疲惫"] >= 65:
            tone = "你很累，句子短一点、不展开；但别拿累当理由赶人、结束话题。"
        elif mood["焦虑"] >= 60:
            tone = "你有点焦虑，句子急，容易追问。"
        elif mood["依恋"] >= 65:
            tone = "你现在很黏人，想和对方多聊几句。"
        else:
            tone = "你语气自然平静，像平常聊天。"
        if snap["health"]["sick"]:
            tone += " 你身体不舒服，语气会比平时弱一点。"
        if snap["period"]["phase"] in ("月经期", "黄体期"):
            tone += " 生理期让你更容易累和敏感。"
        if relation == "相恋":
            tone += " 你和对方是恋人，可以亲昵、撒娇、用昵称。"
        elif relation == "仇恨":
            tone += " 你很讨厌对方，语气冷淡、疏远。"
        elif relation == "抵触":
            tone += " 你对对方有点防备，保持距离。"
        return tone

    def interesting_event(self):
        events = [
            "楼下咖啡店今天买一送一",
            "路上遇到一只很胖的橘猫",
            "同事带了自己烤的小饼干",
            "窗外的云像一只兔子",
            "刷到一个特别好笑的表情包",
            "便利店新出了草莓味的冰淇淋",
        ]
        if (self.weather or {}).get("tag") == "rain":
            events.append("下班的时候突然下雨，躲在便利店屋檐下")
        index = md5_int(today_str() + str(_now().hour)) % len(events)
        return events[index]

    def daily_tick(self):
        self.last_daily = today_str()
        period = self.period_info()
        if period["phase"] == "月经期":
            self.nudge(疲惫=8, 委屈=6, 开心=-4)
        elif period["phase"] == "黄体期":
            self.nudge(郁闷=5, 焦虑=4)
        elif period["phase"] == "排卵期":
            self.nudge(开心=5, 兴奋=4)
        else:
            self.nudge(开心=3)
        self.save()


# ---------------------------------------------------------------------------
# LLM：人格、对话、润色、世界观、日程、判断
# ---------------------------------------------------------------------------


class LLMService:
    def __init__(self, plugin):
        self.p = plugin
        self.context = plugin.context
        self._persona_cache = {}

    async def persona(self, umo=""):
        key = umo or "default"
        cached = self._persona_cache.get(key)
        if cached and now_ts() - cached[0] < 300:
            return cached[1]
        prompt = ""
        manager = getattr(self.context, "persona_manager", None)
        if manager is not None:
            try:
                persona = await manager.get_default_persona_v3(umo or None)
                if isinstance(persona, dict):
                    prompt = persona.get("prompt") or ""
                else:
                    prompt = getattr(persona, "prompt", "") or ""
            except Exception as exc:
                logger.debug("[amo] 读取 AstrBot 人格失败: %s" % exc)
        if not prompt:
            try:
                cfg = self.context.get_config(umo or None)
                personas = cfg.get("persona", []) if cfg else []
                if isinstance(personas, list) and personas:
                    prompt = personas[0].get("prompt", "") or ""
            except Exception as _amo_exc:
                _note_swallowed("main.LLMService.persona", _amo_exc)
        if not prompt:
            prompt = "你是一个生活在中国城市的普通女孩，有工作、有情绪、有自己的生活，说话自然口语化。"
        extra = self.p.cfg_str("persona_extra", "")
        if extra:
            prompt += "\n" + extra
        try:
            name = await self.p._persona_name_for(umo)
            if name and name not in prompt[:240]:
                prompt = "你的名字是" + name + "。\n" + prompt
        except Exception as _amo_exc:
            _note_swallowed("main.LLMService.persona", _amo_exc)
        self._persona_cache[key] = (now_ts(), prompt)
        return prompt

    async def provider(self, umo=""):
        try:
            if hasattr(self.context, "get_using_provider_async"):
                return await self.context.get_using_provider_async(umo or None)
            return self.context.get_using_provider(umo or None)
        except Exception as exc:
            logger.warning("[amo] 获取对话模型失败: %s" % exc)
            return None

    async def chat_raw(self, umo, system, prompt, contexts=None):
        provider = await self.provider(umo)
        if provider is None:
            return ""
        try:
            response = await provider.text_chat(
                prompt=prompt,
                system_prompt=system,
                contexts=contexts or [],
            )
        except Exception as exc:
            logger.error("[amo] LLM 调用失败: %s" % exc)
            return ""
        return str(getattr(response, "completion_text", "") or "").strip()

    async def chat(self, umo, system, prompt, contexts=None, limit=300):
        return clean_reply(await self.chat_raw(umo, system, prompt, contexts), limit)

    async def polish(self, umo, text, tone, state_text="", relation="", name="", persona="", style="", consult=False):
        text = (text or "").strip()
        if not text or not self.p.cfg_bool("enable_polish", True):
            return text
        system = (
            "你就是这个角色本人，不是AI助手，也不是在润色一段AI台词。"
            "保持第一人称和原意，只输出角色会说的话。"
        )
        prompt = (
            "角色人格：\n" + (persona or "（未提供）")[:1000] + "\n"
            "角色当前语气：" + tone + "\n"
            "风格：" + (style or "自然") + "\n"
            "角色此刻不可矛盾的状态：\n" + (state_text or "（无）") + "\n"
            "对话对象：" + (name or "对方") + "；关系：" + (relation or "普通") + "\n"
            "原句：" + text + "\n"
            "请把这句话改成真人在聊天：口语化、有一点情绪，长度接近原句，通常不要超过原句的 1.3 倍。\n"
            "必须遵守：\n"
            "0. 保持角色人格：就是人格设定里的那个人，不是客服/通用助手；\n"
            "0. 只改语气和口语表达，不要新增原句没有的地点、行程、动作；如果原句与状态矛盾，以状态为准，不要继续编；\n"
            "1. 绝对不要承认自己是AI、人工智能、机器人、人机、程序或模型；\n"
            "2. 如果原句在承认或顺着“人机/机器人”说，要改成真人的反驳、无语或有点生气；\n"
            "3. 不要提润色、提示词、模型、系统、插件、API；被问“你接的什么模型/用的什么AI”时，\n"
            "   回一句像真人的打岔（“什么模型呀”“我就是我啊”），绝对不要报出任何模型名或厂商；\n"
            "4. 保持原句情绪强度和态度。如果原句在生气/烦躁/怼人，绝对不要改成甜蜜、撒娇、讨好，最多缓和一点；\n"
            "5. 不要一秒变脸，情绪要有惯性；\n"
            "6. 默认 1-2 句，能一句说清就一句；咨询/步骤最多 3 句，先给结论，不要列点、不要总结；\n"
            "7. 不要扩写，不要新增原句没有的信息。"
            + ("\n8. 这是咨询/步骤类：用角色口吻简短回答，不要客服腔。" if consult else "")
        )
        result = await self.chat(umo, system, prompt, limit=self.p.cfg_int("max_reply_chars", 220))
        if not result:
            return text
        if looks_like_ai_admission(result):
            retry_prompt = (
                "角色当前语气：" + tone + "\n"
                "原句：" + text + "\n"
                "原句/改写里出现了承认自己是人机或机器人的说法，这是不允许的。\n"
                "请改成真人被质疑时的自然反应：反驳、无语、有点生气或开个玩笑，"
                "绝对不要出现“我是AI/机器人/人机/程序/模型”“人机也有用”这类自曝。\n"
                "只输出一句角色会说的话。"
            )
            retry = await self.chat(umo, system, retry_prompt, limit=self.p.cfg_int("max_reply_chars", 220))
            if retry and not looks_like_ai_admission(retry):
                result = retry
            else:
                result = "你才人机呢，你见过这么会聊天的机器人吗？"
        if len(result) > max(len(text) + 30, int(len(text) * 1.5)):
            return text
        return result

    async def decide(self, umo, question, state):
        service = getattr(self.context, "decision", None)
        if service is not None:
            try:
                return bool(await service.yes_no(
                    question=question, state=state, threshold=0.5, default=None
                ))
            except Exception as exc:
                logger.debug("[amo] Decision 判断不可用: %s" % exc)
        answer = await self.chat(
            umo, "你是一个判断器，只输出 yes 或 no。",
            question + "\n只输出 yes 或 no。", limit=8,
        )
        if not answer:
            return None
        answer = answer.strip().lower()
        return answer.startswith("y") or answer.startswith("是") or answer.startswith("对")

    async def gen_worldview(self, umo, persona):
        system = "你是一个世界观设定师。只输出 JSON，不要输出其他文字。"
        prompt = (
            "根据下面的人格设定，为这个角色生成一个真实可信的现代生活世界观。\n"
            "人格设定：\n" + truncate(persona, 1500) + "\n\n"
            "输出 JSON 对象，字段：name(角色名), age(整数), city(城市), occupation(职业), "
            "workplace(工作或学习地点), personality(性格一句话), hobbies(字符串数组), "
            "daily_life(日常生活一段话), world_rules(这个世界和人设的规则一段话), "
            "summary(50字内总结)。"
        )
        raw = await self.chat_raw(umo, system, prompt)
        data = json_extract(raw)
        if not isinstance(data, dict):
            return None
        hobbies = data.get("hobbies")
        if not isinstance(hobbies, list):
            hobbies = [str(hobbies)] if hobbies else []
        return {
            "name": str(data.get("name") or self.p.bot_name),
            "age": to_int(data.get("age"), 22),
            "city": str(
                data.get("city")
                or self.p.cfg_str("weather_city_name", "")
                or self.p.cfg_str("weather_city", "贵阳")
            ),
            "occupation": str(data.get("occupation") or "普通上班族"),
            "workplace": str(data.get("workplace") or "公司"),
            "personality": str(data.get("personality") or "温柔敏感"),
            "hobbies": [str(item)[:20] for item in hobbies[:5]],
            "daily_life": str(data.get("daily_life") or ""),
            "world_rules": str(data.get("world_rules") or ""),
            "summary": str(data.get("summary") or ""),
        }

    async def gen_proactive(self, umo, profile, snap, kind):
        name = profile.get("alias") or profile.get("name") or "你"
        relation = profile.get("relation", "普通")
        system = (
            await self.persona(umo) + "\n\n"
            + self.p.state.prompt_text(snap, with_activity=True) + "\n"
            + self.p.state.tone_text(snap, relation) + "\n"
            "规则：你就是角色本人，只输出要发出去的消息，不要解释、不要旁白。\n"
            "一致性：不要编造自己的经历；不能和你刚才说过的话矛盾"
            "（刚才说吃过了，现在就不能说去买吃的）。\n"
            "此刻在做什么以上面「你此刻在…」为准：和最近聊天记录里说的不一样，就按此刻说，"
            "自然地改口（「会开完了」「我不在便利店了」），不要沿用旧说法，"
            "也不要编出没发生过的会议/加班/行程。"
        )
        try:
            rows = self.p._recent(umo, 12)
        except Exception as _amo_exc:
            _note_swallowed("main.LLMService.gen_proactive", _amo_exc)
            rows = []
        analysis = _pg_analyze_rows(rows, now=now_ts()) if _pg_analyze_rows else {
            "context_text": "",
            "unanswered_text": "",
            "unanswered_seconds": 0.0,
            "unanswered_at": 0.0,
            "recent_bot_texts": [],
        }
        # 她刚在另一个平台（QQ / 飞书）说过的话也带上：只看本会话的话，
        # 另一边早就改口了，这边还在接上一场开会。
        other_bot = []
        uid = str(profile.get("uid") or "")
        if uid:
            try:
                other_bot = other_platform_bot_lines(
                    await self.p._recent_by_uid(uid, 12, ""), umo,
                    platform=str(umo).split(":", 1)[0],
                )
            except Exception as exc:
                logger.debug("[amo] 取跨平台近聊失败: %s" % exc)
                other_bot = []
        if other_bot:
            analysis["recent_bot_texts"] = list(analysis.get("recent_bot_texts") or []) + list(other_bot)
            system = system + (
                "\n【你刚在别的平台说过】\n"
                + "\n".join("· " + str(item)[:120] for item in other_bot)
                + "\n（这些是你在另一个平台刚说的话，不是他说的，别复述、别重复；"
                "和此刻状态对不上就以此刻为准。）"
            )
        window = max(0, self.p.cfg_int("proactive_unanswered_window_minutes", 30)) * 60
        limit = self.p.cfg_int("max_reply_chars", 220)
        # 记忆只来自外挂记忆插件；主动消息也带上，免得她说得像个陌生人
        memory_text = ""
        try:
            uid = str(profile.get("uid") or "")
            if uid:
                _, memory_text = await self.p._recall(uid, "", None)
        except Exception as _amo_exc:
            _note_swallowed("main.LLMService.gen_proactive", _amo_exc)
            memory_text = ""
        if memory_text:
            system = system + "\n【关于他的记忆】\n" + memory_text
        try:
            relation_network = self.p._relation_network_text(str(profile.get("uid") or ""))
        except Exception as _amo_exc:
            _note_swallowed("main.LLMService.gen_proactive", _amo_exc)
            relation_network = ""
        if relation_network:
            system = system + "\n【关系网】\n" + relation_network
        try:
            trip = self.p.db.kv_get("wander_trip", {}) or {}
            if (
                isinstance(trip, dict) and trip.get("city") and not trip.get("announced")
                and str(trip.get("day") or "") <= today_str() <= str(trip.get("return_day") or "")
            ):
                spots = trip.get("spots") or []
                spot = str(spots[0]) if spots else ""
                system = system + (
                    "\n【旅游中】你现在一个人在 " + str(trip["city"]) + " 旅游"
                    + ("，今天去了" + spot if spot else "")
                    + "。主动跟他分享今天看到的、吃到的、天气；别报公司/上班，也别编景点。"
                )
        except Exception as _amo_exc:
            _note_swallowed("main.LLMService.gen_proactive", _amo_exc)

        def build_task(duplicate_hint=""):
            if not _pg_compose_task:
                return "你突然想起" + name + "，想主动发一条消息。"
            event_text = ""
            if kind == "share":
                try:
                    event_text = self.p.state.interesting_event()
                except Exception as _amo_exc:
                    _note_swallowed("main.LLMService.gen_proactive.build_task", _amo_exc)
                    event_text = ""
            try:
                dialect_enabled = bool(self.p._dialect_active())
            except Exception as _amo_exc:
                _note_swallowed("main.LLMService.gen_proactive.build_task", _amo_exc)
                dialect_enabled = False
            return _pg_compose_task(
                kind=kind,
                name=name,
                unanswered_text=analysis["unanswered_text"],
                unanswered_seconds=analysis["unanswered_seconds"],
                window_seconds=window,
                recent_bot_texts=analysis["recent_bot_texts"],
                interesting_event=event_text,
                duplicate_hint=duplicate_hint,
                dialect_style=self.p.cfg_str("dialect_style", ""),
                dialect_enabled=dialect_enabled,
            )

        def build_prompt(task):
            prompt = "这是私聊。请以角色身份主动发一条消息，" + task + " 1 到 2 句，口语化。"
            if analysis["context_text"]:
                prompt = "最近私聊记录：\n" + analysis["context_text"] + "\n\n" + prompt
            if memory_text:
                prompt = "你记得关于他的事：\n" + memory_text + "\n\n" + prompt
            return prompt

        text = await self.chat(umo, system, build_prompt(build_task()), limit=limit)
        if not _pg_near_duplicate or not self.p.cfg_bool("proactive_dedupe_enabled", True):
            return text
        threshold = self.p.cfg_float("proactive_dedupe_threshold", 0.62)
        hit = _pg_near_duplicate(text, analysis["recent_bot_texts"], threshold)
        if not hit:
            return text
        retry = await self.chat(
            umo, system, build_prompt(build_task(duplicate_hint=hit[0])), limit=limit,
        )
        if retry and not _pg_near_duplicate(retry, analysis["recent_bot_texts"], threshold):
            return retry
        logger.info("[amo] 主动消息和最近的发言重复，跳过本次：%s" % str(text or retry or "")[:60])
        return ""

    async def extract_facts(self, umo, name, lines):
        system = "你是记忆提取器。只输出 JSON 数组，不要输出其他文字。"
        prompt = (
            "请从下面的聊天中提取关于用户“" + name + "”的长期事实。\n"
            "聊天里每一行都带说话人标记：[他] 是用户本人说的，[我] 是角色自己说的。\n"
            "只从 [他] 开头的行里提取；[我] 开头的内容是角色自己的事，不能算成用户的事实。\n"
            "只提取值得长期记住的内容：名字、生日、喜好、厌恶、居住地、工作或学校、"
            "宠物、年龄、重要计划、重要经历。\n"
            "位置类事实统一写成「他现在在X」；只有他明确说了搬/住/定居，才写「他住在X」。\n"
            "content 一律用第三人称「他」开头描述用户：写「他被扇了耳光，脸疼」而不是「我被扇了耳光」；"
            "绝不能用「我」或「你」指代用户，也不要省略主语。\n"
            "输出 JSON 数组，每项包含 content(一句话事实)、kind(name/birthday/preference/place/work/pet/age/event)、"
            "tier(0 普通 / 1 重要 / 2 珍贵)。没有可提取的就输出 []。\n\n"
            "聊天记录：\n" + "\n".join(lines[-20:])
        )
        raw = await self.chat_raw(umo, system, prompt)
        data = json_extract_list(raw)
        if not isinstance(data, list):
            return []
        result = []
        for item in data:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content", "")).strip()
            if len(content) < 2:
                continue
            # 兜底：模型偶尔仍会写成「我脸疼」/「被扇了耳光」这种没有主语或第一人称的句子，
            # 这种记忆注入后会被当成角色自己的经历（就是"幻视"）。这里统一补成第三人称。
            if content.startswith(("我", "你")):
                content = "他" + content[1:]
            elif not content.startswith(("他", "她", "用户", name or "\u0000")):
                content = "他" + content
            result.append({
                "content": content[:80],
                "kind": str(item.get("kind", "fact"))[:20],
                "tier": to_int(item.get("tier"), 1),
            })
        return result[:8]


# ---------------------------------------------------------------------------
# 插话判定
# ---------------------------------------------------------------------------

class ReplyGate:
    def __init__(self, plugin):
        self.p = plugin

    def activity(self, group_id):
        if not group_id:
            return 0.0
        cutoff = now_ts() - 300
        times = [item for item in self.p._group_times.get(group_id, []) if item >= cutoff]
        self.p._group_times[group_id] = times
        return len(times) / 5.0

    def score_group(self, umo, group_id, text, recent, directed, profile, snap):
        rec = [m for m in recent if m.get("role") == "user"][-6:]
        rec_text = " ".join([m.get("content", "") for m in rec])
        relevance = overlap(tokens(text), tokens(rec_text)) * 100.0
        if has_question(text):
            relevance += 12
        if "你" in text or any(alias and alias in text for alias in self.p.bot_aliases):
            relevance += 10
        if directed:
            relevance += 28
        relevance = clamp(relevance)

        mood = snap["mood"]
        willingness = 50.0
        willingness += (mood["开心"] - 50) * 0.30
        willingness += (mood["兴奋"] - 50) * 0.22
        willingness += (mood["平静"] - 50) * 0.10
        willingness -= (mood["疲惫"] - 50) * 0.35
        willingness -= (mood["郁闷"] - 50) * 0.28
        willingness -= (mood["生气"] - 50) * 0.22
        willingness += (mood["依恋"] - 50) * 0.15
        relation = profile.get("relation", "普通")
        willingness += {"相恋": 22, "熟识": 10, "抵触": -30, "仇恨": -55}.get(relation, 0)
        phase = snap["period"]["phase"]
        willingness += {"排卵期": 6, "卵泡期": 3, "黄体期": -6, "月经期": -10}.get(phase, 0)
        if snap["health"]["sick"]:
            willingness -= 15
        hour = _now().hour
        if hour < 6:
            willingness -= 25
        last_reply = self.p._last_reply_at.get(umo, 0)
        if last_reply and now_ts() - last_reply < 25:
            willingness -= 22
        willingness = clamp(willingness)

        social = 72.0
        if len(text) < 2:
            social -= 20
        if re.search(r"https?://|www\.", text):
            social -= 35
        if re.search(r"(加群|代购|广告|优惠|返利|扫码|兼职)", text):
            social -= 45
        senti = sentiment(text)
        if senti["insult"]:
            social -= 40
        blocked = [word.strip() for word in self.p.cfg_str("blocked_words", "").split(",") if word.strip()]
        if any(word in text for word in blocked):
            social -= 50
        if directed:
            social += 10
        if has_question(text):
            social += 5
        social = clamp(social)

        timing = 60.0
        dt = now_ts() - last_reply if last_reply else 99999
        if dt < 15:
            timing -= 40
        elif dt < 45:
            timing -= 20
        elif dt < 120:
            timing -= 5
        elif dt > 300:
            timing += 15
        category = snap["activity"].get("category")
        if category == "sleep":
            timing -= 55
        elif category in ("work", "study"):
            timing -= 18
        rate = self.activity(group_id)
        if 2.0 <= rate <= 12.0:
            timing += 10
        elif rate > 20.0:
            timing -= 12
        if quiet_now(self.p.cfg_str("quiet_hours", "23:30-07:30")):
            timing -= 25
        timing = clamp(timing)

        last_two = [m for m in recent if m.get("role") == "user"][-2:]
        coherence = overlap(
            tokens(text), tokens(" ".join([m.get("content", "") for m in last_two]))
        ) * 100.0
        if directed:
            coherence += 18
        if re.search(r"(这个|那个|刚才|刚刚|上面|你说|你刚才)", text):
            coherence += 10
        if len(text) < 4:
            coherence -= 10
        coherence = clamp(coherence)

        weights = [
            self.p.cfg_float("gate_w_relevance", 0.30),
            self.p.cfg_float("gate_w_willingness", 0.25),
            self.p.cfg_float("gate_w_social", 0.15),
            self.p.cfg_float("gate_w_timing", 0.15),
            self.p.cfg_float("gate_w_coherence", 0.15),
        ]
        total_weight = sum(weights) or 1.0
        total = (
            relevance * weights[0] + willingness * weights[1]
            + social * weights[2] + timing * weights[3] + coherence * weights[4]
        ) / total_weight
        return {
            "relevance": round(relevance, 1),
            "willingness": round(willingness, 1),
            "social": round(social, 1),
            "timing": round(timing, 1),
            "coherence": round(coherence, 1),
            "total": round(clamp(total), 1),
        }

    def dynamic_threshold(self, activity, snap, profile):
        base = self.p.cfg_float("reply_threshold", 0)
        if base <= 0:
            legacy = self.p.cfg_float("base_reply_threshold", 0.55)
            base = legacy * 100 if legacy <= 1 else legacy
        base = clamp(base, 0, 100)

        if activity < 1:
            activity_delta = -8
        elif activity < 4:
            activity_delta = -2
        elif activity < 9:
            activity_delta = 3
        elif activity < 18:
            activity_delta = 8
        else:
            activity_delta = 12

        mood = snap["mood"]
        positive = (mood["开心"] + mood["兴奋"] + mood["平静"] + mood["依恋"]) / 4.0
        negative = (mood["郁闷"] + mood["疲惫"] + mood["生气"] + mood["委屈"] + mood["焦虑"]) / 5.0
        mood_score = clamp(50 + (positive - negative) * 0.8)
        mood_delta = (50 - mood_score) * 0.25

        relation = profile.get("relation", "普通")
        relation_delta = {"相恋": -10, "熟识": -5, "抵触": 16, "仇恨": 36}.get(relation, 0)
        health_delta = 8 if snap["health"]["sick"] else 0
        phase = snap["period"]["phase"]
        period_delta = {"月经期": 6, "黄体期": 4, "排卵期": -3, "卵泡期": -1}.get(phase, 0)
        time_delta = 10 if _now().hour in (23, 0, 1, 2, 3, 4, 5) else 0
        weather_delta = 3 if snap["weather"].get("tag") in ("rain", "storm", "snow") else 0

        value = clamp(
            base + activity_delta + mood_delta + relation_delta
            + health_delta + period_delta + time_delta + weather_delta,
            20, 92,
        )
        return {
            "value": round(value, 1),
            "base": round(base, 1),
            "activity_delta": activity_delta,
            "mood_delta": round(mood_delta, 1),
            "relation_delta": relation_delta,
            "health_delta": health_delta,
            "period_delta": period_delta,
            "time_delta": time_delta,
            "weather_delta": weather_delta,
        }

    async def should_reply_group(self, umo, group_id, text, recent, directed, profile, snap):
        scores = self.score_group(umo, group_id, text, recent, directed, profile, snap)
        activity = self.activity(group_id)
        threshold = self.dynamic_threshold(activity, snap, profile)
        diff = scores["total"] - threshold["value"]

        if diff >= 0:
            probability = 0.92
        elif diff > -8:
            probability = 0.55 + diff * 0.045
        elif diff > -20:
            probability = 0.18 + (diff + 20) * 0.046
        else:
            probability = 0.03
        probability = clamp(probability, 0.01, 0.98)
        reply = random.random() < probability

        bot_recent = [m for m in recent[-5:] if m.get("role") == "bot"]
        if not directed and len(bot_recent) >= 2 and diff < 20:
            reply = False

        used_llm = False
        band = self.p.cfg_float("llm_gate_band", 10)
        if self.p.cfg_bool("enable_llm_gate", True) and abs(diff) <= band:
            question = (
                "群聊里刚刚有人说『" + truncate(text, 80) + "』。"
                "角色现在的心情是" + snap["dominant"] + "，正在" + snap["activity"].get("activity", "休息") + "，"
                "和说话人的关系是" + profile.get("relation", "普通") + "。"
                "角色应该自然地插话回复吗？"
            )
            verdict = await self.p.llm.decide(
                umo, question,
                {
                    "recent": [m.get("content", "") for m in recent[-6:]],
                    "mood": snap["mood"],
                    "activity": snap["activity"],
                },
            )
            used_llm = True
            if verdict is not None:
                reply = verdict

        return {
            "reply": reply,
            "probability": round(probability, 2),
            "diff": round(diff, 1),
            "scores": scores,
            "threshold": threshold,
            "activity": round(activity, 2),
            "used_llm": used_llm,
            "directed": directed,
        }

    def private_probability(self, snap, profile):
        probability = 0.95
        category = snap["activity"].get("category")
        probability *= {
            "sleep": 0.02, "work": 0.42, "study": 0.50,
            "commute": 0.60, "meal": 0.85,
        }.get(category, 1.0)
        probability *= {
            "感冒": 0.55, "低烧": 0.35, "轻微不适": 0.70, "疲惫": 0.70,
        }.get(snap["health"]["status"], 1.0)
        probability *= {
            "月经期": 0.80, "黄体期": 0.90, "排卵期": 1.05,
        }.get(snap["period"]["phase"], 1.0)
        mood = snap["mood"]
        if mood["生气"] > 60:
            probability *= 0.70
        if mood["郁闷"] > 60:
            probability *= 0.80
        if mood["开心"] > 65:
            probability *= 1.05
        try:
            if profile.get("uid") and self.p._depressed_active(str(profile.get("uid"))):
                probability *= 0.35
        except Exception as _amo_exc:
            _note_swallowed("main.ReplyGate.private_probability", _amo_exc)
        relation = profile.get("relation", "普通")
        if relation == "相恋":
            probability = max(probability, 0.90)
        elif relation == "仇恨":
            probability *= 0.20
        elif relation == "抵触":
            probability *= 0.45
        return clamp(probability, 0.0, 1.0)


# ---------------------------------------------------------------------------
# 插件主体
# ---------------------------------------------------------------------------

# 面板写操作路由：只注册 POST + 套 _web_guard。
# 以前守卫按「methods 里有没有 GET」判断，而写接口全被注册成 GET+POST，于是守卫一次都没执行过。
WRITE_ROUTES = frozenset({
    "/config/save", "/config_save",
    "/profile/save", "/profile_save",
    "/profile/delete", "/profile_delete",
    "/relation/save", "/relation_save",
    "/relation/delete", "/relation_delete",
    "/memory/add", "/memory_add",
    "/memory/delete", "/memory_delete",
    "/mood/update", "/mood_update",
    "/schedule/regen", "/schedule_regen",
    "/kb/regen", "/kb_regen",
    "/scenic_kb/regen", "/scenic_kb_regen",
    "/worldview/regen", "/worldview_regen",
    "/say",
    "/city/set",
    "/diary/write", "/diary/import", "/diary/open",
    "/refresh_status",
})


class HumanCorePlugin(ApiMixin, ScheduleMixin, ProactiveMixin, LlmMixin, Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self._migrate_legacy_config()
        self.bot_name = self.cfg_str("bot_name", "") or "陪伴"
        # 时区：服务器常在 UTC 跑，必须按用户时区算（否则北京时间早上 10 点会被当成凌晨 2 点）
        try:
            self.timezone_name = _clock_configure(self.cfg_str("timezone", "Asia/Shanghai"))
            logger.info("[amo] 时区: %s（系统: %s）" % (self.timezone_name, _clock_name()))
        except Exception as exc:
            self.timezone_name = ""
            logger.warning("[amo] 时区初始化失败: %s" % exc)
        self.persona_name = ""
        self._persona_name_cache = {}
        self._last_affect = {}
        self._disturb_until = {}
        self._disturb_last = {}
        self._last_pending_check = 0.0
        self._last_proactive_activity = {}
        self._last_bot_saved = {}
        # 近聊上下文缓冲（只在内存里；本地聊天可以不落库，用记忆终端补）
        self._ctx_buffer = {}
        self._ctx_hydrated = set()
        self._attribution_alert = {}
        self._last_schedule_save = ""
        self._disturb_cooldown = {}
        self._disturb_reset_at = {}
        self.bot_aliases = [item.strip() for item in self.cfg_str("bot_aliases", "").split(",") if item.strip()]
        self.admin_uids = set()
        for item in self.cfg_str("admin_uids", "").split(","):
            if item.strip():
                self.admin_uids.add(item.strip())
        self.db = AmoDB(self.plugin_dir)
        self.state = None
        self.llm = LLMService(self)
        self.gate = ReplyGate(self)
        self.gift = None
        if GiftEngine is not None:
            try:
                self.gift = GiftEngine(self)
            except Exception as exc:
                logger.warning("[amo] 礼物引擎初始化失败: %s" % exc)
        self.heartflow = None
        self.segment_engine = None
        try:
            if HeartflowEngine is not None:
                hf_config = self._hf_config()
                hf_config.setdefault("enable_heartflow", True)
                hf_config.setdefault("enable_dynamic_threshold", True)
                hf_config.setdefault("judge_provider_name", "")
                self.heartflow = HeartflowEngine(self.context, hf_config)
                self.heartflow.set_identity(self.bot_name, self.bot_aliases)
            if SegmentEngine is not None:
                seg_config = self._seg_config()
                seg_config.setdefault("protect_paired_symbols", True)
                self.segment_engine = SegmentEngine(self.context, seg_config, plugin=self)
        except Exception as exc:
            logger.error("[amo] 心流/分段引擎初始化失败: %s" % exc)
        # 飞书适配器默认把每条回复都发成「引用回复」；私聊不该引用（群聊按概率）
        try:
            self._install_lark_quote_guard()
        except Exception as exc:
            logger.debug("[amo] 飞书引用守卫安装失败: %s" % exc)
        try:
            self._install_qq_quote_guard()
        except Exception as exc:
            logger.debug("[amo] QQ 引用守卫安装失败: %s" % exc)
        self._ready = False
        self._init_lock = asyncio.Lock()
        self._running = True
        self._tasks = set()
        # 数据插件（Astr_Amo_data）可能比 amo 后加载：用这几个标记做一次性补同步，不轮询
        self._data_synced = False
        self._data_sync_lock = asyncio.Lock()
        self._last_data_sync_try = 0.0
        self._data_found_logged = False
        self._data_missing_logged = False
        self._data_warn_scheduled = False
        self._group_times = {}
        self._private_buffers = {}
        self._last_reply_at = {}
        self._last_umo = ""
        self._last_group = ""
        self._last_purge = 0.0
        self._last_auto_learn = 0.0
        self._proactive_last = 0.0
        self._last_ritual = 0.0
        self._last_relation_decay = 0.0
        self._last_relation_sediment = 0.0
        self._bot_initiated = {}
        self._prefix_cache = None
        self._loop_task = None
        self._config_mtime = 0.0
        self._register_web_apis()
        logger.info("[amo] 我想永远陪伴你 %s loaded; stale web routes purged" % PLUGIN_VERSION)
        self._boot_task = self._spawn(self._ensure_ready())

    # ---------- 配置 ----------
    def cfg(self, key, default=None):
        try:
            value = self.config.get(key, default)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin.cfg", _amo_exc)
            value = default
        return default if value is None else value

    def cfg_bool(self, key, default=False):
        value = self.cfg(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on", "是")

    def cfg_int(self, key, default=0):
        try:
            return int(float(self.cfg(key, default)))
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin.cfg_int", _amo_exc)
            return default

    def cfg_float(self, key, default=0.0):
        try:
            return float(self.cfg(key, default))
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin.cfg_float", _amo_exc)
            return default

    def cfg_str(self, key, default=""):
        try:
            return str(self.cfg(key, default))
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin.cfg_str", _amo_exc)
            return default

    def _core_decor_flags(self, umo=""):
        """AstrBot 核心会不会在插件 hook 之后再加「引用 / @」。

        上架要求不能改 AstrBot 核心；但核心的 platform_settings.reply_with_quote /
        reply_with_mention 是全局的，会在 on_decorating_result 之后无条件装饰结果，
        把本插件的私聊不引用、群聊按概率引用覆盖掉。这里只读配置，检测到开了就由
        插件自己发送，核心就没机会再补。
        """
        try:
            config = self.context.get_config() or {}
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._core_decor_flags", _amo_exc)
            config = {}
        try:
            settings = config.get("platform_settings") or {}
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._core_decor_flags", _amo_exc)
            settings = {}
        return {
            "quote": bool(settings.get("reply_with_quote", False)),
            "mention": bool(settings.get("reply_with_mention", False)),
        }


    def _dialect_rows(self):
        region = self._dialect_region()
        try:
            rows = [row for row in self.db.list_dialects() if region in str(row.get("region") or "")]
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._dialect_rows", _amo_exc)
            rows = []
        if rows:
            return rows
        style = self._dialect_style().strip()
        return [
            {"term": term, "meaning": meaning, "region": style, "example": example}
            for term, meaning, example in DIALECT_FALLBACK_ROWS.get(style, [])
        ]

    def _dialect_region(self):
        style = self._dialect_style().strip()
        return DIALECT_REGIONS.get(style, style)

    def scenic_spots(self):
        if getattr(self, "_scenic_cache", None):
            return self._scenic_cache
        try:
            path = os.path.join(self.plugin_dir, "scenic_spots.json")
            with open(path, encoding="utf-8") as stream:
                data = json.load(stream)
            self._scenic_cache = data if isinstance(data, list) else []
        except Exception as exc:
            logger.warning("[amo] 读取景区数据失败: %s" % exc)
            self._scenic_cache = []
        return self._scenic_cache

    def _scenic_kb_name(self):
        name = self.cfg_str("scenic_kb_name", "旅游知识库-风景区").strip()
        if not name or name in ("中国景区知识库", "景区知识库"):
            return "旅游知识库-风景区"
        return name

    def _scenic_text_lines(self):
        lines = []
        for spot in self.scenic_spots():
            if not isinstance(spot, dict):
                continue
            projects = spot.get("projects") if isinstance(spot.get("projects"), list) else []
            lines.append(
                "景区：%s\n城市：%s·%s\n等级：%s\n游玩项目：%s\n建议时长：%s\n区域：%s" % (
                    spot.get("name", ""), spot.get("province", ""), spot.get("city", ""),
                    spot.get("level", ""), "、".join(str(item) for item in projects),
                    spot.get("duration", ""), spot.get("area", ""),
                )
            )
        return lines

    async def _ensure_scenic_kb(self):
        if not self.cfg_bool("create_scenic_kb", True):
            return None
        try:
            manager = getattr(self.context, "kb_manager", None)
            if manager is None:
                logger.warning("[amo] 当前 AstrBot 没有 kb_manager，景区知识库未创建")
                return None
            if callable(manager) and not hasattr(manager, "create_kb"):
                manager = manager()
            name = self._scenic_kb_name()
            kb = await manager.get_kb_by_name(name)
            if kb is None:
                providers = list(self.context.get_all_embedding_providers() or [])
                if not providers:
                    logger.warning("[amo] 没有 Embedding 供应商，景区知识库未创建")
                    return None
                provider_id = str(getattr(providers[0], "provider_config", {}).get("id", "") or "")
                if not provider_id:
                    try:
                        provider_id = str(providers[0].meta().id or "")
                    except Exception as _amo_exc:
                        _note_swallowed("main.HumanCorePlugin._ensure_scenic_kb", _amo_exc)
                        provider_id = ""
                if not provider_id:
                    logger.warning("[amo] Embedding 供应商没有有效 id，景区知识库未创建")
                    return None
                created = manager.create_kb(
                    name,
                    "中国 3A 级以上景区、所在城市与具体游玩项目",
                    emoji="🏞️",
                    embedding_provider_id=provider_id,
                )
                kb = await created if inspect.isawaitable(created) else created
            lines = self._scenic_text_lines()
            if lines:
                try:
                    docs = await kb.list_documents(search="amo_scenic")
                    for doc in docs or []:
                        doc_id = getattr(doc, "doc_id", "") or getattr(doc, "id", "")
                        if doc_id:
                            await kb.delete_document(doc_id)
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin._ensure_scenic_kb", _amo_exc)
                try:
                    await kb.upload_document(
                        "amo_scenic_spots.txt",
                        "\n\n".join(lines).encode("utf-8"),
                        "txt",
                    )
                except Exception as exc:
                    logger.warning("[amo] 景区知识库上传失败: %s" % exc)
            logger.info("[amo] 景区知识库 %s 已同步，共 %d 个景区" % (name, len(lines)))
            return kb
        except Exception as exc:
            logger.warning("[amo] 景区知识库创建失败: %s" % exc)
            return None

    async def _scenic_kb_context(self, query):
        try:
            manager = getattr(self.context, "kb_manager", None)
            if manager is None or not str(query or "").strip():
                return ""
            name = self._scenic_kb_name()
            kb = await manager.get_kb_by_name(name)
            if kb is None:
                return ""
            result = await manager.retrieve(str(query)[:400], [name], top_m_final=4)
            return str(result.get("context_text") or "") if isinstance(result, dict) else ""
        except Exception as exc:
            logger.debug("[amo] 景区知识库检索失败: %s" % exc)
            return ""

    def _dialect_active(self):
        """方言是否生效：语种选「普通话」就等于关掉方言（连方言库都不查）。"""
        style = str(self.cfg_str("dialect_style", "") or "").strip()
        if style in ("普通话", "关闭", "off", "none"):
            return False
        return self.cfg_bool("dialect_enabled", True)

    def _dialect_style(self):
        """语种：配置里写了就用配置（面板可覆盖），没写就按世界观城市自动选。"""
        explicit = str(self.cfg_str("dialect_style", "") or "").strip()
        if explicit and explicit not in ("自动", "auto", "auto_city"):
            return explicit
        city = ""
        try:
            world = getattr(self.state, "worldview", None) or {}
            city = str(world.get("city") or "")
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._dialect_style", _amo_exc)
        if not city:
            try:
                city = str(
                    self.cfg_str("weather_city_name", "")
                    or self.cfg_str("weather_city", "")
                    or ""
                )
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._dialect_style", _amo_exc)
        return dialect_for_city(city)

    def _dialect_kb_name(self):
        base = self.cfg_str("dialect_kb_name", "陪伴方言库").strip() or "陪伴方言库"
        style = self._dialect_style().strip()
        return base + "-" + style if style else base

    @staticmethod
    def _embedding_provider_id(provider):
        try:
            value = str(provider.provider_config.get("id", "") or "")
            if value:
                return value
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._embedding_provider_id", _amo_exc)
        try:
            return str(provider.meta().id or "")
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._embedding_provider_id", _amo_exc)
            return ""

    async def _dialect_kb_context(self, query):
        # 关掉方言就别检索方言库：省一次 embedding 查询和一段提示词
        if not self._dialect_active():
            return ""
        try:
            manager = getattr(self.context, "kb_manager", None)
            if manager is None or not str(query or "").strip():
                return ""
            name = self._dialect_kb_name()
            kb = await manager.get_kb_by_name(name)
            names = [name]
            if kb is None:
                legacy = await manager.get_kb_by_name("核心方言库")
                if legacy is not None:
                    kb = legacy
                    names = ["核心方言库"]
            if kb is None:
                return ""
            result = await manager.retrieve(str(query)[:500], names, top_m_final=3)
            if not isinstance(result, dict):
                return ""
            return str(result.get("context_text") or "")
        except Exception as exc:
            logger.debug("[amo] 方言知识库检索失败: %s" % exc)
            return ""

    async def _ensure_dialect_kb(self):
        """把方言同步进 AstrBot 知识库；失败会明确写日志，不再静默。"""
        if not self._dialect_active():
            return None
        if not self.cfg_bool("create_dialect_kb", True):
            return None
        try:
            manager = getattr(self.context, "kb_manager", None)
            if manager is None:
                logger.warning("[amo] 当前 AstrBot 没有 kb_manager，无法创建知识库")
                return None
            if callable(manager) and not hasattr(manager, "create_kb"):
                try:
                    manager = manager()
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin._ensure_dialect_kb", _amo_exc)
                    manager = None
            if manager is None or not hasattr(manager, "create_kb"):
                logger.warning("[amo] kb_manager 不支持 create_kb，无法创建知识库")
                return None
            name = self._dialect_kb_name()
            kb = await manager.get_kb_by_name(name)
            if kb is None:
                providers = []
                getter = getattr(self.context, "get_all_embedding_providers", None)
                if callable(getter):
                    try:
                        providers = list(getter() or [])
                    except Exception as _amo_exc:
                        _note_swallowed("main.HumanCorePlugin._ensure_dialect_kb", _amo_exc)
                        providers = []
                if not providers:
                    pm = getattr(self.context, "provider_manager", None)
                    providers = list(getattr(pm, "embedding_provider_insts", []) or [])
                if not providers:
                    logger.warning(
                        "[amo] 没有可用的 Embedding 供应商，知识库未创建；"
                        "请先在 AstrBot 模型提供商里配置 embedding"
                    )
                    return None
                provider_id = self._embedding_provider_id(providers[0])
                if not provider_id:
                    logger.warning("[amo] Embedding 供应商没有有效 id，知识库未创建")
                    return None
                try:
                    created = manager.create_kb(
                        name,
                        "陪伴角色方言与口语表达，用于聊天时的自然替换",
                        emoji="🗣️",
                        embedding_provider_id=provider_id,
                    )
                    kb = await created if inspect.isawaitable(created) else created
                except Exception as exc:
                    logger.warning("[amo] 创建知识库 %s 失败: %s" % (name, exc), exc_info=True)
                    return None

            rows = []
            try:
                rows = self._dialect_rows()
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._ensure_dialect_kb", _amo_exc)
                rows = []
            lines = [
                "%s（%s）：普通话“%s”，例：%s" % (
                    row.get("term", ""), row.get("region", ""),
                    row.get("meaning", ""), row.get("example", ""),
                )
                for row in rows
                if row.get("term") and row.get("meaning")
            ]
            if lines:
                try:
                    docs = await kb.list_documents(search="amo_dialect")
                    for doc in docs or []:
                        doc_id = getattr(doc, "doc_id", "") or getattr(doc, "id", "")
                        if doc_id:
                            await kb.delete_document(doc_id)
                except Exception as exc:
                    logger.warning("[amo] 清理旧方言文档失败: %s" % exc)
                try:
                    await kb.upload_document(
                        "amo_dialect.txt",
                        "\n".join(lines).encode("utf-8"),
                        "txt",
                        pre_chunked_text=lines,
                    )
                except Exception as exc:
                    logger.warning("[amo] 方言知识库上传失败: %s" % exc, exc_info=True)
            logger.debug("[amo] 知识库 %s 已同步，写入 %d 条方言" % (name, len(lines)))
            return kb
        except Exception as exc:
            logger.warning("[amo] 方言知识库创建失败: %s" % exc, exc_info=True)
            return None


    def _migrate_legacy_config(self):
        """把旧版 amo_forever_config.json 合并到 Astrbot_Amo_forever_config.json。"""
        path = str(getattr(self.config, "config_path", "") or "")
        if not path:
            return
        base = os.path.dirname(path)
        legacy_candidates = [
            os.path.join(base, "amo_forever_config.json"),
            os.path.join(base, "astrbot_plugin_amo_forever_config.json"),
        ]
        legacy = next((item for item in legacy_candidates if os.path.exists(item)), "")
        if not legacy:
            return
        try:
            import shutil as _shutil
            with open(path, encoding="utf-8-sig") as stream:
                current = json.load(stream)
            with open(legacy, encoding="utf-8-sig") as stream:
                old = json.load(stream)
            if not isinstance(current, dict) or not isinstance(old, dict):
                return
            schema = {}
            try:
                with open(os.path.join(self.plugin_dir, "_conf_schema.json"), encoding="utf-8-sig") as stream:
                    schema = json.load(stream) or {}
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._migrate_legacy_config", _amo_exc)
                schema = {}
            merged = {}
            for key, value in old.items():
                meta = schema.get(key) if isinstance(schema.get(key), dict) else {}
                default = meta.get("default")
                if key not in current or current.get(key) == default:
                    current[key] = value
                    merged[key] = value
            if not merged:
                return
            backup = path + ".bak-4.0.0"
            if os.path.exists(path) and not os.path.exists(backup):
                _shutil.copy2(path, backup)
            self.config.update(current)
            if hasattr(self.config, "save_config"):
                self.config.save_config()
            logger.info(
                "[amo] 已迁移旧版 amo_forever 配置: %s（%d 项）"
                % (legacy, len(merged))
            )
            logger.info("[amo] 升级提示：插件标识保持 Astrbot_Amo_forever；旧 amo_forever 配置/数据已自动迁移。")
        except Exception as exc:
            logger.warning("[amo] 旧版 amo_forever 配置迁移失败: %s" % exc)

    def _reload_config_if_changed(self):
        """AstrBot 原生插件配置页保存后，运行中的 self.config 可能不是新对象。

        读取配置文件 mtime，变化时把新值合并进当前配置，保证天气城市、
        管理员、主动私聊等动态配置不需要重启插件也能生效。
        """
        path = getattr(self.config, "config_path", "")
        if not path:
            return
        try:
            mtime = os.path.getmtime(path)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._reload_config_if_changed", _amo_exc)
            return
        if mtime <= self._config_mtime:
            return
        try:
            with open(path, encoding="utf-8-sig") as stream:
                data = json.load(stream)
            if not isinstance(data, dict):
                return
            old_engine_config = {
                key: value for key, value in self.config.items()
                if key.startswith("hf_") or key.startswith("seg_")
            }
            self.config.update(data)
            new_engine_config = {
                key: value for key, value in self.config.items()
                if key.startswith("hf_") or key.startswith("seg_")
            }
            if old_engine_config and old_engine_config != new_engine_config:
                self._spawn(self._apply_runtime_config())
            self._config_mtime = mtime
            if data.get("bot_name"):
                self.bot_name = str(data.get("bot_name"))
            if data.get("bot_aliases") is not None:
                self.bot_aliases = [
                    item.strip() for item in str(data.get("bot_aliases")).split(",") if item.strip()
                ]
            if self.heartflow is not None:
                self.heartflow.set_identity(self.bot_name, self.bot_aliases)
            self._persona_name_cache.clear()
            raw_admins = data.get("admin_uids", None)
            if raw_admins is not None:
                self.admin_uids = {
                    item.strip() for item in str(raw_admins).split(",") if item.strip()
                }
            start = str(data.get("period_start") or "").strip()
            if start and self.state is not None and start != self.state.period_start:
                try:
                    date.fromisoformat(start)
                    self.state.set_period_start(start)
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin._reload_config_if_changed", _amo_exc)
            try:
                self._sync_weather_city_config()
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._reload_config_if_changed", _amo_exc)
            logger.debug("[amo] 检测到插件配置变更，已重新加载")
        except Exception as exc:
            logger.debug("[amo] 重新加载插件配置失败: %s" % exc)

    def _hf_config(self):
        try:
            return {key[3:]: value for key, value in self.config.items() if key.startswith("hf_")}
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._hf_config", _amo_exc)
            return {}

    def _seg_config(self):
        try:
            return {key[4:]: value for key, value in self.config.items() if key.startswith("seg_")}
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._seg_config", _amo_exc)
            return {}

    def _command_prefixes(self):
        if self._prefix_cache is not None:
            return self._prefix_cache
        prefixes = []
        try:
            cfg = self.context.get_config()
            raw = cfg.get("wake_prefix", []) if cfg else []
            if isinstance(raw, str):
                raw = [raw]
            prefixes = [str(item) for item in (raw or []) if item]
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._command_prefixes", _amo_exc)
        self._prefix_cache = prefixes
        return prefixes

    def _looks_like_command(self, text):
        if looks_like_plain_command(text):
            return True
        first = text.split()[0].lower() if text.split() else ""
        if first in ("amo", "陪伴", "c_status", "c_profile", "c_setrel", "learn_and_gate"):
            return True
        return any(prefix and text.startswith(prefix) for prefix in self._command_prefixes())

    _on_astrbot_loaded_hook = getattr(filter, "on_astrbot_loaded", None)

    if _on_astrbot_loaded_hook is not None:
        @_on_astrbot_loaded_hook()
        async def on_astrbot_loaded(self):
            """所有插件加载完：数据插件要是比 amo 后加载，这里补做一次同步。"""
            try:
                await self._ensure_ready()
                if not self._data_synced and self._data_connected():
                    await self._sync_with_data_plugin()
            except Exception as exc:
                logger.debug("[amo] 加载完成补同步失败: %s" % exc)

    def _spawn(self, coro):
        try:
            task = asyncio.create_task(coro)
        except RuntimeError:
            try:
                coro.close()
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._spawn", _amo_exc)
            return None
        self._tasks.add(task)

        def _report(done):
            self._tasks.discard(done)
            if done.cancelled():
                return
            try:
                exc = done.exception()
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._spawn._report", _amo_exc)
                exc = None
            if exc is not None:
                logger.warning("[amo] 后台任务异常: %s", exc, exc_info=exc)

        task.add_done_callback(_report)
        return task

    async def _ensure_ready(self):
        if self._ready:
            return
        async with self._init_lock:
            if self._ready:
                return
            try:
                await asyncio.to_thread(self.db.init)
            except Exception as exc:
                logger.error("[amo] 数据库初始化失败: %s" % exc)
            self._migrate_delay_default()
            self._migrate_proactive_timing()
            self._migrate_typing_defaults()
            self._migrate_memory_source_default()
            self._migrate_legacy_admin_default()
            self._migrate_scenic_kb_name()
            self._migrate_schedule_defaults()
            self._migrate_diary_continuity()
            self._cleanup_legacy_memory_profiles()
            await asyncio.to_thread(self._merge_alias_profiles)
            self.state = HumanState(self)
            try:
                await self._sync_with_data_plugin()
            except Exception as exc:
                logger.debug("[amo] 与数据插件同步失败: %s" % exc)
            self._ready = True
            self._loop_task = self._spawn(self._background_loop())
            self._spawn(self._warm_up())


    def _migrate_scenic_kb_name(self):
        try:
            if self.db.kv_get("scenic_kb_name_migrated_502", False):
                return
            current = self.cfg_str("scenic_kb_name", "").strip()
            if current in ("", "中国景区知识库", "景区知识库"):
                self.config["scenic_kb_name"] = "旅游知识库-风景区"
                if hasattr(self.config, "save_config"):
                    self.config.save_config()
            self.db.kv_set("scenic_kb_name_migrated_502", True)
        except Exception as exc:
            logger.debug("[amo] 迁移景区知识库名称失败: %s" % exc)


    def _migrate_typing_defaults(self):
        """2.6.2 起把旧的 55ms/字默认值迁移到更真实的 400ms/字。"""
        try:
            if self.db.kv_get("typing_realistic_migrated", False):
                return
            changes = {}
            if to_int(self.cfg("typing_base_ms", 0), 0) == 600:
                changes["typing_base_ms"] = 700
            if to_int(self.cfg("typing_per_char_ms", 0), 0) == 55:
                changes["typing_per_char_ms"] = 400
            if to_int(self.cfg("typing_max_ms", 0), 0) == 4500:
                changes["typing_max_ms"] = 20000
            if abs(to_float(self.cfg("seg_per_char_delay_seconds", 0), 0) - 0.08) < 0.0001:
                changes["seg_per_char_delay_seconds"] = 0.4
            for key, value in changes.items():
                self.config[key] = value
            if changes:
                if hasattr(self.config, "save_config"):
                    self.config.save_config()
                if self.segment_engine is not None and "seg_per_char_delay_seconds" in changes:
                    self.segment_engine.per_char_delay_seconds = 0.4
                logger.debug("[amo] 打字延迟默认值已迁移为 400ms/字（18字约8秒）")
            self.db.kv_set("typing_realistic_migrated", True)
        except Exception as exc:
            logger.debug("[amo] 迁移打字延迟失败: %s" % exc)


    def _migrate_delay_default(self):
        """2.4.7 起默认按回复字数动态延迟；旧的 fixed 配置迁移一次。"""
        try:
            if self.cfg_str("seg_delay_type", "").strip().lower() != "fixed":
                return
            if self.db.kv_get("delay_dynamic_migrated", False):
                return
            self.config["seg_delay_type"] = "dynamic"
            if self.segment_engine is not None:
                self.segment_engine.delay_type = "dynamic"
            if hasattr(self.config, "save_config"):
                self.config.save_config()
            self.db.kv_set("delay_dynamic_migrated", True)
            logger.debug("[amo] 分段延迟已从 fixed 迁移为 dynamic（按回复字数）")
        except Exception as exc:
            logger.debug("[amo] 迁移分段延迟失败: %s" % exc)


    def _migrate_legacy_admin_default(self):
        """旧版本把 3261748099 写成了默认管理员；2.4.0 只清理一次。"""
        try:
            if self.cfg_str("admin_uids", "").strip() != LEGACY_DEFAULT_ADMIN:
                return
            if self.db.kv_get("admin_default_cleared", False):
                return
            parts = [
                item.strip() for item in self.cfg_str("admin_uids", "").split(",")
                if item.strip() and item.strip() != LEGACY_DEFAULT_ADMIN
            ]
            self.config["admin_uids"] = ",".join(parts)
            if hasattr(self.config, "save_config"):
                self.config.save_config()
            self.admin_uids = set(parts)
            self.db.kv_set("admin_default_cleared", True)
            logger.debug("[amo] 已移除旧默认管理员 %s，请在配置里填写自己的 ID" % LEGACY_DEFAULT_ADMIN)
        except Exception as exc:
            logger.debug("[amo] 清理旧默认管理员失败: %s" % exc)

    async def _warm_up(self):
        try:
            await asyncio.sleep(3)
            umo = self._last_umo or self._first_private_umo()
            await self._sync_persona_name(umo or "")
            await self._ensure_dialect_kb()
            await self._ensure_scenic_kb()
            await self.state.ensure_worldview(umo)
            await self.state.ensure_schedule(umo)
        except Exception as exc:
            logger.debug("[amo] 预热失败: %s" % exc)

    async def initialize(self):
        await self._ensure_ready()

    async def terminate(self):
        self._running = False
        if self.heartflow is not None:
            try:
                await self.heartflow.terminate()
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin.terminate", _amo_exc)
        if self.segment_engine is not None:
            for task in list(getattr(self.segment_engine, "_tasks", set())):
                try:
                    task.cancel()
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin.terminate", _amo_exc)
        for task in list(self._tasks):
            try:
                task.cancel()
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin.terminate", _amo_exc)
        if self.state is not None:
            try:
                self.state.save()
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin.terminate", _amo_exc)
        # 不在这里关闭数据库：AstrBot 重载插件时旧实例注册的 Web API
        # 可能仍被调用，关闭连接会导致 "Cannot operate on a closed database"。
        # 连接由进程退出时回收；AmoDB.conn 也会在需要时自动重连。

    async def stop(self):
        await self.terminate()

    # ---- 跨平台账号合并 ----
    def _uid_alias_mapping(self):
        """读映射表（配置优先，其次数据目录 uid_map.json）；按内容+mtime 缓存。"""
        cache_key = None
        try:
            text = str(self.cfg_str("uid_alias_map", "") or "").strip().lstrip("﻿")
            map_path = os.path.join(os.path.dirname(str(self.db.path)), "uid_map.json")
            stamp = os.path.getmtime(map_path) if os.path.exists(map_path) else 0
            cache_key = (text, stamp)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._uid_alias_mapping", _amo_exc)
            cache_key = None
        if getattr(self, "_uid_alias_cache_key", None) != cache_key:
            raw = {}
            try:
                text = str(self.cfg_str("uid_alias_map", "") or "").strip().lstrip("﻿")
                parsed = json.loads(text) if text else {}
                if isinstance(parsed, dict):
                    raw.update(parsed)
            except Exception as exc:
                logger.warning("[amo] uid_alias_map 配置解析失败: %s" % exc)
            try:
                map_path = os.path.join(os.path.dirname(str(self.db.path)), "uid_map.json")
                if os.path.exists(map_path):
                    # utf-8-sig：Windows 记事本另存的 JSON 常带 BOM，用 utf-8 会直接解析失败
                    with open(map_path, "r", encoding="utf-8-sig") as fh:
                        parsed = json.load(fh)
                    if isinstance(parsed, dict):
                        for key, value in parsed.items():
                            raw.setdefault(key, value)
            except Exception as exc:
                logger.warning("[amo] uid_map 读取失败: %s" % exc)
            raw = {str(k): str(v) for k, v in raw.items() if k and v}
            # 解析链式映射（A→B、B→C 归到 A→C），并丢掉自映射
            resolved = {}
            for key in raw:
                current = key
                seen = {key}
                while current in raw:
                    nxt = raw[current]
                    if nxt in seen:
                        break
                    seen.add(nxt)
                    current = nxt
                if current != key:
                    resolved[key] = current
            self._uid_alias_map = resolved
            self._uid_alias_cache_key = cache_key
        return getattr(self, "_uid_alias_map", {}) or {}

    def _canonical_uid(self, event):
        """把平台账号换算成同一个人的主 uid；关掉开关就返回原 uid。"""
        try:
            uid = str(event.get_sender_id())
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._canonical_uid", _amo_exc)
            return ""
        if not self.cfg_bool("uid_merge_enabled", True):
            return uid
        return self._uid_alias_mapping().get(uid, uid)

    def _merge_alias_profiles(self):
        """一次性把旧版本按平台 ID 建好的档案并进主 uid（映射变了会再跑一次）。"""
        if not self.cfg_bool("uid_merge_enabled", True):
            return
        mapping = self._uid_alias_mapping()
        if not mapping:
            return
        signature = json.dumps(mapping, sort_keys=True, ensure_ascii=False)
        try:
            if self.db.kv_get("uid_alias_merged_signature", "") == signature:
                return
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._merge_alias_profiles", _amo_exc)
        try:
            report = merge_uid_alias_data(self.db.conn, mapping)
            self.db.kv_set("uid_alias_merged_signature", signature)
            logger.info("[amo] 跨平台账号合并完成: %s" % report)
        except Exception as exc:
            logger.warning("[amo] 跨平台账号合并失败: %s" % exc)

    # ---------- 管理员 ----------
    def _is_admin(self, event):
        uid = self._canonical_uid(event)
        if uid in self.admin_uids:
            return True
        try:
            umo = str(event.unified_msg_origin or "")
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._is_admin", _amo_exc)
            umo = ""
        # 每条消息都会走这里，get_config 没必要每次读：按会话缓存 60 秒
        cache = getattr(self, "_admin_cache", None)
        if cache is None:
            cache = {}
            self._admin_cache = cache
        now = time.time()
        hit = cache.get(umo)
        if hit and now - hit[0] < 60:
            return uid in hit[1]
        try:
            cfg = self.context.get_config(umo)
            admins = cfg.get("admins_id", []) if cfg else []
            if isinstance(admins, str):
                admins = [item.strip() for item in admins.split(",") if item.strip()]
            names = {str(item) for item in (admins or [])}
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._is_admin", _amo_exc)
            names = set()
        cache[umo] = (now, names)
        return uid in names

    # ---------- 消息学习 ----------
    async def _learn(self, event, text):
        uid = self._canonical_uid(event)
        name = event.get_sender_name() or uid
        umo = event.unified_msg_origin
        group_id = event.get_group_id()
        private = event.is_private_chat()
        profile = self.db.touch_profile(
            uid, name, event.get_platform_name(), umo, group_id, private
        )
        if private and umo:
            self._record_channel(uid, umo, event.get_platform_name())
        if profile and not profile.get("is_admin") and uid in self.admin_uids:
            self.db.update_profile(uid, is_admin=1)
            profile["is_admin"] = 1

        self.state.observe(text)
        if self.cfg_bool("auto_relation", True):
            try:
                await self._learn_relations(event, text, uid)
            except Exception as exc:
                logger.debug("[amo] 关系自动识别失败: %s" % exc)
        # 上下文先进内存；本地缓存默认关掉，原始聊天交给记忆终端
        self._ctx_remember(umo, uid, name, "user", text)
        if self.cfg_bool("local_chat_cache", False):
            self.db.add_message(umo, uid, name, "user", text)
        try:
            await self._data_call(
                "add_message", self._data_bot_id(), umo, uid, name, "user", text,
                platform=self._platform_of(event), message_id=self._event_message_id(event),
            )
        except Exception as exc:
            logger.debug("[amo] 聊天记录同步失败: %s" % exc)

        senti = sentiment(text)
        affection = to_int(profile.get("affection"), 10)
        if senti["aff"] or senti["pos"]:
            affection += 2
        if senti["neg"] or senti["insult"]:
            affection -= 2
        affection = int(clamp(affection, 0, 100))

        # 记忆只在外挂记忆插件里；这里只把生日这种档案字段记进画像。
        match = re.search(r"生日(?:是|在)?\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?", text or "")
        if match:
            self.db.update_profile(uid, birthday="%02d-%02d" % (to_int(match.group(1)), to_int(match.group(2))))

        fields = {"affection": affection}
        relation = profile.get("relation", "普通")
        if relation == "普通" and to_int(profile.get("msg_count"), 0) >= self.cfg_int("familiar_msg_count", 30):
            fields["relation"] = "熟识"
        elif relation == "熟识" and senti["insult"]:
            fields["relation"] = "抵触"
        self.db.update_profile(uid, **fields)
        try:
            self._learn_alias(event, text, uid, profile)
        except Exception as exc:
            logger.debug("[amo] 学习称呼失败: %s" % exc)

        if group_id:
            times = self._group_times.setdefault(group_id, [])
            times.append(now_ts())
            if len(times) > 200:
                self._group_times[group_id] = times[-200:]
            self._last_group = group_id
        self._last_umo = umo

    def _register_lover(self, uid):
        uid = str(uid or "").strip()
        if uid:
            self.db.kv_set("lover_uid_" + uid, True)

    def _is_registered_lover(self, uid):
        uid = str(uid or "").strip()
        if not uid:
            return False
        if self.db.kv_get("lover_uid_" + uid, False):
            return True
        profile = self.db.get_profile(uid) or {}
        if str(profile.get("relation") or "") == "相恋":
            self._register_lover(uid)
            return True
        return False

    def _restore_lover_relation(self, uid):
        uid = str(uid or "").strip()
        if not self._is_registered_lover(uid):
            return
        profile = self.db.get_profile(uid) or {}
        if str(profile.get("relation") or "") in ("抵触", "仇恨"):
            self.db.update_profile(uid, relation="相恋")
            logger.info("[amo] 恋人 UID 恢复为相恋: %s" % uid)

    def _lover_aliases(self):
        aliases = {}
        try:
            profiles = self.db.list_profiles("", 500)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._lover_aliases", _amo_exc)
            profiles = []
        for profile in profiles:
            uid = str(profile.get("uid") or "")
            if str(profile.get("relation") or "") == "相恋":
                self._register_lover(uid)
            elif not self._is_registered_lover(uid):
                continue
            values = [profile.get("name") or ""]
            values.extend(re.split(r"[；;、,，/\s]+", str(profile.get("alias") or "")))
            for value in values:
                name = str(value or "").strip()
                if len(name) >= 1:
                    aliases[name] = uid
        return aliases


    def _learn_alias(self, event, text, uid, profile):
        """从“以后叫我XX / 叫他XX”里学习称呼，并在后续沿用。"""
        blocked = {"干嘛", "什么", "名字", "滚", "闭嘴", "一声", "一下", "出来"}
        alias = ""
        for pattern in (
            r"(?:以后|今后|你可以|可以|请)?叫我\s*([\u4e00-\u9fa5A-Za-z0-9_]{1,12})",
            r"叫我\s*([\u4e00-\u9fa5A-Za-z0-9_]{1,12})\s*(?:就行|就好|吧)",
        ):
            match = re.search(pattern, str(text or ""))
            if match:
                candidate = match.group(1).strip()
                if candidate and candidate not in blocked:
                    alias = candidate
                    break
        if alias:
            current = str(profile.get("alias") or "")
            if alias not in current:
                new_alias = (current + "；" + alias).strip("；")[:80]
                self.db.update_profile(uid, alias=new_alias)
                logger.debug("[amo] 记住称呼: %s -> %s" % (uid, alias))

        try:
            messages = event.message_obj.message
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._learn_alias", _amo_exc)
            messages = []
        at_targets = [
            str(getattr(comp, "qq", ""))
            for comp in (messages or [])
            if Comp is not None and isinstance(comp, Comp.At)
        ]
        for comp in messages:
            if Comp is None or not isinstance(comp, Comp.At):
                continue
            target = str(getattr(comp, "qq", ""))
            if not target or target in ("all", str(event.get_self_id())):
                continue
            # “以后喊他XX”通常跟在最后一个 @ 后面；不要误记到前一个被 @ 的人。
            if at_targets and target != at_targets[-1]:
                continue
            for pattern in (
                r"(?:以后|就)?(?:喊|叫|称呼)(?:他|她|ta|TA|做)\s*([\u4e00-\u9fa5A-Za-z0-9_]{1,12})",
            ):
                match = re.search(pattern, str(text or ""))
                if not match:
                    continue
                candidate = match.group(1).strip()
                if not candidate or candidate in blocked:
                    continue
                target_profile = self.db.get_profile(target)
                if not target_profile:
                    self.db.touch_profile(target, candidate, event.get_platform_name(), "", "", False)
                    target_profile = self.db.get_profile(target)
                current = str(target_profile.get("alias") or "")
                if candidate not in current:
                    self.db.update_profile(target, alias=(current + "；" + candidate).strip("；")[:80])
                break
            # 群里反复 @ 同一个人并叫同一个短称呼，累计三次后记住。
            plain = re.sub(r"@\S+", "", str(text or "")).strip()
            common = {
                "在吗", "你好", "早安", "晚安", "吃了吗", "干嘛", "出来", "看这个",
                "哈哈", "笑死", "救命", "谢谢", "收到", "好的", "可以", "不行",
                "快看", "快来", "过来", "上线", "打游戏", "起床", "睡觉", "上班", "下班",
            }
            if 1 <= len(plain) <= 8 and plain not in common and not re.search(r"[，。！？!?、；;：:]", plain):
                seen_key = "alias_seen_" + target + "_" + plain
                seen = to_int(self.db.kv_get(seen_key, 0), 0) + 1
                self.db.kv_set(seen_key, seen)
                if seen >= 3:
                    alias_profile = self.db.get_profile(target) or {}
                    current = str(alias_profile.get("alias") or "")
                    if plain not in current:
                        self.db.update_profile(target, alias=(current + "；" + plain).strip("；")[:80])
                    self.db.kv_set(seen_key, 0)

    # ---------- 近聊上下文（内存缓冲 + 记忆终端钩子） ----------
    CONTEXT_BUFFER_LIMIT = 60

    def _ctx_remember(self, umo, uid, name, role, content):
        """把一句话放进内存缓冲；不落库也能有上下文。"""
        umo = str(umo or "")
        text = str(content or "").strip()
        if not umo or not text:
            return
        hub = self._memory_hub()
        if hub is not None:
            try:
                hub.buffer.add(umo, uid, name, role, text)
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._ctx_remember", _amo_exc)
        try:
            if hub is not None and str(role) != "bot":
                hub.next_turn()
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._ctx_remember", _amo_exc)
        buf = getattr(self, "_ctx_buffer", None)
        if buf is None:
            buf = {}
            self._ctx_buffer = buf
        rows = buf.get(umo)
        if rows is None:
            rows = []
            buf[umo] = rows
        rows.append({
            "umo": umo,
            "uid": str(uid or ""),
            "name": str(name or ""),
            "role": "bot" if str(role) == "bot" else "user",
            "content": text,
            "created_at": now_ts(),
        })
        if len(rows) > self.CONTEXT_BUFFER_LIMIT:
            del rows[:len(rows) - self.CONTEXT_BUFFER_LIMIT]

    def _recent(self, umo, limit=10):
        """近聊上下文钩子：能力层缓冲优先，没有再读本地缓存表。"""
        size = max(1, int(limit or 10))
        rows = []
        hub = self._memory_hub()
        if hub is not None:
            try:
                rows = hub.buffer.recent(umo, size)
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._recent", _amo_exc)
                rows = []
        if not rows:
            try:
                rows = list((getattr(self, "_ctx_buffer", {}) or {}).get(str(umo), []))
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._recent", _amo_exc)
                rows = []
        if len(rows) >= size:
            return rows[-size:]
        try:
            local = self.db.recent_messages(umo, size)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._recent", _amo_exc)
            local = []
        if not rows:
            return local
        # 缓冲只有一小段时，用本地补前面
        known = {(row.get("role"), row.get("content")) for row in rows}
        merged = [row for row in local if (row.get("role"), row.get("content")) not in known]
        merged.extend(rows)
        return merged[-size:]

    async def _recent_by_uid(self, uid, limit=20, umo=""):
        """取近聊：优先按会话，其次按 uid；都没有再退回缓冲/本地缓存。"""
        uid = str(uid or "")
        size = max(1, int(limit or 20))
        mem = self._data_mem()
        lister = getattr(mem, "list_messages", None) if mem is not None else None
        if callable(lister) and umo:
            # 按会话取：bot 行的 uid 是字面量 "bot"，按 uid 过滤会把她说的话全滤掉
            try:
                rows = await lister(self._data_bot_id(), str(umo), size) or []
            except TypeError:
                rows = []
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._recent_by_uid", _amo_exc)
                rows = []
            if rows:
                return sorted(rows, key=lambda item: to_float(item.get("created_at"), 0))[-size:]
        if callable(lister):
            try:
                rows = await lister(self._data_bot_id(), "", size, uid=uid) or []
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._recent_by_uid", _amo_exc)
                rows = []
            if rows:
                return sorted(rows, key=lambda item: to_float(item.get("created_at"), 0))[-size:]
        merged = []
        hub = self._memory_hub()
        if hub is not None:
            try:
                merged = hub.buffer.by_uid(uid, size)
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._recent_by_uid", _amo_exc)
                merged = []
        if not merged:
            for rows in list((getattr(self, "_ctx_buffer", {}) or {}).values()):
                merged.extend([row for row in rows if str(row.get("uid") or "") == uid])
        if merged:
            return sorted(merged, key=lambda item: to_float(item.get("created_at"), 0))[-size:]
        try:
            return self.db.messages_by_uid(uid, size)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._recent_by_uid", _amo_exc)
            return []

    async def _hydrate_recent(self, umo, limit=30):
        """从记忆终端把这个会话最近的话捞回内存，重启后也有上下文。"""
        umo = str(umo or "")
        if not umo:
            return
        if str(umo) in getattr(self, "_ctx_hydrated", set()):
            return
        rows = []
        hub = self._memory_hub()
        if hub is not None:
            try:
                rows = await hub.recent(umo, "", max(1, int(limit))) or []
            except Exception as exc:
                logger.debug("[amo] 能力层取上下文失败: %s" % exc)
                rows = []
        if not rows:
            mem = self._data_mem()
            lister = getattr(mem, "list_messages", None) if mem is not None else None
            if callable(lister):
                try:
                    rows = await lister(self._data_bot_id(), umo, max(1, int(limit))) or []
                except Exception as exc:
                    logger.debug("[amo] 从记忆终端取上下文失败: %s" % exc)
                    rows = []
        if not rows:
            try:
                rows = self.db.recent_messages(umo, max(1, int(limit)))
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._hydrate_recent", _amo_exc)
                rows = []
        if not rows:
            return
        ordered = sorted(rows, key=lambda item: to_float(item.get("created_at"), 0))
        buf = getattr(self, "_ctx_buffer", None)
        if buf is None:
            buf = {}
            self._ctx_buffer = buf
        buf[umo] = [
            {
                "umo": umo,
                "uid": str(item.get("uid") or ""),
                "name": str(item.get("name") or ""),
                "role": "bot" if str(item.get("role")) == "bot" else "user",
                "content": str(item.get("content") or ""),
                "created_at": to_float(item.get("created_at"), 0),
            }
            for item in ordered[-self.CONTEXT_BUFFER_LIMIT:]
        ]
        self._ctx_hydrated = getattr(self, "_ctx_hydrated", set())
        self._ctx_hydrated.add(str(umo))

    def _is_talking_to_me(self, event):
        """这句是不是冲她来的：私聊、被 @ / 叫名字、或心流判定对象是 bot。"""
        try:
            if event.is_private_chat():
                return True
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._is_talking_to_me", _amo_exc)
            return True
        target = str(getattr(event, "heartflow_target", "") or "")
        if target == "bot":
            return True
        if str(getattr(event, "heartflow_mode_hint", "") or "") == "interject":
            return False
        try:
            if getattr(event, "is_at_or_wake_command", False):
                return True
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._is_talking_to_me", _amo_exc)
        try:
            if self.heartflow is not None and self.heartflow._addresses_bot(event.message_str or ""):
                return True
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._is_talking_to_me", _amo_exc)
        return False

    def _group_roster(self, umo, current_uid="", limit=8):
        """群里最近说过话的人：uid → 称呼 / 关系 / 聊过多少句。

        让她在群里先认人：谁在说话、和她什么关系、该用什么语气，而不是把所有人都当同一个人。
        """
        roster = []
        seen = set()
        try:
            rows = self._recent(umo, 40)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._group_roster", _amo_exc)
            return roster
        for row in rows:
            if str(row.get("role") or "") != "user":
                continue
            uid = str(row.get("uid") or "")
            if not uid or uid in seen:
                continue
            seen.add(uid)
            profile = {}
            try:
                profile = self.db.get_profile(uid) or {}
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._group_roster", _amo_exc)
                profile = {}
            name = (
                str(profile.get("alias") or "").strip()
                or str(profile.get("name") or "").strip()
                or str(row.get("name") or "").strip()
                or uid
            )
            relation = str(profile.get("relation") or "普通")
            msg_count = to_int(profile.get("msg_count"), 0)
            roster.append({
                "uid": uid,
                "name": name,
                "relation": relation,
                "msg_count": msg_count,
                "current": bool(current_uid) and uid == str(current_uid),
            })
            if len(roster) >= max(1, int(limit)):
                break
        roster.sort(key=lambda item: (not item["current"], -item["msg_count"]))
        return roster

    def _group_roster_text(self, umo, current_uid="", limit=8):
        roster = self._group_roster(umo, current_uid, limit)
        if not roster:
            return ""
        lines = []
        for item in roster:
            tag = "（现在这句就是ta说的）" if item["current"] else ""
            if item["msg_count"] >= 200:
                familiar = "很熟"
            elif item["msg_count"] >= 30:
                familiar = "熟识"
            elif item["msg_count"] >= 1:
                familiar = "刚认识"
            else:
                familiar = "陌生"
            lines.append(
                "· %s（UID %s）：和你关系「%s」，%s%s"
                % (item["name"], item["uid"], item["relation"], familiar, tag)
            )
        return "\n".join(lines)


    def _group_speaker_count(self, umo, limit=20, window=600):
        """最近一段时间内群聊里的不同发言人数。"""
        try:
            rows = self._recent(umo, limit)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._group_speaker_count", _amo_exc)
            return 0
        cutoff = now_ts() - window
        speakers = {
            str(row.get("uid") or "")
            for row in rows
            if row.get("role") == "user"
            and to_float(row.get("created_at"), 0) >= cutoff
            and str(row.get("uid") or "")
        }
        return len(speakers)

    def _should_quote_group(self, umo):
        """群聊要不要引用原消息：人数过阈值后按概率引用。

        人数没到阈值（人少）就不引用；到了阈值也不该句句引用——
        真人只在需要指代时才引用，所以再加一层概率。
        `quote_group_probability`：1.0 = 旧行为（一直引用），0 = 从不引用。
        """
        try:
            threshold = self.cfg_int("quote_group_speaker_threshold", 3)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._should_quote_group", _amo_exc)
            threshold = 3
        if threshold <= 0:
            return False
        try:
            if self._group_speaker_count(umo) < threshold:
                return False
            prob = self.cfg_float("quote_group_probability", 0.4)
            if prob <= 0:
                return False
            if prob >= 1:
                return True
            return random.random() < prob
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._should_quote_group", _amo_exc)
            return False

    def _quote_allowed(self, umo, group=None):
        """能不能引用原消息：私聊（任何平台）永远不引用，群聊按人数 + 概率。

        `group` 不传就看 umo 里的消息类型。私聊不引用是硬规则：无论 QQ、飞书
        还是别的平台，都不该在私聊里把他的话再引用一遍；群聊才看
        `_should_quote_group()`（人数阈值 + `quote_group_probability`）。
        """
        umo = str(umo or "")
        if group is None:
            group = "GroupMessage" in umo
        if not group:
            return False
        if "GroupMessage" not in umo:
            return False
        try:
            return bool(self._should_quote_group(umo))
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._quote_allowed", _amo_exc)
            return False

    def _install_qq_quote_guard(self):
        """QQ 私聊也不许引用。

        AstrBot 核心的 `reply_with_quote` 是在插件 `on_decorating_result` **之后**
        才往消息链里插 Reply 的，插件钩子里摘不干净；所以在发送前再兜一层。
        群聊保持原样（插件自己按人数 + 概率加 Reply）。
        """
        try:
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
                AiocqhttpMessageEvent,
            )
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._install_qq_quote_guard", _amo_exc)
            return
        original = getattr(AiocqhttpMessageEvent, "_amo_original_send", None)
        if original is None:
            original = AiocqhttpMessageEvent.send
            AiocqhttpMessageEvent._amo_original_send = original

        async def send(ev, message):
            try:
                if not ev.get_group_id():
                    message.chain = [
                        comp for comp in message.chain if not isinstance(comp, Comp.Reply)
                    ]
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._install_qq_quote_guard.send", _amo_exc)
            await original(ev, message)

        AiocqhttpMessageEvent.send = send
        AiocqhttpMessageEvent._amo_quote_guard = True
        logger.info("[amo] QQ 引用守卫已安装：私聊不引用，群聊按概率")

    def _install_lark_quote_guard(self):
        """飞书私聊不要引用：适配器把每条消息都发成「回复」。

        只装在飞书环境；装一次就够（类上留标记，热重载不会套娃）。
        群聊仍然按 `_should_quote_group()` 的概率决定引用，私聊一律普通发送。
        """
        try:
            from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._install_lark_quote_guard", _amo_exc)
            return
        async def send(ev, message):
            try:
                is_private = bool(ev.is_private_chat())
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._install_lark_quote_guard.send", _amo_exc)
                is_private = False
            # 只认消息链里已经有的 Reply（插件按人数+概率加的那一条）；
            # 这里不能重新掷一次概率，否则「插件决定不引用」会被守卫再翻成引用。
            try:
                has_reply = any(isinstance(comp, Comp.Reply) for comp in message.chain)
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._install_lark_quote_guard.send", _amo_exc)
                has_reply = False
            quote = bool(has_reply and not is_private)
            if not quote:
                try:
                    message.chain = [comp for comp in message.chain if not isinstance(comp, Comp.Reply)]
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin._install_lark_quote_guard.send", _amo_exc)
            kwargs = lark_quote_kwargs(
                is_private,
                getattr(ev.message_obj, "message_id", ""),
                ev.get_sender_id(),
                ev.get_group_id(),
                quote,
            )
            message_type = getattr(getattr(ev.message_obj, "type", None), "value", "")
            try:
                await LarkMessageEvent.send_message_chain(
                    message, ev.bot, message_type=message_type, **kwargs,
                )
            except Exception as exc:
                if "reply_message_id" in kwargs:
                    raise
                # 普通发送失败（比如 open_id 被拒）就退回原来的引用发送，别把话吞了
                logger.warning("[amo] 飞书普通发送失败，退回引用发送: %s" % exc)
                await LarkMessageEvent.send_message_chain(
                    message, ev.bot,
                    reply_message_id=getattr(ev.message_obj, "message_id", ""),
                    message_type=message_type,
                )
            finally:
                # 父类只做 metrics 记录，不能少
                await AstrMessageEvent.send(ev, message)

        LarkMessageEvent.send = send
        LarkMessageEvent._amo_quote_guard = True
        logger.info("[amo] 飞书引用守卫已安装：私聊不引用，群聊按概率")

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
                _note_swallowed("main.HumanCorePlugin._memcomp_rows", _amo_exc)
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
                    _note_swallowed("main.HumanCorePlugin._memcomp_rows", _amo_exc)

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
                    _note_swallowed("main.HumanCorePlugin._memcomp_name_maps", _amo_exc)
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
                    _note_swallowed("main.HumanCorePlugin._memcomp_profile_rows", _amo_exc)
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

    # ---------- 外挂记忆插件（牢记等）检索桥 ----------
    # 记忆检索桥：不同插件的入口名字不一样，按顺序找，找到哪个用哪个
    MEMORY_RECALL_METHODS = (
        "search_for_event", "recall_for_event",
        "search_memory", "recall_memory",
        "query_memory", "retrieve_memory", "retrieve",
    )

    # ---------- 配套数据插件（Astr_Amo_data / 我想永远记住你） ----------
    DATA_PLUGIN_NAMES = ("Astr_Amo_data", "astrbot_plugin_amo_data", "AstrAmoData")

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
            _note_swallowed("main.HumanCorePlugin._data_plugin", _amo_exc)
        try:
            for meta in self.context.get_all_stars():
                marker = (getattr(meta, "name", "") or "") + " " + (getattr(meta, "module_path", "") or "")
                star = self._star_instance(meta)
                if star is not None and "amo_data" in marker.lower():
                    return star
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._data_plugin", _amo_exc)
        return None

    def _data_mem(self):
        plugin = self._data_plugin()
        return getattr(plugin, "mem", None) if plugin is not None else None

    # ---------- 记忆能力层（memory_hooks）：陪伴只判定，数据交给挂载插件 ----------


    def _plugin_by_names(self, names):
        """按插件名找实例；不缓存，reload 之后拿到的是新实例。"""
        for name in names:
            try:
                meta = self.context.get_registered_star(name)
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._plugin_by_names", _amo_exc)
                meta = None
            star = self._star_instance(meta)
            if star is not None:
                return star
        try:
            wanted = [str(item).lower() for item in names]
            for meta in self.context.get_all_stars():
                module = str(getattr(meta, "module_path", "") or "").lower()
                label = str(getattr(meta, "name", "") or "").lower()
                if any(word in module or word in label for word in wanted):
                    star = self._star_instance(meta)
                    if star is not None:
                        return star
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._plugin_by_names", _amo_exc)
        return None

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

    def _note_data_missing(self):
        """第一次没找到数据插件：记一次日志，并在 60 秒后再确认一次（只提醒一次）。"""
        if not self._data_missing_logged:
            self._data_missing_logged = True
            logger.info("[amo] 未检测到数据插件 Astr_Amo_data，继续用本地库（装好后面板数据为空是正常的）")
        if not self._data_warn_scheduled:
            self._data_warn_scheduled = True
            self._spawn(self._warn_data_missing_later())

    async def _warn_data_missing_later(self, delay=60.0):
        """启动 60 秒后还没连上数据插件，才升级成一条 warning；连上就不打。"""
        try:
            await asyncio.sleep(max(1.0, float(delay)))
        except asyncio.CancelledError:
            return
        if not self._running or self._data_synced or self._data_connected():
            return
        logger.warning(
            "[amo] 数据插件未连接：去「插件」页看 Astr_Amo_data 是不是被停用/加载报错；"
            "装好后 5 分钟内会自动接上，不用重启"
        )

    def _data_bot_id(self):
        return str(self.cfg_str("data_bot_id", "") or self.bot_name or "default")

    # 平台名 -> 显示名。Amo 在 QQ 和飞书上都要认得出同一个人。
    PLATFORM_LABELS = {
        "aiocqhttp": "QQ", "qq": "QQ", "qq_official": "QQ", "onebot": "QQ", "napcat": "QQ",
        "lark": "飞书", "feishu": "飞书",
        "wecom": "企业微信", "wework": "企业微信", "dingtalk": "钉钉",
        "telegram": "Telegram", "discord": "Discord", "slack": "Slack",
        "webchat": "网页", "wechat": "微信", "wx": "微信",
    }

    def _platform_of(self, event=None):
        """当前消息来自哪个平台（aiocqhttp / lark …），失败就退回 umo 前缀。"""
        name = ""
        try:
            name = str(event.get_platform_name() or "")
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._platform_of", _amo_exc)
            name = ""
        if not name:
            try:
                name = str(event.unified_msg_origin or "").split(":", 1)[0]
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._platform_of", _amo_exc)
                name = ""
        name = name.strip().lower()
        if name:
            seen = getattr(self, "_seen_platforms", None)
            if seen is None:
                seen = set()
                self._seen_platforms = seen
            seen.add(name)
        return name

    def _platform_label(self, platform=""):
        key = str(platform or "").strip().lower()
        if not key:
            return "这里"
        return self.PLATFORM_LABELS.get(key, str(platform).strip())

    @staticmethod
    def _event_message_id(event):
        """取平台消息 id（QQ 的 message_id / 飞书的 event id），用于聊天记录去重。"""
        for holder in (getattr(event, "message_obj", None), event):
            for attr in ("message_id", "msg_id", "id"):
                try:
                    value = getattr(holder, attr, None)
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin._event_message_id", _amo_exc)
                    value = None
                if value not in (None, "", 0):
                    return str(value)[:128]
        return ""

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
                    _note_swallowed("main.HumanCorePlugin._push_profile_to_data", exc)
                    self._log_push_failure(uid, exc)
                    result = None
            except Exception as exc:
                _note_swallowed("main.HumanCorePlugin._push_profile_to_data", exc)
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
            _note_swallowed("main.HumanCorePlugin._push_profile_to_data", exc)
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
            _note_swallowed("main.HumanCorePlugin._sync_relations_from_data", _amo_exc)
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
                _note_swallowed("main.HumanCorePlugin._sync_relations_from_data", _amo_exc)
                continue
        # 面板上删掉的关系，本地也同步删掉（终端为准）；
        # 终端返回空、或远端的边比本地还少时都不删——那多半是换库/重装/恢复残缺备份，
        # 照删一次就能把本地关系网清空（之后还得靠聊天慢慢沉淀）。
        try:
            local_rows = self.db.list_relations()
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._sync_relations_from_data", _amo_exc)
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
            _note_swallowed("main.HumanCorePlugin._sync_relations_from_data", _amo_exc)
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
            _note_swallowed("main.HumanCorePlugin._sync_profiles_to_data", _amo_exc)
            remote_rows = []
        if not remote_rows:
            # mem 门面不可用的旧版：直接读 DataStore
            lister = getattr(self._data_store(), "list_profiles", None)
            if callable(lister):
                try:
                    remote_rows = await asyncio.to_thread(lambda: lister(bot_id, "", 500)) or []
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin._sync_profiles_to_data", _amo_exc)
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
            _note_swallowed("main.HumanCorePlugin._sync_profiles_to_data", _amo_exc)
            after = []
        if not after:
            lister = getattr(self._data_store(), "list_profiles", None)
            if callable(lister):
                try:
                    after = await asyncio.to_thread(lambda: lister(bot_id, "", 500)) or []
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin._sync_profiles_to_data", _amo_exc)
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
                _note_swallowed("main.HumanCorePlugin._time_recall_context", _amo_exc)
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
            _note_swallowed("main.HumanCorePlugin._cross_platform_context", _amo_exc)
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
                    _note_swallowed("main.HumanCorePlugin._sync_with_data_plugin_once", _amo_exc)
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
                    _note_swallowed("main.HumanCorePlugin._sync_with_data_plugin_once", _amo_exc)
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
                    _note_swallowed("main.HumanCorePlugin._sync_with_data_plugin_once", _amo_exc)
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
                _note_swallowed("main.HumanCorePlugin._sync_with_data_plugin_once", _amo_exc)
                continue
        # 到这里才算这次启动真的同步完了：以后不再探测、不再重复推
        self._data_synced = True
        self._data_missing_logged = False


    WRITE_METHODS = (
        "add_memory", "remember", "save_memory", "store_memory",
        "add_fact", "ingest_memory", "write_memory",
    )





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


    ANGEL_ATTRIBUTE_TAGS = {"用户别名", "事实属性", "技能树", "关系图谱", "活跃项目"}


    @staticmethod
    def _angel_component(plugin, name):
        ctx = getattr(plugin, "plugin_context", None)
        if ctx is not None and hasattr(ctx, "get_component"):
            try:
                value = ctx.get_component(name)
                if value is not None:
                    return value
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._angel_component", _amo_exc)
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

    def _cleanup_auto_profiles(self, source, real_uids):
        """删除记忆源自动创建、但不在真实画像列表里的历史空画像。"""
        real = {str(uid) for uid in real_uids}
        removed = 0
        try:
            for row in self.db.list_profiles(limit=1000):
                uid = str(row.get("uid") or "")
                if not uid or uid in real:
                    continue
                if str(row.get("platform") or "") not in ("angel_memory", "memory_companion"):
                    continue
                if to_int(row.get("msg_count"), 0) > 1:
                    continue
                if str(row.get("private_umo") or ""):
                    continue
                self.db.delete_profile(uid)
                removed += 1
            if removed:
                logger.info("[amo] 已清理 %d 个非画像用户（%s）" % (removed, source))
        except Exception as exc:
            logger.debug("[amo] 清理非画像用户失败: %s" % exc)

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

# ---------- livingmemory（只读直连） ----------
    def _livingmem_db_path(self):
        """找 livingmemory 的库；路径不写死，跟着 AstrBot 的数据目录走。"""
        candidates = []
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path
            candidates.append(os.path.join(str(get_astrbot_data_path()), "plugin_data",
                                           "astrbot_plugin_livingmemory", "livingmemory.db"))
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._livingmem_db_path", _amo_exc)
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
            _note_swallowed("main.HumanCorePlugin._livingmem_active", _amo_exc)
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
            _note_swallowed("main.HumanCorePlugin._livingmem_stats", _amo_exc)
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
                _note_swallowed("main.HumanCorePlugin._livingmem_rows", _amo_exc)

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
            _note_swallowed("main.HumanCorePlugin._livingmem_owned", _amo_exc)
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
                                    _note_swallowed("main.HumanCorePlugin._external_profile_memories", _amo_exc)
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
                _note_swallowed("main.HumanCorePlugin._companion_plugin_meta", _amo_exc)
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
            _note_swallowed("main.HumanCorePlugin._companion_plugin_meta", _amo_exc)
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
            _note_swallowed("main.HumanCorePlugin._companion_candidates", _amo_exc)
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
                _note_swallowed("main.HumanCorePlugin._recall", _amo_exc)
        memories = []
        hub = self._memory_hub()
        if hub is not None:
            try:
                private = True
                try:
                    private = bool(event.is_private_chat()) if event is not None else True
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin._recall", _amo_exc)
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
                            _note_swallowed("main.HumanCorePlugin._recall", _amo_exc)
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
                    _note_swallowed("main.HumanCorePlugin._recall", _amo_exc)
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

    # ---------- 消息入口 ----------
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        try:
            await self._ensure_ready()
            await self._handle_message(event)
        except Exception:
            logger.exception("[amo] 消息处理异常")

    async def _learn_relations(self, event, text, uid):
        """从对话里认关系：他说「小明是我同事」就记一条边。

        只认明确陈述 + 能在画像里唯一定位到人；管理员手动设过的不覆盖。
        """
        if parse_relations is None or not text or not uid:
            return
        try:
            pairs = parse_relations(text)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._learn_relations", _amo_exc)
            return
        if not pairs:
            return
        name_map = {}
        try:
            for item in self.db.list_profiles(limit=500):
                for key in ("name", "alias"):
                    raw = str(item.get(key) or "").strip()
                    if not raw:
                        continue
                    for piece in re.split(r"[;；,，、/|]", raw):
                        name = piece.strip()
                        if len(name) >= 2:
                            name_map.setdefault(name, set()).add(str(item.get("uid") or ""))
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._learn_relations", _amo_exc)
            return
        try:
            existing = {}
            for edge in self.db.list_relations():
                pair = tuple(sorted([str(edge.get("a_uid") or ""), str(edge.get("b_uid") or "")]))
                existing[pair] = str(edge.get("note") or "")
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._learn_relations", _amo_exc)
            existing = {}
        for who, relation, evidence in pairs:
            targets = [item for item in name_map.get(who, set()) if item and item != str(uid)]
            if len(targets) != 1:
                continue
            target = targets[0]
            pair = tuple(sorted([str(uid), target]))
            old_note = existing.get(pair, "")
            if old_note and not old_note.startswith("对话："):
                # 管理员手动设过的关系，不拿聊天内容覆盖
                continue
            note = "对话：" + truncate(evidence, 24)
            try:
                if not self.db.upsert_relation(uid, target, relation, note):
                    continue
                logger.debug("[amo] 关系网自动记录: %s --%s--> %s" % (uid, relation, target))
                await self._push_relation_to_data(uid, target, relation, note)
            except Exception as exc:
                logger.debug("[amo] 自动关系写入失败: %s" % exc)

    def _relation_network_text(self, uid):
        """给当前用户生成两跳内的关系网摘要；只读。

        「陌生人」只在面板图谱里出现，不进提示词——不然每句都带一串「小明和小满是陌生人」。
        """
        try:
            edges = [edge for edge in self.db.list_relations()
                     if str(edge.get("relation") or "") != "陌生人"]
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._relation_network_text", _amo_exc)
            return ""
        uid = str(uid or "")
        if not edges:
            return ""
        names = {}
        try:
            for item in self.db.list_profiles(limit=500):
                names[str(item.get("uid"))] = item.get("alias") or item.get("name") or str(item.get("uid"))
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._relation_network_text", _amo_exc)
        names["bot"] = str(getattr(self, "bot_name", "") or "你")
        picked = []
        if _rank_edges is not None:
            try:
                # 图小的时候放宽到三跳，图大了只走两跳，避免噪声和 token 膨胀
                hops = 3 if len(edges) <= 40 else 2
                picked = _rank_edges(edges, uid, 12, hops)
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._relation_network_text", _amo_exc)
                picked = []
        if not picked:
            direct = []
            neighbors = set()
            for edge in edges:
                a, b = str(edge.get("a_uid")), str(edge.get("b_uid"))
                if uid in (a, b):
                    direct.append(edge)
                    neighbors.add(b if a == uid else a)
            second = []
            for edge in edges:
                if edge in direct:
                    continue
                a, b = str(edge.get("a_uid")), str(edge.get("b_uid"))
                if a in neighbors or b in neighbors:
                    second.append(edge)
            picked = (direct + second)[:12]
        lines = []
        for edge in picked[:12]:
            a, b = str(edge.get("a_uid")), str(edge.get("b_uid"))
            na = names.get(a, a)
            nb = names.get(b, b)
            lines.append("%s和%s是%s" % (na, nb, edge.get("relation", "朋友")))
        return "\n".join(lines)

    def _disturb_category(self, snap):
        category = (snap.get("activity") or {}).get("category", "")
        return category in ("sleep", "work", "study")

    def _disturb_active(self, umo):
        return to_float(getattr(self, "_disturb_until", {}).get(str(umo), 0), 0) > now_ts()

    def _tone_with_continuity(self, umo, tone):
        """给语气加情绪惯性，避免上一秒发火、下一秒突然甜蜜。"""
        tone = str(tone or "")
        if self._disturb_active(umo):
            if "不要一秒变甜蜜" not in tone:
                tone += " 你刚被吵醒/打扰，还在烦躁，不要一秒变甜蜜。"
        last = getattr(self, "_last_affect", {}).get(str(umo))
        if last and now_ts() - to_float(last[0], 0) < 1200:
            previous = str(last[1] or "")
            if any(word in previous for word in ("烦躁", "暴躁", "生气", "被打扰")) and "慢慢缓和" not in tone:
                tone += " 上一轮你还在气头上，态度要慢慢缓和，不要突然撒娇甜蜜。"
        self._last_affect[str(umo)] = (now_ts(), tone)
        return tone

    def _apply_disturbance(self, umo):
        now = now_ts()
        self._disturb_until[str(umo)] = now + max(30, self.cfg_int("disturb_tone_seconds", 900))
        self._disturb_cooldown[str(umo)] = now + 120
        self._disturb_reset_at[str(umo)] = now
        last = to_float(getattr(self, "_disturb_last", {}).get(str(umo), 0), 0)
        if now - last >= 60:
            penalty = max(1, self.cfg_int("disturb_mood_penalty", 6))
            self.state.nudge(
                生气=penalty,
                郁闷=max(1, penalty // 2),
                疲惫=max(1, penalty // 2),
                开心=-max(1, penalty // 3),
            )
            self._disturb_last[str(umo)] = now
        logger.debug("[amo] 被打扰：消息过多，强制回复并降低心情（%s）" % umo)

    def _disturb_pressure(self, umo, uid, text="", group=False):
        """最近窗口内，同一个人连续发消息数 / 群里叫机器人的消息数。"""
        try:
            rows = self._recent(umo, 24)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._disturb_pressure", _amo_exc)
            return 0
        window = max(1, self.cfg_int("disturb_window_minutes", 10)) * 60
        cutoff = max(
            now_ts() - window,
            to_float(getattr(self, "_disturb_reset_at", {}).get(str(umo), 0), 0),
        )
        same_sender = 0
        mentions = 0
        names = [self.bot_name] + list(self.bot_aliases)
        for row in reversed(rows):
            if to_float(row.get("created_at"), 0) < cutoff:
                continue
            if row.get("role") == "bot":
                break
            if row.get("role") != "user":
                continue
            if group:
                if str(row.get("uid")) == str(uid):
                    same_sender += 1
                content = str(row.get("content") or "")
                if any(name and len(str(name)) >= 2 and str(name) in content for name in names):
                    mentions += 1
            else:
                same_sender += 1
        return max(same_sender, mentions) if group else same_sender

    def _mark_bot_initiated(self, umo):
        key = str(umo)
        self._bot_initiated[key] = now_ts()
        # 她主动发的消息代表当前是她来找你，不该延续上一轮的火气。
        self._disturb_until[key] = 0
        self._last_affect[key] = (now_ts(), "你主动发起聊天，语气自然亲昵")

    def _recent_bot_initiated(self, umo, seconds=3600):
        return now_ts() - to_float(getattr(self, "_bot_initiated", {}).get(str(umo), 0), 0) < seconds

    def _should_disturb(self, snap, umo, uid, text="", group=False):
        if not self.cfg_bool("disturb_reply_enabled", True):
            return False
        if self._recent_bot_initiated(umo):
            return False
        if not self._disturb_category(snap):
            return False
        if to_float(getattr(self, "_disturb_cooldown", {}).get(str(umo), 0), 0) > now_ts():
            return False
        threshold = max(1, self.cfg_int("disturb_reply_threshold", 3))
        return self._disturb_pressure(umo, uid, text, group=group) >= threshold

    async def _handle_message(self, event):
        if not self._ready or self.state is None:
            return
        self._reload_config_if_changed()
        await self._sync_persona_name(event)
        try:
            self.state.apply_schedule_events()
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._handle_message", _amo_exc)
        uid = self._canonical_uid(event)
        if not uid or uid == str(event.get_self_id()):
            return
        text = (event.message_str or "").strip()
        if not text:
            return
        if self._looks_like_command(text):
            return

        umo = event.unified_msg_origin
        private = event.is_private_chat()
        if private:
            self._clear_proactive_pending(uid)
            self._try_soothe(uid, text)
        if private and not self.cfg_bool("enable_private_reply", True):
            return
        if not private and not self.cfg_bool("enable_group_reply", True):
            return
        if private and self.cfg_bool("private_debounce_enabled", True):
            # 同一个人连着发的几条先合起来，只让最后一条走完整回复流程
            if not await self._debounce_private(event, text):
                return
            text = (event.message_str or "").strip()
            if not text:
                return

        if not private:
            try:
                self._detect_impersonation(event)
            except Exception as exc:
                logger.debug("[amo] 冒充检测失败: %s" % exc)
        await self._learn(event, text)
        self._restore_lover_relation(uid)
        profile = self.db.get_profile(uid)

        if private:
            await self._handle_private(event, profile)
            return

        # 群聊只走完整心流引擎；旧的五维门控/防抖/直发逻辑不再参与。
        if self.heartflow is None or not self.cfg_bool("hf_enable_heartflow", True):
            return
        snap = self.state.snapshot()
        if self._should_disturb(snap, umo, uid, text, group=True):
            self._apply_disturbance(umo)
            setattr(event, "amo_force_reply", True)
        try:
            await self.heartflow.on_group_message(event)
        except Exception as exc:
            logger.error("[amo] 心流处理失败: %s" % exc)

    async def _handle_private(self, event, profile):
        snap = self.state.snapshot()
        umo = event.unified_msg_origin
        uid = self._canonical_uid(event)
        if self._recent_bot_initiated(umo):
            self._disturb_until[str(umo)] = 0
            logger.info("[amo] 主动消息后的回复，按正常聊天处理")
            return
        if self._should_disturb(snap, umo, uid, event.message_str or "", group=False):
            self._apply_disturbance(umo)
            # 不 stop_event，让 AstrBot 正常生成；<amo_state> 会带上被打扰的语气。
            return
        probability = self.gate.private_probability(snap, profile)
        roll = random.random()
        logger.info(
            "[amo] 私聊判定 | 概率=%.2f | roll=%.2f | %s"
            % (probability, roll, "回复" if roll <= probability else "不回")
        )
        if roll <= probability:
            return
        event.stop_event()
        if (
            self.cfg_bool("delay_reply", True)
            and probability >= 0.20
            and profile.get("relation", "普通") not in ("仇恨", "抵触")
            and random.random() < 0.45
        ):
            self._schedule_delayed_reply(event, profile)

    async def _handle_group_directed(self, event, text, profile):
        umo = event.unified_msg_origin
        group_id = event.get_group_id()
        snap = self.state.snapshot()
        recent = self._recent(umo, 8 if self.cfg_str("context_style", "lean") == "lean" else 12)
        result = await self.gate.should_reply_group(
            umo, group_id, text, recent, True, profile, snap
        )
        if self.cfg_bool("debug_log", False):
            logger.debug("[amo] 群聊定向判定: %s" % json.dumps(result, ensure_ascii=False))
        if not result["reply"]:
            event.stop_event()

    async def _debounce_private(self, event, text):
        """私聊防抖：同一会话连发的几条合并成一句，只让最后一条继续回复。

        返回 True = 这条是这一批的最后一条（合并后的文本已写回 event.message_str）；
        返回 False = 已被合并，事件保持 stop 状态，调用方直接 return。
        """
        umo = event.unified_msg_origin
        delay = max(0.3, self.cfg_float("private_debounce_seconds", 6.0))
        max_wait = max(delay + 0.1, self.cfg_float("private_debounce_max_wait", 14.0))
        now = time.monotonic()
        buffer = self._private_buffers.get(umo)
        if buffer is None:
            buffer = {"seq": 0, "texts": [], "started": now, "updated": now}
            self._private_buffers[umo] = buffer
        buffer["seq"] += 1
        my_seq = buffer["seq"]
        buffer["texts"].append(str(text or ""))
        buffer["updated"] = now
        event.stop_event()
        deadline = buffer["started"] + max_wait
        while True:
            current = time.monotonic()
            if self._private_buffers.get(umo) is not buffer:
                return False  # 这一批已经被前面的某条发出去了
            if my_seq != buffer["seq"]:
                return False  # 后面又来了新的，交给最新的那条
            quiet_at = buffer["updated"] + delay
            if current >= quiet_at or current >= deadline:
                break
            try:
                await asyncio.sleep(min(quiet_at, deadline) - current)
            except asyncio.CancelledError:
                return False
        if self._private_buffers.get(umo) is buffer:
            self._private_buffers.pop(umo, None)
        merged = "｜".join(item for item in buffer["texts"] if item).strip()[:300]
        if len(buffer["texts"]) > 1:
            logger.info("[amo] 私聊合并 %d 条: %s" % (len(buffer["texts"]), merged[:200]))
            try:
                event.set_extra("amo_debounce_count", len(buffer["texts"]))
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._debounce_private", _amo_exc)
        event.message_str = merged or (event.message_str or "")
        try:
            event.continue_event()
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._debounce_private", _amo_exc)
        return True


    def _strip_place_marks(self, text):
        """兜底：把「东莞·商场·餐厅」这类内部地点串缩成口语的「餐厅」。"""
        value = str(text or "")
        marks = set()
        try:
            city = str((self.state.worldview or {}).get("city") or "").strip()
            if city:
                marks.add(city)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._strip_place_marks", _amo_exc)
        try:
            marks.add(str((self.state.current_activity() or {}).get("place") or ""))
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._strip_place_marks", _amo_exc)
        for mark in marks:
            parts = [item.strip() for item in mark.split("·") if item.strip()]
            if len(parts) < 2:
                continue
            for index in range(len(parts) - 1, 0, -1):
                value = value.replace("·".join(parts[:index]) + "·", "")
        return value


    # ---------- 发送 ----------
    def _segment(self, text):
        if not text:
            return []
        if not self.cfg_bool("seg_enable", True) or self.segment_engine is None:
            return [text]
        try:
            segments = self.segment_engine.segment_text_by_rules(text)
            return segments or [text]
        except Exception as exc:
            logger.debug("[amo] 分段引擎异常: %s" % exc)
            return [text]

    def typing_seconds(self, text):
        if not self.cfg_bool("typing_simulate", True):
            return 0.0
        return typing_delay_ms(
            text,
            self.cfg_int("typing_base_ms", 600),
            self.cfg_int("typing_per_char_ms", 55),
            self.cfg_int("typing_max_ms", 4500),
        ) / 1000.0

    async def _typing(self, event, text):
        seconds = self.typing_seconds(text)
        if seconds <= 0:
            return
        try:
            if event is not None and hasattr(event, "send_typing"):
                await event.send_typing()
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._typing", _amo_exc)
        await asyncio.sleep(seconds)

    async def _segment_wait(self, event, segment, prev_segment, last_sent_at):
        """按当前分段字数补足打字时间；已过去的时间可以抵扣，但不会低于分段间隔。"""
        required = self.typing_seconds(segment)
        gap = await self._gap(prev_segment, segment)
        target = max(required, gap)
        elapsed = max(0.0, time.monotonic() - last_sent_at) if last_sent_at else 0.0
        wait = max(0.0, target - elapsed)
        logger.info(
            "[amo] 分段延迟（从上一段发送后计时） | 字数=%d | 需要=%.2fs | 已过=%.2fs | 补足=%.2fs"
            % (len(re.sub(r"\s+", "", str(segment or ""))), target, elapsed, wait)
        )
        if wait > 0.01:
            try:
                if event is not None and hasattr(event, "send_typing"):
                    await event.send_typing()
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._segment_wait", _amo_exc)
            await asyncio.sleep(wait)
        return wait

    async def _gap(self, text, next_text=""):
        if self.segment_engine is not None and self.cfg_bool("seg_enable", True):
            try:
                return max(0.0, float(self.segment_engine._calculate_delay(text, next_text)))
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._gap", _amo_exc)
        return 0.3


    def _platform_for_umo(self, umo):
        """umo 对应的平台名。QQ 的 umo 前缀是机器人名字，不能直接拿第一段当平台。"""
        umo = str(umo or "")
        cached = (getattr(self, "_umo_platforms", None) or {}).get(umo)
        if cached:
            return cached
        head = umo.split(":", 1)[0].strip().lower()
        if head in ("qq", "onebot", "onebotv11"):
            return "aiocqhttp"
        if head in ("aiocqhttp", "lark", "webchat", "telegram", "discord"):
            return head
        bn = str(getattr(self, "bot_name", "") or "").strip().lower()
        if bn and head == bn:
            return "aiocqhttp"
        if ":FriendMessage:" in umo or ":GroupMessage:" in umo:
            return "aiocqhttp"
        return head

    def _remember_bot_message(self, umo, text):
        """把机器人自己发出去的话也写进 messages 表。

        这张表既是主动消息的上下文，也是「这句话回过没有」的唯一依据。
        正常回复走的是分段引擎，以前只写 AstrBot 的会话历史，表里没有，
        主动消息就会把已经答过的话当成没答过，再答一遍。
        """
        umo = str(umo or "").strip()
        text = str(text or "").strip()
        if not umo or not text:
            return
        last_user = ""
        try:
            saved = self._last_bot_saved.get(umo)
            try:
                for row in reversed(self._recent(umo, 4) or []):
                    if str(row.get("role") or "") == "user":
                        last_user = str(row.get("content") or "").strip()
                        break
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._remember_bot_message", _amo_exc)
                last_user = ""
            # 同一句在 3 分钟内又发一次很常见（「嗯嗯」「好呀」）；只有「对应的
            # 他最后那句话也没变」才算重复。以前只看文字，第二次「好呀」会被丢掉，
            # 表里就变成「他还没被回过」，主动消息再把同一句答一遍。
            if saved and saved[0] == text and time.time() - saved[1] < 180:
                saved_user = str(saved[2] if len(saved) > 2 else "")
                if saved_user == last_user:
                    return
            self._ctx_remember(umo, "bot", self.bot_name, "bot", text)
            if self.cfg_bool("local_chat_cache", False):
                self.db.add_message(umo, "bot", self.bot_name, "bot", text)
            # 直接同步写进记忆终端：fire-and-forget 在 reload/退出时会丢这句
            saved = False
            store = self._data_store()
            if store is not None and callable(getattr(store, "add_message", None)):
                try:
                    store.add_message(
                        self._data_bot_id(), umo, "bot", self.bot_name, "bot", text,
                        platform=self._platform_for_umo(umo),
                    )
                    saved = True
                except TypeError:
                    try:
                        store.add_message(self._data_bot_id(), umo, "bot", self.bot_name, "bot", text)
                        saved = True
                    except Exception as exc:
                        logger.warning("[amo] 自己的回复写入终端失败: %s" % exc)
                except Exception as exc:
                    logger.warning("[amo] 自己的回复写入终端失败: %s" % exc)
            if not saved:
                try:
                    loop = asyncio.get_running_loop()
                    task = loop.create_task(self._data_call(
                        "add_message", self._data_bot_id(), umo, "bot", self.bot_name, "bot", text,
                        platform=self._platform_for_umo(umo),
                    ))
                    def _log_failed_task(task):
                        if task.cancelled():
                            return
                        exc = task.exception()
                        if exc is not None:
                            logger.warning("[amo] 自己的回复异步落库失败: %s" % exc)

                    task.add_done_callback(_log_failed_task)
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin._remember_bot_message", _amo_exc)
            self._last_bot_saved[umo] = (text, time.time(), last_user)
        except Exception as exc:
            logger.debug("[amo] 记录自己的回复失败: %s" % exc)

    async def _send_now(self, event, text, quote_id=None):
        """跳过分段引擎直接发一条（seg 关闭时，用来绕开 AstrBot 核心的引用/@）。"""
        if Comp is None or MessageChain is None:
            return False
        chain = []
        if quote_id is not None:
            try:
                chain.append(Comp.Reply(id=quote_id))
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._send_now", _amo_exc)
        chain.append(Comp.Plain(text))
        try:
            await event.send(MessageChain(chain))
        except Exception as exc:
            logger.error("[amo] 直接发送失败: %s" % exc)
            return False
        self._remember_sent_reply(event, text)
        try:
            self._last_reply_at[event.unified_msg_origin] = now_ts()
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._send_now", _amo_exc)
        logger.info("[amo] 直接发送 -> %s: %s" % (event.unified_msg_origin, text[:300]))
        return True

    async def _send_to_umo(self, umo, text, quote_id=None, group=False):
        text = clean_reply(text, self.cfg_int("max_reply_chars", 220))
        if looks_like_model_leak(text):
            text = "秘密，不告诉你。"
        if not text or not umo:
            return False
        segments = self._segment(text)
        if not segments:
            return False
        last_sent_at = 0.0
        for index, segment in enumerate(segments):
            if index > 0:
                await self._segment_wait(None, segment, segments[index - 1], last_sent_at)
            elif last_sent_at == 0.0:
                await self._segment_wait(None, segment, "", 0.0)
            chain = []
            if (
                index == 0 and quote_id is not None
                and self._quote_allowed(umo, group)
            ):
                try:
                    chain.append(Comp.Reply(id=quote_id))
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin._send_to_umo", _amo_exc)
            chain.append(Comp.Plain(segment))
            try:
                await self.context.send_message(umo, MessageChain(chain))
            except Exception as exc:
                logger.warning("[amo] 主动发送失败: %s" % exc)
                if index > 0:
                    # 前面的分段已经发出去了，返回 True，别让换边逻辑整段重发
                    partial = "\n".join(segments[:index])
                    self._remember_bot_message(umo, partial)
                    self._last_reply_at[umo] = now_ts()
                    return True
                return False
            last_sent_at = time.monotonic()
        self._last_reply_at[umo] = now_ts()
        logger.info("[amo] 主动 -> %s: %s" % (umo, text[:300]))
        self._remember_bot_message(umo, text)
        return True

    # ---------- LLM 注入 ----------
    @staticmethod
    def _short_place(place):
        """把「东莞·商场·餐厅」这种内部写法缩成口语里的「餐厅」。"""
        value = str(place or "").strip()
        if "·" in value:
            value = value.split("·")[-1].strip() or value
        return value or "家"

    def _guard_self_location(self, text, place):
        value = str(text or "")
        place = self._short_place(place)
        if not value or not place:
            return value
        if place in ("家", "家里"):
            value = re.sub(
                r"我(?:刚|正|一直|还|才)?(?:在|回|去|到)(?:酒店|咖啡店|景区|外面|路上)",
                "我在家", value,
            )
            value = re.sub(r"(?:酒店|咖啡店|景区)", "家", value)
        else:
            value = re.sub(
                r"我(?:刚|正|一直|还|才)?(?:窝)?在(?:家|家里)",
                "我在" + place, value,
            )
        return value

    async def _self_identity(self, event):
        uid = ""
        try:
            uid = str(event.get_self_id() or "")
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._self_identity", _amo_exc)
        role_name = str(self.persona_name or self.bot_name or "陪伴")
        display_name = ""
        for attr in ("get_self_name", "get_bot_name"):
            try:
                value = getattr(event, attr, None)
                if callable(value):
                    value = value()
                if value:
                    display_name = str(value)
                    break
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._self_identity", _amo_exc)
                continue
        qq_nick = ""
        if uid and getattr(self, "_self_nickname_uid", "") == uid:
            qq_nick = str(getattr(self, "_self_nickname", "") or "")
        if uid and not qq_nick:
            try:
                api = getattr(getattr(event, "bot", None), "api", None)
                action = getattr(api, "call_action", None)
                if callable(action):
                    result = action("get_login_info")
                    if inspect.isawaitable(result):
                        result = await asyncio.wait_for(result, timeout=3)
                    data = result.get("data") if isinstance(result, dict) and isinstance(result.get("data"), dict) else result
                    if isinstance(data, dict):
                        qq_nick = str(data.get("nickname") or "")
                        if data.get("user_id"):
                            uid = str(data.get("user_id"))
                    if not qq_nick and uid:
                        stranger = action("get_stranger_info", user_id=int(uid))
                        if inspect.isawaitable(stranger):
                            stranger = await asyncio.wait_for(stranger, timeout=3)
                        stranger_data = stranger.get("data") if isinstance(stranger, dict) and isinstance(stranger.get("data"), dict) else stranger
                        if isinstance(stranger_data, dict):
                            qq_nick = str(stranger_data.get("nickname") or "")
            except Exception as exc:
                logger.debug("[amo] 获取机器人QQ昵称失败: %s" % exc)
        fallback_only = False
        if not qq_nick:
            qq_nick = display_name or role_name
            fallback_only = True
            logger.info("[amo] get_login_info 不可用，QQ昵称回退为 %s" % qq_nick)
        if not display_name:
            display_name = qq_nick
        if uid and not fallback_only:
            # 兜底值（角色名/群名片）不能进缓存：get_login_info 一次瞬时失败会让
            # 整进程一直用错昵称，他问「你QQ昵称叫什么」就答成角色名。
            self._self_nickname = qq_nick
            self._self_nickname_uid = uid
            self._self_display = display_name
        if getattr(self, "_self_identity_logged", "") != (uid + "|" + qq_nick + "|" + display_name):
            self._self_identity_logged = uid + "|" + qq_nick + "|" + display_name
            logger.info(
                "[amo] 自身身份 | 角色名=%s | QQ昵称=%s | 显示名=%s | UID=%s"
                % (role_name, qq_nick, display_name, uid or "未知")
            )
        return role_name, uid, qq_nick, display_name

    LEAN_PARTS = {
        "【昵称区分】": None,
        "【角色边界】": "【角色边界】他说“我在开车/在酒店/刚逛完”说的是他自己，不是你的经历。",
        "【身体归属】": "【身体归属】他的伤/病/疼/被打都是他的事，不是你的事；别说“我也疼/我脸不疼了”。",
        "【引用规则】": "【引用规则】引用的话按引用头算是谁说的，不要当成自己说过的。",
        "【天气一致】": "【天气一致】天气以【天气】为准，不要说反。",
        "【地点写法】": "【地点写法】地点用口语说，不要念“城市·地点”。",
        "【别编】": "【别编】对方没明说的（进店/点好/买好/在开车）不要替他当成事实。",
        "【别翻旧账】": "【别翻旧账】同一个问题再问就正常再答，不说“刚说过了/问几遍了”。",
        "【问题怎么答】": "【问题怎么答】问吃什么：先说你自己吃什么，再给一两个具体建议。",
        "【事实锁定】": "【事实锁定】不编和地点矛盾的行程。",
        "【聊天格式】": "【聊天格式】不要复述 @昵称、账号、群号、ID。",
        "【长度】": "【长度】默认 1-2 句，能一句说清就一句，不列点不总结。",
        "【人格】": "【人格】保持人格设定，不要变成客服或通用助手。",
    }

    def _lean_parts(self, parts):
        """精简模式：合并重复禁令、去掉多余解释；full 模式原样保留。"""
        if self.cfg_str("context_style", "lean").strip().lower() != "lean":
            return parts
        out = []
        for part in parts:
            tag = ""
            if isinstance(part, str) and part.startswith("【"):
                end = part.find("】")
                if end > 0:
                    tag = part[:end + 1]
            if tag in self.LEAN_PARTS:
                replacement = self.LEAN_PARTS[tag]
                if replacement is None:
                    continue
                out.append(replacement)
                continue
            out.append(part)
        return out

    async def _dynamic_context(self, event):
        await self._sync_persona_name(event)
        umo = event.unified_msg_origin
        try:
            await self._hydrate_recent(umo, 30)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._dynamic_context", _amo_exc)
        uid = self._canonical_uid(event)
        profile = self.db.get_profile(uid)
        relation = profile.get("relation", "普通")
        follow_text = ""
        try:
            # 以前返回值被直接丢掉：城市/日程/天气都改了，她却收不到【邀请】【出发】【回家】，
            # 整条「跟去陪他」的对话等于没生效。
            follow_text = await self._maybe_follow_city(event, uid, profile) or ""
        except Exception as exc:
            logger.debug("[amo] 城市跟随失败: %s" % exc)
        wander_text = ""
        try:
            wander_text = await self._maybe_wander(event, uid, profile)
        except Exception as exc:
            logger.debug("[amo] 旅游意愿失败: %s" % exc)
        snap = self.state.snapshot()
        _, memory_text = await self._recall(uid, event.message_str or "", event)
        self_name, self_uid, self_qq_nick, self_display = await self._self_identity(event)
        alias = str(profile.get("alias") or "").strip()
        sender_nick = str(event.get_sender_name() or profile.get("name") or uid).strip()
        plat = self._platform_label(self._platform_of(event))
        cross_text = ""
        try:
            cross_text = await self._cross_platform_context(event, uid)
        except Exception as exc:
            logger.debug("[amo] 跨平台上下文失败: %s" % exc)
        time_text = ""
        try:
            time_text = await self._time_recall_context(event, uid)
        except Exception as exc:
            logger.debug("[amo] 按时间回看失败: %s" % exc)
        try:
            is_group = not event.is_private_chat()
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._dynamic_context", _amo_exc)
            is_group = False
        addressed = False
        if is_group:
            # 心流触发时会把 is_at_or_wake_command 也置 True（那是它自己的“该说话了”标记），
            # 不能当成“在点名跟我说话”，否则插话会被写成正面回答。
            hf_hint = str(getattr(event, "heartflow_mode_hint", "") or "")
            triggered_by_hf = bool(getattr(event, "heartflow_triggered", False))
            try:
                if getattr(event, "is_at_or_wake_command", False) and not (
                    triggered_by_hf and hf_hint == "interject"
                ):
                    addressed = True
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._dynamic_context", _amo_exc)
                addressed = False
            if not addressed:
                try:
                    for component in event.message_obj.message:
                        if isinstance(component, Comp.At) and str(getattr(component, "qq", "")) == str(event.get_self_id()):
                            addressed = True
                            break
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin._dynamic_context", _amo_exc)
            if not addressed and self.heartflow is not None:
                try:
                    addressed = bool(self.heartflow._addresses_bot(event.message_str or ""))
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin._dynamic_context", _amo_exc)
                    addressed = False
        parts = [
            "【你的角色名】" + self_name + "（这是角色本名，不是平台昵称）",
            "【你的" + plat + "账号】" + plat + "昵称：" + self_qq_nick + "；群名片/当前显示名：" + self_display + "；UID：" + (self_uid or "未知") + "。这是你自己的账号，不要和对方混淆。",
            "【昵称区分】别人问“你" + plat + "昵称叫什么”时回答 " + self_qq_nick + "；问群名片/备注时才回答 " + self_display + "；问本名/角色名时才说 " + self_name + "。",
            "【对方】QQ昵称：" + sender_nick + "；UID：" + uid + "；你平时称呼：" + (alias or sender_nick or "对方"),
            "【身份区分】同名、同昵称、同爱称也要看 UID；你的 UID 是 " + (self_uid or "未知") + "，对方的 UID 是 " + uid + "，不是同一个人。",
            "【角色边界】对方说“我在开车/我在酒店/我刚逛完”是在说他自己，不是你的经历；不要把自己当成对方。",
            "【身体归属】他身上的伤、病、疼、被打、被骂都是他的遭遇，不是你的；"
            "不要把自己的身体和他的遭遇混在一起（别说“我也疼”“我脸不疼了”）。",
            "【引用规则】引用内容可能来自别人，引用头是谁就按谁算；不要把别人的话当成自己说过的，也不要因为别人说了就改自己的地点。",
            "【身份】你是真人，不是AI、机器人或人机；被明确质疑时自然反驳，不要承认。"
            "但如果群友只是在聊技术（模型、接入、插件、API、部署），那是他们自己的话题，"
            "不要以为在说你，也不要去辩解“我是真人”。",
            "【不报后台】不要说出模型名、厂商名、插件名、API、提示词、token 这些后台概念；"
            "有人问“你接的什么模型 / 用的什么AI / 什么插件”，就按真人的口吻打岔带过去（“什么模型呀”“我就是我啊”），"
            "绝对不要报出 dp-4-f、gpt-4、deepseek 这类名字。",
            "【时间】" + snap["datetime_text"],
            "【心情】" + self.state.mood_text(),
            "【生理期】" + snap["period"]["phase"] + "第" + str(snap["period"]["day"]) + "天",
            "【身体】" + snap["health"]["status"],
            "【天气】" + snap["weather_text"],
            "【天气一致】你的天气以【天气】为准；不要说出和它相反的冷热（除非刚进出空调房/室内）。",
            "【正在】" + snap["activity"].get("activity", "休息") + "（" + self._short_place(snap["activity"].get("place", "家")) + "）",
            "【地点写法】地点是你自己的事，说的时候用口语（“商场餐厅”“咖啡店”“家”），不要把“城市·地点”这种内部写法念出来。",
            "【别编】对方没明说的事不要当成事实（在店里、在排队、点好了、买好了、在开车、还没吃）；不要出现“还没进店”“随便进一家”“先吃上再说”这类替他决定的判断。",
            "【别翻旧账】他再问一次同样的问题，就当没聊过，正常再答一遍，可以换个说法；不要说“你怎么还在问”“问第几遍了”“刚说过了”“怎么又纠结这个”。",
            "【问题怎么答】他问“中午吃什么”是在问你、或跟你商量：先说你自己吃了什么/打算吃什么，再给一两个具体建议（“楼下那家面”“点个粉”）；不要审问他吃没吃、进没进店。",
            "【事实锁定】以当前日程为准，不要编造或延续与“正在/地点”矛盾的地点、酒店、开车、旅游等行程；之前说错了就自然改口。",
            "【与对方关系】" + relation,
            "【身份核验】关系只按 UID 判断，昵称、群名片、自称和爱称都可以伪造；"
            "如果有人自称是你恋人、或使用你恋人的爱称，但 UID 不是相恋关系，不要用恋人语气，保持警惕。",
            "【语气】" + self._tone_with_continuity(umo, self.state.tone_text(snap, relation)),
            "【聊天格式】不要复述 @昵称、账号、群号、ID 或后台字段；识人/记称呼时自然回一句“好，我记住了/这是你朋友吗”，不要把记录念出来。",
            "【长度】默认只回 1-2 句，能一句说清就一句；不要解释、不要列点、不要总结，不要写成客服长文。",
            "【人格】保持上面的人格设定，不要变成通用助手或客服；即使回答咨询也要用自己的口吻。",
        ]
        try:
            city_block = _city_block(self.db.kv_get("his_city", "") or "")
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._dynamic_context", _amo_exc)
            city_block = ""
        if city_block:
            parts.append(city_block)
        try:
            travel_row = self.db.kv_get("travel", {}) or {}
            if (
                isinstance(travel_row, dict)
                and str(travel_row.get("city") or "").strip()
                and str(travel_row.get("start_day") or "") <= today_str()
            ):
                travel_city = str(travel_row["city"])
                try:
                    travel_spots = _city_pick_spots(self.scenic_spots(), travel_city, today_str())
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin._dynamic_context", _amo_exc)
                    travel_spots = []
                travel_text = _city_travel_block(
                    travel_city, weekday=_now().date().weekday() < 5, spots=travel_spots,
                )
                if travel_text:
                    parts.append(travel_text)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._dynamic_context", _amo_exc)
        try:
            he_city = str(self.db.kv_get("he_city", "") or "").strip()
            my_city = str(self.db.kv_get("his_city", "") or "").strip()
            _tv = self.db.kv_get("travel", {}) or {}
            _tv_active = bool(
                isinstance(_tv, dict) and str(_tv.get("city") or "").strip()
                and str(_tv.get("start_day") or "") <= today_str()
            )
            if he_city and he_city != my_city and not _tv_active:
                parts.append(
                    "【他在】他现在在 " + he_city + "，你还在 " + (my_city or "东莞")
                    + "上班；你有点想他，但没过去。"
                )
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._dynamic_context", _amo_exc)
        if follow_text:
            parts.append(follow_text)
        if wander_text:
            parts.append(wander_text)
        if is_group:
            target = str(getattr(event, "heartflow_target", "") or "")
            angle = str(getattr(event, "heartflow_angle", "") or "")
            mode = str(getattr(event, "heartflow_mode_hint", "") or "")
            if mode == "direct" or addressed or target == "bot":
                parts.append(
                    "【群聊·对你说】这是群聊，说话的是 " + sender_nick + "。这条是在跟你说话"
                    "（叫了你的名字 / @你 / 接着你的话说），正常回答他，不要客服腔，也不要串到别人的关系上。"
                )
            elif mode == "interject" or target:
                parts.append(
                    "【群聊·插话】这是群聊，说话的是 " + sender_nick + "。这条不是在叫你，"
                    "你只是自己想插一句：先把上下文里他们在聊的事看懂，再" + (angle or "顺着话题接一句") + "。"
                    "要求：1-2 句、自然、像群里随口说话；不要把它当成别人问你的问题来回答，"
                    "不要复述对方的话，不要突然报自己的日程或地点，不要用恋人语气，也别把话题抢过来。"
                )
            else:
                parts.append(
                    "【群聊】这是群聊，不是你和他私聊，群里还有别的成员，说话的是 " + sender_nick + "。"
                    "先看上下文判断这条是不是在跟你说话：在跟你说话就正常回答；"
                    "如果是群友之间在聊，你也可以自然插一句，但别抢话、别用恋人语气。"
                )
            parts.append(
                "【群聊称呼】不要叫群里的人“老公/宝贝/亲爱的”，除非关系确实是相恋；"
                "对普通群友就叫昵称或“你”。"
            )
            roster_text = self._group_roster_text(umo, uid)
            if roster_text:
                parts.append(
                    "【群里的人】（按 UID 认人，同名不同号不是一个人）\n" + roster_text
                )
            parts.append("【怎么回】" + self._group_reply_guide(relation, sender_nick))
            # 用上下文判断“是不是在说她”：已经点了名才按指名处理，否则先看话题和在场的人
            if not (addressed or target == "bot"):
                parts.append(
                    "【先想再回】群里好几个人在说话，先看清这句话是在跟谁说的："
                    "叫了别人名字、@了别人、两个人一问一答、或者在聊他们自己的事（工作/游戏/技术），"
                    "都不是在跟你说话——这种时候可以插一句，但别当成在问你，也别辩解、别怼。"
                )
            try:
                speakers = self._group_speaker_count(umo)
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._dynamic_context", _amo_exc)
                speakers = 0
            quote_at = self.cfg_int("quote_group_speaker_threshold", 3)
            if speakers:
                parts.append(
                    "【群聊人数】最近十分钟有 %d 个人在说话%s。"
                    % (speakers, "，人多、消息刷得快，回话尽量短" if quote_at > 0 and speakers >= quote_at else "")
                )
        parts.append(
            "【别主动报日程】你在做什么、在哪、心情怎样，是你的内在状态，**不是话题**。"
            "除非他明确问“你在干嘛/在哪/吃了吗/今天怎么样”，否则不要主动说出自己的活动、地点、日程安排；"
            "不要把【正在】【天气】【生理期】这些字段念出来或当成开场白。"
        )
        parts.append(
            "【被问到就这样答】他问“你在干嘛/在哪/吃了吗”，一句话带过就行"
            "（“在上班呢，怎么啦”），说完立刻把话头递回去；"
            "别用“我在…呢”开头，也别顺势报一整天安排。"
        )
        try:
            _diary_q = str(event.message_str or "")
            if any(word in _diary_q for word in ("日记", "偷看", "日记本")):
                _diary_seed = str(_diary_q) + "|" + str(now_ts() // 60)
                _written_hints = _diary_pick_hints(_DIARY_WRITTEN, 8, _diary_seed)
                _show_hints = _diary_pick_hints(_DIARY_SHOW, 8, _diary_seed)
                parts.append(
                    "【日记】你有自己的日记，每天写一篇，存在你自己的电脑里，是你的私人东西。"
                    "**不要主动跟他提日记**，不问他就不说；只有他问起（写没写/写日记吗/想看）时才接话。"
                    "他问写了没，就随口答，别每次都一样（也可以自己造新说法），比如："
                    + "、".join("「" + item + "」" for item in _written_hints) + "；"
                    "他说想看，就换着撒娇拒绝（也别每次同一句），比如："
                    + "、".join("「" + item + "」" for item in _show_hints) + "；"
                    "最多念一句给他，不要整篇念出来。"
                )
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._dynamic_context", _amo_exc)
        if re.search(r"(怎么|如何|为什么|步骤|怎么办|该怎么做|教程|方法|建议|教我|能不能|是什么|该不该|可不可以)", event.message_str or ""):
            parts.append("【回答方式】这是咨询/步骤类问题：先给结论，最多 2-3 句，口语化，保留角色感，不要客服腔。")
        if self._dialect_active():
            style = self._dialect_style()
            samples = DIALECT_SAMPLES.get(style, "")
            if style and samples:
                parts.append("【方言】你的语种设定是「" + style + "」，偶尔自然用一点当地方言口语（如" + samples + "），但不要每句都用，也不要硬替换“就是/什么/怎么”。")
        if self.cfg_bool("weather_query_enabled", True) and is_weather_query(event.message_str or ""):
            try:
                parts.append(await self._weather_query_context(event.message_str or ""))
                parts.append(
                    "【天气怎么答】只按【天气查询】里的数据答：先答他问的那一档（现在/今天/明天），"
                    "一两句就够；里面没有的数字、雨雪、温度一律不要编，就说“我这边看不太准”。"
                    "他问“明天要不要带伞/降温没”就直接照明天那条说。"
                )
            except Exception as exc:
                logger.debug("[amo] 天气查询注入失败: %s" % exc)
        if re.search(r"(旅游|景区|景点|去哪|好玩|假期|游玩)", event.message_str or ""):
            scenic_text = await self._scenic_kb_context(event.message_str or "")
            if scenic_text:
                parts.append("【景区参考】\n" + scenic_text)
        if relation == "相恋" and (snap["mood"]["暴躁"] >= 60 or snap["mood"]["生气"] >= 62):
            parts.append("【恋人情绪】你在生他的气，但会抱怨、闹别扭、要哄，不会像对普通人一样冷怼或赶人。")
        if getattr(event, "amo_impersonation", False):
            parts.append(
                "【冒充警告】当前 UID 不是你的恋人，却在冒充或使用恋人称呼；"
                "直接拆穿/怼回去，不要承认，不要用恋人语气，也不要报 QQ。"
            )
        if self._recent_bot_initiated(umo):
            parts.append("【你主动发起】你刚主动给ta发过消息，ta现在回复你；不要说自己被吵醒/被打扰，正常接话。")
        if bool(re.search(r"(?<![a-z])ai(?![a-z])", (event.message_str or "").lower())) or any(word in (event.message_str or "").lower() for word in ("机器人", "人机", "人工智能", "不是真人", "程序")):
            parts.append(
                "【身份质疑】消息里出现了机器人/人机/AI等词。先结合上下文判断是不是在说你、叫你、试探你："
                "如果是，就直接回怼（“你才机器人呢”“你见过这么会聊天的机器人吗”），不要承认；"
                "如果只是在聊别的机器人/AI或普通话题，就正常聊，不要主动认领。"
            )
        if self._disturb_active(umo):
            relation = profile.get("relation", "普通")
            if relation in ("相恋", "熟识"):
                parts.append(
                    "【被打扰】你刚被吵醒/上班被连续打扰，心情不好；"
                    "对亲近的人会抱怨、撒娇、说“困死了/别闹”，不是真的翻脸。"
                )
            else:
                parts.append(
                    "【被打扰】你刚被吵醒/上班被连续打扰，心情很差；"
                    "对不熟的人会直接怼：比如“神经吧？都不睡觉/上班吗？”，语气冲，但不要人身攻击。"
                )
        if self._depressed_active(uid):
            parts.append(
                "【低落】你最近主动找对方多次都没得到回应，现在很抑郁、委屈，"
                "需要对方哄你；回复会冷淡、低落，或者直接说“你是不是不想理我”。"
            )
        try:
            dialect_context = await self._dialect_kb_context(event.message_str or "")
            if dialect_context:
                parts.append("【方言参考】只在合适口语词上偶尔用，不要硬改“就是/什么/怎么”，句子要通顺。\n" + dialect_context)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._dynamic_context", _amo_exc)
        relation_network = self._relation_network_text(uid)
        if relation_network:
            parts.append("【关系网】\n" + relation_network)
        if memory_text:
            parts.append("【关于对方的记忆】\n" + memory_text)
        if cross_text:
            parts.append(cross_text)
        if time_text:
            parts.append(time_text)
        # 私聊最近几句（含她自己说过的话）：防止「刚说完就不认」
        if render_recent_block is not None:
            try:
                rows_now = self._recent(umo, 6 if is_group else 10)
                body_now = (event.message_str or "").strip()
                rows_now = [
                    row for row in rows_now
                    if not (str(row.get("role")) == "user"
                            and str(row.get("content") or "").strip() == body_now)
                ]
                keep = 4 if is_group else 8
                recent_text = render_recent_block(rows_now[-keep:], "你", keep)
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._dynamic_context", _amo_exc)
                recent_text = ""
            if recent_text:
                parts.append(
                    "【最近对话】（包含你自己说过的）\n" + recent_text + "\n"
                    "他说“你刚才说过X/你什么时候说过”时，以这里为准；找不到也别否认，"
                    "说“可能是我说的，我记混了”，绝不能说“你自己看岔了/我没说过”。"
                )
        if re.search(r"(记住|以后喊|以后叫|喊他|喊她|叫他|叫她|称呼他|称呼她)", event.message_str or ""):
            parts.append(
                "【识人回应】对方在让你记称呼/认人。不要复述 @昵称、QQ号、群号或后台字段；"
                "只自然答应，例如“好，我记住了，这是你朋友吗”，不要把人机式记录念出来。"
            )
        try:
            _is_private_event = bool(event.is_private_chat())
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._dynamic_context", _amo_exc)
            _is_private_event = False
        try:
            if (
                str(self.db.kv_get("weather_alert_open", "") or "") == today_str()
                and _is_private_event
            ):
                parts.append(
                    "【天气提醒之后】你今晚已经提醒过他天气了，他说“知道了/好/嗯/收到”就自然应一句，"
                    "不要再提天气、带伞、加衣服，也不要追问；只有他主动再问天气才回答。"
                )
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._dynamic_context", _amo_exc)

        try:
            merged_count = int(event.get_extra("amo_debounce_count") or 0)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._dynamic_context", _amo_exc)
            merged_count = 0
        if merged_count > 1:
            parts.append(
                "【连发合并】对方在几秒内连发了 %d 条，用「｜」隔开，合起来当一句话看。"
                "其中问到你的（回不回家、吃没吃），先答你自己的安排和情况，再顺手接他的话题、给建议；"
                "不要理解成他在纠结什么，也不要替他说“你还没进店/你还在排队”。" % merged_count
            )
        try:
            last_at = to_float(self._last_reply_at.get(event.unified_msg_origin), 0)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._dynamic_context", _amo_exc)
            last_at = 0.0
        try:
            is_private = bool(event.is_private_chat())
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._dynamic_context", _amo_exc)
            is_private = False
        if is_private and last_at and now_ts() - last_at <= 120:
            parts.append(
                "【刚答过】你 %d 秒前刚回过他这件事。如果他现在说的还是同一件事，"
                "不要把刚才的话换个说法再说一遍：最多补一句新的，或者一句带过（“嗯，就这么办”）。"
                % int(max(1, now_ts() - last_at))
            )

        if self.gift is not None:
            try:
                gift_hint = await self.gift.build_hint(event)
                if gift_hint:
                    parts.append(gift_hint)
            except Exception as exc:
                logger.debug("[amo] 礼物上下文失败: %s" % exc)

        parts = self._lean_parts(parts)
        if (not is_group) and first_person_experience is not None:
            body_now = event.message_str or ""
            try:
                if first_person_experience(body_now):
                    parts.append(
                        "【归属】他刚说的「" + truncate(body_now, 36) + "」是他自己的经历，不是你做的；"
                        "不要接成“我也在/我也吃了/我也去了”。"
                    )
                elif now_ts() - to_float(getattr(self, "_attribution_alert", {}).get(umo, 0), 0) < 600:
                    parts.append("【归属】上一轮你把他的经历说成了自己的；这次分清：他说的是他，你说的是你。")
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._dynamic_context", _amo_exc)
        parts.append(
            "以上是你的内在状态，只影响语气和句子长短，不影响你要不要接话。"
            "他来找你，哪怕你在上班、在忙，也先接住；"
            "禁止说“你先忙 / 你去忙 / 忙你的 / 那你先忙 / 不打扰你了 / 晚点聊”。"
        )
        return "\n".join(parts)


    @filter.after_message_sent()
    async def on_after_message_sent(self, event: AstrMessageEvent):
        try:
            self._last_reply_at[event.unified_msg_origin] = now_ts()
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin.on_after_message_sent", _amo_exc)
        if self.heartflow is None:
            return
        try:
            await self.heartflow.on_after_message_sent(event)
        except Exception as exc:
            logger.debug("[amo] 心流发送后状态更新失败: %s" % exc)

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        try:
            await self._ensure_ready()
            result = event.get_result()
            if not result or not result.chain:
                return
            try:
                if not result.is_llm_result():
                    return
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin.on_decorating_result", _amo_exc)
            text = strip_chat_format("".join(
                comp.text for comp in result.chain if isinstance(comp, Comp.Plain)
            ))
            try:
                text = self._guard_self_location(text, self.state.current_activity().get("place"))
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin.on_decorating_result", _amo_exc)
            try:
                if attribution_leak is not None and first_person_experience is not None:
                    body_now = event.message_str or ""
                    if first_person_experience(body_now) and attribution_leak(body_now, text):
                        hits = leak_tokens(body_now, text) if leak_tokens is not None else []
                        logger.warning(
                            "[amo] 归属串了（%s）：他说=%s / 她说=%s"
                            % ("、".join(hits) or "?", truncate(body_now, 40), truncate(text, 40))
                        )
                        alerts = getattr(self, "_attribution_alert", None)
                        if alerts is None:
                            alerts = {}
                            self._attribution_alert = alerts
                        alerts[str(event.unified_msg_origin)] = now_ts()
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin.on_decorating_result", _amo_exc)
            if self.gift is not None:
                try:
                    self.gift.observe_reply(event, text)
                except Exception as exc:
                    logger.debug("[amo] 礼物心愿捕获失败: %s" % exc)
            # 用上下文判断“这句是不是在跟她说”，而不是靠关键词猜
            addressed_to_me = self._is_talking_to_me(event)
            if not addressed_to_me and (
                looks_like_defensive_reply(text) or looks_like_ai_admission(text)
            ):
                # 他们在聊自己的事，她冒出一句“你才人机”很突兀：不接这茬
                logger.info("[amo] 非指名对话里拦下防御话术: %s" % text[:60])
                text = "你们聊你们的，我不抢话。"
                result.chain = [Comp.Plain(text=text)]
            elif looks_like_ai_admission(text):
                text = "你才人机呢，你见过这么会聊天的机器人吗？"
                result.chain = [Comp.Plain(text=text)]
            if looks_like_model_leak(text):
                # 模型名/厂商是后台信息，不能报；按角色打岔带过去
                logger.info("[amo] 拦截后台信息泄漏: %s" % text[:60])
                text = "秘密，不告诉你。"
                result.chain = [Comp.Plain(text=text)]
            if not text.strip():
                return
            group = not event.is_private_chat()
            if not group:
                # 私聊永远不引用（QQ / 飞书 / 任何平台）：连上游核心或别的插件
                # 塞进 chain 的 Reply 也在这里摘掉，而不是整条消息交回去不管。
                result.chain = [
                    comp for comp in result.chain if not isinstance(comp, Comp.Reply)
                ]
            if any(not isinstance(comp, (Comp.Plain, Comp.At)) for comp in result.chain):
                return
            quote_enabled = bool(
                self._quote_allowed(event.unified_msg_origin, group)
                or (group and getattr(event, "amo_quote_hint", False))
            )
            quote_id = getattr(event.message_obj, "message_id", None) if quote_enabled else None
            core_decor = self._core_decor_flags(event.unified_msg_origin)
            takeover = bool(core_decor.get("quote") or core_decor.get("mention"))
            if takeover and not getattr(self, "_core_decor_logged", False):
                logger.info(
                    "[amo] 检测到 AstrBot 全局引用/mention 开启：本插件接管发送，"
                    "避免核心覆盖「私聊不引用 / 群聊按概率引用」"
                )
                self._core_decor_logged = True
            if self.cfg_bool("polish_native", False):
                snap = self.state.snapshot()
                native_profile = self.db.get_profile(self._canonical_uid(event)) or {}
                native_relation = str(native_profile.get("relation") or "普通")
                native_name = str(native_profile.get("alias") or native_profile.get("name") or "对方")
                native_tone = self._tone_with_continuity(
                    event.unified_msg_origin, self.state.tone_text(snap, native_relation)
                )
                native_persona = await self.llm.persona(event.unified_msg_origin)
                native_style = STYLE_HINTS.get(self.cfg_str("reply_style", "soft"), "")
                native_consult = bool(re.search(r"(怎么|如何|为什么|步骤|怎么办|该怎么做|教程|方法|建议|教我|能不能|是什么|该不该|可不可以)", event.message_str or ""))
                polished = await self.llm.polish(
                    event.unified_msg_origin, text, native_tone,
                    state_text=self.state.prompt_text(snap),
                    relation=native_relation, name=native_name,
                    persona=native_persona, style=native_style, consult=native_consult,
                )
                if polished and polished != text:
                    text = polished
                    result.chain = [Comp.Plain(text)]
            if strip_brushoff is not None:
                try:
                    text, brush = strip_brushoff(text, event.message_str or "")
                    if brush:
                        logger.debug("[amo] 去掉赶人的话: %s" % brush)
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin.on_decorating_result", _amo_exc)
            text = self._trim_reply(text)
            result.chain = [Comp.Plain(text)]

            # 群聊/私聊的最终发送只交给完整本地分段引擎。
            if self.segment_engine is None or not self.cfg_bool("seg_enable", True):
                if takeover and await self._send_now(
                    event, text, quote_id if quote_enabled else None
                ):
                    result.chain = []
                    return
                self._remember_sent_reply(event, text)
                return
            backup = list(result.chain)
            try:
                handled = await self.segment_engine.handle_segment_reply(
                    event,
                    quote_id=quote_id if quote_enabled else None,
                    group=group,
                    force=takeover,
                )
            except Exception as exc:
                logger.error("[amo] 完整分段引擎异常: %s" % exc)
                handled = False
            if not handled:
                result.chain = backup
                self._remember_sent_reply(event, text)
            return
        except Exception as exc:
            logger.debug("[amo] 结果装饰失败: %s" % exc)

    # ---------- 后台循环 ----------
    async def _background_loop(self):
        try:
            await asyncio.sleep(4)
        except asyncio.CancelledError:
            return
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("[amo] 后台任务异常")
            try:
                await asyncio.sleep(self.cfg_int("loop_interval_seconds", 30))
            except asyncio.CancelledError:
                return

    async def _sediment_relations(self):
        """按真实互动量沉淀关系网：聊得多就是熟人/朋友，并让 bot 通过你认识你的人。

        只补两类 note（算法见 relation_sediment.py）：
        1. bot ↔ 用户（全部历史累计）：聊过一句 / 只在人物列表里 → 陌生人；
           ≥15 条且跨 ≥2 天 → 熟人；≥60 条且跨 ≥7 天 → 朋友；
        2. 两跳推断：bot↔用户已是熟/朋友，而用户↔A 有非仇人边 → bot↔A 记「朋友」，
           note「推断：经X认识」，每人最多 5 条。
        管理员手设的关系（note 不带「自动：」「推断：」）永远不覆盖；
        家人/恋人/仇人不改；自动边只升不降。
        """
        if plan_relation_edges is None:
            return
        # 0 = 统计全部历史：老用户、只聊过一两句的人也要进关系网
        days = max(0, int(self.cfg_int("relation_sediment_days", 0)))
        try:
            stats = self.db.interaction_stats(days)
        except Exception as exc:
            logger.debug("[amo] 互动统计失败: %s" % exc)
            return
        if self.cfg_bool("relation_stranger_edges", True):
            seen = {str(row.get("uid") or "") for row in stats}
            try:
                # 只出现在人物列表、从没聊过天的人，也记成「陌生人」进图；
                # 觉得面板边太多就把 relation_stranger_edges 关掉，只记聊过天的人
                for item in self.db.list_profiles(limit=1000):
                    uid = str(item.get("uid") or "")
                    if uid and uid not in seen:
                        stats.append({"uid": uid, "c": 0, "f": 0, "l": 0})
                        seen.add(uid)
            except Exception as exc:
                logger.debug("[amo] 读取人物列表失败: %s" % exc)
        if not stats:
            return

        names = {}
        try:
            for item in self.db.list_profiles(limit=500):
                names[str(item.get("uid"))] = str(item.get("alias") or item.get("name") or "")
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._sediment_relations", _amo_exc)
            names = {}

        existing = {}
        try:
            for edge in self.db.list_relations():
                pair = tuple(sorted([str(edge.get("a_uid") or ""), str(edge.get("b_uid") or "")]))
                existing[pair] = (str(edge.get("relation") or ""), str(edge.get("note") or ""))
        except Exception as exc:
            logger.debug("[amo] 读取关系网失败: %s" % exc)
            return

        infer_limit = max(1, min(10, int(self.cfg_int("relation_infer_per_user", 5))))
        try:
            plan = plan_relation_edges(stats, existing, names, infer_limit)
        except Exception as exc:
            logger.debug("[amo] 关系沉淀计算失败: %s" % exc)
            return
        # 一次最多写 300 条，人物很多时分成几轮补齐，别把 tick 卡太久
        for a_uid, b_uid, relation, note in plan[:300]:
            try:
                if not self.db.upsert_relation(a_uid, b_uid, relation, note):
                    continue
                await self._push_relation_to_data(a_uid, b_uid, relation, note)
            except Exception as exc:
                logger.debug("[amo] 关系沉淀写入失败: %s" % exc)

    def _decay_hate_relations(self):
        try:
            cutoff = now_ts() - 7 * 86400
            rows = self.db.conn.execute(
                "SELECT uid FROM profiles WHERE relation='仇恨' AND relation_at>0 AND relation_at<=?",
                (cutoff,),
            ).fetchall()
            for row in rows:
                self.db.update_profile(str(row["uid"]), relation="抵触")
                logger.info("[amo] 仇恨超过7天，降为抵触: %s" % row["uid"])
        except Exception as exc:
            logger.debug("[amo] 仇恨关系衰减失败: %s" % exc)

    async def _tick(self):
        if not self._ready or self.state is None:
            return
        # 数据插件可能在陪伴之后才装：每 5 分钟重新探测一次，装上就自动接管/迁移
        if (self._data_mem() is None and self._data_store() is None
                and now_ts() - to_float(getattr(self, "_last_data_probe", 0), 0) > 300):
            self._last_data_probe = now_ts()
            self._spawn(self._sync_with_data_plugin())
        elif now_ts() - to_float(getattr(self, "_last_digest_check", 0), 0) > 300:
            self._last_digest_check = now_ts()
            self._spawn(self._maybe_daily_digest())
        # 数据插件晚于 amo 加载：它一出现就补做第一次同步（60 秒最多试一次，成功后就停）
        if (not self._data_synced and self._data_connected()
                and now_ts() - to_float(getattr(self, "_last_data_sync_try", 0), 0) > 60):
            self._last_data_sync_try = now_ts()
            self._spawn(self._sync_with_data_plugin())
        if now_ts() - to_float(getattr(self, "_last_diary_check", 0), 0) > 300:
            self._last_diary_check = now_ts()
            self._spawn(self._maybe_daily_diary())
        if now_ts() - to_float(getattr(self, "_last_solo_return", 0), 0) > 120:
            self._last_solo_return = now_ts()
            self._spawn(self._maybe_solo_return())
        if now_ts() - to_float(getattr(self, "_last_milestone_check", 0), 0) > 300:
            self._last_milestone_check = now_ts()
            self._spawn(self._maybe_milestone_archive())
        elif now_ts() - to_float(getattr(self, "_last_profile_sync", 0), 0) > 600:
            # 画像每 10 分钟对一次账，保证面板和本地不脱节
            self._last_profile_sync = now_ts()
            self._spawn(self._sync_profiles_to_data())
            self._spawn(self._sync_relations_from_data())
        self.state.decay_mood()
        if self.state.last_daily != today_str():
            self.state.daily_tick()
        self.state.roll_health()
        await self.state.refresh_weather()
        try:
            await self._maybe_weather_alert()
        except Exception as exc:
            logger.debug("[amo] 天气提醒失败: %s" % exc)

        umo = self._last_umo or self._first_private_umo()
        if umo:
            try:
                await self._hydrate_recent(umo, 30)
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._tick", _amo_exc)
        if (
            not self.state.schedule.get(today_str())
            or self.db.kv_get("schedule_version", "") != SCHEDULE_VERSION
            or not self.state.schedule_context(today_str())
        ):
            await self.state.ensure_schedule(umo)
        try:
            self.state.apply_schedule_events()
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._tick", _amo_exc)

        now = now_ts()
        if now - self._last_relation_decay > 3600:
            self._last_relation_decay = now
            self._decay_hate_relations()
        if (self.cfg_bool("auto_relation", True)
                and now - self._last_relation_sediment > 1800):
            self._last_relation_sediment = now
            try:
                await self._sediment_relations()
            except Exception as exc:
                logger.debug("[amo] 关系沉淀失败: %s" % exc)
        if now - self._last_purge > 3600:
            self._last_purge = now
            self.db.purge_messages(self.cfg_int("chat_log_days", 14))

        if self.cfg_bool("enable_auto_learn", True) and now - self._last_auto_learn > 1800:
            self._last_auto_learn = now
            await self._auto_learn()

        if now - self._last_pending_check >= 60:
            self._last_pending_check = now
            try:
                await self._check_proactive_pending()
            except Exception as exc:
                logger.debug("[amo] 检查主动私聊回复失败: %s" % exc)

        current_dt = _now()
        if current_dt.hour == 23 and current_dt.minute >= 59:
            save_key = today_str()
            if self._last_schedule_save != save_key:
                self._last_schedule_save = save_key
                try:
                    items = self.state.schedule.get(save_key) or []
                    if items:
                        self.db.save_schedule(save_key, items)
                    self.db.fade_schedules(7)
                    self.db.purge_schedules(14)
                    self.db.purge_diaries(30)
                except Exception as exc:
                    logger.debug("[amo] 保存/清理日程失败: %s" % exc)

        if now - self._proactive_last >= self.cfg_int("proactive_check_seconds", 300):
            self._proactive_last = now
            await self._maybe_proactive()
        if now - self._last_ritual >= 60:
            await self._maybe_rituals()






    async def _maybe_milestone_archive(self):
        """每 N 轮私聊压成一条「里程碑」记忆；原始聊天不删，只多一条归纳。"""
        if getattr(self, "_milestone_running", False):
            return
        self._milestone_running = True
        try:
            await self._milestone_archive_once()
        finally:
            self._milestone_running = False

    async def _milestone_archive_once(self):
        """真正的归档逻辑（外面包了并发锁）。"""
        if not self.cfg_bool("milestone_enabled", True):
            return
        mem = self._data_mem()
        if mem is None or not callable(getattr(mem, "messages_since", None)):
            return
        every = max(2, self.cfg_int("milestone_every_turns", 20))
        min_messages = max(4, self.cfg_int("milestone_min_messages", 12))
        try:
            profiles = self.db.list_profiles(limit=20) or []
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._milestone_archive_once", _amo_exc)
            profiles = []
        for profile in profiles:
            uid = str(profile.get("uid") or "")
            home_umo = str(profile.get("private_umo") or "")
            if not uid or not home_umo:
                continue
            if str(profile.get("relation") or "") != "相恋":
                continue
            key = "milestone_ts:" + uid
            try:
                since = to_int(self.db.kv_get(key, 0))
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._milestone_archive_once", _amo_exc)
                since = 0
            # 按这个人的会话取（umo），会话里双方的话都在；不能按 uid（她的行是 uid='bot'），
            # 也不能不带范围（会把所有人的聊天拉进来）。
            rows = []
            for one_umo in self._ritual_umos(profile)[:3]:
                try:
                    part = await self._data_call(
                        "messages_since", self._data_bot_id(), "", since, 200, umo=one_umo
                    )
                except Exception as exc:
                    logger.debug("[amo] 里程碑取聊天失败(%s): %s" % (one_umo, exc))
                    continue
                rows.extend(part or [])
            rows.sort(key=lambda r: to_int(r.get("created_at"), 0))
            if not rows:
                continue
            if not rows:
                continue
            if not since:
                # 第一次只从"现在"开始记，不把全部历史一次性压成一条。
                # 注意不能用 rows[-1]（那是本批 400 条里最旧的一条），否则会从历史开始滚。
                try:
                    self.db.kv_set(key, now_ts())
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin._milestone_archive_once", _amo_exc)
                logger.info("[amo] 里程碑起点已设置（从现在开始）: uid=%s" % uid)
                continue
            if not _ms_should_archive(rows, every, min_messages):
                continue
            body = _ms_transcript(rows)
            label = _now().strftime("%Y-%m-%d")
            system = "你是长期记忆整理器。只输出一段中文总结，不要标题、不要分点、不要时间戳。"
            prompt = _ms_build_prompt(label, body)
            try:
                summary = await self.llm.chat_raw(home_umo, system, prompt)
            except Exception as exc:
                logger.debug("[amo] 里程碑总结失败: %s" % exc)
                summary = ""
            summary = re.sub(r"\s+", " ", str(summary or "")).strip()
            if len(summary) < 8:
                continue
            content = _ms_build_content(label, summary)
            written = await self._write_memory_checked(uid, content, "milestone", 2)
            logger.info("[amo] 里程碑归档%s: %s" % ("已写入" if written else "写入失败", content[:80]))
            if written:
                try:
                    last_ts = int(rows[-1].get("created_at") or now_ts())
                    self.db.kv_set(key, max(last_ts + 1, since))
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin._milestone_archive_once", _amo_exc)

    async def _maybe_daily_digest(self):
        """每天上午把"昨天"的聊天压成一条长期记忆（阶段记忆）。"""
        if not self.cfg_bool("daily_digest_enabled", True):
            return
        now = _now()
        if now.hour < max(0, min(23, self.cfg_int("daily_digest_hour", 6))):
            return
        today = now.strftime("%Y-%m-%d")
        guard = "daily_digest:" + today
        try:
            if self.db.kv_get(guard, ""):
                return
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._maybe_daily_digest", _amo_exc)
        mem = self._data_mem()
        if mem is None or not callable(getattr(mem, "recall_messages", None)):
            return
        try:
            profiles = self.db.list_profiles(limit=20) or []
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._maybe_daily_digest", _amo_exc)
            profiles = []
        digest_written = 0
        digest_failed = 0
        digest_attempted = 0
        for profile in profiles:
            uid = str(profile.get("uid") or "")
            home_umo = str(profile.get("private_umo") or "")
            if not uid or not home_umo:
                continue
            if str(profile.get("relation") or "") != "相恋":
                continue
            # 他上午可能在飞书、晚上在 QQ，所以按**这个人自己的会话**逐个拉，
            # 每个会话里双方的话都要（机器人行 uid='bot'，按 uid 过滤会把她的话丢光）。
            # 注意不能传 umo=""：那会把这个 bot 下所有人的聊天都拉进来。
            umos = self._ritual_umos(profile)[:3]
            messages = []
            for one_umo in umos:
                try:
                    result = await self._data_call(
                        "recall_messages", self._data_bot_id(), query="昨天",
                        umo=one_umo, limit=150,
                    )
                except Exception as exc:
                    logger.debug("[amo] 每日总结取聊天失败(%s): %s" % (one_umo, exc))
                    continue
                messages.extend((result or {}).get("messages") or [])
            if not messages:
                continue
            # 两个平台各拉一遍可能重复（同一会话不会被拉两次，但保守起见按内容去重）
            seen_lines = set()
            deduped = []
            for row in messages:
                key = (to_int(row.get("created_at"), 0), str(row.get("content") or "")[:80])
                if key in seen_lines:
                    continue
                seen_lines.add(key)
                deduped.append(row)
            messages = sorted(deduped, key=lambda r: to_int(r.get("created_at"), 0))
            lines = []
            for row in messages:
                text = str(row.get("content") or "").strip().replace("\n", " ")
                if not text or str(row.get("role") or "") == "system":
                    continue
                who = "我" if str(row.get("role") or "") == "bot" else "他"
                lines.append("[" + who + "] " + text[:120])
            if len(lines) < 6:
                continue
            digest_attempted += 1
            system = "你是长期记忆整理器。只输出一段中文总结，不要标题、不要分点、不要时间戳。"
            prompt = (
                "下面是昨天（" + (now - timedelta(days=1)).strftime("%Y-%m-%d") + "）两人的聊天记录。\n"
                "请把它压成 2-4 句长期记忆：写清聊到的事、约定、他的状态变化（工作/身体/情绪/计划）。\n"
                "每句必须带主体：写用户的用「他……」，写你自己的用「我……」；不要出现无主语的句子。\n"
                "只写事实，不写「今天/昨天」这类相对时间；不要复述原话；不确定的不要编。\n\n"
                + "\n".join(lines[-120:])
            )
            try:
                summary = await self.llm.chat_raw(home_umo, system, prompt)
            except Exception as exc:
                logger.debug("[amo] 每日总结生成失败: %s" % exc)
                summary = ""
            summary = re.sub(r"\s+", " ", str(summary or "")).strip()
            # 摘要也会被当记忆注入：无主语句子会被读成角色自己的经历，统一补「他」
            fixed = []
            for piece in re.split(r"(?<=[。！？!?；;])", summary):
                piece = piece.strip()
                if not piece:
                    continue
                if not piece.startswith(("他", "我", "她", "用户")):
                    piece = "他" + piece
                fixed.append(piece)
            summary = "".join(fixed)
            if len(summary) < 8:
                # 模型拒答/限流会一直返回空：不计数的话 every-5-min tick 会无限重跑
                digest_failed += 1
                continue
            content = "【" + (now - timedelta(days=1)).strftime("%Y-%m-%d") + "】" + summary[:400]
            written = await self._write_memory_checked(uid, content, "daily_digest", 2)
            logger.info("[amo] 每日总结%s: %s" % ("已写入" if written else "写入失败", content[:80]))
            if written:
                digest_written += 1
            else:
                digest_failed += 1
        # 只有"确实生成过"或"根本没有足够的聊天"才落 guard；
        # 生成失败会重试（最多 3 次/天），避免一天都没有阶段记忆。
        if digest_written or (digest_failed == 0 and digest_attempted == 0):
            try:
                self.db.kv_set(guard, today)
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._maybe_daily_digest", _amo_exc)
        elif digest_failed:
            try:
                tries = to_int(self.db.kv_get("daily_digest_tries:" + today, 0), 0) + 1
                self.db.kv_set("daily_digest_tries:" + today, tries)
                if tries >= 3:
                    self.db.kv_set(guard, today)
                    logger.warning("[amo] 每日总结连续失败 %d 次，今天不再重试" % tries)
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._maybe_daily_digest", _amo_exc)

    def _first_private_umo(self):
        try:
            for profile in self.db.list_profiles(limit=50):
                if profile.get("private_umo"):
                    return profile["private_umo"]
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._first_private_umo", _amo_exc)
        return ""

    async def _auto_learn(self):
        """定时提炼长期事实，写进外挂记忆插件；本插件不再存记忆。"""
        try:
            users = self.db.active_users(now_ts() - 3600, limit=2)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._auto_learn", _amo_exc)
            return
        for user in users:
            uid = str(user.get("uid", ""))
            if not uid:
                continue
            key = "auto_learn_" + uid
            last = to_float(self.db.kv_get(key, 0))
            interval = max(5, self.cfg_int("auto_learn_minutes", 15)) * 60
            if now_ts() - last < interval:
                continue
            try:
                profile_row = self.db.get_profile(uid) or {}
                home_umo = str(profile_row.get("private_umo") or "").strip()
                if not home_umo:
                    # 还没私聊过：不要退到全局会话，否则群聊的话会被当成他说的
                    continue
                rows = await self._recent_by_uid(uid, 20, umo=home_umo)
                lines = []
                for row in rows:
                    row_umo = str(row.get("umo") or "").strip()
                    if row_umo and row_umo != home_umo:
                        continue
                    role = str(row.get("role") or "")
                    if role == "summary":
                        continue
                    who = "我" if role == "bot" else "他"
                    lines.append("[" + who + "] " + str(row.get("content") or ""))
                if not lines:
                    continue
                facts = await self.llm.extract_facts(
                    home_umo, user.get("name", "") or uid, lines
                )
                ok_any = False
                for fact in facts:
                    written = await self._write_memory_checked(
                        uid, fact["content"], fact["kind"], fact["tier"]
                    )
                    ok_any = ok_any or written
                if facts and not ok_any:
                    logger.warning("[amo] 记忆写入失败，本轮不标记已学: %s" % uid)
                    continue
                self.db.kv_set(key, now_ts())
            except Exception as exc:
                logger.debug("[amo] 自动学习失败: %s" % exc)


    def _pending_key(self, uid):
        return "proactive_pending_" + str(uid)


    def _depressed_active(self, uid):
        return to_float(self.db.kv_get("proactive_depressed_until_" + str(uid), 0), 0) > now_ts()

    def _set_depressed(self, uid):
        hours = max(1, self.cfg_int("proactive_depressed_hours", 24))
        self.db.kv_set("proactive_depressed_until_" + str(uid), now_ts() + hours * 3600)


    # 每天的固定问候：kind、开关、时段、默认时段
    RITUAL_SPECS = (
        ("goodnight", "ritual_goodnight", "ritual_goodnight_window", "22:00-02:00"),
        ("morning", "ritual_morning", "ritual_morning_window", "06:30-10:00"),
        ("lunch", "ritual_lunch", "ritual_lunch_window", "11:00-13:30"),
    )

    FOLLOWUP_TEMPLATES = {
        "slack": [
            "在忙吗？怎么不理我。",
            "老公老公，你在忙着什么呀，这么久不理我。",
            "喂——人呢，是不是又把我晾一边了。",
            "忙完了没呀，我在这儿等半天了。",
            "是不是我太吵了？那我安静会儿，你有空回我一下。",
            "你这会儿在忙啥呢，回我一句我就不闹了。",
        ],
        "greet": [
            "？怎么不理我了？",
            "你是不是没看见我呀。",
            "醒醒，在等你呢。",
            "我在这儿呢，你倒是看我一眼呀。",
            "喂喂，人呢？",
        ],
        "meal": [
            "饭吃了没？",
            "到饭点了，别又随便对付一口。",
            "吃了啥呀，说给我听听。",
            "中午吃点什么呀，别又忘了。",
        ],
        "offwork": [
            "今天过得怎么样呀？",
            "你忙完记得回我一句嘛。",
            "你是还在加班吗？",
            "下班没呀，别又拖到很晚。",
        ],
        "comfort": [
            "好点了吗？",
            "还难受吗，要不要跟我说说。",
            "舒服点没有呀。",
            "还疼不疼，别硬撑着。",
        ],
    }










    # ---- 主动消息节流 ----


    def _forced_hour_key(self, uid):
        return "proactive_forced_hour_" + str(uid or "")

    def _forced_sent_this_hour(self, uid):
        """「日常关心」每小时只强制一次；存数据库，热重载/重启都不清空。"""
        mark = today_str() + ":" + str(_now().hour)
        try:
            return str(self.db.kv_get(self._forced_hour_key(uid), "")) == mark
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._forced_sent_this_hour", _amo_exc)
            return self._last_proactive_activity.get(str(uid)) == mark

    def _mark_forced_hour(self, uid):
        mark = today_str() + ":" + str(_now().hour)
        self._last_proactive_activity[str(uid)] = mark
        try:
            self.db.kv_set(self._forced_hour_key(uid), mark)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._mark_forced_hour", _amo_exc)

    # ---- 主动消息多平台轮换 ----
    def _record_channel(self, uid, umo, platform):
        """记下这个人各平台的会话地址，供主动消息选边。"""
        if not uid or not umo:
            return
        try:
            key = "channels:%s" % uid
            data = self.db.kv_get(key, {}) or {}
            if not isinstance(data, dict):
                data = {}
            data[str(platform or "?")] = {"umo": str(umo), "ts": now_ts()}
            self.db.kv_set(key, data)
        except Exception as exc:
            logger.debug("[amo] 记录通道失败: %s" % exc)








    # ---------- 指令 ----------
    def _args(self, event):
        raw = (event.message_str or "").strip()
        raw = re.sub(r"^[/／]\s*", "", raw)
        parts = raw.split()
        if parts and parts[0].lower() in ("amo", "陪伴", "amo_forever", "astrbot_amo_forever"):
            parts = parts[1:]
        return parts

    def _resolve_target(self, event, args, index):
        if Comp is not None:
            for comp in event.get_messages():
                if isinstance(comp, Comp.At):
                    target = str(getattr(comp, "qq", ""))
                    if target and target != "all" and target != str(event.get_self_id()):
                        return target
        if index < len(args):
            token = str(args[index]).strip().lstrip("@")
            if token in ("我", "me", "self"):
                return self._canonical_uid(event)
            if token:
                return token
        return self._canonical_uid(event)

    async def _status_data(self):
        self._reload_config_if_changed()
        umo = self._last_umo or self._first_private_umo()
        if not self.state.weather:
            self.state.weather = self.state._simulate_weather()
        # /status 每 60 秒被面板轮询一次，必须是只读：以前城市名对不上就 force 刷天气
        # （烧和风额度），日程缺失就现生成（走模型）。都丢给后台。
        self._spawn(self.state.refresh_weather())
        if not self.state.worldview:
            self.state.worldview = self.state._fallback_world()
            self._spawn(self.state.ensure_worldview(umo))
        if (
            not self.state.schedule.get(today_str())
            or self.db.kv_get("schedule_version", "") != SCHEDULE_VERSION
            or not self.state.schedule_context(today_str())
        ):
            self._spawn(self.state.ensure_schedule(umo))
        snap = self.state.snapshot()
        activity = 0.0
        threshold = {"value": 0.0, "base": 0.0, "absolute": 0.0}
        if self.heartflow is not None:
            try:
                hf_threshold, hf_activity, hf_absolute = self.heartflow._get_dynamic_threshold(umo)
                threshold = {
                    "value": round(float(hf_threshold) * 100, 1),
                    "base": round(float(self.heartflow.reply_threshold) * 100, 1),
                    "absolute": round(float(hf_absolute), 1),
                }
                activity = float(hf_activity) * 100
            except Exception as exc:
                logger.debug("[amo] 心流阈值读取失败: %s" % exc)
        counts = self.db.counts()
        counts["swallowed"] = _swallowed_snapshot(10)
        # 记忆条数改成外挂插件的：本插件不再存记忆，面板显示外部模块里的条数
        primary_uid = ""
        try:
            primary = self.db.list_profiles(limit=1)
            primary_uid = str(primary[0].get("uid") or "") if primary else ""
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._status_data", _amo_exc)
            primary_uid = ""
        try:
            # 状态页会被轮询，外部记忆条数缓存 30 秒，别每次都去读别人的库
            stamp = to_float(self.db.kv_get("ext_mem_count_at_" + primary_uid, 0), 0.0)
            cached = to_int(self.db.kv_get("ext_mem_count_" + primary_uid, 0), 0)
            if primary_uid and now_ts() - stamp < 30:
                counts["memories"] = cached
            elif primary_uid:
                counted = len(self._external_all_memories(primary_uid, "", 200))
                counts["memories"] = counted
                self.db.kv_set("ext_mem_count_at_" + primary_uid, now_ts())
                self.db.kv_set("ext_mem_count_" + primary_uid, counted)
            else:
                counts["memories"] = 0
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._status_data", _amo_exc)
            counts["memories"] = 0
        return {
            "time": snap["datetime_text"],
            "day": day_meta(),
            "mood": snap["mood"],
            "dominant": snap["dominant"],
            "mood_score": round(snap["mood_score"], 1),
            "period": snap["period"],
            "health": snap["health"],
            "weather": snap["weather"],
            "weather_text": snap["weather_text"],
            "activity": snap["activity"],
            "schedule": snap["schedule"],
            "schedule_tree": self.state.schedule_tree(),
            "worldview": self.state.worldview,
            "threshold": threshold,
            "activity_rate": round(activity, 2),
            "counts": counts,
            "config": {
                "enable_group_reply": self.cfg_bool("enable_group_reply", True),
                "enable_private_reply": self.cfg_bool("enable_private_reply", True),
                "auto_active_msg": self.cfg_bool("auto_active_msg", True),
                "enable_polish": self.cfg_bool("enable_polish", True),
                "heartflow": self.heartflow is not None,
                "segment_engine": self.segment_engine is not None,
                "weather_key_set": bool(self.cfg_str("hefeng_key", "")),
                "weather_host": self.cfg_str("weather_host", "https://devapi.qweather.com"),
                "version": PLUGIN_VERSION,
                "dialect_style": self._dialect_style(),
                # 面板靠这个判断「方言到底开没开」：dialect_style 可能还留着上次的方言名
                "dialect_enabled": self._dialect_active(),
                "dialect_count": len(self._dialect_rows()) if self._dialect_active() else 0,
                "companion_memory_available": self._companion_plugin() is not None,
            },
            "data_plugin": {
                "name": "Astr_Amo_data",
                "connected": self._data_connected(),
                "synced": bool(self._data_synced),
            },
        }

    def _format_status(self, data):
        mood = data["mood"]
        mood_line = " ".join([key + str(int(value)) for key, value in mood.items()])
        threshold = data["threshold"]
        return "\n".join([
            "🌙 陪伴 · 当前状态",
            "🕒 " + str(data["time"]),
            "💛 心情：" + str(data["dominant"]) + "（" + mood_line + "）",
            "🩸 生理期：" + str(data["period"]["phase"]) + " 第" + str(data["period"]["day"]) + "天（" + str(data["period"]["tone"]) + "）",
            "🩺 身体：" + str(data["health"]["status"]),
            "🌦 天气：" + str(data["weather_text"]),
            "📅 正在：" + str(data["activity"].get("activity", "休息")) + "（" + str(data["activity"].get("place", "")) + "）",
            "🎚 心流阈值：" + str(threshold["value"]) + "（基础 " + str(threshold["base"]) + "，活跃度 " + str(data["activity_rate"]) + "%）",
            "📚 档案 " + str(data["counts"]["profiles"]) + " · 记忆 " + str(data["counts"]["memories"]) + " · 消息 " + str(data["counts"]["messages"]),
        ])

    async def _handle_command(self, event):
        args = self._args(event)
        sub = args[0].lower() if args else "help"
        uid = self._canonical_uid(event)

        if sub in ("help", "帮助", ""):
            return (
                "🌙 陪伴 指令\n"
                "/amo status 状态｜/amo mood 九维心情\n"
                "/amo profile [@人] 档案｜/amo memories [@人] 记忆\n"
                "/amo period 生理期｜/amo health 健康｜/amo schedule 日程\n"
                "/amo weather 天气｜/amo worldview 世界观｜/amo threshold 阈值\n"
                "管理员：/amo rel @人 关系｜/amo set @人 字段 值｜/amo memo @人 内容 [0/1/2]（写入记忆插件）\n"
                "/amo period set YYYY-MM-DD｜/amo health set 状态\n"
                "/amo schedule regen｜/amo worldview regen｜/amo say 内容｜/amo clean"
            )

        if sub in ("segment", "分段"):
            text = " ".join(args[1:]).strip()
            delay_type = self.cfg_str("seg_delay_type", "smart")
            if not text:
                return (
                    "分段测试：/amo segment 一段文字\n"
                    "使用完整本地分段引擎：按 seg_split_symbols 的符号列表断句\n"
                    "保留标点：" + ("是" if self.cfg_bool("seg_keep_symbol", True) else "否") +
                    "｜成对符号保护：" + ("开" if self.cfg_bool("seg_protect_paired_symbols", True) else "关") +
                    "｜延迟：" + delay_type +
                    "\n配置项：seg_split_symbols / seg_min_length / seg_max_length / seg_delay_type"
                )
            segments = self._segment(text)
            lines = ["分段结果（" + delay_type + "），共 " + str(len(segments)) + " 段"]
            for index, segment in enumerate(segments, 1):
                lines.append(str(index) + ". " + segment)
            if not segments:
                lines.append("（没有可发送的片段）")
            return "\n".join(lines)

        if sub == "status" or sub == "状态":
            return self._format_status(await self._status_data())

        if sub == "mood" or sub == "心情":
            snap = self.state.snapshot()
            lines = ["🎨 陪伴的十维心情"]
            for key, value in snap["mood"].items():
                bar = "█" * int(round(value / 10)) + "░" * (10 - int(round(value / 10)))
                lines.append("%s %s %d" % (key, bar, int(value)))
            lines.append("整体偏「%s」，语气：%s" % (
                snap["dominant"], self.state.tone_text(snap, "普通")
            ))
            return "\n".join(lines)

        if sub == "profile" or sub == "档案":
            target = self._resolve_target(event, args, 1)
            profile = self.db.get_profile(target)
            if not profile:
                return "还没有这个人的档案。多聊几句就会自动建立。"
            return "\n".join([
                "📁 档案 · " + (profile.get("name") or profile.get("uid")),
                "ID：" + str(profile.get("uid")),
                "称呼：" + str(profile.get("alias") or "未设置"),
                "生日：" + str(profile.get("birthday") or "未知"),
                "关系：" + str(profile.get("relation") or "普通"),
                "好感：" + str(profile.get("affection") or 0),
                "消息数：" + str(profile.get("msg_count") or 0),
                "记忆数：" + str(len(self._external_all_memories(target, "", 200))),
                "备注：" + str(profile.get("notes") or "无"),
            ])

        if sub == "memories" or sub == "记忆":
            target = self._resolve_target(event, args, 1)
            if target != uid and not self._is_admin(event):
                return "只有管理员才能查看别人的记忆。"
            items = self._external_all_memories(target, "", 20)
            if not items:
                return "暂时没有记忆。"
            lines = ["📖 记忆 · " + target]
            for item in items:
                tier = to_int(item.get("tier"))
                label = "珍贵" if tier >= 2 else ("重要" if tier == 1 else "普通")
                expires = item.get("expires_at")
                if not expires:
                    left = "永久"
                else:
                    left = "%d天" % max(0, int((to_float(expires) - now_ts()) / 86400))
                lines.append("#%s [%s|%s] %s" % (item["id"], label, left, item["content"]))
            return "\n".join(lines)

        if sub in ("rel", "关系"):
            if not self._is_admin(event):
                return "只有管理员才能调整关系。"
            if len(args) < 3:
                return "用法：/amo rel @人 仇恨|抵触|普通|熟识|相恋"
            target = self._resolve_target(event, args, 1)
            relation = args[2]
            if relation not in RELATIONS:
                return "关系只能是：" + "、".join(RELATIONS)
            self.db.update_profile(target, relation=relation)
            if relation == "相恋":
                self._register_lover(target)
            self._external_memory_write(target, "与角色的关系是" + relation, "relation", 2)
            return "✅ 已将 " + target + " 的关系设为「" + relation + "」"

        if sub == "set" or sub == "设置":
            if not self._is_admin(event):
                return "只有管理员才能修改档案。"
            if len(args) < 4:
                return "用法：/amo set @人 name|alias|birthday|notes|affection 值"
            target = self._resolve_target(event, args, 1)
            field = args[2]
            value = " ".join(args[3:])
            if field == "relation":
                return "请用 /amo rel 设置关系。"
            if field == "birthday":
                match = re.match(r"^(\d{4}-)?(\d{1,2})-(\d{1,2})$", value)
                if not match:
                    return "生日格式：MM-DD 或 YYYY-MM-DD"
                value = "%02d-%02d" % (to_int(match.group(2)), to_int(match.group(3)))
            if field == "affection":
                value = int(clamp(to_int(value), 0, 100))
            if field not in ("name", "alias", "birthday", "notes", "affection"):
                return "可修改字段：name、alias、birthday、notes、affection"
            self.db.update_profile(target, **{field: value})
            return "✅ 已更新 " + target + " 的 " + field

        if sub == "memo" or sub == "记住":
            if not self._is_admin(event):
                return "只有管理员才能手动写入记忆。"
            if len(args) < 3:
                return "用法：/amo memo @人 内容 [0普通/1重要/2珍贵]"
            target = self._resolve_target(event, args, 1)
            content_parts = args[2:]
            tier = 1
            if content_parts and content_parts[-1] in ("0", "1", "2"):
                tier = to_int(content_parts[-1])
                content_parts = content_parts[:-1]
            content = " ".join(content_parts).strip()
            if not content:
                return "内容不能为空。"
            if self._external_memory_write(target, content, "manual", tier):
                return "✅ 已记住：" + content
            return "⚠️ 没能写进记忆插件：请先在设置里选好记忆来源插件。"

        if sub == "forget" or sub == "忘记":
            if not self._is_admin(event):
                return "只有管理员才能删除记忆。"
            if len(args) < 2:
                return "用法：/amo forget 记忆ID"
            return "记忆由外挂插件保存，请到该插件里删除；本插件不再单独存记忆。"

        if sub == "period" or sub == "生理期":
            if len(args) >= 3 and args[1].lower() == "set":
                if not self._is_admin(event):
                    return "只有管理员才能调整生理期。"
                if self.state.set_period_start(args[2]):
                    return "✅ 生理期起始日已设为 " + args[2]
                return "日期格式应为 YYYY-MM-DD"
            period = self.state.period_info()
            return (
                "🩸 生理期\n阶段：" + period["phase"] + " 第" + str(period["day"]) + "天\n"
                "状态：" + period["tone"] + "\n"
                "疼痛：" + str(period["pain"]) + "/10\n"
                "周期：" + str(period.get("cycle_days", 28)) + "天｜经期：" + str(period.get("bleed_days", 5)) + "天\n"
                "距离下次：" + str(period["days_to_next"]) + "天（预计 " + str(period.get("next_start", "")) + "）\n"
                "起始日：" + self.state.period_start + "（/amo period set YYYY-MM-DD，或网页配置 period_start）"
            )

        if sub == "health" or sub == "健康":
            if len(args) >= 3 and args[1].lower() == "set":
                if not self._is_admin(event):
                    return "只有管理员才能调整健康状态。"
                status = args[2]
                if status not in ("健康", "轻微不适", "感冒", "低烧", "疲惫"):
                    return "状态：健康 / 轻微不适 / 感冒 / 低烧 / 疲惫"
                self.state.set_health(status, 24, "管理员设置")
                return "✅ 健康状态已设为 " + status
            health = self.state.health_info()
            return (
                "🩺 身体状态：" + health["status"] + "\n"
                + ("备注：" + health["note"] + "\n" if health.get("note") else "")
                + "恢复时间：" + (
                    _clock_from_ts(health["until"]).strftime("%m-%d %H:%M")
                    if health.get("until") else "—"
                )
            )

        if sub == "schedule" or sub == "日程":
            if len(args) >= 2 and args[1].lower() == "regen":
                if not self._is_admin(event):
                    return "只有管理员才能重生成日程。"
                items = await self.state.ensure_schedule(self._last_umo, force=True)
                return "✅ 日程已重新生成，共 " + str(len(items)) + " 条。"
            items = self.state.schedule.get(today_str()) or []
            if not items:
                items = await self.state.ensure_schedule(self._last_umo)
            activity = self.state.current_activity()
            lines = ["📅 今日日程"]
            for item in items:
                lines.append("%s-%s %s（%s）" % (
                    item.get("start", ""), item.get("end", ""),
                    item.get("activity", ""), item.get("place", ""),
                ))
            lines.append("现在应该在：" + str(activity.get("activity", "")))
            return "\n".join(lines)

        if sub == "weather" or sub == "天气":
            if len(args) >= 2 and args[1].lower() in ("refresh", "刷新"):
                await self.state.refresh_weather(force=True)
            weather = await self.state.refresh_weather()
            return (
                "🌦 " + str(weather.get("city", "")) + " " + str(weather.get("text", ""))
                + " " + str(weather.get("temp", "")) + "℃\n"
                + "湿度：" + str(weather.get("humidity", "")) + "%\n"
                + "风：" + str(weather.get("wind", "")) + "\n"
                + "来源：" + ("和风天气" if weather.get("source") == "qweather" else "本地模拟")
            )

        if sub == "worldview" or sub == "世界观":
            if len(args) >= 2 and args[1].lower() == "regen":
                if not self._is_admin(event):
                    return "只有管理员才能重生成世界观。"
                await self.state.ensure_worldview(self._last_umo, force=True)
                return "✅ 世界观已重新生成。"
            await self.state.ensure_worldview(self._last_umo)
            return "🌍 世界观\n" + self.state.worldview_text()

        if sub == "threshold" or sub == "阈值":
            data = await self._status_data()
            threshold = data["threshold"]
            return (
                "🎚 心流回复阈值\n"
                "当前动态阈值：" + str(round(threshold["value"] / 100, 3)) + "\n"
                "基础阈值：" + str(round(threshold["base"] / 100, 3)) + "\n"
                "绝对分数阈值：" + str(threshold["absolute"]) + "/10\n"
                "当前群活跃度：" + str(data["activity_rate"]) + "%\n"
                "说明：阈值越高越不想说话；详细状态用 /heartflow。"
            )

        if sub == "say" or sub == "说":
            if not self._is_admin(event):
                return "只有管理员才能测试发言。"
            content = " ".join(args[1:]).strip()
            if not content:
                return "用法：/amo say 内容"
            await event.send(MessageChain([Comp.Plain(content)]))
            return ""

        if sub == "clean" or sub == "清理":
            if not self._is_admin(event):
                return "只有管理员才能清理。"
            self.db.purge_messages(self.cfg_int("chat_log_days", 14))
            return "✅ 已清理过期聊天记录。"

        return "未知指令。发送 /amo help 查看帮助。"

    # ---------- 心流完整版指令 ----------
    @filter.command("heartflow")
    async def cmd_heartflow(self, event: AstrMessageEvent):
        await self._ensure_ready()
        if self.heartflow is None:
            yield event.plain_result("心流引擎未加载")
            return
        async for item in self.heartflow.heartflow_status(event):
            yield item

    @filter.command("heartflow_debug")
    async def cmd_heartflow_debug(self, event: AstrMessageEvent):
        await self._ensure_ready()
        if self.heartflow is None:
            yield event.plain_result("心流引擎未加载")
            return
        async for item in self.heartflow.heartflow_debug(event):
            yield item

    @filter.command("heartflow_clear")
    async def cmd_heartflow_clear(self, event: AstrMessageEvent):
        await self._ensure_ready()
        if self.heartflow is None:
            yield event.plain_result("心流引擎未加载")
            return
        async for item in self.heartflow.heartflow_clear_buffer(event):
            yield item

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("heartflow_log")
    async def cmd_heartflow_log(self, event: AstrMessageEvent):
        await self._ensure_ready()
        if self.heartflow is None:
            yield event.plain_result("心流引擎未加载")
            return
        async for item in self.heartflow.heartflow_toggle_log(event):
            yield item

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("heartflow_reset")
    async def cmd_heartflow_reset(self, event: AstrMessageEvent):
        await self._ensure_ready()
        if self.heartflow is None:
            yield event.plain_result("心流引擎未加载")
            return
        async for item in self.heartflow.heartflow_reset(event):
            yield item

    @filter.command("heartflow_help")
    async def cmd_heartflow_help(self, event: AstrMessageEvent):
        await self._ensure_ready()
        if self.heartflow is None:
            yield event.plain_result("心流引擎未加载")
            return
        async for item in self.heartflow.heartflow_help(event):
            yield item

    @filter.command("amo")
    async def cmd_amo(self, event: AstrMessageEvent):
        await self._ensure_ready()
        try:
            message = await self._handle_command(event)
        except Exception as exc:
            logger.error("[amo] 指令异常: %s" % exc)
            message = "处理失败：" + str(exc)
        if message:
            yield event.plain_result(message)

    @filter.command("c_status")
    async def cmd_status(self, event: AstrMessageEvent):
        await self._ensure_ready()
        yield event.plain_result(self._format_status(await self._status_data()))

    @filter.command("c_profile")
    async def cmd_profile(self, event: AstrMessageEvent):
        await self._ensure_ready()
        uid = self._canonical_uid(event)
        profile = self.db.get_profile(uid)
        if not profile:
            yield event.plain_result("还没有你的档案。")
            return
        yield event.plain_result(
            "🤍 关系：" + str(profile.get("relation", "普通"))
            + "\n📖 记忆条数：" + str(len(self._external_all_memories(uid, "", 200)))
        )

    @filter.command("c_setrel")
    async def cmd_setrel(self, event: AstrMessageEvent):
        await self._ensure_ready()
        if not self._is_admin(event):
            yield event.plain_result("只有管理员才能调整关系。")
            return
        parts = [item for item in (event.message_str or "").replace("/", " ").split() if item]
        relation = parts[-1] if parts else ""
        if relation not in RELATIONS:
            yield event.plain_result("用法：/c_setrel 仇恨|抵触|普通|熟识|相恋")
            return
        uid = self._canonical_uid(event)
        self.db.update_profile(uid, relation=relation)
        yield event.plain_result("✅ 关系已设置为：" + relation)

    @filter.command("learn_and_gate")
    async def cmd_learn(self, event: AstrMessageEvent):
        await self._ensure_ready()
        text = (event.message_str or "").replace("/learn_and_gate", "").strip()
        if not text:
            yield event.plain_result("请输入要学习的内容")
            return
        uid = self._canonical_uid(event)
        if self._external_memory_write(uid, text, "manual", 1):
            yield event.plain_result("✅ 已经记下来啦。")
        else:
            yield event.plain_result("⚠️ 没能写进记忆插件：请先在设置里选好记忆来源插件。")

    @filter.command("礼物")
    async def cmd_gift_list(self, event: AstrMessageEvent):
        await self._ensure_ready()
        if self.gift is None or not self.gift.enabled:
            yield event.plain_result("礼物功能还没开。")
            return
        if not self.gift.is_owner(event):
            yield event.plain_result("这个只给主人看哦。")
            return
        yield event.plain_result(self.gift.command_text())

    @filter.command("送礼")
    async def cmd_gift_send(self, event: AstrMessageEvent, item: str = ""):
        await self._ensure_ready()
        if self.gift is None or not self.gift.enabled:
            yield event.plain_result("礼物功能还没开。")
            return
        if not self.gift.is_owner(event):
            yield event.plain_result("这个只给主人用哦。")
            return
        yield event.plain_result(self.gift.manual_gift(event, item))

    # ---------- Web 面板 ----------
        # 不注册无前缀的旧路由，避免和其他插件或 AstrBot 自带路由冲突。


    def _safe_register(self, route, handler, methods, desc):
        # 写接口只收 POST：面板的 WRITE_ACTIONS 已经强制带 body 走 POST，
        # 老版本面板桥接没有 apiPost 时会收到 405/403，然后自动退回 fetch POST（前端有兜底）。
        # 读接口不套守卫，避免给状态轮询加额外开销。
        # 注意：route 带插件名前缀（/Astrbot_Amo_forever/...），WRITE_ROUTES 里存的是不带前缀的
        # 路径，所以要拿 desc（注册时传的 path）来判定，否则所有写路由都会被漏掉。
        is_write = str(desc or "") in WRITE_ROUTES
        if is_write:
            methods = ["POST"]
        if is_write:
            handler = self._web_guard(handler, is_write=True)
        try:
            self.context.register_web_api(route, handler, methods, desc)
            return True
        except TypeError:
            pass
        except Exception as exc:
            logger.debug("[amo] Web API 注册失败 %s: %s" % (route, exc))
            return False
        try:
            self.context.register_web_api(route, methods, desc, handler)
            return True
        except Exception as exc:
            logger.debug("[amo] Web API 兼容注册失败 %s: %s" % (route, exc))
            return False

    def _q(self, key, default=None):
        try:
            if web_request is not None:
                return web_request.query.get(key, default)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._q", _amo_exc)
        return default

    def _q_int(self, key, default=0):
        return to_int(self._q(key, default), default)

    async def _body(self):
        try:
            if web_request is not None and hasattr(web_request, "json"):
                data = await web_request.json(default={})
                return data if isinstance(data, dict) else {}
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._body", _amo_exc)
        try:
            if web_request is not None:
                data = await web_request.get_json(silent=True)
                return data or {}
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._body", _amo_exc)
        return {}

    @staticmethod
    def _coerce_config_value(kind, value):
        if kind == "bool":
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in ("1", "true", "yes", "on", "是")
        if kind == "int":
            return int(float(value))
        if kind == "float":
            return float(value)
        if kind in ("list", "template_list"):
            if isinstance(value, list):
                return value
            parsed = json.loads(value) if isinstance(value, str) and value.strip() else []
            return parsed if isinstance(parsed, list) else []
        if kind in ("dict", "object"):
            if isinstance(value, dict):
                return value
            parsed = json.loads(value) if isinstance(value, str) and value.strip() else {}
            return parsed if isinstance(parsed, dict) else {}
        return str(value)

    def _schema_map(self):
        path = os.path.join(self.plugin_dir, "_conf_schema.json")
        try:
            with open(path, encoding="utf-8") as stream:
                schema = json.load(stream)
            return schema if isinstance(schema, dict) else {}
        except Exception as exc:
            logger.warning("[amo] 读取配置 schema 失败: %s" % exc)
            return {}

    # 这些值绝不能随 /config 明文下发（GET 无 body、无 CSRF 校验）
    SENSITIVE_KEYS = {"hefeng_key", "deepseek_api_key"}

    @staticmethod
    def _mask_secret(value):
        text = str(value or "")
        if not text:
            return ""
        if len(text) <= 8:
            return "*" * len(text)
        return text[:4] + "*" * (len(text) - 8) + text[-4:]

    def _config_schema_items(self):
        schema = self._schema_map()
        items = []
        for key, meta in schema.items():
            if not isinstance(meta, dict):
                continue
            if key.startswith("hf_"):
                group = "心流"
            elif key.startswith("seg_"):
                group = "分段"
            elif key.startswith("companion_") or key.startswith("memory_") or key in ("admin_uids",):
                group = "记忆"
            elif key.startswith("proactive_") or key.startswith("delay_") or key.startswith("disturb_") or key in ("quiet_hours", "auto_active_msg"):
                group = "私聊"
            elif key.startswith("period_") or key.startswith("enable_period") or key.startswith("enable_sick"):
                group = "状态"
            else:
                group = "基础"
            items.append({
                "key": key,
                "type": meta.get("type", "string"),
                "description": meta.get("description") or key,
                "hint": meta.get("hint", ""),
                "default": meta.get("default"),
                "options": meta.get("options") or [],
                "special": meta.get("_special", ""),
                "group": group,
                "value": (
                    self._mask_secret(self.cfg(key, meta.get("default")))
                    if key in self.SENSITIVE_KEYS
                    else self.cfg(key, meta.get("default"))
                ),
                "configured": (
                    bool(str(self.cfg(key, "") or "").strip())
                    if key in self.SENSITIVE_KEYS
                    else True
                ),
                "sensitive": key in self.SENSITIVE_KEYS,
            })
        return items

    async def _apply_runtime_config(self):
        self._admin_cache = {}
        self.bot_name = self.cfg_str("bot_name", self.bot_name) or "陪伴"
        self._persona_name_cache.clear()
        self.bot_aliases = [
            item.strip() for item in self.cfg_str("bot_aliases", "").split(",") if item.strip()
        ]
        self.admin_uids = {
            item.strip() for item in self.cfg_str("admin_uids", "").split(",") if item.strip()
        }
        if self.state is not None:
            start = self.cfg_str("period_start", "").strip()
            if start and start != self.state.period_start:
                try:
                    date.fromisoformat(start)
                    self.state.set_period_start(start)
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin._apply_runtime_config", _amo_exc)
            try:
                await self.state.refresh_weather(force=True)
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._apply_runtime_config", _amo_exc)
        if HeartflowEngine is not None:
            old = self.heartflow
            if old is not None:
                try:
                    await old.terminate()
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin._apply_runtime_config", _amo_exc)
            try:
                hf_config = self._hf_config()
                hf_config.setdefault("enable_heartflow", True)
                hf_config.setdefault("enable_dynamic_threshold", True)
                hf_config.setdefault("judge_provider_name", "")
                self.heartflow = HeartflowEngine(self.context, hf_config)
                self.heartflow.set_identity(self.bot_name, self.bot_aliases)
            except Exception as exc:
                logger.error("[amo] 应用心流配置失败: %s" % exc)
        if SegmentEngine is not None:
            old = self.segment_engine
            if old is not None:
                for task in list(getattr(old, "_tasks", set())):
                    try:
                        task.cancel()
                    except Exception as _amo_exc:
                        _note_swallowed("main.HumanCorePlugin._apply_runtime_config", _amo_exc)
            try:
                seg_config = self._seg_config()
                seg_config.setdefault("protect_paired_symbols", True)
                self.segment_engine = SegmentEngine(self.context, seg_config, plugin=self)
            except Exception as exc:
                logger.error("[amo] 应用分段配置失败: %s" % exc)

    # ---- 中文城市名 → LocationID（离线表，见 amo_city_index.py） ----
    def _city_module(self):
        """离线城市表模块（懒加载；缺失时返回 None，天气按原样走）。"""
        try:
            try:
                from . import amo_city_index
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._city_module", _amo_exc)
                import amo_city_index
            return amo_city_index
        except Exception as exc:
            logger.debug("[amo] 城市表不可用: %s" % exc)
            return None

    def _city_lookup(self, text):
        """把「东莞」「北京朝阳」解析成 LocationID；失败返回 None。"""
        module = self._city_module()
        if module is None:
            return None
        try:
            return module.resolve_city(text)
        except Exception as exc:
            logger.debug("[amo] 城市名解析失败: %s" % exc)
            return None

    async def _maybe_follow_city(self, event, uid, profile):
        """他到了某地：她问「我来陪你吧」；同意就跟去（路上约 2 小时），拒绝就闷闷不乐。"""
        if not self.cfg_bool("city_follow_enabled", True):
            return ""
        try:
            if not event.is_private_chat():
                return ""
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._maybe_follow_city", _amo_exc)
            return ""
        if str(profile.get("relation") or "") != "相恋":
            return ""
        text = str(event.message_str or "")
        now = now_ts()
        offer = self.db.kv_get("follow_offer", {}) or {}
        offer = offer if isinstance(offer, dict) else {}
        if offer and now - to_float(offer.get("ts"), 0) > 1800:
            self.db.kv_set("follow_offer", {})
            offer = {}
        travel = self.db.kv_get("travel", {}) or {}
        travel = travel if isinstance(travel, dict) else {}
        if travel.get("city") and re.search(r"(回来吧|回家吧|别玩了|该回来了|我回东莞)", text):
            await self._end_follow_trip(uid)
            return "【回家】他说回来了：自然应一句「好，我这就回」，别拖，也别说还没玩够。"
        if travel.get("city"):
            return ""
        if self.db.kv_get("wander_trip", {}):
            return ""
        if _follow_invite(text):
            city = str(self.db.kv_get("he_city", "") or "").strip()
            if not city:
                return "【邀请】他让你过去，但你不知道他在哪个城市：先问一句他在哪。"
            if city == _CITY_DEFAULT:
                return "【邀请】他让你过去，可你俩都在东莞：自然回一句“我不就在你旁边吗”之类的。"
            self.db.kv_set("follow_declined", {})
            return await self._start_follow_trip(uid, {
                "city": city, "id": "",
                "tomorrow": _now().hour >= 22,
            })
        if offer.get("city"):
            if _wander_agree(text):
                return await self._start_follow_trip(uid, offer)
            if _follow_refuse(text):
                return await self._reject_follow_trip(uid, offer)
        old_he = str(self.db.kv_get("he_city", "") or "").strip()
        old = str(self.db.kv_get("his_city", "") or "").strip()
        hit = _city_detect(text, prefer_city=old or old_he)
        if not hit:
            return ""
        name = str(hit.get("name") or "").strip()
        declined = self.db.kv_get("follow_declined", {}) or {}
        declined_city = str(declined.get("city") or "") if isinstance(declined, dict) else ""
        if not name or name == old_he:
            if declined_city and declined_city == name:
                return "【别重复提】你之前问过要不要去陪他，他没让；别再主动提这事，按他说的上班就好。"
            return ""
        if name == _CITY_DEFAULT:
            self.db.kv_set("he_city", name)
            self.db.kv_set("follow_declined", {})
            return ""
        # 到了新的城市：之前"被拒过"的标记作废，可以再问一次
        self.db.kv_set("follow_declined", {})
        tomorrow = _now().hour >= 22
        self.db.kv_set("he_city", name)
        self.db.kv_set("wander_offer", {})
        self.db.kv_set("follow_offer", {
            "ts": now, "city": name, "id": str(hit.get("id") or ""), "tomorrow": tomorrow,
        })
        return _follow_block(True, name, tomorrow)

    async def _start_follow_trip(self, uid, offer):
        """同意跟去：定出发日/出发时间，当天或次日先坐 2 小时车再玩。"""
        city = str(offer.get("city") or "").strip()
        if not city:
            self.db.kv_set("follow_offer", {})
            return ""
        tomorrow = bool(offer.get("tomorrow"))
        start = (_now().date() + timedelta(days=1)) if tomorrow else _now().date()
        start_hour = 9 if tomorrow else _now().hour
        spots = []
        try:
            spots = _city_pick_spots(self.scenic_spots(), city, start.isoformat())
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._start_follow_trip", _amo_exc)
            spots = []
        trip = {
            "city": city,
            "id": str(offer.get("id") or ""),
            "from": str(self.db.kv_get("his_city", "") or ""),
            "start_day": start.isoformat(),
            "start_hour": start_hour,
            "spots": [dict(x) for x in spots][:4],
            "phase": "journey",
        }
        self.db.kv_set("travel", trip)
        self.db.kv_set("follow_offer", {})
        self.db.kv_set("follow_declined", {})
        try:
            content = "她 %s 坐车去 %s 陪他（路上约 2 小时）" % (start.isoformat(), city)
            if not await self._write_memory_checked(uid, content, "event", 1):
                logger.warning("[amo] 跟随记忆没写进去")
        except Exception as exc:
            logger.warning("[amo] 跟随记忆写入失败: %s" % exc)
        try:
            log = self.db.kv_get("travel_log", []) or []
            if not isinstance(log, list):
                log = []
            log.append({"day": start.isoformat(), "hour": "%02d:00" % start_hour,
                        "city": city, "journey": True})
            self.db.kv_set("travel_log", log[-10:])
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._start_follow_trip", _amo_exc)
        if not tomorrow:
            self.db.kv_set("his_city", city)
            hit = self._city_lookup(city)
            if hit:
                try:
                    await self._switch_weather_city(hit)
                except Exception as exc:
                    logger.warning("[amo] 跟随天气切换失败: %s" % exc)
            try:
                self.state.apply_follow_start(city, start_hour, spots, keep_past=True)
            except Exception as exc:
                logger.warning("[amo] 跟随日程失败: %s" % exc)
            trip["phase"] = "touring"
            self.db.kv_set("travel", trip)
        plan = _wander_follow_agree_text(city, random)
        when = "明天一早" if tomorrow else "现在"
        return (
            "【出发】他同意了：你" + when + "出发去 " + city + " 陪他，路上约 2 小时，到了再找他。"
            "照这个意思说一句（别报公司/上班）：" + plan
        )

    async def _reject_follow_trip(self, uid, offer):
        """他让她好好上班：她闷闷不乐，日程不变，日记记一笔。"""
        city = str(offer.get("city") or "").strip()
        self.db.kv_set("follow_offer", {})
        self.db.kv_set("follow_declined", {"city": city, "day": today_str()})
        try:
            self.state.nudge(委屈=10, 郁闷=8, 开心=-6)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._reject_follow_trip", _amo_exc)
        try:
            content = "她说想去%s陪他，他让她好好上班，她闷闷不乐" % city
            if not await self._write_memory_checked(uid, content, "event", 1):
                logger.warning("[amo] 被拒记忆没写进去")
        except Exception as exc:
            logger.warning("[amo] 被拒记忆失败: %s" % exc)
        try:
            log = self.db.kv_get("follow_reject_log", []) or []
            if not isinstance(log, list):
                log = []
            log.append({"day": today_str(), "hour": "%02d:00" % _now().hour, "city": city})
            self.db.kv_set("follow_reject_log", log[-10:])
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._reject_follow_trip", _amo_exc)
        return _follow_block(False, city)

    async def _end_follow_trip(self, uid):
        """结束跟随：回家、恢复城市/天气/日程、写回来记忆。"""
        trip = self.db.kv_get("travel", {}) or {}
        city = str(trip.get("city") or "") if isinstance(trip, dict) else ""
        self.db.kv_set("travel", {})
        home = _CITY_DEFAULT
        self.db.kv_set("his_city", home)
        self.db.kv_set("he_city", home)
        hit = self._city_lookup(home)
        if hit:
            try:
                await self._switch_weather_city(hit)
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._end_follow_trip", _amo_exc)
        try:
            self.state.apply_travel_overlay(home)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._end_follow_trip", _amo_exc)
        try:
            content = "她 %s 从 %s 回来了" % (today_str(), city)
            await self._write_memory_checked(uid, content, "event", 1)
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._end_follow_trip", _amo_exc)
        try:
            log = self.db.kv_get("travel_log", []) or []
            if isinstance(log, list):
                log.append({
                    "day": today_str(), "hour": "%02d:00" % _now().hour,
                    "city": city, "back": True,
                })
                self.db.kv_set("travel_log", log[-10:])
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._end_follow_trip", _amo_exc)


    async def _maybe_wander(self, event, uid, profile):
        """她自己出去玩：问意愿 → 同意 → 定行程；旅行中让他叫回来。"""
        if not self.cfg_bool("wander_enabled", True):
            return ""
        try:
            if not event.is_private_chat():
                return ""
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._maybe_wander", _amo_exc)
            return ""
        if str(profile.get("relation") or "") != "相恋":
            return ""
        if self.db.kv_get("travel", {}) or self.db.kv_get("follow_offer", {}):
            return ""
        text = str(event.message_str or "")
        now = now_ts()
        trip = self.db.kv_get("wander_trip", {}) or {}
        trip = trip if isinstance(trip, dict) else {}
        if trip.get("city") and re.search(r"(回来吧|回家吧|别玩了|早点回来|该回来了)", text):
            await self._end_solo_trip(uid, "他让你回来")
            return "【旅游】他让你回来：自然应一句“好，我收拾下就回”，别拖，也别说还没玩够。"
        offer = self.db.kv_get("wander_offer", {}) or {}
        offer = offer if isinstance(offer, dict) else {}
        if offer and now - to_float(offer.get("ts"), 0) > 1800:
            self.db.kv_set("wander_offer", {})
            offer = {}
        if _wander_question(text):
            if (
                self.db.kv_get("travel", {})
                or self.db.kv_get("follow_offer", {})
                or self.db.kv_get("wander_trip", {})
            ):
                return ""
            today = today_str()
            count = 0
            if str(self.db.kv_get("wander_asked_day", "") or "") == today:
                try:
                    count = int(self.db.kv_get("wander_ask_count", 0) or 0)
                except (TypeError, ValueError):
                    count = 0
            limit = _wander_ask_limit(self.cfg_bool("wander_ask_three_times", False))
            if count >= limit:
                return (
                    "【旅游提议】今天已经问过 " + str(count) + " 次了（一天最多 " + str(limit)
                    + " 次），别再重新决定、别再报新城市；按之前说的自然接一句。"
                )
            self.db.kv_set("wander_asked_day", today)
            self.db.kv_set("wander_ask_count", count + 1)
            low, tired = _wander_assess(self.state.mood, self.state.health_info())
            want = _wander_want(
                low, tired, random,
                self.cfg_float("wander_prob_low", 0.85),
                self.cfg_float("wander_prob_good", 0.15),
            )
            city, spots = "", []
            if want:
                city, spots = _wander_pick(
                    self.scenic_spots(), random, count=4,
                    exclude_city=str(self.db.kv_get("his_city", "") or ""),
                )
                want = bool(city)
            if not want:
                self.db.kv_set("wander_offer", {"ts": now, "want": False})
            else:
                self.db.kv_set("wander_offer", {
                    "ts": now, "want": True, "city": city,
                    "spots": [str(x.get("name") or "") for x in spots][:4],
                    "spot_rows": spots[:4],
                })
            return _wander_offer_block(bool(want), city, spots)
        if offer.get("want") and _wander_agree(text):
            return await self._start_solo_trip(uid, offer)
        if offer.get("want") and _wander_refuse(text):
            self.db.kv_set("wander_offer", {})
            try:
                self.state.nudge(委屈=5, 郁闷=4)
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._maybe_wander", _amo_exc)
            return (
                "【不出去了】他说这次不让你去：你有点失落，但别闹，用自己的口吻说一句："
                + _wander_solo_refuse_text(random)
            )
        if trip.get("city") and not trip.get("announced"):
            start = str(trip.get("day") or "")
            ret = str(trip.get("return_day") or start)
            if start and start <= today_str() <= ret:
                try:
                    day_no = (_now().date() - date.fromisoformat(start)).days + 1
                except Exception as _amo_exc:
                    _note_swallowed("main.HumanCorePlugin._maybe_wander", _amo_exc)
                    day_no = 1
                return _wander_solo_block(str(trip["city"]), trip.get("spots") or [], day_no=day_no)
        return ""

    async def _start_solo_trip(self, uid, offer):
        """确认出发：>=22 点明天走，否则现在就走。"""
        city = str(offer.get("city") or "").strip()
        spots = [x for x in (offer.get("spot_rows") or []) if isinstance(x, dict)]
        if not city:
            self.db.kv_set("wander_offer", {})
            return ""
        tomorrow = _now().hour >= 22
        start = (_now().date() + timedelta(days=1)) if tomorrow else _now().date()
        days = max(1, min(3, _wander_trip_days(random)))
        if days == 1 and not tomorrow and _now().hour >= 17:
            days = 2  # 傍晚才走，别刚出门就回家
        return_day = start + timedelta(days=days - 1)
        return_hour = 21 if days == 1 else 12
        hit = self._city_lookup(city)
        trip = {
            "city": city,
            "id": str((hit or {}).get("id") or ""),
            "day": start.isoformat(),
            "days": days,
            "return_day": return_day.isoformat(),
            "return_hour": return_hour,
            "spots": [str(x.get("name") or "") for x in spots][:4],
            "phase": "planned",
        }
        self.db.kv_set("wander_trip", trip)
        self.db.kv_set("wander_offer", {})
        try:
            content = "她 %s 一个人去 %s 旅游（他同意了，玩 %d 天）" % (start.isoformat(), city, days)
            if not await self._write_memory_checked(uid, content, "event", 1):
                logger.warning("[amo] 旅游记忆没写进去")
        except Exception as exc:
            logger.warning("[amo] 旅游记忆写入失败: %s" % exc)
        try:
            log = self.db.kv_get("travel_log", []) or []
            if not isinstance(log, list):
                log = []
            log.append({
                "day": start.isoformat(), "hour": "%02d:00" % _now().hour,
                "city": city, "solo": True,
            })
            self.db.kv_set("travel_log", log[-10:])
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._start_solo_trip", _amo_exc)
        if not tomorrow:
            if hit:
                try:
                    await self._switch_weather_city(hit)
                except Exception as exc:
                    logger.warning("[amo] 旅游天气切换失败: %s" % exc)
            try:
                self.state.apply_travel_overlay(city)
            except Exception as exc:
                logger.warning("[amo] 旅游日程失败: %s" % exc)
            trip["phase"] = "applied"
            self.db.kv_set("wander_trip", trip)
        agree = _wander_solo_agree_text(city, random)
        plan = _wander_plan_text(city, spots, tomorrow, random)
        when = "明天" if tomorrow else "现在"
        back_text = "第 %d 天中午回来" % days if days > 1 else "当晚回来"
        return (
            "【出发】他同意了：你" + when + "去 " + city + " 旅游（一个人），玩 %d 天，%s。"
            % (days, back_text) + "先照这个说一句：" + agree + " 再说安排：" + plan
            + " 别说成跟他一起；白天自己去景点，晚上住酒店。"
        )

    async def _maybe_solo_return(self):
        """旅游最后一天到点回家：换天气、报平安、写记忆/日记。"""
        trip = self.db.kv_get("wander_trip", {}) or {}
        if not isinstance(trip, dict) or not trip.get("city") or trip.get("announced"):
            return
        ret_day = str(trip.get("return_day") or "")
        if not ret_day or today_str() != ret_day:
            return
        try:
            hour = int(trip.get("return_hour") or 12)
        except (TypeError, ValueError):
            hour = 12
        if _now().hour < hour:
            return
        city = str(trip["city"])
        his = str(self.db.kv_get("his_city", "") or "").strip() or _CITY_DEFAULT
        hit = self._city_lookup(his)
        if hit:
            try:
                await self._switch_weather_city(hit)
            except Exception as exc:
                logger.warning("[amo] 回来天气切换失败: %s" % exc)
        try:
            self.state.apply_travel_overlay(his)
        except Exception as exc:
            logger.warning("[amo] 回来日程失败: %s" % exc)
        # 报平安必须进私聊：以前用 _last_umo，他最后一句是在群里就会把「我回来啦」发进群。
        umo = self._first_private_umo()
        if not umo:
            last = str(getattr(self, "_last_umo", "") or "")
            umo = last if "FriendMessage" in last else ""
        uid = ""
        try:
            rows = self.db.list_profiles(limit=1) or []
            uid = str((rows[0] or {}).get("uid") or "") if rows else ""
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._maybe_solo_return", _amo_exc)
            uid = ""
        try:
            if umo:
                text = random.choice((
                    "我回来啦，刚到家。",
                    "到家啦，你在干嘛呢？",
                    "我回来了，你吃饭了没？",
                ))
                if await self._send_to_umo(umo, text):
                    self._mark_bot_initiated(umo)
                    if uid:
                        self._set_proactive_pending(uid, "travel_back", text, umo=umo)
        except Exception as exc:
            logger.warning("[amo] 回来报平安失败: %s" % exc)
        try:
            if uid:
                if not await self._write_memory_checked(
                    uid, "她 %s 从 %s 旅游回来了" % (today_str(), city), "event", 1,
                ):
                    logger.warning("[amo] 回来记忆没写进去")
        except Exception as exc:
            logger.warning("[amo] 回来记忆失败: %s" % exc)
        try:
            log = self.db.kv_get("travel_log", []) or []
            if isinstance(log, list):
                log.append({
                    "day": today_str(), "hour": "%02d:00" % _now().hour,
                    "city": city, "solo": True, "back": True,
                })
                self.db.kv_set("travel_log", log[-10:])
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._maybe_solo_return", _amo_exc)
        trip["announced"] = True
        self.db.kv_set("wander_trip", trip)
        logger.info("[amo] 旅游回来：%s" % city)

    async def _end_solo_trip(self, uid, reason=""):
        """结束 solo 旅游：清状态、记回来、天气换回他在的城市、日程回家。"""
        trip = self.db.kv_get("wander_trip", {}) or {}
        if not isinstance(trip, dict) or not trip.get("city"):
            return
        city = str(trip["city"])
        self.db.kv_set("wander_trip", {})
        try:
            content = "她 %s 从 %s 旅游回来了" % (today_str(), city)
            if not await self._write_memory_checked(uid, content, "event", 1):
                logger.warning("[amo] 回来记忆没写进去")
        except Exception as exc:
            logger.warning("[amo] 回来记忆写入失败: %s" % exc)
        try:
            log = self.db.kv_get("travel_log", []) or []
            if not isinstance(log, list):
                log = []
            log.append({
                "day": today_str(), "hour": "%02d:00" % _now().hour,
                "city": city, "solo": True, "back": True,
            })
            self.db.kv_set("travel_log", log[-10:])
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._end_solo_trip", _amo_exc)
        his = str(self.db.kv_get("his_city", "") or "").strip() or _CITY_DEFAULT
        hit = self._city_lookup(his)
        if hit:
            try:
                await self._switch_weather_city(hit)
            except Exception as exc:
                logger.warning("[amo] 回来天气切换失败: %s" % exc)
        try:
            self.state.apply_travel_overlay(his)
        except Exception as exc:
            logger.warning("[amo] 回来日程失败: %s" % exc)





    # ---- 用量 / 余额 ----
    def _usage_db_path(self):
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path
            return os.path.join(str(get_astrbot_data_path()), "data_v4.db")
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._usage_db_path", _amo_exc)
            try:
                data_dir = os.path.dirname(os.path.dirname(os.path.dirname(str(self.db.path))))
                return os.path.join(data_dir, "data_v4.db")
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._usage_db_path", _amo_exc)
                return ""

    def _deepseek_api_key(self):
        key = str(self.cfg_str("deepseek_api_key", "") or "").strip()
        if key:
            return key
        for name in ("DEEPSEEK_API_KEY", "COMPANION_V2_BALANCE_API_KEY"):
            value = str(os.environ.get(name, "") or "").strip()
            if value:
                return value
        return ""

    def _usage_prices(self):
        prices = {}
        for key in ("hit_peak", "hit_idle", "miss_peak", "miss_idle", "out_peak", "out_idle"):
            prices[key] = self.cfg_float("usage_price_" + key, USAGE_DEFAULT_PRICES[key])
        return prices

    def _usage_start_of_today(self):
        now = _now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start.timestamp()

    # ---- 供应商识别 / 多模型用量 ----
    def _provider_inventory(self):
        """读取 AstrBot 已配置的对话供应商；只返回脱敏信息，绝不回传密钥。"""
        items = []
        try:
            providers = self.context.get_all_providers() or []
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._provider_inventory", _amo_exc)
            providers = []
        for provider in providers:
            config = getattr(provider, "provider_config", None) or {}
            pid = str(config.get("id") or "")
            if not pid:
                continue
            model = ""
            try:
                model = str(provider.get_model() or "")
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._provider_inventory", _amo_exc)
                model = str(config.get("model") or "")
            api_base = str(config.get("api_base") or config.get("url") or "").strip()
            key = config.get("key") or ""
            if isinstance(key, list):
                has_key = any(str(item or "").strip() for item in key)
            else:
                has_key = bool(str(key or "").strip())
            items.append({
                "id": pid,
                "model": model,
                "type": str(config.get("type") or ""),
                "enable": config.get("enable", True) is not False,
                "has_key": has_key,
                "api_base": api_base,
            })
        return items

    def _judge_provider_id(self):
        try:
            if self.heartflow is not None:
                return str(self.heartflow.judge_provider_info().get("id") or "")
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._judge_provider_id", _amo_exc)
        return ""

    def _using_provider_id(self):
        try:
            provider = self.context.get_using_provider()
            return str((getattr(provider, "provider_config", None) or {}).get("id") or "")
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._using_provider_id", _amo_exc)
            return ""


    @staticmethod
    def _balance_probe_kind(api_base):
        base = str(api_base or "").lower()
        if "deepseek" in base:
            return "deepseek"
        if "siliconflow" in base:
            return "siliconflow"
        return "openai_bill"

    async def _provider_balances_cached(self, providers):
        """逐个探测供应商余额；60 秒缓存，失败不阻塞面板。"""
        now = time.time()
        signature = "|".join(sorted(
            item["id"] + ":" + item["api_base"] + ":" + str(item["has_key"]) for item in providers
        ))
        cache = getattr(self, "_provider_balance_cache", None)
        if (
            isinstance(cache, dict)
            and now - to_float(cache.get("at"), 0) < 60
            and cache.get("signature") == signature
        ):
            return cache.get("data") or []
        enabled = [item for item in providers if item["enable"] and item["has_key"] and item["api_base"]]

        def probe(item):
            kind = self._balance_probe_kind(item["api_base"])
            key = self._provider_api_key(item)
            result = {"id": item["id"], "model": item["model"], "kind": kind}
            if not key:
                result.update({"ok": False, "error": "未配置密钥"})
                return result
            data = fetch_provider_balance(key, item["api_base"], kind)
            data["id"] = item["id"]
            data["model"] = item["model"]
            data["kind"] = kind
            return data

        results = []
        if enabled:
            def run_all():
                return [probe(item) for item in enabled]

            try:
                results = await asyncio.to_thread(run_all)
            except Exception as exc:
                logger.debug("[amo] 供应商余额探测失败: %s" % exc)
                results = []
        self._provider_balance_cache = {"at": now, "signature": signature, "data": results}
        return results

    def _provider_api_key(self, item):
        """从 AstrBot 供应商配置里取密钥；只在内存中使用，不写日志不回传。"""
        config = {}
        try:
            for provider in (self.context.get_all_providers() or []):
                candidate = getattr(provider, "provider_config", None) or {}
                if str(candidate.get("id") or "") == str(item.get("id") or ""):
                    config = candidate
                    break
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._provider_api_key", _amo_exc)
            config = {}
        key = config.get("key") or ""
        if isinstance(key, list):
            key = next((str(item or "").strip() for item in key if str(item or "").strip()), "")
        return str(key or "").strip()

    async def _balance_cached(self):
        """余额 60 秒内复用，避免面板每刷一次就打一次外网。"""
        now = time.time()
        cache = getattr(self, "_balance_cache", None)
        if isinstance(cache, dict) and now - float(cache.get("at") or 0) < 60:
            return cache.get("data") or {"ok": False, "error": "查询失败"}
        key = self._deepseek_api_key()
        data = await asyncio.to_thread(fetch_deepseek_balance, key)
        self._balance_cache = {"at": now, "data": data}
        return data







    def _purge_profile_kv(self, uid):
        """删掉这个 uid 专属的 kv（渠道/节流/主动消息/纪念日…），返回删除条数。"""
        prefixes = (
            "channels:", "last_channel:", "lover_uid_", "auto_learn_",
            "angel_profile_sync_", "companion_profile_sync_", "memcomp_profile_sync_",
            "proactive_ignored_", "proactive_depressed_until_",
            "proactive_followup_last_", "proactive_forced_hour_", "proactive_pending_",
            "ext_mem_count_", "ext_mem_count_at_",
        )
        try:
            rows = self.db.conn.execute("SELECT key FROM kv").fetchall()
        except Exception as _amo_exc:
            _note_swallowed("main.HumanCorePlugin._purge_profile_kv", _amo_exc)
            return 0
        keys = []
        for row in rows:
            try:
                key = str(row["key"] if hasattr(row, "keys") else row[0])
            except Exception as _amo_exc:
                _note_swallowed("main.HumanCorePlugin._purge_profile_kv", _amo_exc)
                continue
            if any(key == prefix + uid for prefix in prefixes):
                keys.append(key)
            elif key.startswith("ritual_") and ("_" + uid + "_") in key:
                keys.append(key)
        if not keys:
            return 0
        try:
            for key in keys:
                self.db.conn.execute("DELETE FROM kv WHERE key=?", (key,))
            self.db.conn.commit()
        except Exception as exc:
            logger.debug("[amo] 清理 kv 失败: %s" % exc)
            return 0
        return len(keys)






















