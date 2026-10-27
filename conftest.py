"""pytest 根配置：把本机已知工具链位置注入 PATH（在测试收集前生效）。

覆盖：D:/Lab/_tools/mingw64/bin（x86_64，优先）与 D:/Lab/_tools/mingw32/bin
（i686）——均为 MinGW-Builds GCC 14.2.0。C 编译冒烟与 fr_selftest 依赖，
避免在无 PATH 编译器的机器上被静默 SKIP。新工具链位置往这里加。
"""
import os

for _TOOLCHAIN in (r"D:\Lab\_tools\mingw64\bin", r"D:\Lab\_tools\mingw32\bin"):
    if os.path.isdir(_TOOLCHAIN):
        os.environ["PATH"] = _TOOLCHAIN + os.pathsep + os.environ.get("PATH", "")
