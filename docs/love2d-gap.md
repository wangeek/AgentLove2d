# LÖVE 魔改 × FR：结合现有条件的设计与差距分析（v2）

> 前提修正（2026-10-26 用户纠偏）：**本项目先建 FR 工具链，载体是魔改 LÖVE**——内核是跑在 LÖVE Lua VM 上的脚本（借鉴它用 Lua），捕获/消费/记录都长在引擎里；sango 是将来的 lowering 前端之一，与本项目解耦。v1（外部消费者前提）的 G2/G3/G4 结论作废，本文重写；v1 的 G0（版本对齐）与 GUI 子系统事实仍成立，移入附录。
>
> 取证基线：`love2d/love-src` 官方 11.5 tag（`6eb8d54`）。

## 一、FR 结合 LÖVE 现有条件的六个挂点

| 现有条件 | 事实（源码） | FR 挂进去的方式 |
|---|---|---|
| Lua VM + `love.*` API | 内核脚本对引擎的一切操作都过 C 包装边界（`w_*` 函数族） | **捕获层挂在这里**：栈上实参拷贝成记录，按 cmd.tbl 的 section 列路由进 in/log/out |
| Graphics/OpenGL 栈 | `w_draw` 检查参数后直调 `instance()->draw(texture, quad, m)`（wrap_Graphics.cpp:2332/2360） | **回放层直调同一入口**：解码 FR 行→构造 Matrix4→`Graphics::draw` 系，跳过 Lua 边界与脚本防线 |
| 事件模块 | SDL 事件全过 `Event::pump()`（sdl/Event.cpp:124）→`convert()` 造 `Message{name, Variant[]}`（:178，如 :227 `Message("keypressed", vargs)`） | **in 段捕获点**：Message 的形状就是 ev 行的形状，序列化近乎白送 |
| `love.event.push` | `w_push`（wrap_Event.cpp:75）用 `Variant::fromLua`（Variant.cpp:155）拷栈成 Message | Lua 注入的捕获点；回放注入走同队列的 C 侧直推 |
| `love.run` 编排层 | 本体是 Lua 用户代码（callbacks.lua:135；:148 poll→handlers 分发） | **整体替换成 FR run loop**：帧首排干快照→分发→update→present 闭合 |
| LuaJIT（lua51.dll） | FFI 可用；挂 debug hook 时 JIT 基本退解释执行 | 边界捕获与 JIT 无关（纯观察者）；栈钩只配审计工具 |

## 二、绘制层：Lua 还是 C

**结论：生产消费层=引擎内 C；另留一个 Lua 消费者当契约证人。**

1. **回放器用 C 写进引擎**（魔改点）：解码 .frb out 段（fr-gen 生成的 C codec，直接编进引擎构建）→ 直调 `Graphics::draw` 系——与 `w_draw` 调的同一入口（wrap_Graphics.cpp:2360），但不付 Lua marshalling、不做脚本级参数检查（那是给脚本用的防线；回放器信自己解码的行，校验已在 codec/CRC 层）。
2. **架构决定：捕获后回放（capture-then-replay）**〔已拍板并落地——B4-2 里程碑二实证：fr_capture 层 + Canvas 三点回读自证 + tee₁ 会话 fr-check 过（2026-10-27，fork fr-capture@1d340b7）；null Graphics 顺延阶段三拓扑 C〕：内核模式下 `love.graphics.*` **只记录不执行**；`present()` 闭合帧后，回放器消费 out 段上屏。收益：
   - 屏幕上看到的就是 IR 回放——**视觉真源唯一**，直渲与流不可能静默分叉；
   - IR 完备性变成硬约束：漏表达的绘制状态表现为"画不出"，不是悄悄走样——实验床要的正是这种压力；
   - 无头模式=同一管线跳过回放（Graphics 允许 null 后端，魔改点），录制/游玩/对拍共享一套代码路径。
