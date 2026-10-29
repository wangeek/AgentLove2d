# AGENTS.md

FR 帧流 IR（.fr / .frb 双形态）工具链，载体为魔改 LÖVE 11.5：Lua 内核脚本产出 FR 流，引擎内 C 层捕获与回放。先建工具、后改造 sango——sango 只是未来的 lowering 前端之一，与本项目解耦，**不得把 sango 的实现形态当成本项目的设计约束**。

## 真源文件（动手前先读）

- `docs/design.md` — **总纲入口**：系统全貌、一帧的一生、机制卡、工具族地图、实施路线——新会话从这里进，再按其 §0 读者地图跳真源
- `docs/fr-rationale.md` — **动机总纲**：FR 为 Agent 图形化验证而设计的推理链、五条设计原则、Agent 工作流、MCP 工具预留接口面
- `docs/fr-spec.md` — FR 规格 v1.2（封版）：段语义、级别三档、命令集、事件词汇表、工具族、取证清单
- `docs/decisions.md` — 架构决策 D1–D13：LLVM 模式总则、语义四准则、验证两律、树不进协议、语境纪律、LÖVE 定位、魔改宿主架构（D8）、sango 剥离（D9）、GPU 边界（D10）、相机归属（D11）、捕获面全 API 三分类与回放侧三机制（D12）、环境层家族 v1 透明放行（D13）
- `docs/love2d-gap.md` — 魔改设计与差距分析 v2：六个挂点、绘制层（引擎内 C 回放 + 捕获后回放）、事件层（C 捕获/注入 + 自有 run loop）、log（API 边界记录，debug 栈钩仅审计）
- `docs/benchmarks.md` — **性能基准线**（录制吞吐/流体积/观测规模，持续优化锚——优化落地必更新对照行）
- `tables/cmd.tbl` — 命令表 = 单一真源；两端编解码代码从它生成，**不许手写编解码**

## 硬纪律

- IR 词汇表只用现代语义（f32 `%.6f`、RGBA8、TTF 字体字节、HID scancode、UTF-8），宿主 = LÖVE，它的事件名/像素格式/字体管线就是普通话；**legacy 方言（GDI / WM_ / VK_ / 调色板 / 点阵）不进本仓库**，未来前端的兼容映射住前端自己的仓库
- 判据只许"符号比较"（锚行 diff）或"字节相等"；墙钟时间只进注释列
- 规格条目状态：sealed 不擅改；draft 待 fr-gen 首版落定；待取证项先取证再定
- 内核与渲染端的唯一通道是 FR 流，内核不得读渲染端状态（D8 生效，取代 D6，见 docs/decisions.md）
- 工具命名不与现成 shell 命令撞语义
- 修改规格 = 改 `docs/fr-spec.md` + 在其 §13 版本记录追加一行；决策修订 = 在 `docs/decisions.md` 追加新条目注明取代关系

## Setup commands

