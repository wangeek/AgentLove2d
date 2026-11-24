# FR 帧流 IR（AgentLove2d）

把"游戏跑了一趟"变成一个**可传递、可复查、可计算**的物——不是像素录像，是带状态、带输入、带校验和的**确定性执行历史**。载体：魔改 LÖVE 11.5（fork），Lua 游戏内核产出 FR 流，引擎内 C 层捕获与回放。

## 这是什么（一分钟）

```
游戏（LÖVE 游戏，零改动）
   │  FR_CAPTURE=1 FR_OUT=game.fr
   ▼
FR 流（.fr 文本 / .frb 二进制，帧五段：head/in/log/out/end）
   │  python tools/fr_render.py game.fr        ← 脱离原程序回放（判据）
   │  FR_PLAY=1 python tools/fr_render.py ...  ← 视觉播放（可看可关）
   ▼
画面 + 逐帧 D_CRC/像素锚（符号判据，不是人眼）
```

同一份流：LLM 直接读文本验证逻辑、diff 出回归点、离线重渲任意视觉风格。**X11 送画面的命令，视频送画面的像素，FR 送世界的执行历史。**

## MVP 已实证（v0.1.0，2026-10-29）

- **第三方游戏闭环**：newgame《剑侠无敌》零改动录制（240 帧 rc=0）→ 脱离原程序回放/播放 rc=0，画面与原版逐像素一致（--auto-shot 对拍）
- **格式封版**：v1.2.7（.fr/.frb round-trip 逐字节相等；font 字节池化引用形态）
- **性能基准**（newgame 30 帧）：录制 0.09 s/帧（状态根注入）；流 23.5MB 文本 / 11.2MB 二进制；串流档位 15fps≈12Mbps（详见 docs/benchmarks.md）
- **健壮性**：OTF/TTC/垃圾字节字体三态捕获全通；NaN/Inf 参数防线；当时 101 项回归全绿

## 快速开始

下面第一行的 `love.exe` 是**魔改后的引擎**，不是官方 LÖVE，需要先构建（见"依赖"）。

```bash
# 录制（SHA 可缺省；表指纹对账时才必需）
FR_CAPTURE=1 FR_OUT=/tmp/game.fr FR_SEED=1 \
  megasource/build115/love/Release/love.exe <LÖVE 游戏目录>

# 回放（判据：D_CRC 序列）/ 播放（视觉，窗口可关）
python tools/fr_render.py /tmp/game.fr
FR_PLAY=1 python tools/fr_render.py /tmp/game.fr

# 转二进制 / 反汇编 / 结构统计
python tools/fr_as.py /tmp/game.fr -o /tmp/game.frb
python tools/fr_dis.py /tmp/game.frb | head
python tools/fr_dump.py /tmp/game.frb --stats
```

## 依赖

分三层，只有中间那层需要编译。

