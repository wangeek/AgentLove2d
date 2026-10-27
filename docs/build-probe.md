# B4 Task 1（线 A）：fork 构建可行性探针报告

## 附录 A：里程碑一实际构建记录（2026-10-27，全量通过）

```
git clone --depth 1 https://gh-proxy.com/https://github.com/love2d/megasource.git megasource
git -C megasource config url."https://gh-proxy.com/https://github.com/".insteadOf "https://github.com/"
git -C megasource submodule update --init --depth 1        # libs 依赖齐（含 SDL2 2.28.5/mpg123-1.25.6）
robocopy love2d\love-src megasource\libs\love /E           # 基线 love 入官方布局（保留 .git）
cmake -B megasource\build115 -S megasource -G "Visual Studio 17 2022" "-DCMAKE_POLICY_VERSION_MINIMUM=3.5"
$env:CMAKE_POLICY_VERSION_MINIMUM='3.5'                    # openal native-tools 内部 cmake 需要
cmake --build megasource\build115 --config Release -- -m   # 全量通过，约 9 分钟
```

要点：
- megasource **master 是 love12/SDL3 布局**（默认 `LOVE_USE_SDL3=ON`、无 mpg123）——构建 11.5 必须 checkout **tag `11.5`**；切换后 libs 自动变为 11.5 依赖集（mpg123 回归、SDL3/harfbuzz 消失）。
- PowerShell 传参坑：`-DX=3.5` 必须整体加引号（被拆成 "3" 的报错即此）。
- CMake 4.x 对 openal 内部 cmake（native-tools/bin2h）的旧 policy 墙：设同名环境变量即可（子 cmake 继承）。
- 产物：`megasource\build115\love\Release\`（love.exe + love.dll 4.31MB + lua51/SDL2/OpenAL32/mpg123 DLL）。
- **行为等价实证**：自建 love.exe 跑 L0（`--demo --frames 4 --fixed-dt 0.016667 --sha <指纹> --seed 3056735`）产物与官方运行时 golden（tests/golden/l0_session.fr）**逐字节一致**（2144B）。

- 日期：2026-10-27
- 探针对象：`love2d/love-src/`（gitignored，盘上在位；git 仓库 HEAD = `6eb8d54`，`git describe` = `11.5`，与任务书一致）
- 工作区：`D:\Lab\AgentLove2d` @ main `79aaa81`（探针时 HEAD，未含本报告）
- 约束遵守：未安装/未下载任何软件或依赖；仓库代码零改动（探针产物只在 `love-src/build-probe/`、`love-src/build-msvc/`，其父目录 `.gitignore:14` 覆盖）
- 时间盒消耗：尝试性构建约 10 分钟（远低于 30 分钟上限）

## 结论

**三选一归入：需 MSVC 工具链 + 依赖——但工具链已全部在位，依赖走 megasource 源码自建，本机无需安装任何软件、无需逐个找预编译包。**

1. **MSVC 官方路线（megasource）端到端验证通过**：VS2022 BuildTools（cl 19.44.35229）+ Windows SDK 10.0.26100 + cmake 4.2.1 全部在位且实测可用——cl 编链运行 hello 通过、clang 21.1.5（MSVC target）编链运行通过、cmake 用 VS2022 生成器成功驱动 cl 完成编译器探测。唯一未做的获取动作是 `git clone megasource`（下载类，受"不许为补依赖下载"约束未执行）。
2. **MinGW 路径存在**：configure 实测走完编译器 ABI 探测、找到 OpenGL，死在第一个缺失依赖 FreeType（`CMakeLists.txt:187`）。但 10 项外置依赖本机全缺，MinGW 路线人时成本最高（见选项 A）。
3. **MSVC 独立构建被源码主动拒绝**（`CMakeLists.txt:180-185`）：非 megasource 布局下 `if(MSVC)` 直接 FATAL_ERROR，官方原文「It is currently only possible to build with megasource or (experimental) mingw on Windows.」——**MSVC 路线必须走 megasource 布局，没有源码级绕法**。

```
PROBE: PASS（fork 构建路径存在：MSVC+megasource 官方路线工具链已实测可用，仅差 megasource 克隆；MinGW 路径可达依赖墙但 10 项外置依赖全缺）
```

## 一、构建体系清点

`Get-ChildItem love-src -Recurse -Include CMakeLists.txt,*.cmake,*.vcxproj,*.sln,Makefile,*.mk` 结果：

| 文件 | 角色 |
|---|---|
| `CMakeLists.txt`（根，1967 行） | **唯一 Windows 构建入口**。L88 `if(MEGA)` 进 megasource 分支；L179 `else()` 进独立构建分支 |
| `extra/cmake/Find*.cmake` ×8 | SDL2/OpenAL/LuaJIT/ModPlug/MPG123/Ogg/Vorbis/Theora 的查找模块；**只搜 `/usr/local`、`/usr`**（如 `FindLuaJIT.cmake:8-9`），预设 MSYS2 类环境 |
| `Android.mk` | Android 构建，与 Windows 无关 |
| `src/libraries/luasocket/libluasocket/makefile` | 上游遗留；luasocket 的 .c 已列入 CMake 源码清单（`CMakeLists.txt:1475-1545`），由 CMake 编译，此 makefile 不参与主路径 |
| `extra/appveyor/appveyor.yml` | **官方 Windows CI 的权威构建配方**（见下） |
| `extra/windows/love.rc`、`extra/nsis/` | 资源与打包素材 |

**关键事实**：

- **仓库不带 .sln/.vcxproj**。官方 Windows 构建 = megasource 仓库 + CMake 生成 VS 工程：`readme.md:44-45`「Windows: Follow the instructions at the megasource repository page」；`appveyor.yml:29,35,38,41`——clone megasource → 把 love 源码挪进 `megasource/libs/love` → `cmake -G "Visual Studio 12" -H. -Bbuild` → `cmake --build build --target PACKAGE --config Release`。CI 镜像是 VS2013（`appveyor.yml:3`）。
- **官方 11.5 发行版是 MSVC 构建**，运行时目录里的 `msvcp120.dll`/`msvcr120.dll`（VS2013 CRT）与此互证。
- megasource 分支下依赖全是 CMake target（`CMakeLists.txt:98-110` 的 `MEGA_*` 变量：`MEGA_FREETYPE/MEGA_LIBOGG/.../MEGA_SDL2`），LuaJIT 除外（`CMakeLists.txt:146-150` `MEGA_LUAJIT_LIB/MEGA_LUAJIT_DLL`，外部 target）。

## 二、工具探测结果

| 工具 | 状态 | 证据 |
|---|---|---|
| cmake | ✅ 4.2.1（在 PATH） | `cmake --version`；安装于 `D:\Program Files\cmake-4.2.1-windows-x86_64\`（报错路径取证） |
| ninja | ❌ 不存在 | `ninja --version` 报不存在 |
| MSVC cl | ✅ 19.44.35229（x64），不在 PATH | `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64\cl.exe`，banner 实测 |
| Windows SDK | ✅ 10.0.26100.0 库齐全 | `um\x64\kernel32.lib`、`ucrt\x64\libucrt.lib` 实测存在；cl 编 physfs TU 时 SDK 头实测可用 |
| vcvarsall / DevShell 模块 | ✅ 均在 | `VC\Auxiliary\Build\vcvarsall.bat`、`Common7\Tools\Microsoft.VisualStudio.DevShell.dll` |
| LLVM clang | ✅ 21.1.5，默认 target `x86_64-pc-windows-msvc` | `D:\Lab\_tools\LLVM\bin\clang.exe --version`；编链运行实测通过 |
| mingw64 gcc | ✅ 14.2.0 x86_64 UCRT | `gcc --version` |
| mingw32-make | ✅ **存在** | `D:\Lab\_tools\mingw64\bin\mingw32-make.exe`——MinGW-Builds 实际带了 make（修正"通常不带"的预期） |

**MSVC 环境置入的两条可行路线（均实测）**：

- 路线 1（推荐）：`Import-Module` DevShell.dll + `Enter-VsDevShell -VsInstallPath ... -Arch amd64 -HostArch amd64`，之后 PATH/INCLUDE/LIB 自动就绪。注意：本 harness 下首次尝试 cl 未入 PATH（疑似管道截断干扰 `Enter-VsDevShell` 的输出处理），第二次原样重跑成功；建议每次跑完用 `Get-Command cl` 自检。
- 路线 2（确定性备用）：手动设三个环境变量 + 全路径 cl：
  ```powershell
  $msvc='C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.44.35207'
  $sdk='C:\Program Files (x86)\Windows Kits\10'
  $env:PATH="$msvc\bin\Hostx64\x64;$env:PATH"
  $env:INCLUDE="$msvc\include;$sdk\Include\10.0.26100.0\ucrt;$sdk\Include\10.0.26100.0\shared;$sdk\Include\10.0.26100.0\um"
  $env:LIB="$msvc\lib\x64;$sdk\Lib\10.0.26100.0\ucrt\x64;$sdk\Lib\10.0.26100.0\um\x64"
  ```

## 三、实测记录（命令与输出摘录）

### 3.1 MinGW configure——走到依赖墙即停（时间盒规则）

```
cmake -S love-src -B love-src/build-probe -G "MinGW Makefiles" '-DCMAKE_POLICY_VERSION_MINIMUM=3.5'
```

- `-DCMAKE_POLICY_VERSION_MINIMUM=3.5` 为必带旗标：cmake 4.2.1 对 `CMakeLists.txt:26` 的 `cmake_minimum_required(VERSION 3.1)` 报「Compatibility with CMake < 3.5 has been removed from CMake」，报错原文建议加此旗标（**未改任何仓库文件**）。
- 输出关键行（完整输出见探针日志段尾）：
  ```
  -- The C compiler identification is GNU 14.2.0
  -- The CXX compiler identification is GNU 14.2.0
  -- Detecting C compiler ABI info - done
  -- Check for working CXX compiler: D:/Lab/_tools/mingw64/bin/c++.exe - skipped
  -- LuaJIT: Enabled
  -- Target platform: x64
  -- Found OpenGL: opengl32
  CMake Error: Could NOT find Freetype (missing: FREETYPE_LIBRARY FREETYPE_INCLUDE_DIRS)
    ...Modules/FindFreetype.cmake:218  ← cmake 内置模块
    CMakeLists.txt:187 (find_package)
  -- Configuring incomplete, errors occurred!  (EXITCODE=1)
  ```
- **含义**：MinGW 工具链 + 仓库 CMake 结构完全兼容，首个缺失依赖 = FreeType，与依赖表预期一致。

### 3.2 VS2022 生成器 configure——命中 megasource 硬检查（结构性证据）

```
cmake -S love-src -B love-src/build-msvc -G "Visual Studio 17 2022" '-DCMAKE_POLICY_VERSION_MINIMUM=3.5'
```

```
-- Check for working C compiler: C:/Program Files (x86)/.../cl.exe - skipped
-- Detecting CXX compiler ABI info - done
-- LuaJIT: Enabled
-- Target platform: x64
-- Found OpenGL: opengl32
CMake Error at CMakeLists.txt:181 (message):
  It is currently only possible to build with megasource or (experimental)
  mingw on Windows.
  Please see https://github.com/love2d/megasource
