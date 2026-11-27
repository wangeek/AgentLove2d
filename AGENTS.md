# AGENTS.md

FR 帧流 IR（.fr / .frb 双形态）工具链，载体为魔改 LÖVE 11.5：Lua 内核脚本产出 FR 流，引擎内 C 层捕获与回放。先建工具、后改造 sango——sango 只是未来的 lowering 前端之一，与本项目解耦，**不得把 sango 的实现形态当成本项目的设计约束**。

## 真源文件（动手前先读）

- **`docs/fr-agent-guide.md`** — **Agent 使用手册（观察/调试/验证 LÖVE 游戏的端到端路径）**：接入录制（env 表）→ 观察工具 → 锚行 diff 定位法 → 判据文件格式（CHECK/CHECK-NEXT/CHECK-NOT）→ 回归循环 → 剑侠 worked example。新 agent/新会话从这本进
- **`docs/fr-agent-practice-report.md`** — **实战实践报告（第三方工程实测）**：MemoryRemake 整轮开发用 FR 当主验证手段的数据与教训——39 项判据/72 秒、92% 时间在进程启动、五步闭环、体积三档、六个录制坑、20.4GB 失控流（含 2.2GB 单行混 NUL 致流不可判定）。动手前先看这本避坑
- `docs/design.md` — **总纲入口**：系统全貌、一帧的一生、机制卡、工具族地图、实施路线——新会话从这里进，再按其 §0 读者地图跳真源
- `docs/fr-rationale.md` — **动机总纲**：FR 为 Agent 图形化验证而设计的推理链、五条设计原则、Agent 工作流、MCP 工具预留接口面
- `docs/fr-spec.md` — FR 规格（现行 v1.5，以 §13 版本记录为准）：段语义、级别三档、命令集、事件词汇表、工具族、取证清单
- `docs/decisions.md` — 架构决策 D1–D14：LLVM 模式总则、语义四准则、验证两律、树不进协议、语境纪律、LÖVE 定位、魔改宿主架构（D8）、sango 剥离（D9）、GPU 边界（D10）、相机归属（D11）、捕获面全 API 三分类与回放侧三机制（D12）、环境层家族 v1 透明放行（D13）、流是唯一持久化物+ev 双生产者+dream 直出（D14）
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
- 讨论收尾三步走：决策结论 → decisions.md 追加条目；批次设计/讨论沉淀 → docs/plans/ 文档；总纲 design.md 同步正文与指针——**不允许结论只存在于会话记录**

## Setup commands