| 层 | 需要什么 | 有了它能做什么 |
|---|---|---|
| 读写与判定已有的流 | Python 3.11（只用标准库；跑测试另需 pytest） | `fr_dump`、`fr_check`、`fr_diff`、`fr_lint`、`fr_stats`、`fr_as` / `fr_dis`、`fr_assets`、`fr_prec`；MCP 的 `fr_read`、`fr_diff` |
| **录制与回放** | **魔改后的 `love.exe`**：源码在 [wangeek/love-fr](https://github.com/wangeek/love-fr)（`fr-capture` 分支），构建步骤见其 README（Windows + MSVC，需放进 megasource） | 录制游戏、`fr_render`（离线回放、`--sim` 内核重演、`FR_PLAY` 播放）、MCP 的 `fr_record`、`demo` 验证程序 |
| 可选 | ffmpeg；C 编译器（gcc 或 clang）；官方 LÖVE 11.5 运行时 | ffmpeg 只用于 `fr_render --record` 出 mp4（路径写死在 `tools/fr_render.py`，换机器要改）；C 编译器用于改命令表后的编解码自测，没有则跳过；官方运行时只用于 `tests/test_l0.py` 的 L0 样机对拍 |

另外两处零散的依赖：

- `tools/gen_pixel_frames.py`（生成测试素材的辅助脚本，不属于 `fr_*` 工具族）需要 Pillow。
- `dream/`（让 LLM 直接写 FR 流的实验模块）运行时需要一个能访问的 OpenAI 兼容端点，由环境变量 `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` 指定；它的实时 Runner 同样要用魔改后的 `love.exe`。

引擎和工具是否配套，由**命令表指纹**保证：`tables/cmd.tbl` 的 sha256 编进引擎，并写进每条流的会话头，`fr_check` 会核对。

### 测试在什么条件下能跑

2026-11-24 的实测：把本仓库克隆到一个**不含** `megasource/` 和 `love2d/` 的目录（等于没构建引擎），`pytest tests` 的结果是 **129 通过、48 失败或报错、3 跳过**，4 秒跑完。构建好引擎后是 180 项全过。

需要注意两点：

- **那 48 项不会自动跳过，会直接失败。** 43 项需要魔改后的 `love.exe`：`test_capture` 25、`test_render` 6、`test_ctee_guard` 5、`test_stats` 4、`test_fr_mcp` 2、`test_delta_check` 1；另外 5 项需要官方运行时（`test_l0`）。
- **跳过的 3 项**：`test_interactive` 一项（缺引擎），`test_world` 两项（缺 `dream/kit_heroes/assets.txt`——kit 资产按设计不入库，再生方法见 `dream/.gitignore`）。

所以看到大量 `FileNotFoundError: [WinError 2]`，先确认 `megasource/build115/love/Release/love.exe` 在不在。

## 实战验证（第三方项目实测，2026-11）

MemoryRemake（LÖVE 重制工程）把 FR 流当主验证手段跑了整轮开发，数据与教训见
**[docs/fr-agent-practice-report.md](docs/fr-agent-practice-report.md)**。要点：

- **规模**：23 份判据 / 39 项冒烟 / 72 秒跑完（并行 4 路）；落盘 75 条流
- **判据不吃时间**：92% 的时间是进程启动与封口等待，真正跑游戏 < 10 秒——杠杆在录制路径，不在写更细的判据
- **五步闭环**：双录 → `fr_diff -1`（确定性）→ 扰动必帧 0 分叉 → 正例 rc=0 → 负例必 FAIL
- **体积三档**：全量 10.2MB / 精简 93KB（1.4%，判据链路默认）/ `.frb` 5.0MB（留存）
- **六个录制坑**：普通游戏无头不推帧、不 terminate 必超时 180s、窗口输入污染、存档串味、
  env 传中文崩 UTF-8、GUI 子系统 stdout 无处写
- **最贵一课**：一条手工调试流长到 20.4GB（36.7 万帧、2.2GB 单行混进 NUL），
  之后**整条流对文本工具静默失效**——录制必须带帧上限，工具应当能识别"不可判定流"

## 文档地图

| 想了解 | 去哪 |
|---|---|
| 项目动机与 Agent 工作流 | docs/fr-rationale.md |
| **上手：接入录制、观察、判据、回归循环** | **docs/fr-agent-guide.md**（含 MCP 三件的用法） |
| **agent 怎么用 FR 做验证（实践报告）** | **docs/fr-agent-practice-report.md** |
| 系统全貌 / 一帧的一生 / 实施路线 | docs/design.md（总纲入口） |
| 流格式规格（现行 v1.5，§13 是版本记录） | docs/fr-spec.md + tables/cmd.tbl（命令单一真源） |
| 架构决策 D1–D16 | docs/decisions.md |
| 性能基准线与优化路径 | docs/benchmarks.md |
| 魔改设计与取证 | docs/love2d-gap.md |
| 魔改引擎源码（LÖVE 11.5 的 fork，`fr-capture` 分支，含构建说明） | [github.com/wangeek/love-fr](https://github.com/wangeek/love-fr) |

## 测试

```bash
pytest tests/   # 180 项：格式/编解码/round-trip/捕获/回放/对拍/闭环
```

这是构建好引擎时的数字。没构建引擎时会有 48 项直接失败，见上面"依赖"。
