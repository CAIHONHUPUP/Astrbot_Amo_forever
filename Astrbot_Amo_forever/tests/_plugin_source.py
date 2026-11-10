# -*- coding: utf-8 -*-
"""测试辅助：读拆分后的全部插件模块源码。"""
import os

MODULES = ("main.py", "amo_shared.py", "amo_api.py", "amo_proactive.py",
           "amo_schedule.py", "amo_llm.py")


def module_paths(root):
    return [os.path.join(root, name) for name in MODULES
            if os.path.exists(os.path.join(root, name))]


def all_source(root):
    return "\n\n".join(open(path, encoding="utf-8").read() for path in module_paths(root))