- 运行官方 LÖVE 11.5：`love2d/love-11.5-win64/love.exe <游戏目录>`（官方运行时，不入库；只有 L0 样机与 `tests/test_l0.py` 用它——**录制走下面的 fork，不是这个**）
- L0 产流样机（B3b）：`love2d/love-11.5-win64/love.exe l0 --demo --frames N --fixed-dt X --sha <表指纹> --seed S --out <path>`（表指纹=`tools.fr_gen.tbl` 的 `tbl_sha256(tbl.parse(表文本))`；golden 在 `tests/golden/l0_session.fr`）
- **fork 构建（B4 起）**：megasource 在 `megasource/`（11.5 tag，不入库）；增量构建 `cmake --build megasource\build115 --config Release`；环境变量 `CMAKE_POLICY_VERSION_MINIMUM=3.5` 必设（openal 内部 cmake 用）；自建运行时在 `megasource\build115\love\Release\`
- **fork 源码的公开镜像（2026-11-24 首推）**：`git@github.com:wangeek/love-fr.git` 的 `fr-capture` 分支——官方 `11.5` 完整历史 + FR 提交；本地 `megasource/libs/love` 的同名分支已设上游跟踪（远端名 `fr`）。**捕获层改动必须提交并推送到这里**（2026-11-23 曾发现 424 行改动只存在本机磁盘）。复原：clone 后放到 `megasource/libs/love`，构建步骤与环境变量见其 readme（已标注"修改版/非官方"，含已验证与未验证边界）
- **依赖分层（2026-11-24 干净 clone 实测）**：① 纯 Python（标准库，clone 即可用）=读写与判定**已有流**——fr_dump/check/diff/lint/stats/as/dis/assets/prec 与 MCP 的 fr_read/fr_diff；② **需 fork 构建 love.exe**=录制、fr_render（离线回放/`--sim`/`FR_PLAY`）、MCP 的 fr_record、demo rig；③ 可选=ffmpeg（仅 `fr_render --record` 出 mp4，**路径写死**在 `tools/fr_render.py`）、C 编译器（C 编解码自测，无则跳过）、官方运行时（仅 test_l0）。引擎与工具是否配套由**命令表指纹**保证（`tables/cmd.tbl` 的 sha256 编进 fork 并写入流头，fr_check 对账）。**测试不自声明引擎依赖**（只有 test_interactive 与 test_world 的 kit 两项会跳过）：干净 clone（引擎与官方运行时都没有）里 48 项直接失败/报错（43 需 fork、5 需官方运行时），症状是 `FileNotFoundError: [WinError 2]`——排障先确认 `megasource\build115\love\Release\love.exe` 在位
- fork 捕获 rig（B4-2）：`megasource\build115\love\Release\love.exe megasource\libs\love\demo`（`FR_CAPTURE=1` 时捕获/回放，缺省 3 帧验证 rig 打 PIXEL/会话行）；tee₁ 会话加 `--out <path> --sha <表指纹> [--seed S] [--frames N 缺省 4]`；全 API 闭环加 `--api-parade`（B8 T4：20 API 靶直调通道，sim 重演须同通道 `python tools/fr_render.py --sim <in.fr> --api-parade`）；回归 tests/test_capture.py
- 任意游戏 C 侧 tee（B10）：`FR_CAPTURE=1 FR_OUT=<path> FR_SHA=<表指纹> [FR_SEED n] [FR_FRAMES n] [FR_DT f] [FR_MAX_MB f] [FR_OVERWRITE=1]` → **零游戏侧改动出流**（in=Event::pump convert 捕获、dt=w_timer_step 钩、帧边界=present 钩逐帧追加、lua_close 前封口）；**FR_DT=覆写 step 返回值**（固定步长真确定性——双跑逐字节前提，2026-11-07 兑现：原实现只兜底不覆写，帧 0 启动抖动破逐字节）；无头头几何 FR_W/FR_H 钉定/缺省回退 640×480；**写者护栏（2026-11-18）**：FR_OUT 已存在默认拒绝覆盖（需 `FR_OVERWRITE=1`）、独占打开（`_SH_DENYRW`，第二写者共享冲突）、`FR_MAX_MB` 体积封口（帧边界判，末帧完整）；离线回放 `python tools/fr_render.py <流>`。newgame 实证：30 帧 smoke rc=0 → 38MB 流（18 资产/83591 out 行）→ 离线回放 rc=0、帧 5-30 D_CRC 稳定。与 demo `--out`（Lua tee）并存正交；`_frSessionFrame` 显式补帧口=验证帧等价点
- 熵剖面（B13）：`python tools/fr_stats.py <流> [--json]`——四层（op/参数默认值命中率/量化模拟/时间层），B14 紧凑编码的准入裁判；动态基准锚 `FR_BOOT_SCRIPT=tools/fr_boot_battle.lua` 直切 battle（形态基准——跨跑 D_CRC 不适用，见 benchmarks.md 双场景节）
- 离线回放视觉播放（B11）：`FR_PLAY=1 python tools/fr_render.py <流>`——离线画布贴屏+present+按流内 dt 节奏（播完停留 1s）；判据输出与关闭时逐帧一致（播放只追加上屏，拓扑 B 默认无头形态不变）
- dream runner（B18 M1）：`python -m dream.run --frames 60 --out <path> [--kit <dir>] [--from-file <chunks.txt> | --llm] [--chunk-frames 10] [--directive "<剧本>"] [--ev "<帧号>:<type> <args...>"]`——LLM 直出 canonical FR（`--llm` 走 env：LLM_BASE_URL/LLM_MODEL/LLM_API_KEY；`--from-file` 确定性零 token）。**口径注意：回放 stdout D_CRC=画布像素 CRC，流内 d_crc=out 行文本 CRC——两域不可互比**（判据=rc=0+出齐+双跑稳定）；会话日志缺省 `<out>.chatlog`（SYSTEM 一次+逐回合增量+usage）
- dream 交互会话（B18 M2，ev 驱动）：`python -m dream.loop --llm --out <s.fr> --kit dream --directive "..."`——Runner=微型 LÖVE 游戏（`love.exe dream/runner`）实时渲染，点击/按键由 Lua 捕获→LLM 响应续写（ev 行落流 in 段+协议行注入）；空闲不增帧；`FR_EV_INJECT` 文件通道注入合成事件（CI 确定性，走 love.event.push 正规队列）；测试 tests/test_interactive.py（Fake LLM 端到端）
- 无限流地牢（B18 M2b，实验态）：`bash dream/run_world_ds.sh`（DeepSeek 真交互实录：EVINJ 协议行抓注入路径+方向键序列）或 `python -m dream.world --llm --out run.fr --kit dream/kit_heroes [--headless] [--rooms-max N]`——room=上下文边界（每房重建会话只传房间数/积分两数），pass/over 三连信令+lint 门结算，帧数上限兜底，积分杠杆（奖励:遇怪=0.3+0.7×完美度）；产物 run.fr=整局存档（.chatlog 各房对话）。**出口闸（2026-11-24）**：总时长 `--max-total`、静默 `--max-idle`、连续展开失败 `--max-bad-bursts` 三闸都在房内循环顶部每轮必检（headless 也生效——此前只在窗口模式的无事件轮检查，LLM 一直不给合法信令就无限跑、`--max-total` 不生效）；LLM 调用抛异常由 main 接住并收尾（退出码 3，chatlog 记 `RUN ABORTED`）；失败 burst 的回滚只撤本 burst。仍为实验态：真 LLM 的 headless 回归未覆盖
- 资产 kit 抽取（B18）：`python tools/fr_assets.py <in.fr|in.frb> -o <kit_dir>`——asset 行抽取/renumber/目录单（assets.json 喂 LLM + assets.txt 回放）；**从文件建 kit**：`python tools/fr_assets.py --from-files <kit_dir> <a.png> [b.ttf ...]`（PNG 头解析 w/h、编码字节原样登记、assets.json 记 src 语义名）；kit 字节不入库按需再生（dream/.gitignore）
- 流诊断器（B18）：`python tools/fr_lint.py <in.fr> [--dream] [--max-line-mb N]`——L001 幻资产/L002 d_crc 对账/L004 帧行序（--dream 加 L003 st 口径）/**L006 不可判定流**（行内 NUL/单行超 256MB/非法 UTF-8，流式扫描越界即返——20.4GB 坏流 0.11s 报出行号）；退出码 0=全绿
- Python 工具（fr-*）：`python tools/<tool>.py ...`（fr-gen 已交付：`python -m tools.fr_gen.gen_python` / `gen_c` / `gen_js` 再生三目标，改表后必跑；`gen_js` 产 JS 表数据面并同步到 `../phaser-fr/src/`）
- 前端仓 `phaser-fr`（D17 第二宿主试点，v0.2）：`npm test` 四段全绿——conformance（吃主仓 golden：逐行 round-trip + 逐帧 d_crc 重算）/ semantics 11 条 / replay（golden 逐行一致）/ **capture 8 条**（捕获行 == 独立手算期望、d_crc 自洽、双实例双跑逐字节、回放对账、像素 CRC 双回放稳定、不静默丢）；需 Chromium 系浏览器。**捕获已落地**（`src/capture.mjs`：clear/draw/print/rect 填+描、**atlas 帧发 quad 资产**、**`draw.rot` 由四角按规格 §7.1/D18 规范分解**（剪切/退化不近似、发 `err`）、**对象层对账让静默丢结构上不可能**、缺口同时以 `err` 写进流；s_crc 固定 0）+ **回放已落地**（11 op，`scissor` 已知缺口用了判 FAIL，`npm run test:known-gaps` 单跑）。只覆盖 full 档文本流。**真实靶子冒烟**（不进 npm test）：`FR_QUERY=game=breakout|stacker|snowmen node test/run.mjs smoke.html`——三个 Phaser 官方示例游戏原样拷在 `test/smoke/`，Breakout 前 36 帧与独立期望逐行零失配、三靶子零静默丢、流过主仓 lint/check 零改动；**真游戏跨运行逐字节相同仍未做到**（加载期场景已跑可变帧数，见计划文档）。**计划文档 docs/plans/2026-11-27-multi-frontend-phaser.md 的"时间基准""捕获挂点""P1 落地记录""P2 落地记录"四节是实测结论**（Phaser 4.2.1 + 无头 Edge）：帧步长**五步**配方（除 sleep/关平滑器/原点钉 0/乘法步进外，还要**虚拟化 `Date.now`**——TweenManager 用墙钟且基数要小；并**钉 `lastTime` 让 delta 恒等**——物理固定步进是严格浮点比较，ulp 差就跳步）；捕获挂点=对象层设身份 + 节点层 `run` **返回后**读几何（读早一格整体错位且流仍合法）；**描边走 StrokePath（matrix 新、quad 旧）不走 FillRect**；Color 的 alpha 是 0–255；帧字段 `cutX/Y/W/H`=源图矩形、`x/y`=trim 偏移、`width/height`=裁后尺寸、未裁尺寸只在 `data.sourceSize`。**动 Phaser API 前先查这四节或从源码列名字**——凭 3.x 记忆写 4.x API 已错六次。捕获流可落盘喂主仓工具：`FR_STREAM_OUT=<path> node test/run.mjs capture.html` → `fr_lint`/`fr_check` 零改动全绿。探针复跑：`node docs/probes/phaser/run.mjs`（零 npm 依赖，首次从 CDN 取 Phaser）
- 会话封装互转（fr-as/fr-dis 已交付）：`python tools/fr_as.py <in.fr> -o out.frb` / `python tools/fr_dis.py <in.frb>`
- dump 与判据（fr-dump/fr-check 已交付）：`python tools/fr_dump.py <in.fr|in.frb> [--frames a-b] [--stats] [--strip-assets] [--geo] [--names assets.json]`（strip=asset 行 hex 体剥成 `# … (+NB hex)` 摘要，观察面 3.0MB→10.5KB；geo=draw 行后插 `# geo: rect=…` 屏幕有效矩形派生行（D15 读侧派生不进流；资产预处理只建议不代做——见 fr_record description）；names=kit 目录单 src 语义名 join 进摘要/geo 行）/ `python tools/fr_check.py <in.fr|in.frb> [判据文件] [--strict]`
- MCP 工具面（2026-11-02 精简三件）：`fr_record`（env 组装+headless 录制）/`fr_read`（canonical 文本，默认剥资产 hex，frames 选帧，封顶 100KB，**描述内含 op 词汇表**——版本随 cmd.tbl 表头，测试防漂移）/`fr_diff`（首分歧帧+行 diff）——服务 `tools/fr_mcp.py`，工作区 `.mcp.json` 已注册 `fr-tools`；全量与结构化消费走 CLI（grep/check/stats 由 agent 对 read 结果自做）
- C 工具链：本机 `D:/Lab/_tools/mingw64`（x86_64，主力）与 `D:/Lab/_tools/mingw32`（i686——**2026-10-27 起编译子进程损坏**：连 hello.c 都静默 exit 1，待重置；跨架构对账暂依赖 gyl）——均为 GCC 14.2.0，无 PATH——根 conftest.py 自动注入（mingw64 优先）；另有 MSVC BuildTools 2022（cl 19.44，x86 根下）与 LLVM 21.1.5（`D:/Lab/_tools/LLVM`，clang/lld-link/lldb）——B4 fork 的 MSVC 官方构建路线零安装可行（docs/build-probe.md）
- 测试：`pytest tests/`（193 项、零跳过，**前提是三样都在位**：fork love.exe、官方运行时 `love2d/love-11.5-win64/`、kit 资产 `dream/kit_heroes/assets.txt`——缺引擎 43 项失败、缺官方运行时 5 项失败（都不自跳过），缺 kit 则 test_world 七项跳过；见上"依赖分层"。**kit 这道跳过要保留**：缺 kit 时信令必被 lint 判 L001，这些用例必然失败（修复前还会因 headless 循环无出口把 pytest 进程挂死——该无界循环 2026-11-24 已修，见 world 行）。分组：解析/量化/编解码/会话封装/CLI/round-trip/零漂移与跨目标锚/C emit+解码自测/L0 headless/fork 捕获与 tee₁/真字节物化/离线回放 d_crc/无头拓扑 C/事件捕获与 sim 重演/堆 s_crc 与 st 物理行/d_crc 与 str 敏感 s_crc/B8 状态类+绘制五 op+rt/scissor/Shader 边界+api-parade 闭环/B9 代理方法族+去重+形态/B10 C 侧 tee 对拍+FR_DT 覆写双跑逐字节+无头几何+写者护栏（存在即拒/独占/体积封口）/B13 fr-stats 剖面/B14 :px 档编解码与 fr-prec 转换/B15 增量词汇与 fr_delta_check 对拍/B18 dream 组（会话壳/lint/assets/prompt/driver/60 帧端到端/world 状态机+出口闸：headless 总时长与静默、连续失败上限、异常中止、回滚只撤本 burst/gen_burst 调用失败处置：重试而非 UnboundLocalError、不重用旧回应）/MCP 面三件（协议/read 剥 hex+词汇表/路径无关真录）/dump geo 派生视图（五形态/过滤/确定性/零漂移/names join）/lint L006 不可判定流（NUL/超长行/非法 UTF-8/流式早退/CLI 面））
- 事件注入回放（B5）：`python tools/fr_render.py --sim <in.fr>`——严格档内核重演（录制 ev 事件注入队列重新驱动内核，再生 out 行与录制逐帧比对）；demo 注入参数 `--inject-click <x>,<y> --inject-key <key>`（帧 1/2）
- 发布包（B7a）：`dist/fr-capture-demo.zip`——fork 运行时+VC143 CRT+捕获 rig demo（含 golden），解压即跑（README 有命令）
- 堆状态观测（B6）：s_crc 常开（注册状态根子图 CRC——demo 侧 `_frStateRoot(kernel.state)`）；st 物理行 FR_LOGLEVEL=full 按需（影子镜像 diff，数组 `[i]`/hash `"key"`，表重建走 err 载体）；sim 比对集含 st/s_crc
- 离线回放（B4 阶段三）：`python tools/fr_render.py <in.fr|in.frb>`——拓扑 B 离线回放驱动（fork love.exe 的 --offline-replay 模式），输出逐帧 D_CRC 与采样像素；无头录制（拓扑 C）：fork demo 加 `FR_HEADLESS=1`（t.window=false，tee 与有窗逐字节一致）