3. **捕获层=lowering**：`setColor`+`draw` 折进自描述行参数（D2 行自描述准则）。love API 是方言（有状态、对象引用），FR 是普通话——这张 `love API→FR` 折算表与 sango 将来的 `gdi_map.tsv` 同构，cmd.tbl 的 source 列登记来源 API。对象参数（Image/Quad）记**已登记资产号**，不拷贝对象（只流通符号）。
4. **资产注册**：`newImage`/`newQuad`/`newFont` 在创建包装处登记（id、sha256、几何），注册表在 C 侧，外部工具可校验。
5. **阶梯**：
   - **L0 纯 Lua 代理 shim**（零魔改）：代理 `love` 表，绘制调用只记不发——先产出合法 .fr 流，验证格式与工具链；
   - **L1 引擎魔改**（真身）：生成的捕获层接入 w_* 边界 + C 回放器 + 自有 run loop + null Graphics 后端。
   - v1 遗留的"codec DLL+FFI 绑定"待拍板项**消解**：无需独立 DLL，codec 编进引擎；fr-gen 两目标 = C（引擎内）+ Python（工具族）。
6. **为什么要留 Lua 消费者**：同一份流被一个不含引擎内部知识的 Lua 程序消费成功 = 契约自证（LLVM 多后端互证的道理）。慢，但它是工具族的一员，不是生产路径。

## 三、事件层：三源统一入队、单线程全序、present 为唯一同步点

**同步的根本保障不是"小心"，是构造**：捕获只发生在主线程的固定点（pump / w_push / 分发循环）；帧边界=present——两次 present 之间捕获的一切行属于同一帧记录，按捕获序落段；单线程 run loop=全序，无竞争。

帧时间线（每一步落进哪段，一目了然）：

```
present(N)：状态遍历→st 行/s_crc；out 段 d_crc；帧 N 闭合 → 写出/回放
帧 N+1：
  ① pump 排干队列成快照      → in 段 ev 行（slot=快照序号；含帧 N 处理中 push 进来的）
  ② 逐条分发（就是 Lua 调用） → CALL 行记深度；处理中 push → 落帧 N+2
                                clear()/混合自由被快照驯服：快照已排干，清不掉已取走的
  ③ update(dt)               → rngc（love.math.random 边界捕获）；dt 进帧头
  ④ draw 调用（任何时候）     → out 段行（捕获于 w_*，只记不发，全序）
present(N+1)：闭合 → 下一段流
```

**三源事件的统一入口=一个队列**，配一条定义：**事件=进队的东西；直接函数调用=代码，不是事件**。

| 源 | 路径 | 捕获点 |
|---|---|---|
| OS 事件（键鼠/焦点/resize…） | SDL → `Event::pump()`（sdl/Event.cpp:124）→ `convert()` 造 Message（:178） | Message 创建处——注意 convert 本身就有合成成分（isrepeat、touch→mouse 折算），捕获在创建点即全覆盖 |
| 组合事件（双击/拖拽/hover…） | 框架层监听 raw → 状态机合成 → `fr.emit` 入队 | 同一队列，w_push 边界 |
| 开发者自定义事件 | `love.event.push` / `fr.emit` | w_push（wrap_Event.cpp:75）；内核直调 handler 允许，但那是 CALL 行，不是事件 |

**"穿越 Lua 调用"的规则**：分发本身就是 Lua 调用（`handlers[name](args)`）。分发过程中——push 新事件=落队尾（下一帧快照取走）；直接调另一个 handler=CALL 行（分发循环记深度）；调 draw=随时可记（捕获层不关心时机，④ 全序吸收）。一条硬规则：**单个事件的分发当帧完成**——内核协程可以有，但其恢复由 update(dt) 驱动（确定性），分发过程不跨帧 yield。

**三个真坑与对策**（"没这么简单"的实处）：

1. **回放双重派发**：若组合事件既被记录、回放时合成器又重算一遍，会双份。注入策略两档：**严格（默认推荐）**——只注入 OS 源事件，合成器照常重算，流内记录的合成事件当**对拍预言**（fr-check 校验）；**快速**——全量注入、跳过合成（测内核不测合成器）。最小输入原则，Quake demo 同法。要求 ev 行带 source 标记（OS / 合成 / 自定义），签名随 fr-gen 定稿。
2. **dt 与墙钟**：dt 是墙钟派生的**状态输入**，不是纯几何——进帧头（head 行），回放喂记录值；内核禁读墙钟（lint：`love.timer.getTime` / `os.clock` / `os.time` 禁入内核）。
3. **worker 线程**：捕获只在主线程；`love.thread` 的产出必须经 Channel 回主线程、以事件形式入队——流的全序不被打破；状态根主线程独占。

注入（回放）实现在 C：直接向队列 push 预构 Message，绕过 Variant 往返，in 段字节精确。事件量小（每帧十数条），性能无关紧要，**完整性与单点**才是要点。

