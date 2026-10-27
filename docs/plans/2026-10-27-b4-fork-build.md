# B4-2 里程碑一：fork 首次全量构建（megasource + MSVC）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用官方 megasource 布局 + 本机 MSVC 工具链把魔改前基线（love-src@6eb8d54）完整构建出 `love.dll`/`love.exe` 并运行验证——B4 全部魔改工作的构建地基。

**Architecture:** megasource（官方依赖打包仓库，已 clone 至工作区 `megasource/`，依赖以 git 子模块承载）期望 love 位于 `libs/love`；把 `love2d/love-src` 内容复制过去（保留 .git 供版本探测），CMake `Visual Studio 17 2022` 生成器全量构建。构建通过后，后续所有魔改（捕获层、语义替代、回放器、null Graphics）都在这份布局上迭代，编解码文件由 gen_c 生成后纳入同一 CMake 目标。

**Tech Stack:** CMake ≥3.5（4.2.1 在位，需 `-DCMAKE_POLICY_VERSION_MINIMUM=3.5` 兼容旧声明）+ VS2022 BuildTools（cl 19.44 + SDK 10.0.26100，均已验证）+ mingw32-make 备选。

**依据：** docs/build-probe.md（PROBE: PASS；CMakeLists.txt:180-185 megasource 硬约束；appveyor.yml 官方配方）；B3b 终审 B4 输入清单。

**事实前置（探针已证）**：cmake 4.2.1 在位；VS2022 cl + SDK 库齐全；cmake+VS2022 生成器可驱动 cl 完成编译器探测；旧 `cmake_minimum_required(VERSION 3.1)` 需 policy 旗标；官方 CI 配方=clone megasource → love 挪到 `libs/love` → cmake 生成 → build → PACKAGE。

---

### Task 1: megasource 获取与布局

**Files:** `megasource/`（gitignored 外部仓库，不入库——随 Task 3 补 .gitignore）

- [ ] **Step 1**: clone（gh-proxy，浅克隆）+ 本地 insteadOf 让子模块走代理 + `submodule update --init --depth 1`（后台任务已在跑）
- [ ] **Step 2**: 验证子模块齐全：`libs/` 下 SDL、freetype、openal-soft、luajit、mpg123、libmodplug、libvorbis、libogg、libtheora、zlib 等目录非空（缺失项如实记录——子模块浅更新偶发失败需单独重试）
- [ ] **Step 3**: love 布局：`robocopy love2d\love-src megasource\libs\love /E`（保留 .git——love 的 CMake 用 git describe 探版本；robocopy 退出码 1-7 均为成功形态，≥8 失败）
- [ ] **Step 4**: `megasource/` 加入根 .gitignore

### Task 2: CMake 生成与全量构建

- [ ] **Step 1: 生成**：`cmake -B megasource\build -S megasource -G "Visual Studio 17 2022" -DCMAKE_POLICY_VERSION_MINIMUM=3.5`（首次 configure 可能因 love 的 CMake 在 git 缺失/版本探测上出问题——如实记录并按报错修路径）
- [ ] **Step 2: 构建**：`cmake --build megasource\build --config Release -- -m`（MSBuild 并行）。预期时长 10–30 分钟；报错就地修最小问题（如字符集/宏差异），**不修 love 源码语义**——基线必须是纯净上游
- [ ] **Step 3: 产物验证**：`build\Release\love.exe --version`（自建产物直接跑）→ 应输出 `LOVE 11.5 (Mysterious Mysteries)`；再用它跑我们自己的 L0：`love.exe l0 --demo … --out <tmp>` 产物与 golden 逐字节一致（**自建运行时与官方运行时行为等价的实证**）

### Task 3: 收尾

- [ ] gen_c 生成的 `render/fr_codec.h/.c` 纳入构建的可行性注记（CMake target 挂接方式写进 build-probe.md 附录，不实现）
- [ ] 文档回写：design.md §6 B4-2 行追加"里程碑一 ✅（fork 全量构建通过，自建运行时跑 L0 与 golden 一致）"；build-probe.md 附录记录实际构建命令与耗时；AGENTS Setup 补 megasource 路径
- [ ] 全量 + 提交

---

## Self-Review 记录

- **范围**：本里程碑只做"构建地基"，捕获层/回放器/语义替代在构建验证后另立计划（届时真实 CMake 集成方式已知，计划更准）。
- **风险**：①子模块浅克隆个别 pinned commit 拉不到（重试该模块单独处理）；②love 11.5 + VS2022/cl 19.44 的编译器代差警告（官方 CI 是 VS2013——新编译器更严，可能有历史代码警告，非错误即可继续；错误则逐个最小修并记录，仍属"构建适配"非语义修改）；③cmake 4.x 对旧 minimum 的 policy 强制（已知绕法）。
- **gitignore 纪律**：megasource/（含子模块）与 build 目录全部不入库，与 love-src 同例。
