# -*- coding: utf-8 -*-
"""测试环境补丁（只影响 Windows 本机，CI 不变）。

DSH 沙箱会把 `tempfile.mkdtemp()` 建的 0o700 目录封成不可写（进程自己都写不进去），
所以 Windows 上换成 `os.mkdir(path, 0o777)` 的等价实现，并把 tempdir 指到仓库内的
`.test-tmp/`（继承工作区的 ACL）。Linux CI 上 tempfile 本来正常，这里什么都不做。

清理分两层：
1. 正常退出：`atexit` 删掉本进程建的目录；
2. 兜底：`pytest_sessionstart` 先扫一遍 `.test-tmp/`，删掉「够旧」的残留。
   超时/强杀/崩溃都不会触发 atexit，一次全量测试就会留下几百个 `amo-*` 目录
   （每个带一份 80KB 的插件库副本），所以必须有这一层。
   兜底只按 mtime 判断：活跃测试进程的目录总是刚刚建的，绝不误删，并发跑测安全。
阈值可用环境变量调：`AMO_TEST_TMP_PRUNE_HOURS`（默认 6）、
`AMO_TEST_TMP_MAX_KEEP`（默认 1200）、`AMO_TEST_TMP_GRACE_MINUTES`（默认 15）。
"""
import atexit
import os
import shutil
import tempfile
import time

_TMP = None
_names = None
_created = []

_PRUNE_HOURS = float(os.environ.get("AMO_TEST_TMP_PRUNE_HOURS", "6"))
_MAX_KEEP = int(os.environ.get("AMO_TEST_TMP_MAX_KEEP", "1200"))
_GRACE_SECONDS = float(os.environ.get("AMO_TEST_TMP_GRACE_MINUTES", "15")) * 60


def _release_handles() -> None:
    """关掉测试残留的 sqlite 连接：Windows 上有句柄占着就删不掉目录。"""
    try:
        import gc
        import sqlite3
    except Exception:  # pragma: no cover - 环境缺库时直接放弃
        return
    try:
        gc.collect()
        for obj in gc.get_objects():
            if isinstance(obj, sqlite3.Connection):
                try:
                    obj.close()
                except Exception:
                    pass
    except Exception:  # pragma: no cover - gc 走查失败也不该影响退出
        pass


def _cleanup_created_dirs() -> None:
    if not _created:
        return
    _release_handles()
    pending = []
    while _created:
        path = _created.pop()
        if not os.path.isdir(path):
            continue
        shutil.rmtree(path, ignore_errors=True)
        if os.path.exists(path):
            pending.append(path)
    if pending:  # 还占着就先留着，下次 pytest 启动时按时间兜底清掉
        _created.extend(pending)


if os.name == "nt" and not getattr(tempfile, "_amo_mkdtemp_patched", False):
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _TMP = os.path.join(_root, ".test-tmp")
    os.makedirs(_TMP, exist_ok=True)
    tempfile.tempdir = _TMP

    _names = tempfile._RandomNameSequence()

    def _mkdtemp(suffix: str = "", prefix: str = "tmp", dir: str | None = None) -> str:
        base = dir or tempfile.gettempdir()
        for _ in range(200):
            path = os.path.join(base, prefix + next(_names) + suffix)
            try:
                os.mkdir(path, 0o777)
            except FileExistsError:
                continue
            _created.append(path)
            return path
        raise FileExistsError("could not create a temporary directory")

    tempfile.mkdtemp = _mkdtemp
    tempfile.TemporaryDirectory._mkdtemp = staticmethod(_mkdtemp)
    tempfile._amo_mkdtemp_patched = True

    atexit.register(_cleanup_created_dirs)


def _prune_stale_tmp() -> None:
    """删掉被强杀的测试进程留在 `.test-tmp/` 里的目录（兜底，只在 Windows 上生效）。"""
    if not _TMP or not os.path.isdir(_TMP):
        return
    now = time.time()
    old_cutoff = now - _PRUNE_HOURS * 3600
    fresh_cutoff = now - _GRACE_SECONDS

    def _entry_stamp(entry: str):
        """目录里最新一次写入的时间（含内部文件），比单看目录 mtime 更能反映「还在用」。"""
        path = os.path.join(_TMP, entry)
        try:
            stamp = os.lstat(path).st_mtime
        except OSError:
            return None
        if os.path.isdir(path) and not os.path.islink(path):
            for dirpath, _dirnames, filenames in os.walk(path):
                for name in filenames:
                    try:
                        stamp = max(stamp, os.lstat(os.path.join(dirpath, name)).st_mtime)
                    except OSError:
                        pass
        return stamp

    def _remove(entry: str) -> bool:
        path = os.path.join(_TMP, entry)
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return True
        except OSError:
            return False

    entries = {}
    for entry in os.listdir(_TMP):
        stamp = _entry_stamp(entry)
        if stamp is not None:
            entries[entry] = stamp

    removed = 0
    # 第一层：按时间删旧的（正常路径，凑够了就不动上限逻辑）
    for entry, stamp in list(entries.items()):
        if stamp < old_cutoff and _remove(entry):
            removed += 1
            entries.pop(entry, None)

    # 第二层：如果还有一堆（比如短时间里反复被杀），按最旧的删到上限，
    # 但最近 GRACE 分钟内建的（可能正被另一个跑测进程使用）一律不动。
    over = len(entries) - _MAX_KEEP
    if over > 0:
        for entry, stamp in sorted(entries.items(), key=lambda kv: kv[1]):
            if over <= 0 or stamp >= fresh_cutoff:
                break
            if _remove(entry):
                removed += 1
                over -= 1

    if removed:
        # 纯 ASCII：Windows 控制台可能是 cp936/cp437，中文会 UnicodeEncodeError 把整场测试带崩
        print("[conftest] pruned %d stale entries in .test-tmp (>%gh old or over cap %d)"
              % (removed, _PRUNE_HOURS, _MAX_KEEP), flush=True)


def pytest_sessionstart(session):
    _prune_stale_tmp()


def pytest_sessionfinish(session, exitstatus):
    # 提前清一次：Ctrl+C / 中途失败也能收干净，不必等 atexit
    _cleanup_created_dirs()