-- Configuring incomplete, errors occurred!  (EXITCODE=1)
```

- **含义**：cmake 4.2.1 + VS2022 生成器 + cl 19.44 全链路工作正常；唯一拦截点是源码里写死的 megasource 布局检查（`CMakeLists.txt:180-185`），非工具缺失。

### 3.3 MSVC / clang 端到端 hello（编 + 链 + 运行）

```
cl /nologo hello.c   → hello.exe 运行输出 hello-msvc   (EXITCODE=0)
clang hello.c -o hello_clang.exe → 运行输出 hello-msvc   (EXITCODE=0)
```

- clang 全程零旗标，自动发现 MSVC 头/库并完成链接（默认 target `x86_64-pc-windows-msvc`）。
- 探针期间两次操作失误（如实记录）：① hello.c 首次被写入字面 `` `n ``（PowerShell 单引号吞换行），导致 clang 首轮告警——工具无问题；② DevShell 首次进 shell 后 cl 未入 PATH，原样重试成功（见 §二 备注与备用路线）。

### 3.4 cl 直编 love-src 的无依赖 TU（零源码改动）

```
cl /nologo /c /I src\libraries\xxHash    src\libraries\xxHash\xxhash.c                 → EXITCODE=0（obj 18549 B）
cl /nologo /c /EHsc /I src\libraries\noise1234 src\libraries\noise1234\noise1234.cpp   → EXITCODE=0（obj 23513 B）
cl /nologo /c /I src\libraries\physfs    src\libraries\physfs\physfs_platform_windows.c → EXITCODE=0（obj 26565 B）
```