## 四、log：VM 外镜像与写拦截——按 PostgreSQL WAL 的形状做

**先撤回上一版**："帧末 Lua 树遍历 diff"作废。账算错了：10⁴ 叶子过 Lua C API（lua_next+类型判定+定长格式化）每片 0.5–2µs，合计 5–20ms，帧预算 16.6ms 直接击穿；还要求内核把状态挂根下配合。用户方向正确：**镜像与差异分析都在 C 里做，Lua 环境之外的魔法，内核零感知、零纪律**。

对照 PostgreSQL，每个部件各就各位：

| PostgreSQL | FR 侧 | 成本律 |
|---|---|---|
| WAL 记录：物理、LSN 序、先写日志再改页 | **VM 外写捕获**：表写入→物理记录 (对象id, key, 旧值, 新值) 顺序追加进当前帧 log 缓冲 | **O(变动数)**，与状态规模无关 |
| 事务 / commit record | 帧=事务；present=commit；s_crc=commit 校验 | — |
| checkpoint / base backup | 周期性全量状态镜像（低频，消费者不必从零重放） | O(N) 但低频 |
| full-page write（checkpoint 后首脏整页拷贝，后续靠 redo） | **堆镜像 diff（A，主力）**：C 侧影子副本，帧末 memcmp 出脏槽位——PG 也不是纯行拦截 | O(总槽位) 但 memcmp 速度 |
| logical decoding（消费者把物理记录解成行级变更） | 消费端路径解析：登记表（对象→路径）+ fr-dis 解析成 `unit[3].hp=84` | 消费端负担，不进录制路径 |

**两个实现，都在 C、Lua 无感**：

- **A 堆镜像 diff（主力，PG full-page-write 位）**：LuaJIT 全部 GC 对象挂 `g->gc.root` 单链——C 侧沿链遍历，每个 table 的数组部+hash 部与影子副本做 TValue 原始字节 memcmp，脏槽位→物理记录；**同一次遍历顺手对全堆算 CRC32=s_crc**（帧=事务、s_crc=commit 记录，一次遍历两份产物）。10⁵ 槽 ≈ 0.1–0.5ms、10⁶ 槽 ≈ 数 ms——full 级专用；off/base 不碰堆；无需 patch VM 一行。别名、悬挂对象、NaN 位：影子副本按原始字节比对，跨运行确定性由同一 VM+同一代码保证（与 s_crc 同一前提）。
- **B VM 字节码写拦截（真 WAL，O(变动数)，PG redo 位）**：patch LuaJIT 解释器 TSET 系字节码 handler（lj_vm.asm，汇编级）+ JIT trace 的 store IR 下插记录调用；off 级走旁路分支零开销。改动最深——**放第二批**：A 的 profiling 显示帧末 diff 真超帧预算时再上；届时补拉 luajit 子模块取证（浅克隆未含）。

**路径解析（A/B 共通，= logical decoding）**：物理记录只有对象身份，没有语义路径。解法是登记制：某槽位首次出现新表时登记 (指针→路径)，别名多路径取规范路径（首现/最短）；登记表随 checkpoint 周期重发进流；fr-dis / fr-stats 消费端按需解析。录制路径零路径化开销。不可达/未登记对象不入 st，只进 err 计数行——"状态必须可规范化"的要求不变。

**登记表与调试器的同构（DWARF 对照，2026-10-26 补）**。调试器把栈上的指针/变量对回源码命名空间，机制是生产/消费分工：

- 编译器在**编译时**（它还知道名字的最后时刻）用 DWARF 写下：作用域树（subprogram→lexical block→变量，变量带**位置表达式**——"在 rbx""在 rbp-0x18"，优化下还是**位置列表**：不同 PC 区间不同位置）、类型 DIE（struct 成员名+偏移，`rdi+0x18`→`unit->hp` 靠它）、`.debug_line` 行程序（PC↔文件行）、CFI（每条指令处栈帧怎么拆，向上走帧的依据）。
- 调试器运行时：CFI 逐帧上溯 → PC 查 symtab 得函数 → 在作用域树里**从最内层向外**找变量 → 代入寄存器求值位置表达式。**名字是生产时写下的，调试器从不猜**。

逐条对我们的借鉴：

