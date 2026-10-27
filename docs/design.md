# FR 工具链总体设计（总纲）

> 本文件是整个项目的**总纲入口**：把分散在四份真源里的决定串成一条完整架构叙事。它不取代任何真源——修订仍按"改真源 + 台账记录"的规矩走，本文件只在架构变化时同步。读者：未来的 AI 会话、新加入的人、复盘的自己。读完应能回答：系统是什么、一帧怎么流、模块边界在哪、怎么验证、接下来建什么。

## 0. 读者地图

| 你想… | 去哪 | 性质 |
|---|---|---|
| 通读架构、入门 | 本文 | 总纲（叙事） |
| 查/改流格式（段、行型、级别、语法） | `docs/fr-spec.md` | 格式真源（v1.2 封版） |
| 查/改命令签名与来源行号 | `tables/cmd.tbl` | 命令单一真源（生成源） |
| 追架构依据、修决策 | `docs/decisions.md` | 决策台账 D1–D10（追加式） |
| 查魔改实现细节（挂点/源码行号/开放清单） | `docs/love2d-gap.md` | 魔改设计与取证 |
| 查渲染端设计与流载体 | `docs/love2d-renderer.md` | 消费端设计 |

修订纪律：改格式 = 改 fr-spec + 其 §13 记一行；改决策 = decisions 追加新条目注明取代；改命令 = 改 cmd.tbl 重新生成；改魔改 = gap 文档 + 必要时决策条目。本文件随之同步，**不自行另立决定**。

## 1. 全景

一句话：把"内核怎么想、画面怎么画"编成一种**语义唯一、双形态编码、可 diff 可判据**的帧流（FR, Frame Record；文本 `.fr` / 二进制 `.frb`），宿主是魔改 LÖVE 11.5——Lua 内核脚本产出 FR 流，引擎内 C 层捕获与回放。对应 LLVM IR 之于编译器：FR 是内核世界与渲染世界之间的两界契约；未来任何前端（逆向移植、AI 生成内核）自带 lowering，不进本仓库。

五个关键词：

1. **双形态**：`.fr` 给人 / `.frb` 给机器，fr-as / fr-dis 互转，round-trip 逐字节相等进回归。
2. **帧五段**：head / in / log / out / end——输入事实、内核自述、决定清单、校验和各居其位。
3. **单流双消费**：屏幕与文件消费同一份字节（tee）——"视觉真源 = IR"是构造结果，不是纪律口号。
4. **树不进协议**：结构在内核端结算成绝对坐标，协议只收扁平行；树可作被引用的内容（资产），不可作执行上下文。
5. **符号结算**：一切验证落在"符号比较（锚行）"或"字节相等"上；没有人理解像素，只有脚本计算像素。

## 2. 一帧的一生（数据流主线）

| # | 谁调谁 | 发生什么 | 锚点 |
|---|---|---|---|
| 1 | 内核 Lua → C | `love.graphics.draw(tex, x, y)` 过 w_* 边界——**全程唯一跨语言点** | wrap_Graphics.cpp:2332 |
| 2 | 捕获层 | 解析资产代理→资产号；C codec 编码 out 行进帧缓冲（fr-gen 生成胶水） | D8-1 |
| 3 | 帧首 | pump 排干队列成快照 → in 段 ev 行（slot=快照序号；含上帧处理中 push 进来的） | sdl/Event.cpp:124/178 |
| 4 | 分发 | handlers 逐条分发=Lua 调用；CALL 行记深度；分发中新 push 落下一帧快照 | 自有 run loop |
| 5 | update | dt 进帧头；rngc（boot 已把 math.random 归一到 love.math，单咽喉） | — |
| 6 | present 前 | （full 级）A 方案堆镜像 diff：脏槽位→st 物理行；**同一次遍历产出 s_crc** | LuaJIT g->gc.root |
| 7 | present | 封帧：end 段补 s_crc/d_crc，帧定稿为字节块 | — |
| 8 | tee | tee₁→`.frb` 文件追加（录制开关）；tee₂→C 回放器**同进程直调** | — |
| 9 | 回放器 | 同一份 codec 解码→逐行分发；draw 行→资产号首次引用物化（uploadImageData）→ Graphics::draw → OpenGL | Image.h:115 |
| 10 | swap | 屏幕更新，present 返回，下一帧开始 | — |