- 第三个 TU 依赖 Windows SDK 头，编过 = **love-src 的 C/C++ 源码在 cl 19.44 + SDK 26100 下无障碍**（无依赖 TU 抽样，非全量证明）。
- 注意 `/Fo` 语法：`-Fobuild-probe\xxhash.obj`（无空格）；带空格会被 cl 当成额外源文件（D9027 warning）。

## 四、依赖表

### 4.1 外置依赖（须解决，共 10 项 + OpenGL）

| # | 库 | 构建文件出处 | 本机状态 | MinGW 渠道建议 | MSVC/megasource 渠道 |
|---|---|---|---|---|---|
| 1 | FreeType | `CMakeLists.txt:187`（cmake 内置 FindFreetype，报错调用栈证实） | ❌ 缺 | MSYS2 UCRT64 包或 CMake 自建 | megasource 子模块自建 |
| 2 | ModPlug | `:188`（`FindModPlug.cmake:8-9` 搜 /usr） | ❌ 缺 | 同上 | megasource |
| 3 | OpenAL(soft) | `:189`（`FindOpenAL.cmake:11-12`） | ❌ 缺 | 同上 | megasource（vcpkg openal-soft） |
| 4 | OpenGL | `:86`、`:190` | ✅ 系统 opengl32（两轮 configure 均 Found） | 系统 | 系统 |
| 5 | SDL2 | `:191` **REQUIRED CONFIG**——要的是安装好的 `SDL2Config.cmake`，不用仓库 Find 模块 | ❌ 缺 | SDL 官方 GitHub releases 的 `SDL2-devel-*-mingw.tar.gz`（自带 cmake config） | SDL 官方 `SDL2-devel-*-VC.zip`（推测含 cmake config，以 release 内容为准）/ megasource |
| 6 | Theora | `:192`（`FindTheora.cmake:9-10`） | ❌ 缺 | MSYS2/自建 | megasource |
| 7 | Vorbis | `:193`（`FindVorbis.cmake:9-10`） | ❌ 缺 | 同上 | megasource |
| 8 | zlib | `:194`（cmake 内置 FindZLIB） | ⚠️ MinGW 侧自带（`mingw64\x86_64-w64-mingw32\lib\libz.a` + `include\zlib.h` 实测在）；MSVC 侧无 | 本机已备 | megasource / vcpkg |
| 9 | Ogg | `:195`（`FindOgg.cmake:8-9`） | ❌ 缺 | MSYS2/自建 | megasource |
| 10 | mpg123 | `:61` option 默认 ON；`:226` find（可 `-DLOVE_MPG123=OFF` 关，官方开关 `:70` `-DLOVE_NOMPG123`） | ❌ 缺 | MSYS2 / 官方 Windows 二进制（推测有，未核对） | megasource |
| 11 | LuaJIT | `:59` LOVE_JIT 默认 TRUE；`:238` REQUIRED（`FindLuaJIT.cmake:18` 找 `luajit-5.1`，`:14` 兼容 2.0/2.1 头路径） | ❌ 缺 | LuaJIT 官方源码自建（官方支持 MinGW）或 MSYS2 | megasource 集成（`:146-150` MEGA_LUAJIT_* 接口）；LuaJIT 官方自带 msvcbuild.bat（MSVC 原生支持） |