1. **名称生产时记录、消费时惰性解析**——登记表在发现时更新、fr-dis 才解析，与 DWARF 同形；这是正解不是偷懒。
2. **作用域链 = 路径链**——调试器从最内层块向外走，我们从根向叶走；登记表就是堆的作用域表。
3. **映射带生命周期（本条是补洞）**：DWARF 位置列表存在是因为优化器把变量挪窝/内联；我们的同型问题是 **GC 会复用指针**——今天死的表，明天地址被新表占用，裸指针登记会出现**幽灵路径**。对策：登记项=(指针, 代号 epoch, 首现帧, 末见帧)；GC free 处挂失效钩子，checkpoint 时**全量重推一遍路径做校正**（= 调试器模块重载后的 re-symtab）。此项必须进 fr-gen 的登记表数据结构。
4. **Lua 比 C 便宜一半**：Lua 的键是运行时字符串，名字活到运行时——不需要 DWARF 式静态旁路文件；代价是登记表只能是运行时机制。一句话：**DWARF 是编译语言的登记表，我们的登记表是动态语言的 DWARF**（将来 C 内核前端——sango——反而是 DWARF 形状，静态侧文件可用）。
5. **源码侧分析（IDE 的另一半）**的借鉴留作二阶工具：判据/fr-check 里手写的路径可与内核源码的静态路径图对拍（lint"锚了一个从未出现过的路径"）。不进第一批。
6. `.debug_line` 行程序 ↔ 帧/slot 已同构；CFI 上溯 ↔ CALL 深度——我们显式记录深度，比事后重建便宜，因为我们是生产者。

**轻量调试器源码对照（2026-10-26 二轮，refs/ 下留档，思想借鉴、代码抄用前核授权）**。取材两份：`refs/debugger.lua`（slembcke，纯 Lua 单文件，MIT）与 `refs/luadebug`（cloudwu，C 模块 + 双 VM；仓库未见 LICENSE 文件，只借机制不抄码）。

cloudwu 侧（与我们的"VM 外"方向同路）：

1. **双 VM 分离**（remotedebug.c:96-127）：调试器逻辑跑在独立 `luaL_newstate()` 里，宿主 VM 零内存脚印、零代码注入——README 自述"separate debug code from host code"。**借鉴：FR 登记表/影子副本本就在 C 侧；若哪天需要 Lua 写解析逻辑（路径规范化等），放进第二 VM 跑，绝不落进被观测的内核堆**——观察机器不出现在被观测状态里。
2. **路径描述符链 = 登记表的先行实现**（debugvar.h:9-67）：宿主对象不从跨 VM 拷贝，用 `struct value` 数组描述访问链（帧内局部→表键→upvalue→…），`eval_value_` 逐步求值（:104-247）；键值不内嵌，存进 side table 池、结构里只记池号（`new_index`，:357-383）；`show_detail` 把链渲染成文本路径（:637-729）。**这就是我们的物理记录→逻辑解码，且已写好**：st 记录的 (对象， key) 链可采同构结构；键池/字符串池（首现进池、后续引用池号）直接进 frb 二进制格式设计。
3. **hook 事件唤醒独立 VM 协程**（remotedebug.c:188-210 + 222-274 续体链）：宿主 hook 是 C，事件转发 resume 调试协程，协程间 yield 挂起。**借鉴：fr-trace 审计工具的控制面形态。**
4. **显式探针 `debugger.probe()`**（:131-166）：宿主代码主动调用即停，无 hook 常驻成本——**我们 `fr.st`/`fr.err` 显式调用行就是这个形态，验证了设计**。

slembcke 侧（纯 Lua 层的坑与技巧，fr-trace/L0 直接受用）：

