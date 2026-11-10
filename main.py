# -*- coding: utf-8 -*-
"""
我想永远陪着你 / 我想永远陪伴你 5.4.2
一个尽量“像人”的 AstrBot 智械人类核心：
生理期 / 九维心情 / 世界观与日程 / 天气 / 健康 / 群聊插话阈值 /
私聊判定 / 主动私聊 / 长期记忆与遗忘 / 防抖 / 分段与打字延迟 / 引用回复 / AI 润色
"""

try:
    from .amo_observability import note as _note_swallowed
except ImportError:  # 直接按文件加载时
    from amo_observability import note as _note_swallowed

import asyncio
import json
import math
import os
import random
import re
import sqlite3
import threading
from datetime import date, datetime, timedelta

# 统一时区：容器/服务器常在 UTC 跑，直接取服务器本地时间会把北京时间 10 点算成凌晨 2 点
# （「大晚上的」就是这么来的）。clock.now() 返回目标时区下的 naive 本地时间，
# 和原来的用法完全兼容。
try:
    from .clock import now as _clock_now, from_timestamp as _clock_from_ts, configure as _clock_configure, current_name as _clock_name
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
    from .amo_shared import _now, logger, filter, Context, Star, web_request, HeartflowEngine, SegmentEngine, parse_weather_daily, GiftEngine, _pg_analyze_rows, _pg_compose_task, _pg_near_duplicate, _CITY_DEFAULT, _city_travel_events, _city_travel_to_events, _city_pick_spots, ScheduleEngine, PLUGIN_NAME, SCHEDULE_VERSION, MOOD_KEYS, SICK_STATUSES, MOOD_BASE, now_ts, day_meta, today_str, other_platform_bot_lines, schedule_category_mood, weekday_cn, clamp, to_int, to_float, truncate, md5_int, parse_hhmm, minutes_now, in_minute_range, quiet_now, looks_like_plain_command, has_question, sentiment, tokens, overlap, json_extract_list, json_extract, clean_reply, looks_like_ai_admission
    from .amo_api import ApiMixin
    from .amo_proactive import ProactiveMixin
    from .amo_schedule import ScheduleMixin
    from .amo_llm import LlmMixin
except ImportError:
        from amo_shared import _now, logger, filter, Context, Star, web_request, HeartflowEngine, SegmentEngine, parse_weather_daily, GiftEngine, _pg_analyze_rows, _pg_compose_task, _pg_near_duplicate, _CITY_DEFAULT, _city_travel_events, _city_travel_to_events, _city_pick_spots, ScheduleEngine, PLUGIN_NAME, SCHEDULE_VERSION, MOOD_KEYS, SICK_STATUSES, MOOD_BASE, now_ts, day_meta, today_str, other_platform_bot_lines, schedule_category_mood, weekday_cn, clamp, to_int, to_float, truncate, md5_int, parse_hhmm, minutes_now, in_minute_range, quiet_now, looks_like_plain_command, has_question, sentiment, tokens, overlap, json_extract_list, json_extract, clean_reply, looks_like_ai_admission
        from amo_api import ApiMixin
        from amo_proactive import ProactiveMixin
        from amo_schedule import ScheduleMixin
        from amo_llm import LlmMixin

PLUGIN_VERSION = "6.6.8"

try:
    from .amo_memory import MemoryMixin
    from .amo_commands import CommandMixin
    from .amo_config import ConfigMixin
    from .amo_message import MessageMixin
    from .amo_social import SocialMixin
    from .amo_travel import TravelMixin
    from .amo_runtime import RuntimeMixin
    from .amo_kb import KbMixin
    from .amo_usage import UsageMixin
except ImportError:  # 直接按文件加载时
    from amo_memory import MemoryMixin
    from amo_commands import CommandMixin
    from amo_config import ConfigMixin
    from amo_message import MessageMixin
    from amo_social import SocialMixin
    from amo_travel import TravelMixin
    from amo_runtime import RuntimeMixin
    from amo_kb import KbMixin
    from amo_usage import UsageMixin

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


class HumanCorePlugin(MemoryMixin, CommandMixin, ConfigMixin, MessageMixin, SocialMixin, TravelMixin, RuntimeMixin, KbMixin, UsageMixin, ApiMixin, ScheduleMixin, ProactiveMixin, LlmMixin, Star):
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


    # ---------- 管理员 ----------

    # ---------- 消息学习 ----------




    # ---------- 近聊上下文（内存缓冲 + 记忆终端钩子） ----------
    CONTEXT_BUFFER_LIMIT = 60













    # ---------- 外挂记忆插件（牢记等）检索桥 ----------
    # 记忆检索桥：不同插件的入口名字不一样，按顺序找，找到哪个用哪个
    MEMORY_RECALL_METHODS = (
        "search_for_event", "recall_for_event",
        "search_memory", "recall_memory",
        "query_memory", "retrieve_memory", "retrieve",
    )

    # ---------- 配套数据插件（Astr_Amo_data / 我想永远记住你） ----------
    DATA_PLUGIN_NAMES = ("Astr_Amo_data", "astrbot_plugin_amo_data", "AstrAmoData")


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









    WRITE_METHODS = (
        "add_memory", "remember", "save_memory", "store_memory",
        "add_fact", "ingest_memory", "write_memory",
    )




    ANGEL_ATTRIBUTE_TAGS = {"用户别名", "事实属性", "技能树", "关系图谱", "活跃项目"}






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




# ---------- livingmemory（只读直连） ----------












    # ---------- 消息入口 ----------











    # ---------- 发送 ----------






    # ---------- LLM 注入 ----------


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




    # ---------- 后台循环 ----------








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



    # ---------- 心流完整版指令 ----------








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


    # 这些值绝不能随 /config 明文下发（GET 无 body、无 CSRF 校验）
    SENSITIVE_KEYS = {"hefeng_key", "deepseek_api_key"}


    # ---- 中文城市名 → LocationID（离线表，见 amo_city_index.py） ----








    # ---- 用量 / 余额 ----


    # ---- 供应商识别 / 多模型用量 ----




















