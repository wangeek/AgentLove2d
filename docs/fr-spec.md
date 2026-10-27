# FR 帧流 IR 规格 v1.2（封版）

> 本文件是 FR 规格的真源。v1.0/v1.1 定稿于 2026-10-26 会话 `mvs_cd9c483f96484e5ca5464281bed0e47a`；v1.2 同日修订（见 §13）。此后修订直接改本文件，并在 §13 版本记录追加一行。
>
> 状态标记约定：
> - 〔封版〕= 已拍板，不得擅改
> - 〔定稿中〕= 语义已定，行级/字节级语法由 fr-gen 首版落定
> - 〔待取证〕= 需要证据后才能定

## 0. 定位

FR（Frame Record，帧流）是**游戏内核与渲染端之间的中间表示**，地位对应 LLVM IR 之于编译器：

- 生产者：**魔改 LÖVE 11.5 内核模式下的 Lua 内核脚本**（捕获与回放机制见 `docs/love2d-gap.md`）
- 消费者：引擎内 C 回放器、fr-* 工具族、纯 Lua 契约证人
- 未来任何其它前端（逆向移植体、AI 生成内核等）**自带各自的 lowering 规则**，其映射表住在各自仓库，不进本仓库
- 它不是渲染 API，不是日志格式，不是存档格式——它是**两界契约**：语义唯一、编码两种、每步可观察、判据锚定关键行

## 1. 总则（LLVM IR 模式）

1. **双形态**：文本 `.fr` 给人，二进制 `.frb` 给机器；`fr-as` / `fr-dis` 一键互转；互转本身进回归（round-trip 逐字节相等）。
2. **每步可 dump**：每个变换阶段后可落 dump，diff 相邻阶段定位 bug。
3. **判据锚行不锚全文**：锚关键行，判据不含不稳定成分。
4. **命令表 = 单一真源数据**：`tables/cmd.tbl` 是数据，两端编解码代码从表生成，不许手写编解码。

适用边界：中间物是长期契约 + 要长期回归 + 两端异构才值得；一次性中间数据不套。

## 2. 语境纪律〔封版〕

- IR 词汇表 = **现代语义**：f32 坐标（文本 `%.6f` 定长）、RGBA8、TTF 字体字节+光栅化、HID scancode、UTF-8；锁 IEEE。
- **legacy 方言（GDI / `WM_*` / `VK_*` / 调色板 / 点阵）不进本仓库**——本仓库的宿主是 LÖVE，它的事件名、像素格式、字体管线就是 IR 的普通话。某前端要兼容老环境，映射表是它的私事。
- 调色板类需求在现代管线里是内核/渲染端资产（shader 或像素预处理）的事，不是 IR 命令。
- 自检口诀：动笔先问"这个词是普通话还是方言"。

## 3. 对象模型（session = ELF 的形状）

```
session = header + assets[] + frames[]
header  = 魔数、版本、几何(宽高，会话内固定)、cmd.tbl 指纹(sha256)、loglvl、seed(RNG 初值)
assets  = 编号资产登记：id、种类、载荷或引用
frames  = 帧包序列（frame 0 = checkpoint 基线，见 §4）
```

- **cmd.tbl 指纹进文件头**：表一变，旧流文件立刻报错，绝不静默错解。
- 资产种类与载荷：`image`（RGBA8 字节 + 宽高）／`canvas`（宽高）／`quad`（x,y,w,h + 总宽总高，纯几何）／`font`（字体文件字节 + 字号）。资产号 = fr 注册序号，与内核代码中的变量名无关。
- 资产在流内注册（`asset` 行，head 段），支持运行中加载；frame 0 checkpoint 全量重发。

## 4. 帧结构：五段

一帧 = `head / in / log / out / end`。