5. **栈层级数要与尾调用搏斗**（debugger.lua:38-51、447-448）：`CMD_STACK_LEVEL=6` 精心维持，且 `unpack({...})` 防尾调用消除以保帧序号可预测——**任何在 Lua 里数栈层的代码（含未来 fr-trace）必须防 tail call**；另有 LuaJIT `setlocal` 差一 bug 的 workaround（:50-51、:571-572）。
6. **帧内变量收集的完整顺序**（local_bindings，:115-153）：upvalue 先收、local 同名覆盖、负索引收 vararg、_ENV/getfenv 处理全局——名字遮蔽语义一并解决。**fr-trace 帧快照照抄此序。**
7. **step/next/finish = call/return 事件计数偏移**（hook_factory，:91-107）：call +1 / return −1 / line 比较——**FR 的 CALL 深度追踪同款计数器模式**。
8. **值格式化的防御**（pretty，:6-36）：深度上限、`__tostring` 用 pcall 包裹（会炸，:29-31）、字符串 %q 转储；C/JIT 帧无行号要跳过（frame_has_line，:89）。**L0 走查器与 st 值格式化照此设防。**
9. **协程覆盖是 sethook 类方案的天然短板**：debugger.lua 未处理（sethook 只挂当前线程）；cloudwu 用 `hookmask(coroutine)` 与 `switch` 显式指定（remotedebug.c:277-377）。**这是 B 方案（字节码层拦截）的一个新论据：VM 指令层拦截天然覆盖全部协程，无 per-thread 挂钩遗漏。**

**级别映射（规格三档不变）**：off=不碰堆（游玩零成本）；base=+rngc（仍是边界捕获）；full=跑 A 出 st 物理行。

**旧提案残值**：Lua 侧状态走查只保留为 L0 语义样机（纯 Lua 原型期验证 st 行语义，状态小无所谓），生产路径不采用。

## 五、批次建议

1. cmd.tbl 定稿（source 列补 love API 来源；ev 行加 source 标记）→ fr-gen（C + Python）→ round-trip 回归；
2. L0 纯 Lua：代理 shim 产 out 流 + 状态走查器（L0 语义样机，产 st/s_crc 验证行语义）+ 快照排干式 run loop——产出第一份全段真流，工具族全线吃通；
3. L1 引擎魔改：捕获层生成接入、C 回放器、C 事件注入、null Graphics；
4. （可选）fr-trace 栈钩审计工具。

## 六、拍板状态

已拍板（2026-10-26 用户确认）：① 捕获后回放（视觉真源=IR）；② D8 生效（取代 D6）；③ 项目定位=先建工具链改造创作各类游戏；④ 回放注入默认=严格档；⑤ log=A 主力+B 二批；⑥ §七 开放问题除第 3 条外全部接受（已进 spec v1.2 / cmd.tbl v1.2 / D9）；⑦ sango/GDI 遗产彻底剥离，命令集对照 LÖVE 源码重定。

**待拍板**：无（§七 十条全部定案，最后一条=语义替代方案，2026-10-26）。

## 七、开放问题清单（2026-10-26 全案回顾）

**2026-10-26 拍板：全部十条均已定案**——第 3 条（无头资产 API）定案为**语义替代**：A 类创建 API 保留原名原签名，fork 内实现整体替换为 CPU 侧资产注册（校验实参→登记→返回资产代理），内核代码保持地道 LÖVE 写法；渲染端 = C 解析 FR 流后的 OpenGL 调用（经引擎 Graphics 层）。详见 D8-5 与下方附件。下列各条保留为决策记录。

**会阻断首批实现的：**

1. **输入直读旁路**：内核若在 update 里调 `love.mouse.getPosition` / `isScancodeDown`，输入事实绕过 in 段（直读 SDL 状态不经队列），回放确定性破洞。建议：内核态禁直读（lint），框架把这些 API 换成"读最近 in 段快照"的派生实现。
2. **首版 cmd.tbl 的频度来源**：sango 解耦后"命令集由原版频度表决定"里的原版不存在了。建议：初版频度证据 = love-src/testing 测试套件的调用统计（11.5 自带测试就是第一个"原版"）+ LÖVE 常用 API 子集，后续按实验内核实收增删。
3. **无头资产创建 API**：`newImage` 需要 GL 上下文，无头录制模式内核拿什么建资产。建议：资产注册走 ImageData（CPU 侧）+ fr 资产 API；live 模式同一调用由引擎物化纹理。API 面要定。
4. **math.random 双咽喉（已查证）**：11.5 boot.lua 未将 math.random 别名到 love.math（grep 零命中），内核有两套 RNG，rngc 捕获点不唯一。建议：框架 boot 层把 `math.random`/`math.randomseed` 指向 love.math（我们拥有 fork），单咽喉由构造成立。
5. **A 方案 rehash 噪声**：表扩容 → 布局全变 → memcmp 全脏，st 行爆量。建议：检出游扩容（asize/hmask 变化）即发"表重建事件"（整表重发），与 checkpoint 整页快照同语义；不做逐键语义比对（贵）。

**要写死纪律/进 spec v1.2 的：**