要点：内核对流零感知（只见 Lua API）；编码/封帧/落盘/回放全在 C；present 是唯一同步点（无积压）；跨进程 = 同一字节流按 `[len][bytes]` 分块 + session header 先行（拓扑 B/C 见 §4 机制卡·流载体）。

## 3. 三张横切剖视

### 3.1 多 VM 分配（cloudwu 先例：VM 开销极低，调试/观察代码与宿主分离）

| 层 | 住处 | 职责 |
|---|---|---|
| 内核 VM | 主 lua_State | 游戏内核脚本——**唯一进堆镜像范围的状态** |
| 观察 VM | 第二 lua_State | 事件合成器、登记表维护、fr-trace 审计、工具面——与内核不共堆 |
| C 层 | 无 VM | 捕获、diff、回放器、编解码 |

纪律：观察机器绝不落进被观测的堆；run loop 住主 VM 但属框架代码，内核不得 require。

### 3.2 验证体系

- **符号层 = 日常**：高频锚行 diff 查逻辑（fr-diff / fr-check）。
- **像素层 = 终审**：低频、同机档、定长资产字节相等；D10 确定性旋钮（mipmap 禁用或 CPU 生成、sRGB/linear header 定死）保住其可用性。
- **round-trip**：`.fr`↔`.frb` 逐字节相等、CMNT 保留——压编码漂移。
- **优化验证三层协议**（D10-4，适用于渲染端任何 GPU 改写）：① out 段符号流逐字节不变 ② 同机档截图字节相等 ③ 旁车统计无漂移。边界的意义是解放优化。
- **红线**：GPU 产出的 hash/统计不进校验和；墙钟只进 CMNT；级别不进校验和。

### 3.3 确定性模型

- 事件全序 = 单线程 run loop + present 唯一边界；三源（OS / 合成 / 自定义）统一入队，事件=进队的东西，直接函数调用=CALL 行不是事件。
- dt 进帧头，回放喂记录值；内核禁读墙钟（lint：`love.timer.getTime` / `os.clock` / `os.time`）。
- RNG 单咽喉：boot 层 `math.random`→`love.math`，rngc 白送。
- 输入禁直读：`mouse.getPosition` / `isScancodeDown` 等改为读 in 段派生快照——输入只有一条进账的路。
- 错误帧：err 行 + 照常闭合 + s_crc 照算；回放必须复现同错。
- 回放注入默认严格档：只注入 OS 源事件，合成器重算、流内记录的合成事件当对拍预言。

## 4. 机制卡（职责 / 接口 / 依赖 / 真源指针）

