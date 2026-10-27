"""pytest 根配置：把本机已知工具链位置注入 PATH（在测试收集前生效）。

当前覆盖：D:/Lab/_tools/mingw32/bin（MinGW-w64 GCC 14.2.0，i686）——
C 编译冒烟（tests/test_regen_and_c.py）依赖它，避免在无 PATH 编译器的
机器上被静默 SKIP。新工具链位置往这里加。
"""
import os

_MINGW = r"D:\Lab\_tools\mingw32\bin"
if os.path.isdir(_MINGW):
    os.environ["PATH"] = _MINGW + os.pathsep + os.environ.get("PATH", "")