6. **错误帧语义**：handler 中途 Lua error，帧如何闭合。建议：错误也是事实——err 行记录、各段照常闭合、s_crc 照算；回放必须复现同错。
7. **session 首帧基线**：frame 0 = checkpoint（全量登记表 + 状态镜像 + 资产表），此后增量。
8. **多 VM 分配表**（用户定调：cloudwu 式多 VM 贯穿全项目）：内核 VM（被观测者，唯一进堆镜像范围）／观察 VM（第二 lua_State：事件合成器、登记表维护、fr-trace 审计、工具面）／C 层（捕获、diff、回放器、编解码，无 VM）。run loop 住主 VM 但属框架代码，内核不得 require。
9. **loglvl 会话内不可变**：per-session 定死，切换=重开。
10. **几何固定**：header 几何由内核声明且不可变；resize 只作事件记录不改 header（v1 亦可禁 resize）。

**已在待拍板轨道的旧三件**（不重复展开）：回放注入默认档（推荐严格）；log=A 主力+B 二批；fr-spec v1.2 候选清单（§0 生产者、dt 进帧头、ev source 标记、注入语义 + 上列 6/7/9/10）。

### §七.3 附件：GL 依赖面清单（2026-10-26 源码取证，wrap_Graphics.cpp `luax_checkgraphicscreated` 守卫全集）

**A. GPU 资产创建——内核禁直调，由 fr 注册接管**（13 项，行号=守卫调用处）：

| 类 | API | 行号 |
|---|---|---|
| 纹理 | newImage / newCubeImage / newArrayImage / newVolumeImage | :1005 / :774 / :868 / :932 |
| 目标 | newCanvas | :1189 |
| 字体 | newFont / newImageFont / newText | :1088 / :1116 / :1644 |
| 批次/几何 | newMesh / newSpriteBatch / newParticleSystem | :1622 / :1146 / :1170 |
| 视频 | newVideo | :1666 |
| 着色器 | newShader（经 getShaderSource 守卫） | :1264 |

**B. 纯数据但被同一守卫拦住的例外**：`newQuad`（:1041）——Quad 是纯几何（:1078 只做 `newQuad(v, sw, sh)`，无 GPU 资源），只因走 Graphics 实例被拦。处置：**quad 作为 asset 行数据注册（x,y,w,h+总宽总高），内核根本不需要调 newQuad**，渲染端物化时自己造——正好落在我们已有的资产模型里。

**C. 渲染期调用**（draw/print/clear/setCanvas/setScissor/…）：capture-then-replay 已覆盖，内核模式下被捕获层接住不执行，不单列。

**D. CPU 侧放行的原料层**：`love.image.newImageData`、`love.font.newTrueTypeRasterizer` / `newImageRasterizer`（FreeType/字模光栅化全在 CPU，font 模块不依赖 graphics）、`love.math`、`love.filesystem`——内核可直用。

**E. 回读/截图（渲染端专用，内核禁）**：`Canvas:newImageData`、`love.graphics.captureScreenshot`（D10：旁车数据）。

**F. 窗口/上下文（框架所有，内核禁）**：`love.window.setMode` 等。

处置规则〔定案：语义替代而非禁用，D8-5〕：A 类在 fork 中保留原名原签名，实现替换为 CPU 侧注册（校验实参 → 登记 asset 行 → 返回资产代理对象，代理携带 u32 资产号供 draw 捕获时解析）；newQuad 一并去守卫化（纯数据注册，内核根本不用调也行——quad 本就是 asset 行数据）；B 类不接管、数据行化；无 IR 对应的 A 类成员（newShader/newVideo/newMesh 等）暂记 err 行，按频度增补。live 与 headless 共用同一替代实现，差异只在渲染端有无 GL；渲染端物化 = 首次引用时 uploadImageData。

## 附录：v1 仍成立的事实

- **版本对齐**：素材源码已 checkout 官方 11.5 tag（`6eb8d54`），与锁定运行时同版本——内部实现取证一律以此为准。
- **GUI 子系统实测**（love.exe PE subsystem=2）与 `--console`/`freopen CONOUT$` 机制（love.cpp:562-622）：事实不变，但在魔改架构下降级为调试细节——FR 流出口由引擎 C 侧直接写文件/socket（11.5 自带 luasocket，love.cpp:60/520），stdout 不再是候选通道。