备注：

- `-DLOVE_JIT=OFF` 会落到 `:242` `find_package(Lua51 REQUIRED)`——**同样外置**。`src/libraries/lua53/` 只是 lstrlib/lutf8lib 补丁源码（`CMakeLists.txt:1562-1566`），不是完整 Lua，救不了这条线。
- 仓库 8 个自定义 Find 模块只搜 `/usr/local`、`/usr`——**experimental mingw 路线预设 MSYS2 环境**。用独立 MinGW 前缀时需逐库传 `-D<VAR>=...` 指路。

### 4.2 内置源码依赖（零动作，共 17 项）

Box2D、ddsparse、dr_flac、enet、glad、glslang、lodepng、luasocket、lua53（补丁）、lz4、noise1234、physfs、stb、tinyexr、utf8、Wuff、xxHash —— 均为 `src/libraries/` 下随仓库分发的源码，列入 CMake 源码清单（`CMakeLists.txt:1127-1706` 区间），随 love 一并编译，无需获取。

## 五、选项与成本对比

| 选项 | 内容 | 成本 / 风险 | 判定 |
|---|---|---|---|
| **B：megasource + MSVC（官方路线）** | clone megasource（gh-proxy 直链，`appveyor.yml:29` 同款动作）→ love-src 挂 `libs/love`（`appveyor.yml:35` 布局）→ `cmake -G "Visual Studio 17 2022"`（带 policy 旗标）→ `--target PACKAGE` | 零安装、零找包。clone 体积推测 300–600 MB（子模块未验）；首次全量构建估 15–45 min 机器时（推测）。风险：① megasource 自身 `cmake_minimum_required` 若同样 <3.5，同旗标可解（推测）；② cl 19.44 编 VS2013 时代依赖源码的兼容性——love 11.5 是 2023-12 代码、依赖版本较新，风险低（推测）；③ LuaJIT 子模块的构建环节由 megasource 驱动，细节未验（推测） | **推荐，B4 开工首path** |
| A：MinGW + 逐库补齐 | 走 §3.1 已验证的 configure 路线，10 项外置依赖逐个解决 | 人时最重：8–9 项需 MSYS2 UCRT64 包或自建（估 1–2 个工作日，每库 0.5–2h 首次踩坑——推测）；独立前缀还要逐库 `-D` 指路（Find 模块只搜 /usr）。CRT 对账：本机 gcc 为 UCRT 构建，须配 MSYS2 **UCRT64** 前缀包才同 CRT（推测，需实测对账） | 备选，仅在拒绝 MSVC 时走 |
| C：预编译 love.dll + 注入 | 盘上已有官方 `love.dll`（4.79 MB，VS2013 ABI） | **语义上不满足 B4**：捕获钩要接进 love 源码 w_* 边界（docs/love2d-gap.md 挂点），外部 DLL 触不到内部调用点，只能外围旁路拦截，取证覆盖不足；另有 VS2013 CRT 与新编译器混用风险 | 不推荐做主路径；可作对照影子 |
| D：clang / clang-cl 备胎 | LLVM 21.1.5 已在盘，MSVC ABI 编链实测通过 | 切换成本≈0：cl 19.44 若编旧码报错，VS 生成器 `-T ClangCL` 或独立 clang-cl 平替 | 作为 B 的应急预案 |