## Project layout

- `docs/` — 规格真源与决策台账（中文）
- `tables/` — `cmd.tbl`（IR 单一真源，命令集 v1.2 对照 LÖVE 11.5 源码定稿）
- `tools/` — fr-* 工具族（Python；C 编解码由 fr-gen 生成）
- `render/` — fr-gen 生成的 C 编解码落位（fr_codec.h/.c + fr_selftest.c 跨架构字节自测）；**`render/js/` = JS 前端目标**（`fr_table.mjs` 生成物 + `codec.mjs`/`conformance.mjs` 手写单源，由 `gen_js` 同步到 `../phaser-fr/src/`）；L0 产流原型在 `l0/`
- `tests/` — round-trip 回归、对拍
- `love2d/` — LÖVE 11.5 素材（win64 运行时 / 官方 11.5 源码 / wiki dump；运行时二进制不入 git；**源码必须与锁定运行时同版本**）

### 命名规则（专有名词分四层，勿混）

| 层 | 形态 | 例 |
|---|---|---|
| **仓库**（宿主引擎的 FR 前端/宿主） | `<引擎>-fr`，**引擎在前** | `love-fr`（既有）、未来的 `phaser-fr` / `godot-fr` |
| MCP 服务名 | `fr-tools` | `.mcp.json` 的 key，跨仓一致 |
| CLI 工具 | `fr_<动词>` | `fr_dump` / `fr_check` / `fr_diff` / `fr_lint` |
| 本文档目录 | `fr-<主题>.md` | `fr-spec.md` / `fr-agent-guide.md` |

2026-11-27 教训：提过一个 `fr-phaser`，与既有的 `love-fr` 顺序相反——**新仓库命名先找既有先例，别自造词序**。

## Code style

- 三语并存：Python（工具）、C（编解码，fr-gen 生成）、Lua（渲染端）；**生成代码不手改，改表重新生成**
- 文档与注释用中文，标识符用英文
- 浮点文本 `%.6f` 定长；判据锚行不锚全文

## Testing instructions

- 最高优先回归：`.fr` → `.frb` → `.fr` round-trip 逐字节相等，CMNT 注释保留
- 待取证项（`docs/fr-spec.md` §12）先取证，再改规格，再实现；取证结论登记进 `tables/cmd.tbl` 的 source/notes 列