| 卡 | 职责与要点 | 真源 |
|---|---|---|
| 捕获层 | w_* 边界栈拷贝→按 cmd.tbl 的 section 列路由 in/log/out；fr-gen 生成胶水，零手写；对象参数只记资产号 | D8-1、gap §一 |
| 资产语义替代 | 13 项 GL 依赖创建 API **原名原签名**、实现换成 CPU 注册（校验实参→登记 asset 行→返回资产代理）；newQuad 纯数据绕开；原料层=love.image / love.font；无 IR 对应者暂记 err 行，按频度增补 | D8-5、gap §七.3 附件 |
| 事件层 | pump / w_push 捕获；排干快照再分发（poll 中途 push 的落帧问题被构造性消灭）；slot / CALL 深度 / timer 归一（update 结算产生）；注入两档 | spec §8、gap §三 |
| 自有 run loop | 替换 callbacks.lua:135 的 love.run；帧=事务、present=commit；内核协程由 update 驱动，分发不跨帧 yield | gap §三 |
| log A 方案（主力） | LuaJIT gc.root 全对象链 + 影子副本 TValue memcmp→脏槽位出 st 物理行，同次遍历产 s_crc；rehash 检出→表重建事件（整表重发，checkpoint 同语义）；full 级专用，off/base 不碰堆 | D9-4、gap §四 |
| log B 方案（二批） | TSET 字节码 handler + trace store IR 插桩，O(变动数) 真 WAL；A 的 profiling 证明超帧预算才启动 | gap §四 |
| 登记表与逻辑解码 | 对象→路径映射；登记项=(指针, epoch, 首现帧, 末见帧) 防 GC 指针复用；checkpoint 全量重推校正；消费端 fr-dis 解析成路径文本（DWARF 同构；debugvar.h 路径描述符与键池先例） | gap §四、refs/luadebug |
| fr-gen | cmd.tbl → C（编进引擎）+ Python（工具族）双目标；sha256 指纹写 session header；生成代码不手改；双目标已落（B0：Python 全功能编解码、C API 面+口径常量锚+extern C；**字段级 emit 已实现（B3a）**——类型化签名 + fr_selftest 期望字节嵌入，本地 mingw i686 与 gyl x86_64 跨目标字节回归双通过） | spec §9 |
| 流载体 | 拓扑 A（默认）：C 帧缓冲 + tee，present 同步回放；拓扑 B：`.frb` 文件（离线）或 socket `[len][bytes]`（在线）；拓扑 C：无头录制只 tee₁（null Graphics）。跨进程协议细节随 fr-gen。跨进程线上协议 = FRB1 会话流（B1 封版）的逐块读取。 | renderer 文档 |
| 相机（结算器） | 相机 = 内核状态（st/checkpoint）+ 结算参数，协议零新增；多相机/视口 = rt + scissor + canvas 资产 + draw 合成（行序即 depth）；shim 变换栈就地结算；判据 = 世界层不变性；观战自由视角/双流归 v2 显式演进 | D11 |
| 回放器 | C 解码→Graphics::draw 系（与 w_draw 同入口）；物化=资产号首次引用时 uploadImageData；mipmap/sRGB 按 D10 旋钮 | renderer 文档 |

## 5. 工具族地图

| 工具 | 输入→输出 | 一句话 |
|---|---|---|
| fr-gen | cmd.tbl → C/Python codec | 表到编解码的生成器 |
| fr-as / fr-dis | .fr ↔ .frb | 互转（round-trip 回归的执行者） |
| fr-dump | .fr/.frb → 可读 dump | 锚行判据的素材 |
| fr-check | 流 + 判据脚本 → 通过/失败 | FileCheck 式判据运行器 |
| fr-run | .frb → 回放驱动（注入 in、比对 end） | 回放即测试 |
| fr-diff | 两流 → 锚行级差异 | 日常回归主力 |
| fr-bisect | 两流 → 首分歧帧 | bugpoint 式二分 |
| fr-xor | 流 → 逐帧增量摘要 | 漂移观测 |
| fr-assets | 流 → 资产抽取与 sha 校验 | 资产侧对拍 |
| fr-render | 流 → 图像 / `--diff` 差异报告（符号接口：矩形/计数/hash） | 像素层终审与视觉 diff |
| fr-stats | 流 → 命令频度/结构统计 | 频度表与实收证据 |
| fr-trace（可选） | 运行期 → rngc 覆盖率等审计 | debug 栈钩唯一合法用途 |

## 6. 实施路线（中粒度；任务清单留给实施计划阶段）

