# -*- coding: utf-8 -*-
"""自拍姿势库（2026-11-12）。

她发自拍时从姿势库里随机挑一个姿势（托腮、比耶、撩头发…），不再每次都「随手拍」。
面板「姿势库」可以加/删姿势、保存，并能逐张生成「姿势参考图」给生图当参考。

数据：``plugin_data/Astrbot_Amo_forever/poses.json``
参考图：``plugin_data/Astrbot_Amo_forever/outfit_refs/姿势库/<姿势名>.png``
（和衣服参考图放在一起，备份 plugin_data 时统一带走。）
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import threading
import time

from astrbot.api import logger

try:  # 复用服装参考图的解码/转 PNG，避免两份实现漂移
    from .outfit_refs import _as_png, _decode_item
except Exception:  # pragma: no cover
    try:
        from outfit_refs import _as_png, _decode_item
    except Exception:
        _as_png = _decode_item = None

try:
    from .amo_image_common import find_omni
except Exception:  # pragma: no cover
    try:
        from amo_image_common import find_omni
    except Exception:
        find_omni = None

OUTFIT_REF_DIR_NAME = "outfit_refs"
REF_DIR_NAME = "姿势库"
#: 老版本把姿势图放在 plugin_data/pose_refs 下，启动时自动搬到 outfit_refs/姿势库
LEGACY_REF_DIR_NAME = "pose_refs"
MAX_POSES = 60
_SAFE_RE = re.compile(r'[\\/:*?"<>|\r\n]+')

#: 内置姿势：(名字, 画面描述)。描述会直接进自拍提示词，写得越具体越不容易走形。
SEED_POSES = (
    ("比耶", "一只手在脸颊旁边比耶，笑眼看镜头"),
    ("托腮", "单手托腮，手指轻贴脸颊，笑着看镜头"),
    ("撩头发", "一只手把耳侧的头发撩到耳后"),
    ("歪头笑", "头微微歪向一侧，笑眼弯弯"),
    ("抿嘴笑", "抿着嘴微笑，眼睛看着镜头"),
    ("眯眼笑", "笑到眯起眼睛，很放松"),
    ("嘟嘴", "微微嘟嘴，脸颊有点鼓"),
    ("咬唇", "轻轻咬一下下唇，有点害羞"),
    ("回眸", "侧过身再回头看向镜头"),
    ("侧脸", "脸转向一侧，露出侧脸轮廓"),
    ("低头看镜头", "微微低头、抬眼看镜头"),
    ("手机挡半张脸", "把手机举高挡住半张脸，只露出眼睛和额头"),
    ("单手撑脸", "手肘撑着桌面，手掌撑着脸颊"),
    ("靠墙", "侧身靠在墙上，头轻轻贴着墙面"),
    ("抱膝坐", "抱着膝盖坐在地上，抬眼看镜头"),
    ("趴桌", "趴在桌上，脸贴着胳膊看镜头"),
    ("伸懒腰", "举起双手伸懒腰，闭着眼笑"),
    ("整理头发", "手指穿过头发，眼神看向镜头"),
    ("喝奶茶", "吸管放在嘴边，眼睛看镜头"),
    ("抱着花", "怀里抱着花束，脸凑近花瓣"),
    ("抱枕头", "把枕头抱在胸前，下巴轻轻搭上去"),
    ("戴耳机", "一只耳机戴上，手指碰着耳罩"),
    ("眨眼", "对镜头眨一只眼，嘴角带笑"),
    ("比心", "单手在胸前比心"),
    ("探头", "从画面一侧探出半个身子"),
    ("抬手挡阳光", "手掌放在额头前挡光，眯着眼笑"),
)


def safe_name(name):
    text = _SAFE_RE.sub("_", str(name or "").strip())
    return text[:40].strip(" .") or "pose"


def _now_ts():
    return time.time()


def _new_id():
    return "p-%x" % random.randrange(1 << 40)


class PoseLibrary:
    VERSION = 1
    SEED_VERSION = 1

    def __init__(self, plugin):
        self.plugin = plugin
        self._lock = threading.RLock()
        self._data = None
        base = ""
        try:
            base = os.path.dirname(str(getattr(plugin.db, "path", "") or ""))
        except Exception:
            base = ""
        if not base:
            base = str(getattr(plugin, "plugin_dir", "") or ".")
        self.base = base
        self.path = os.path.join(base, "poses.json")
        # 姿势图跟衣服参考图放一起：outfit_refs/姿势库/<姿势名>.png
        self.ref_dir = os.path.join(base, OUTFIT_REF_DIR_NAME, REF_DIR_NAME)
        self.legacy_ref_dir = os.path.join(base, LEGACY_REF_DIR_NAME)
        self._migrate_legacy_refs()
        logger.info("[amo] 姿势库已加载（%s）" % self.path)

    def _migrate_legacy_refs(self):
        """把旧版 plugin_data/pose_refs/*.png 搬进 outfit_refs/姿势库/（只搬一次）。"""
        try:
            if not os.path.isdir(self.legacy_ref_dir):
                return
            for name in os.listdir(self.legacy_ref_dir):
                if not name.lower().endswith(".png"):
                    continue
                source = os.path.join(self.legacy_ref_dir, name)
                target = os.path.join(self.ref_dir, name)
                if not os.path.isfile(source) or os.path.isfile(target):
                    continue
                os.makedirs(self.ref_dir, exist_ok=True)
                os.replace(source, target)
                logger.info("[amo] 姿势参考图已搬到 outfit_refs/姿势库：%s" % name)
            try:
                if not os.listdir(self.legacy_ref_dir):
                    os.rmdir(self.legacy_ref_dir)
            except OSError:
                pass
        except Exception as exc:
            logger.warning("[amo] 姿势参考图搬迁失败: %s" % exc)

    # ---------- 存储 ----------

    def _empty(self):
        return {"version": self.VERSION, "seed_version": 0, "poses": []}

    def _load(self):
        with self._lock:
            if self._data is not None:
                return self._data
            data = None
            try:
                with open(self.path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except FileNotFoundError:
                data = None
            except Exception as exc:
                logger.warning("[amo] 姿势库读取失败: %s" % exc)
                data = None
            if not isinstance(data, dict) or not isinstance(data.get("poses"), list):
                data = self._empty()
            data.setdefault("version", self.VERSION)
            data.setdefault("poses", [])
            if int(data.get("seed_version") or 0) < self.SEED_VERSION:
                data = self._merge_seed(data)
                data["seed_version"] = self.SEED_VERSION
                self._save(data)
            self._data = data
            return data

    def _merge_seed(self, data):
        existing = {str(p.get("name") or "").strip() for p in data.get("poses") or []}
        for name, note in SEED_POSES:
            if name in existing:
                continue
            data["poses"].append({
                "id": _new_id(), "name": name, "note": note, "created_at": _now_ts(),
            })
        return data

    def _save(self, data=None):
        data = data if isinstance(data, dict) else self._load()
        with self._lock:
            tmp = self.path + ".tmp"
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=2)
                os.replace(tmp, self.path)
                self._data = data
                return True
            except Exception as exc:
                logger.warning("[amo] 姿势库保存失败: %s" % exc)
                return False

    # ---------- 查询 ----------

    def poses(self):
        return list(self._load().get("poses") or [])

    def has_ref(self, pose):
        try:
            return os.path.isfile(self.ref_path(pose)) and os.path.getsize(self.ref_path(pose)) > 0
        except Exception:
            return False

    def ref_path(self, pose):
        pose = pose if isinstance(pose, dict) else {}
        return os.path.join(self.ref_dir, safe_name(pose.get("name")) + ".png")

    def ref_for(self, pose):
        """已有的姿势参考图路径；没有就空串（不在这里现生成，避免拖慢出图）。"""
        path = self.ref_path(pose)
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            return path
        return ""

    def snapshot(self):
        poses = []
        for pose in self.poses():
            poses.append({
                "id": str(pose.get("id") or ""),
                "name": str(pose.get("name") or ""),
                "note": str(pose.get("note") or ""),
                "has_ref": self.has_ref(pose),
            })
        with_ref = len([p for p in poses if p["has_ref"]])
        return {"poses": poses, "count": len(poses), "with_ref": with_ref}

    def random_pose(self):
        poses = [p for p in self.poses() if str(p.get("name") or "").strip()]
        if not poses:
            return None
        return dict(random.choice(poses))

    # ---------- 修改 ----------

    def add(self, name, note=""):
        name = str(name or "").strip()[:40]
        note = str(note or "").strip()[:120]
        if not name:
            return {"ok": False, "msg": "先写个姿势名字，比如：托腮笑"}
        with self._lock:
            data = self._load()
            if len(data.get("poses") or []) >= MAX_POSES:
                return {"ok": False, "msg": "姿势最多 %d 个，先删几个" % MAX_POSES}
            if any(str(p.get("name") or "").strip() == name for p in data.get("poses") or []):
                return {"ok": False, "msg": "已经有「%s」这个姿势了" % name}
            data["poses"].append({
                "id": _new_id(), "name": name, "note": note, "created_at": _now_ts(),
            })
            if not self._save(data):
                return {"ok": False, "msg": "保存失败，看日志"}
            return {"ok": True, "msg": "已添加"}

    def delete(self, pose_id):
        pose_id = str(pose_id or "").strip()
        with self._lock:
            data = self._load()
            poses = list(data.get("poses") or [])
            keep = [p for p in poses if str(p.get("id") or "") != pose_id]
            if len(keep) == len(poses):
                return {"ok": False, "msg": "没找到这个姿势"}
            data["poses"] = keep
            if not self._save(data):
                return {"ok": False, "msg": "保存失败，看日志"}
            return {"ok": True, "msg": "已删除"}

    def save_all(self, items):
        """面板「保存」：整份替换（按名字保留原来的 id / 创建时间）。"""
        items = items if isinstance(items, list) else []
        cleaned = []
        seen = set()
        for item in items[:MAX_POSES]:
            if isinstance(item, str):
                name, note = item, ""
            elif isinstance(item, dict):
                name, note = str(item.get("name") or ""), str(item.get("note") or "")
            else:
                continue
            name = name.strip()[:40]
            note = note.strip()[:120]
            if not name or name in seen:
                continue
            seen.add(name)
            cleaned.append((name, note))
        if not cleaned:
            return {"ok": False, "msg": "至少要留一个姿势"}
        with self._lock:
            data = self._load()
            old = {str(p.get("name") or "").strip(): p for p in data.get("poses") or []}
            poses = []
            for name, note in cleaned:
                base = old.get(name) or {}
                poses.append({
                    "id": str(base.get("id") or _new_id()),
                    "name": name,
                    "note": note or str(base.get("note") or ""),
                    "created_at": float(base.get("created_at") or _now_ts()),
                })
            data["poses"] = poses
            if not self._save(data):
                return {"ok": False, "msg": "保存失败，看日志"}
            return {"ok": True, "msg": "已保存 %d 个姿势" % len(poses)}


# ---------------------------------------------------------------- 参考图

_ref_lock = asyncio.Lock()
_ref_state = {"running": False, "total": 0, "done": 0, "current": "", "failed": []}


def batch_status():
    return dict(_ref_state)


def pending_poses(library):
    return [pose for pose in library.poses() if not library.has_ref(pose)]


async def ensure_pose_ref(plugin, pose, force=False):
    """生成一张「她做这个姿势」的参考图，返回路径；失败返回空串。"""
    pose = pose if isinstance(pose, dict) else {}
    name = str(pose.get("name") or "").strip()
    if not name:
        return ""
    library = getattr(plugin, "pose", None)
    if library is None:
        return ""
    path = library.ref_path(pose)
    if os.path.isfile(path) and os.path.getsize(path) > 0 and not force:
        return path
    omni = find_omni(plugin, plugin, "pose_library.ensure_pose_ref") if find_omni else None
    if omni is None:
        logger.warning("[amo] 姿势参考图：没找到万象画卷")
        return ""
    refs = []
    photo = getattr(plugin, "photo", None)
    getter = getattr(photo, "persona_refs", None) if photo is not None else None
    if callable(getter):
        try:
            refs = [str(item) for item in (getter() or []) if item]
        except Exception:
            refs = []
    note = str(pose.get("note") or "").strip()
    prompt = (
        "自拍姿势参考图：%s。%s。同一个人，手机前置自拍构图，从胸口以上取景，"
        "动作和手的位置清楚，浅灰色纯色背景，自然光，不出现文字、不出现第二个人。"
        % (name, note)
    )
    args = {"prompt": prompt, "count": 1, "record_usage": False}
    if refs:
        args["refs"] = refs
        args["allow_local_refs"] = True
    try:
        result = await asyncio.wait_for(omni.generate_images_for_plugin(**args), timeout=120)
    except asyncio.TimeoutError:
        logger.warning("[amo] 姿势参考图生成超时（%s）" % name)
        return ""
    except Exception as exc:
        logger.warning("[amo] 姿势参考图生成失败（%s）: %s" % (name, exc))
        return ""
    images = result.get("images") if isinstance(result, dict) else None
    if not images:
        return ""
    data = _decode_item(images[0]) if _decode_item else b""
    if not data:
        url = str(images[0].get("url") or images[0].get("image_url") or "")
        if url:
            try:
                import aiohttp

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=60) as resp:
                        if resp.status == 200:
                            data = await resp.read()
            except Exception:
                data = b""
    data = _as_png(data) if _as_png else data
    if not data:
        logger.warning("[amo] 姿势参考图内容为空（%s）" % name)
        return ""
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
        logger.info("[amo] 姿势参考图已生成：%s" % path)
        return path
    except Exception as exc:
        logger.warning("[amo] 姿势参考图保存失败（%s）: %s" % (name, exc))
        return ""


async def ensure_batch(plugin, poses, force=False):
    """逐张生成，确认落盘后再做下一张；已有文件跳过。"""
    async with _ref_lock:
        if _ref_state["running"]:
            return {"ok": False, "msg": "已经在生成了", "state": batch_status()}
        _ref_state.update({"running": True, "total": len(poses), "done": 0,
                           "current": "", "failed": []})
    try:
        done = 0
        for index, pose in enumerate(poses, start=1):
            name = str(pose.get("name") or "")
            _ref_state["current"] = name
            path = await ensure_pose_ref(plugin, pose, force=force)
            if path:
                done += 1
                logger.info("[amo] 姿势参考图进度 %d/%d：%s" % (index, len(poses), name))
            else:
                _ref_state["failed"] = list(_ref_state["failed"]) + [name]
            _ref_state["done"] = done
            await asyncio.sleep(0.3)
        return {"ok": True, "done": done, "failed": list(_ref_state["failed"]),
                "total": len(poses)}
    finally:
        async with _ref_lock:
            _ref_state["running"] = False
            _ref_state["current"] = ""


def pose_line(pose):
    """姿势 → 提示词里的一小段。"""
    pose = pose if isinstance(pose, dict) else {}
    name = str(pose.get("name") or "").strip()
    note = str(pose.get("note") or "").strip()
    if not name:
        return ""
    return "姿势：" + name + (("（" + note + "）") if note else "")