## 六、下一步（B4 开工最小路径）

1. `git clone https://gh-proxy.com/https://github.com/love2d/megasource.git`（gh-proxy 对大文件会断流，`git clone` 失败时改 curl -C - 拉归档——渠道来自既有经验）；
2. 按 `appveyor.yml:28-35` 布局把 love-src 挂进 `megasource/libs/love`（love-src 已含 .git，挪动用复制或 worktree，勿动上游仓库）；
3. `cmake -S megasource -B build -G "Visual Studio 17 2022" '-DCMAKE_POLICY_VERSION_MINIMUM=3.5'`，首个报错如实带回；
4. 通过后 `cmake --build build --target PACKAGE --config Release`（DevShell 环境或手动 INCLUDE/LIB，见 §二）。

## 七、待验项（均为推测，已标注）

- megasource 的子模块清单与总体积、其 `cmake_minimum_required` 版本、LuaJIT 集成方式——**需克隆后核**；
- cl 19.44 对 VS2013 时代 megasource/依赖源码的兼容性——需首编验证；
- MSYS2 UCRT64 包与 MinGW-Builds UCRT gcc 的 CRT 对账（仅选项 A 相关）；
- `Enter-VsDevShell` 首次未置 PATH 的根因（本 harness 管道截断之疑）——已给出确定性备用路线，不阻塞。

## 附：探针产物

- `love-src/build-probe/`：MinGW configure 残留 + hello.c/hello.obj/hello.exe/hello_clang.exe + xxhash.obj/noise1234.obj/physfs_win.obj
- `love-src/build-msvc/`：VS 生成器 configure 残留
- 两目录均在 gitignored 父目录（`.gitignore:14` `love2d/love-src/`）内，不入库