| 批 | 范围 | 验收线（判据形式） |
|---|---|---|
| B0 | cmd.tbl 终表（首版频度 = love-src/testing 调用统计）+ fr-gen C/Python 双目标 | 生成代码可编译、可导入；同表 sha256 指纹可复现 ✅ 已完成（2026-10-27，cb7058e→13690a6：表终表化、双目标生成器、零漂移守卫、跨目标常量锚；28 passed + 1 skipped，gyl gcc -Werror 编译通过） |
| B1 | round-trip 回归（pytest 进仓）；帧/会话封装布局、asset 文本规范形（C 字段级 emit 顺延 B3） | `.fr`→`.frb`→`.fr` 逐字节相等（含 CMNT、err 行） ✅ 已完成（2026-10-27：会话封装封版、CMNT/err 行入回归，golden+生成式双向） |
| B2 | fr-as / fr-dis / fr-dump / fr-check 最小面 | 样例流 dump 锚行可 grep；判据脚本通过 ✅ fr-as/fr-dis 已交付（2026-10-27）；fr-dump/fr-check 移至 B3 批次 |
| B3a | 工具面补全：fr-dump（双输入 canonical dump + stats/选帧）、fr-check（canonical 幂等/sha 对账内置 + FileCheck 式判据）；C 字段级 emit（B0 顺延清偿） | dump 双输入逐字节一致；fr-check 判据全过；gyl 跨目标 `C EMIT OK 24 rows` ✅ 已完成（2026-10-27，mingw i686 与 gyl x86_64 双平台字节回归） |
| B3b | L0 纯 Lua 产流：代理 shim + 排干快照 run loop + 状态走查器（st 语义样机） | 产出五段齐全会话文件；fr-dis 可读；fr-check 通过 ✅ 已完成（2026-10-27：L0 产流五段齐全会话，fr-check 过，golden 固化） |
| B4-1 | **阶段一（已完成 2026-10-27）**：构建链探针（结论=MSVC+megasource 官方路线本机直接可行，工具链零安装，仅差 megasource clone——docs/build-probe.md）+ C 行解码/会话层（fr_dec_* 生成 + fr_session.h/.c 手写，golden 解码-重编码闭环双架构） | 见 docs/build-probe.md `PROBE: PASS`；C DECODE OK（golden 闭环三重锚定）✅ |
| B4-2 | L1 魔改首批（阶段二，前置=clone megasource + 首次 fork 全量构建）：捕获接入 + 资产语义替代四件套（newImage/newCanvas/newFont/newQuad）+ C 回放器 + null Graphics + 自有 run loop 替换 love.run | capture-then-replay 首帧上屏；同流文件经拓扑 B 离线回放与同进程屏幕 d_crc 一致 |
| B5 | 事件注入回放（严格档） | 同一 `.frb` 重放 N 次 s_crc/d_crc 全一致；合成事件对拍零失配 |
| B6 | log A 方案：堆镜像 diff + 登记表 + checkpoint | s_crc 跨运行稳定；st 行噪声实测可控（rehash→表重建事件） |
| B7+ | 按数据排队：B 方案写拦截（profiling 触发）、socket 拓扑、fr-render --diff、fr-bisect、设备端瘦客户端 | 届时随批定 |

排序依据：先钉死格式与编解码（B0–B2 是一切判据的地基），再产真流（B3），再上引擎（B4–B5），最后观测深度（B6+）。每批收尾自查：**是否新造了影响别处的耦合**——是则当场做掉。

## 7. 开放问题与未来工作

- 首版实收频度：love-src/testing 调用统计（spec §12-1）。
- printf / points 多色 / SpriteBatch / Mesh / Shader：按实验内核频度增补（err 行占位）。
- 观察 VM SDK 面与 fr-trace 审计工具。
- B 方案触发条件：等 A 方案 profiling 数据。
- socket 拓扑背压：传输层关切（Wayland 先例），不进语义。
- fr-render --diff 的 GPU 后端：接口先按符号定，后端 CPU 先行。
- 设备端瘦客户端：第二个渲染端，双端异构对拍（LLVM 多后端互证）。

## 8. 术语表

| 术语 | 义 |
|---|---|
| 帧五段 | head / in / log / out / end |
| 资产代理 | 语义替代实现返回的、包着 u32 资产号的 userdata |
| 物化 | 渲染端按资产号把 CPU 字节上传成 GPU 纹理（uploadImageData） |
| 影子副本 | A 方案在 C 侧保存的上一帧堆快照，memcmp 出脏槽位 |
| 登记表 | 对象→路径映射；epoch + 首末帧防 GC 指针复用；随 checkpoint 重发 |
| 逻辑解码 | 消费端把物理记录解析成路径化文本（DWARF 同构） |
| 表重建事件 | rehash 检出后整表重发的 st 形态（checkpoint 同语义） |
| tee | present 封帧后字节块的同源分岔（文件 / 回放 / 网络） |
| 单流双消费 | 屏幕与文件消费同一份字节 |
| 严格档注入 | 回放只注入 OS 源事件、合成器重算对拍 |
| 原料层 | 内核可直用的 CPU 侧创建面（love.image / love.font / love.math / love.filesystem） |