- 运行 LÖVE：`love2d/love-11.5-win64/love.exe <游戏目录>`
- L0 产流样机（B3b）：`love2d/love-11.5-win64/love.exe l0 --demo --frames N --fixed-dt X --sha <表指纹> --seed S --out <path>`（表指纹=`tools.fr_gen.tbl` 的 `tbl_sha256(tbl.parse(表文本))`；golden 在 `tests/golden/l0_session.fr`）
- **fork 构建（B4 起）**：megasource 在 `megasource/`（11.5 tag，不入库）；增量构建 `cmake --build megasource\build115 --config Release`；环境变量 `CMAKE_POLICY_VERSION_MINIMUM=3.5` 必设（openal 内部 cmake 用）；自建运行时在 `megasource\build115\love\Release\`
- fork 捕获 rig（B4-2）：`megasource\build115\love\Release\love.exe megasource\libs\love\demo`（`FR_CAPTURE=1` 时捕获/回放，缺省 3 帧验证 rig 打 PIXEL/会话行）；tee₁ 会话加 `--out <path> --sha <表指纹> [--seed S] [--frames N 缺省 4]`；全 API 闭环加 `--api-parade`（B8 T4：20 API 靶直调通道，sim 重演须同通道 `python tools/fr_render.py --sim <in.fr> --api-parade`）；回归 tests/test_capture.py
- 任意游戏 C 侧 tee（B10）：`FR_CAPTURE=1 FR_OUT=<path> FR_SHA=<表指纹> [FR_SEED n] [FR_FRAMES n] [FR_DT f]` → **零游戏侧改动出流**（in=Event::pump convert 捕获、dt=w_timer_step 钩、帧边界=present 钩逐帧追加、lua_close 前封口）；离线回放 `python tools/fr_render.py <流>`。newgame 实证：30 帧 smoke rc=0 → 38MB 流（18 资产/83591 out 行）→ 离线回放 rc=0、帧 5-30 D_CRC 稳定。与 demo `--out`（Lua tee）并存正交；`_frSessionFrame` 显式补帧口=验证帧等价点
- 熵剖面（B13）：`python tools/fr_stats.py <流> [--json]`——四层（op/参数默认值命中率/量化模拟/时间层），B14 紧凑编码的准入裁判；动态基准锚 `FR_BOOT_SCRIPT=tools/fr_boot_battle.lua` 直切 battle（形态基准——跨跑 D_CRC 不适用，见 benchmarks.md 双场景节）
- 离线回放视觉播放（B11）：`FR_PLAY=1 python tools/fr_render.py <流>`——离线画布贴屏+present+按流内 dt 节奏（播完停留 1s）；判据输出与关闭时逐帧一致（播放只追加上屏，拓扑 B 默认无头形态不变）
- Python 工具（fr-*）：`python tools/<tool>.py ...`（fr-gen 已交付：`python -m tools.fr_gen.gen_python` / `gen_c` 再生双目标，改表后必跑）
- 会话封装互转（fr-as/fr-dis 已交付）：`python tools/fr_as.py <in.fr> -o out.frb` / `python tools/fr_dis.py <in.frb>`
- dump 与判据（fr-dump/fr-check 已交付）：`python tools/fr_dump.py <in.fr|in.frb> [--frames a-b] [--stats]` / `python tools/fr_check.py <in.fr|in.frb> [判据文件] [--strict]`
- C 工具链：本机 `D:/Lab/_tools/mingw64`（x86_64，主力）与 `D:/Lab/_tools/mingw32`（i686——**2026-10-27 起编译子进程损坏**：连 hello.c 都静默 exit 1，待重置；跨架构对账暂依赖 gyl）——均为 GCC 14.2.0，无 PATH——根 conftest.py 自动注入（mingw64 优先）；另有 MSVC BuildTools 2022（cl 19.44，x86 根下）与 LLVM 21.1.5（`D:/Lab/_tools/LLVM`，clang/lld-link/lldb）——B4 fork 的 MSVC 官方构建路线零安装可行（docs/build-probe.md）
- 测试：`pytest tests/`（101 项：解析/量化/编解码/会话封装/CLI/round-trip/零漂移与跨目标锚/C emit+解码自测/L0 headless/fork 捕获与 tee₁/真字节物化/离线回放 d_crc/无头拓扑 C/事件捕获与 sim 重演/堆 s_crc 与 st 物理行/d_crc 与 str 敏感 s_crc/B8 状态类+绘制五 op+rt/scissor/Shader 边界+api-parade 闭环/B9 代理方法族+去重+形态/B10 C 侧 tee 对拍）
- 事件注入回放（B5）：`python tools/fr_render.py --sim <in.fr>`——严格档内核重演（录制 ev 事件注入队列重新驱动内核，再生 out 行与录制逐帧比对）；demo 注入参数 `--inject-click <x>,<y> --inject-key <key>`（帧 1/2）
- 发布包（B7a）：`dist/fr-capture-demo.zip`——fork 运行时+VC143 CRT+捕获 rig demo（含 golden），解压即跑（README 有命令）
- 堆状态观测（B6）：s_crc 常开（注册状态根子图 CRC——demo 侧 `_frStateRoot(kernel.state)`）；st 物理行 FR_LOGLEVEL=full 按需（影子镜像 diff，数组 `[i]`/hash `"key"`，表重建走 err 载体）；sim 比对集含 st/s_crc
- 事件注入回放（B5）：`python tools/fr_render.py --sim <in.fr>`——严格档内核重演（录制 ev 事件注入队列重新驱动内核，再生 out 行与录制逐帧比对）；demo 注入参数 `--inject-click <x>,<y> --inject-key <key>`（帧 1/2）
- 离线回放（B4 阶段三）：`python tools/fr_render.py <in.fr|in.frb>`——拓扑 B 离线回放驱动（fork love.exe 的 --offline-replay 模式），输出逐帧 D_CRC 与采样像素；无头录制（拓扑 C）：fork demo 加 `FR_HEADLESS=1`（t.window=false，tee 与有窗逐字节一致）

## Project layout

- `docs/` — 规格真源与决策台账（中文）
- `tables/` — `cmd.tbl`（IR 单一真源，命令集 v1.2 对照 LÖVE 11.5 源码定稿）
- `tools/` — fr-* 工具族（Python；C 编解码由 fr-gen 生成）
- `render/` — fr-gen 生成的 C 编解码落位（fr_codec.h/.c + fr_selftest.c 跨架构字节自测）；L0 产流原型在 `l0/`
- `tests/` — round-trip 回归、对拍
- `love2d/` — LÖVE 11.5 素材（win64 运行时 / 官方 11.5 源码 / wiki dump；运行时二进制不入 git；**源码必须与锁定运行时同版本**）

## Code style

- 三语并存：Python（工具）、C（编解码，fr-gen 生成）、Lua（渲染端）；**生成代码不手改，改表重新生成**
- 文档与注释用中文，标识符用英文
- 浮点文本 `%.6f` 定长；判据锚行不锚全文

## Testing instructions

- 最高优先回归：`.fr` → `.frb` → `.fr` round-trip 逐字节相等，CMNT 注释保留
- 待取证项（`docs/fr-spec.md` §12）先取证，再改规格，再实现；取证结论登记进 `tables/cmd.tbl` 的 source/notes 列