| 段 | 语义 | 关键规则 |
|---|---|---|
| head | 帧头 | 帧号；`dt`（回放喂记录值）；`asset` 注册行；checkpoint 行（frame 0） |
| in | **事实**（事件），可重放 | slot = 同帧取号序号；行型 ev / call / timer |
| log | **内核自述** | 三档级别（§5）；行型 rngc / st / err |
| out | **决定清单**（渲染端执行） | 全量无增量；有序流；坐标已结算为绝对坐标 |
| end | 校验 | s_crc（状态快照）+ d_crc（out 记录），CRC32 |

通用规则〔封版，v1.2 并入〕：

- 时间坐标 = 帧号 + 时隙；**墙钟只进 CMNT 注释**；内核禁读墙钟（lint：`love.timer.getTime` / `os.clock` / `os.time`）。
- **dt 进帧头**：它是墙钟派生的状态输入，回放必须喂记录值。
- **frame 0 = checkpoint 基线**：全量资产表 + 登记表 + 状态镜像，此后增量。
- **错误帧语义**：handler 中途出错——错误也是事实：err 行记录、各段照常闭合、s_crc 照算；回放必须复现同错。
- **loglvl 会话内不可变**（per-session 定死，切换 = 重开）。
- **几何会话内固定**（header 声明后不可变；resize 只作事件记录，不改变流几何）。
- 级别不进校验和。
- err 行豁免于 off 级——忠实性事实不可关。
- 读取侧筛选不进格式：文本 grep 或工具 `--filter` 参数；生产端全量，与 out 段"全量无增量"同一原则。

## 5. log 段级别：纯三档〔封版〕

| 级 | 内容 | 用途 |
|---|---|---|
| off | 全关（err 豁免仍记） | 生产 / 游玩 |
| base | + rngc | **录制默认** |
| full | + st 全字段 | 调试 |

## 6. 双形态与文本语法

- 文本 `.fr` / 二进制 `.frb`，round-trip **逐字节相等**；CMNT 行保注释不丢。
- 行级字节/文本编码已随 fr-gen 首版封版（§6.1，B0）；变长编码、字符串池/键池不进行级 v1（定宽编码 + 内联 str）；帧级/会话级封装已封版（§6.3，见 §13 v1.2.2）。
- 行级文本语法**示意稿**（非封版，示意语义用；**示意稿已由实测形态取代，见 §6.1/§6.2**）：

```
cmnt demo session
frame 0
  checkpoint assets=4 registry=full state=full
frame 1
  dt 0.016667
  in
    ev 0 keypressed return return false src=0
    ev 1 mousepressed 203.000000 88.000000 1 false 1 src=0
    call 2 hit 203.000000 88.000000 depth=1
  log
    rngc 0x77c1ee
    st 7 hp 84
  out
    clear 0 0 0 255
    draw 1 3 34.000000 56.000000 0.000000 1.000000 1.000000 0.000000 0.000000 255 255 255 255
    print 2 "HELLO" 12.000000 340.000000 0.000000 1.000000 1.000000 255 255 0 255
  end
  s_crc 0x9c27f41b d_crc 0x51e0aa93
```

### 6.1 行级编码〔封版〕

