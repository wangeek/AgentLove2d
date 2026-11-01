# FR Agent 使用手册——用帧流观察、调试、验证 LÖVE 游戏

> 面向：AI agent（及人）。你有一个 LÖVE 游戏（自己的或第三方），要在不看像素截图的前提下
> 观察它跑起来的行为、定位问题、验证修复。全部工具只流通**文本行与数字**——这是设计原则，
> 不是限制：agent 读符号比读图像可靠。
>
> 协议语义真源：`docs/fr-spec.md`；工具 CLI 自带 `--help` 与模块 docstring；本文管"怎么用它们干活"。

## 0. 心智模型（30 秒）

**流 = 游戏"跑了一趟"的完整事实**。一个 `.fr`（文本）/`.frb`（二进制）文件，按帧组织：

```
frb1 640 480 <表指纹> <loglvl> <seed>          ← 会话头（几何/词汇表版本/录制参数）
frame 0
dt 0.016                                   ← 时间（每帧真实步长）
asset image 1 32 32 <hex字节>               ← 注册过的资产（图/字体/画布/子图）
ev 0 "keypressed" 0 2 str "return" num 0     ← 输入事实（in 段）
draw 1 0 132.000000 240.000000 ...           ← 画面事实（out 段）＝游戏这帧画了什么
st 1 "hp" num 87                             ← 状态事实（log 段，full 档）
s_crc 12345 / d_crc 67890                    ← 每帧校验（堆状态 CRC / out 行文本 CRC）
```

三类消费者同一份流：人眼看回放、CI 跑判据、agent 逐行读。**判据只做符号比较**（锚行 diff
或字节相等），墙钟时间不进判据。

## 1. 接入与录制（零游戏侧改动）

游戏不需要任何源码修改。用 fork 构建的 love.exe 跑你的游戏目录，环境变量开捕获：

```bash
# 表指纹（录制会话头要写入；同仓库表变则需重算）
SHA=$(python -c "from tools.fr_gen import tbl; print(tbl.tbl_sha256(tbl.parse(open('tables/cmd.tbl',encoding='utf-8').read())))")

FR_CAPTURE=1 FR_OUT=run.fr FR_SHA=$SHA \
  megasource/build115/love/Release/love.exe <你的游戏目录>
```

| env | 作用 | 缺省 |
|---|---|---|
| `FR_CAPTURE=1` | 开捕获（te 会话：in/out/log 全录） | 关 |
| `FR_OUT=<path>` | 流输出路径 | — |
| `FR_SHA=<指纹>` | 会话头表指纹 | — |
| `FR_FRAMES=<n>` | 录 n 帧自动封口退出（smoke 用） | 手动关窗 |
| `FR_DT=<f>` | 固定步长（确定性录制，跳过真实计时） | 真实 dt |
| `FR_SEED=<n>` | 种子写会话头 | 1 |
| `FR_HEADLESS=1` | 无头（t.window=false，判据链路首选） | 有窗 |
| `FR_BOOT_SCRIPT=<path>` | 外置启动脚本（如 require 游戏状态模块后调 `love.graphics._frStateRoot(根表)`——把 s_crc 观测收缩到你关心的状态子图） | — |
| `FR_VIDEO_OUT=<path>` | 逐帧原始像素倾倒（配 fr-render --record 出 mp4） | — |

**确定性是可调试的前提**：固定 `FR_DT` + `FR_SEED` + 无头，双跑逐字节相等才成立；游戏内若
读 `love.math.random` 之外的真随机/墙钟，先处理。事件由你（或脚本）注入——同一输入序列产
出同一流。

## 2. 观察：四个问题四种工具

