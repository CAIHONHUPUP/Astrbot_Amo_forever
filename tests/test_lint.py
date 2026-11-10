# -*- coding: utf-8 -*-
"""静态检查：main.py 里不能有未定义名字。

上次群聊 NameError（`plat`）从补丁里被重写掉，运行时又被 `_spawn` 静默吞掉；
pyflakes 的 F821 能在 CI 就抓住这类回退。
"""

import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class LintTests(unittest.TestCase):
    def test_no_undefined_names_in_main(self):
        proc = subprocess.run(
            [sys.executable, "-m", "pyflakes", os.path.join(ROOT, "main.py")],
            capture_output=True, text=True,
        )
        output = proc.stdout + proc.stderr
        if "No module named pyflakes" in output:
            self.skipTest("pyflakes not installed")
        undefined = [line for line in output.splitlines() if "undefined name" in line]
        self.assertEqual(undefined, [], "\n".join(undefined))


if __name__ == "__main__":
    unittest.main()