- 数值域：所有 f32/f64 写入前量化到 %.6f 语义域（`qf`）；NaN/Inf 拒收；±0.0 位型互异保留（-0.000000 / 0.000000）
- 二进制（小端）：u8/u32 整数；f32/f64 IEEE；rgba8=r,g,b,a 四字节；str=u32 字节数+UTF-8（二进制侧容纳任意 UTF-8 字节，含控制字符）；f32[]=u32 点数 n+n×2 个 f32；variant=u8 tag+载荷（命名常量 `VARIANT_TAG_NUM/STR/BOOL = 1/2/3`；num 载荷 f64 量化、str 同 str 规则、bool 载荷 f64 0/1）；args...=u8 argc+argc×variant；opcode=u8=cmd.tbl 数据行序（0x00 起）；结构行保留 0xFF=CMNT
- asset 行 payload 按 kind 分支（命名常量 `ASSET_KIND_IMAGE/CANVAS/QUAD/FONT = 0/1/2/3`）：image={u32 w, u32 h, u32 len, 字节}；canvas={u32 w, u32 h}；quad={6×f32}；font={f32 size, u32 len, 字节}
- 解码侧错误族：截断/残尾类 ValueError 含 op 名与偏移（`op X 在 off Y 截断` / `X 行尾冗余字节`）；语义类（非法 tag/kind、非法转义等）ValueError 原样透传（信息含肇事值，不带 op 上下文）
- **文本 canonical〔封版〕**：LF 行尾、无行尾空白、行=空格分隔 token；f32/f64 恒 %.6f；整数十进制；rgba8 四整数；str=双引号包裹，转义集 `\\ \" \n \r \t`，**其余 C0（U+0000–U+001F）与 U+2028/U+2029 在文本 render 侧拒收**（行完整性——splitlines 也切 U+2028）；二进制侧不拒（行完整性仅文本侧约束）；variant 文本形态 `num <%.6f>` / `str "<quoted>"` / `bool 0|1`；args...=argc 十进制+argc 个 variant token
- 指纹 = sha256(规范表)：数据行 `op\tsection\tsignature` 逐行 join("\n")+"\n"（UTF-8），忽略 source/status/notes——改注释与备注不破指纹
- 帧级与会话级封装：**已随 B1 封版（§6.3）**；asset 行文本规范形同见 §6.3（B0 期的 NotImplementedError 占位已由 B1 实现取代）

### 6.2 实测样例行

引自 `tools/fr_codec_gen.py` 的 render 实测输出，替代旧示意稿。注意 ev/call 的 src/depth 字段在 args **前**（旧示意稿"src=/depth= 后缀"写法已废）：

```
dt 0.016667
ev 0 "keypressed" 0 2 str "return" bool 0
call 1 "hit" 1 2 num 203.000000 num 88.000000
st 7 "hp" num 84.000000
draw 1 3 34.000000 56.000000 0.000000 -1.000000 1.000000 0.000000 0.000000 255 255 0 255
print 2 "HELLO" 12.000000 340.000000 0.000000 1.000000 1.000000 255 255 0 255
```

### 6.3 会话封装〔封版〕

- 二进制 `.frb`（小端）：header 50B = magic `"FRB1"`(4B) + version u8=1 + width u16 + height u16 + sha 32B（cmd.tbl 规范表 sha256 原始摘要）+ loglvl u8（0=off 1=base 2=full）+ seed u64；其后 entries 重复至 EOF：tag u8——`0x01` frame（u32 body_len + body，body 为 rows 逐条、各以 opcode 起始，0xFF 禁入帧内）、`0xFF` cmnt（str，禁 \r \n）；其它 tag 非法。**帧号由顺序隐含**（从 0 连续计数，文本侧显式校验）。
- 文本 `.fr`（canonical）：首行 `frb1 <w> <h> <sha64hex小写> <off|base|full> <seed十进制>`；`cmnt <原文>`（"cmnt " 之后逐字保留；可在任意两帧之间）；`frame <n>`（n 连续，行即帧界——cmnt 行亦闭合帧块）；row 行位于 frame 块内。
- asset 行文本规范形：kind 用名字（`asset image <id> <w> <h> <hex>` / `asset canvas <id> <w> <h>` / `asset quad <id> <6×%.6f>` / `asset font <id> <size%.6f> <hex>`；hex 小写连续、空载荷 `-`）；二进制侧 kind 用编号常量（§6.1）。
- 错误口径：文本侧 SessionError 含行号；二进制侧含偏移；行级错误包装透传（含肇事值）；dump 侧对非法 Session 结构以 SessionError 拒绝（共享校验，双出口一致）。
- 实现分层：行级编解码为表生成（§6.1/§9）；**会话层是结构性行（CMNT/帧定界不随 cmd.tbl 变化），手写库 `tools/fr_session.py`**，不参与重生成——这是"生成代码不手改"纪律的明确边界。
- decode 无 cursor 变体的务实解（帧内行长用重编码长度推进）与升级路径见 `tools/fr_session.py` docstring。