| 你想回答 | 工具 | 命令 |
|---|---|---|
| "第 5-10 帧到底画了什么？" | fr-dump | `python tools/fr_dump.py run.fr --frames 5-10` |
| "这流的构成？（多少帧、什么 op 多）" | fr-dump --stats | `python tools/fr_dump.py run.fr --stats` |
| "字节都花在哪？帧间重复率？" | fr-stats | `python tools/fr_stats.py run.fr [--json]`（op/参数默认值/量化/时间四层剖面） |
| "回放是否逐帧可复现？" | fr-render | `python tools/fr_render.py run.fr`（stdout `D_CRC <n> <crc>` + `PIXEL x y r g b` 采样） |
| "给自己/用户看片" | fr-render --record | `python tools/fr_render.py run.fr --record out.mp4`（视频是审看投影，不进判据） |
| "事件驱动的内核逻辑对不对？" | fr-render --sim | `python tools/fr_render.py --sim run.fr`（录制 ev 重新注入内核重演，再生 out 与录制逐行比对；`SIM SUMMARY` 全 MATCH=0） |

读 D_CRC 的正确姿势：`D_CRC 30 1234567890` = 前 30 帧块执行后的画布 CRC。**双跑稳定 =
两流同位置 D_CRC 相等**——这是回归判据的地基。PIXEL 行是末帧采样点颜色，快速 sanity 用。

## 3. 定位：锚行 diff 调试法

问题形态通常是"从某帧起画面不对"。循环：

1. **双录两条流**：改前 `base.fr`、改后（或好/坏版本）`test.fr`，同 env 同输入。
2. **fr-dump 各自导文本**，逐帧对比——第一条不一致的帧即分叉点：
   ```bash
   python tools/fr_dump.py base.fr  > base.txt
   python tools/fr_dump.py test.fr > test.txt
   diff base.txt test.txt | head -40
   ```
3. 分叉帧内**先看 in 段**（ev 是否相同——输入分叉先修输入注入），再看 out 行序与参数，
   最后看 st（状态何时开始错，可能早于画面——st 是因，画面是果）。
4. `--frames a-b` 收窄窗口迭代；`fr_lint`（`python tools/fr_lint.py run.fr`）查结构病
   （幻资产/帧序/d_crc 对账）。

原则：**定位到行，不改到像素**。你拿到的是"帧 17 的 draw tex=3 x=440≠420"，直接映射回
游戏代码里的那一次 draw 调用。

## 4. 判据：FileCheck 式锚行文件

把"这游戏应当如此"写成判据文件 `checks.txt`，随仓库走，CI/agent 反复执行：

```
# 注释行
CHECK: frame 29
CHECK: draw 3 0 420.000000
CHECK-NEXT: print 2 "HP 87"
CHECK-NOT: err
```

- `CHECK: <子串>` —— dump 输出任意行含子串即命中
- `CHECK-NEXT: <子串>` —— 恰为上一命中行的**下一行**才命中
- `CHECK-NOT: <子串>` —— 上一命中行（不含）到本次命中行（不含）之间不得出现；结尾悬空 NOT 扫到 EOF

执行：

```bash
python tools/fr_check.py run.fr checks.txt --strict
# stdout: CHECK OK (4 directives)   → rc=0
# 任一失败 → stderr "FAIL: …"（含指令与定位）→ rc=1
```

**内置校验**（无判据文件也跑）：canonical 幂等（parse→dump 逐字节还原）；流内 sha 与当前
`tables/cmd.tbl` 指纹对账（不一致默认 WARNING，`--strict` 升 FAIL——表变了意味着行语义
可能漂移，先重算指纹重录再谈判据）。

写判据的纪律（spec §原则）：**锚关键行，不锚全文**。挑不稳定的成分（时间戳/绝对 CRC 随环
境变）出判据；稳定的结构事实（"frame 29 后英雄 x=420"、"结算画面含 HP 87"）进判据。

## 5. 回归循环（改一行的完整旅程）

```
改游戏代码
  → FR_CAPTURE=1 FR_DT=0.016 FR_HEADLESS=1 重录 run.fr
  → python tools/fr_check.py run.fr checks.txt --strict   （判据全绿）
  → python tools/fr_render.py run.fr                       （D_CRC 出齐、双跑相等）
  → 需要人审 → --record out.mp4
```