## 7. 命令集〔v1.2 对照 LÖVE 11.5 源码定稿〕

真源 = `tables/cmd.tbl`（签名/来源行号/状态见彼处）。摘要：

- **head**：`dt`、`asset`
- **in**：`ev`（签名=love.event.push 参数序，src 标记 OS/合成/自定义）、`call`（同步直调，深度）、`timer`
- **log**：`rngc`、`st`（物理 records，消费端逻辑解码）、`err`
- **out**：`clear` `draw` `print` `rect` `line` `poly` `circle` `arc` `points` `rt`（setCanvas 对应）`scissor`
- **end**：`s_crc` `d_crc`

设计纪律的落点：color/setColor 折进行参数（行自描述）；翻转=sx/sy 负值；canvas 间合成= `draw` 引用 canvas 资产；`rt`/`scissor` 为有序流上的状态行（对齐 love 的 setCanvas/setScissor）。

## 8. 事件词汇表

- 事件名**直接采用 LÖVE handlers 键名**：`keypressed`、`keyreleased`、`textinput`、`mousepressed`、`mousereleased`、`mousemoved`、`wheelmoved`、`focus`、`visible`、`resize`、`quit`、`filedropped`、`threaderror`……
- **EV 签名 = `love.event.push` 参数序**，零翻译。事件名是 payload 数据：EV 只有一个 opcode；词汇表照抄 handlers 全集（fr-gen 一并生成），**实收清单由宿主测试套件与实验内核的频度决定**〔待取证〕。
- `call` = handler 内直接调用（栈帧增长）；`ev`/push = 队尾追加。分发中 push 落下一帧快照（自有 run loop 构造性定义，不依赖宿主实现细节）。
- `timer` 归一：宿主无定时器事件，定时 = `update(dt)` 结算时产生合成事件。
- **回放注入两档**〔封版：严格为默认〕：严格 = 只注入 OS 源事件，合成器照常重算，流内记录的合成事件当对拍预言（fr-check 校验）；快速 = 全量注入跳过合成。

## 9. cmd.tbl 单一真源与 fr-gen

- `tables/cmd.tbl`：op / 段 / 签名 / 来源（宿主 API + 源码行号）/ 状态 / 约束。
- `fr-gen` 从表生成 **C（编进引擎）+ Python（工具族）** 两份编解码；生成代码不手改，改表重新生成。
- 指纹写进 session header（§3）。

## 10. 工具族

`fr-as` / `fr-dis` / `fr-dump` / `fr-check` / `fr-run` / `fr-diff` / `fr-bisect` / `fr-gen` / `fr-xor` / `fr-assets` / `fr-render` / `fr-stats`

- 工具命名纪律：不与现成 shell 命令撞语义。

## 11. LÖVE 宿主机制

捕获/回放/事件编排/log 机制（堆镜像 diff、多 VM 分配）见 `docs/love2d-gap.md`；消费端设计见 `docs/love2d-renderer.md`。

## 12. 取证清单

1. **首版实收频度**：love-src/testing 测试套件的绘制调用统计 → cmd.tbl 实收顺序与优先级（第一个"原版"就是宿主自己的测试）。**已取证**（2026-10-27，数字在 cmd.tbl notes，取证源与复现命令固化在表头注释）；printf（freq=4）已取证，收录判定见 §13 v1.2.2。
2. `printf`（含 wrap/align）、`points` 多色、`SpriteBatch` / `Mesh` / Shader 的收录时机——按实验内核实收频度增删。
3. **无头资产创建 API 面**（ImageData 注册 + live 物化）——**已定案**：语义替代方案（D8-5，同名原签名、CPU 注册实现），非取证项（见 love2d-gap.md §七.3）。
4. A 方案"表重建事件"（rehash → 整表重发）的实现细节与 st 行噪声实测。

## 13. 版本记录

- **v1.0**（2026-10-26，会话内）：初稿。五段之第三段名 `proc`；full 级含模块分类。
- **v1.1**（2026-10-26，封版）：`proc` → `log`；级别收敛纯三档，去生产端模块分类；err 行豁免于 off 级；读取侧筛选不进格式。
- **v1.2**（2026-10-26，修订）：**sango/GDI 遗产彻底剥离**（gdi_map.tsv 退役删除；lowering 归未来前端私仓）；**命令集对照 LÖVE 11.5 源码重定**（spr/txt/fill/blt/lut/loop/rng 退役；新增 clear/draw/print/rect/line/poly/circle/arc/points/rt/scissor/dt/asset）；并入口径：dt 进帧头、frame 0=checkpoint、错误帧语义、loglvl 会话内不可变、几何固定、回放注入默认严格档、math.random boot 归一 love.math、内核禁直读输入状态。频度准则的"原版"改指宿主：首版 = love-src/testing 调用统计。
- **v1.2.1**（2026-10-27，B0）：行级字节/文本编码随 fr-gen 首版封版（%.6f 量化域、小端、opcode=表行序、0xFF=CMNT、variant/asset 口径常量命名锚、文本转义集含 \r 且 C0/U+2028/2029 文本侧拒收、指纹=规范表 sha256）；帧级/会话级封装与 asset 文本规范形归 B1。频度取证完成（源=origin/main:testing/tests，11.5 tag 无 testing 目录），数字入 cmd.tbl notes；printf freq=4 已取证、收录判定随 B1 实收复核。
- **v1.2.2**（2026-10-27，B1）：会话级封装封版（§6.3：FRB1 头 50B、entry tag 0x01 帧/0xFF cmnt、帧号隐含连续、asset 文本规范形 kind 名字+hex 载荷、dump 侧共享校验）；fr-as/fr-dis 交付；round-trip 双向回归进仓（golden + 生成式）。printf 复核：print freq=8 ≥ printf freq=4，v1 不单列 printf（后续按实收再议）。
- **v1.2.3**（2026-10-27，B3b）：L0 语义样机口径登记——st 行 obj=0+点路径（语义形态，B6 A 方案替换为物理 obj id）、s_crc/d_crc=B3b 期为状态序列化 CRC32（样机，B6 换堆遍历）；L0 只产 .fr 文本（.frb 经 fr-as 转换）。
- **v1.2.4**（2026-10-28，B6 实现形态登记，不改封版语义）：s_crc 物理形态=注册状态根子图 CRC（D8 修订：镜像范围为内核状态非 runtime 簿记；GC64 canonicalization+hash multiset 免疫字符串哈希随机种子）；st 物理行落地（数组 slot `[i]`=键原值 0 基、hash slot `"key"`、nil 槽不产行）；表重建经 err 载体 `err "st-rehash <id> <asize> <hmask>"`（err 行"表重建计数"语义位）；FR_LOGLEVEL=full 按需触发。**欠账登记**：end 段 d_crc 行未随 B6 兑现（无头哨兵口径待定）——B7 首批清偿；s_crc 对 str 内容仍 tag 位（diff 档已补内容 CRC，s_crc 统一归 B7+）。
- **v1.2.5**（2026-10-28，B7a 清偿 v1.2.4 两笔欠账，不改封版语义）：d_crc 进流兑现（end 段双行完整——录制侧当帧 out 行 CRC32，C 算法单一真源，无头可用；与回放侧像素 D_CRC 互补不混同）；canonicalization 单一化（s_crc str 敏感——tag|(len+内容)CRC32 共享函数，diff 档旁路归一，banner-only 等长同 tag 差异已可检出）。