全绿即回归通过；任何一步 FAIL 回到 §3 定位。

## 6. Worked example：第三方游戏 30 帧 smoke（剑侠 newgame）

```bash
SHA=$(…表指纹…)
FR_CAPTURE=1 FR_OUT=newgame.fr FR_SHA=$SHA FR_FRAMES=30 FR_DT=0.016 \
  love.exe /d/Lab/MiniMaxWorkspace/newgame
# → rc=0，38MB 流（18 资产 / 83591 out 行——资产字节占大头，见 fr-stats）
python tools/fr_render.py newgame.fr     # rc=0，帧 5-30 D_CRC 稳定（初始化含 seed 外随机，前 4 帧不锚）
python tools/fr_check.py newgame.fr --strict
```

要点实录：第三方游戏零改动；资产占流体积 99%+ 属已知形态（B16 内容寻址的正靶）；动态场景
D_CRC 判据不适用（含未播种随机），**判据面退化为结构锚行 + 双跑对拍**——先固定随机源再谈
帧级判据。

## 7. 已知边界（截至 2026-11-01）

- `fr_dis` 对 >10MB 单资产行 O(L²)——大流走 fr_dump（cursor 变体待 B18+）
- C 离线解析器 `.frb` 路径不认 st/log 行（`.fr` 文本路径全通）
- 回放 stdout `D_CRC`（画布像素 CRC）≠ 流内 `d_crc`（out 行文本 CRC）——两域不可互比
- 动态基准（FR_BOOT_SCRIPT 直切场景）初始化含 seed 外随机，跨跑 D_CRC 不适用
- `--sim` 严格档要求录制与重演同事件管线（`--api-parade` 场景需同通道重演）

## 8. 工具速查

| 工具 | 一句话 | 关键参数 |
|---|---|---|
| fr_dump | 流→canonical 文本/摘要（判据素材） | `--frames a-b` `--stats` |
| fr_check | 内置校验 + FileCheck 判据 | `checks.txt` `--strict` |
| fr_lint | 结构诊断（幻资产/帧序/对账） | `--dream`（dream 流口径） |
| fr_stats | 四层熵剖面 | `--json` |
| fr_render | 离线回放（D_CRC/PIXEL）/ mp4 / --sim 内核重演 | `--record` `--sim` |
| fr_as / fr_dis | .fr↔.frb 互转 | `-o` |
| fr_assets | 流抽资产 kit / 从文件建 kit | `-o` `--from-files` |
| fr_prec | :px↔:full 精度档转换 | |
| fr_delta_check | 增量流对拍（Tier1 展开 etc.） | |
| fr_diff | 两流帧对齐 diff（首分歧帧+行级差异） | `--frames a-b` `--first-only` |

## 9. MCP 工具面（agent 直调）

以上工具已包成 MCP 服务（`tools/fr_mcp.py`，零依赖 stdio JSON-RPC；工作区 `.mcp.json` 已注册
`fr-tools`）——agent 不必 shell 拼命令，直接工具调用：

| MCP 工具 | 底层 | 备注 |
|---|---|---|
| `fr_record` | love.exe + FR_CAPTURE env | sha 自动算；headless 确定性录制 |
| `fr_read` | fr_dump | frames 选帧视图；响应封顶 100KB |
| `fr_grep` | fr_dump + 行过滤 | 帧头上下文保留——"哪些帧画了 X" |
| `fr_check` | fr_check | 判据文件路径或仅内置校验 |
| `fr_stats` | fr_stats | 四层剖面 |
| `fr_diff` | fr_diff | 首分歧帧（bisect 语义）+ 行 diff |

设计约束（fr-rationale §五）：只流通文本与数字（行/矩形/CRC/计数），不流通图像字节；工具
无状态，状态全在流与判据文件里。
