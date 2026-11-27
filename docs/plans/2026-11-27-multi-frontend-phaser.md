# 2026-11-27 多前端：Phaser（web 2D）试点

决策：`docs/decisions.md` D17 ｜ 前端仓库：`git@github.com:wangeek/phaser-fr`（`<引擎>-fr` 命名）
状态：**v0.1 已交付（编解码 + 跨实现验收 + 捕获 + 回放 + 四段验收全绿）**，前端仓提交 `3ea222f`；
落地记录与新增实测见文末「P1 落地记录」。未做项：Graphics 路径捕获、旋转、atlas 切片、scissor 回放、靶流回填 golden。

## 为什么是 Phaser，不是 three.js

我们的语义是 2D 的——`tables/cmd.tbl` 的 21 条 op 全是 2D 图元 + 绝对坐标，
无 z / 深度 / 相机矩阵 / 光照 / 材质（D4 树不进协议、D11 相机内核端结算共同锁死）。
所以：

- **Phaser**：2D、画家算法（后画覆盖前画）、display list 顺序 = 我们的行序 → 同构，
  协议零改动。
- **three.js**：要正交相机 + 全部 z=0 + 材质退化，或改协议。改协议等于换基石：
  深度/光照进来后，"回放 = 重放同一串调用"不再成立，`d_crc` 跨机器不可比。
  它能"投影后兼容"，但不是忠实记录。
- 附带事实：three.js 现在被用作模型能力测评载体（AA-3D：55 份简报 / 21 模型 /
  1 万+ 盲投）——那是**生成与观感**评估，靠人投票，因为观感没有判据。
  FR 占的是另一格：**正确性**（AA-3D 自己的局限声明也写明"正确性需另行评估"）。

## 结构（D17 三条不变量）

```
AgentLove2d/                     ← 真源：协议 + 工具 + 判据 + 生成器
  tables/cmd.tbl                 ← 唯一真源（前端不得自带可改的表）
  tools/fr_gen/gen_js.py         ← 第三个生成目标（表数据面）
  render/js/
    fr_table.mjs                 ← 生成物（勿手改）
    codec.mjs                    ← 手写单源：逐字段驱动，不按 op 硬编码
    conformance.mjs               ← 手写单源：跨实现验收
  tests/golden/*.fr              ← 契约物
  tests/test_gen_js.py           ← 5 项（含"闸自己能红"的反例）

wangeek/phaser-fr/               ← 前端：只做捕获 + 回放
  src/{fr_table,codec,conformance}.mjs  ← 由上者同步（逐字节相同，勿在此改）
  test/golden/l0_session.fr      ← golden 副本
  package.json / README.md
```

## 已交付（v0）

- `gen_js`：从 `cmd.tbl` 生成表数据面（30 op / 字段序 / 可变长标记 / status / delta 标记 /
  表指纹），产出确定性（同表重复再生逐字节相等）。双路径同步：`../phaser-fr/src/` 在场
  即推送三个文件，缺场跳过。
- `codec.mjs`：文本编解码全通（render/parse/转义/`qf` 量化/variant/`f32[]`/asset 四形态）
  + CRC32（zlib 口径）。
- `conformance.mjs`：三条判据——表指纹一致、逐行 round-trip 逐字节相等、逐帧 `d_crc` 重算相等。
- 验收记录：
  - 主仓 `pytest tests/test_gen_js.py` → 5 passed
  - 前端仓 `npm test` → `CONFORMANCE OK 1 个流 / 4 帧 / 53 行`
  - **闸能红**（反例对照）：改一个坐标 → `d_crc X ≠ 重算 Y`；少写一位小数 →
    `round-trip 不一致` 并打出原文与回渲染差异

## v0 不覆盖（登记，不假装支持）

| 项 | 现状 | 后续 |
|---|---|---|
| `:px` 紧凑档 | 不认 | conformance 遇 `:px` 明确 SKIP；先用 `fr_prec` 转 full |
| `.frb` 二进制 | 不做 | 需要时让 `gen_js` 补字节层（C/Python 已有先例） |
| 帧间增量（CP/SET/INS/DEL/MOVE/PLACE/POSE/ENTER/EXIT） | 只识别不展开 | 需展开器；该帧 CRC 跳过并报"不展开" |
| 捕获（`src/capture.mjs`） | **已做（v0.1）**：clear / draw / print / rect（填+描）；其余进 unsupported | 覆盖面扩展见「P1 落地记录」未做项 |
| 回放（`src/replay.mjs`） | **已做（v0.1）**：11 op；`scissor` 已知缺口（用了判 FAIL） | 修 scissor |

## P1：捕获与回放（已落地，记录见文末）

**当初为什么没做**：这两件要接 Phaser 渲染入口，必须有真实 Phaser 靶游戏才能验；
没验过的代码不入库（v0 只交了能自证的编解码与验收闸）。

**顺序**（每步都要能失败）：

1. **最小靶游戏**：一个单场景 Phaser 游戏，每帧固定几次绘制（含图片 + 文本 + 图形），
   固定步长、无随机、无墙钟。产出的流要能被主仓 `fr_lint` 判全绿。
2. **回放**（先于捕获）：读 golden 流 → 逐帧调 Phaser 绘制。验收：与主仓 Python 侧
   `fr_render` 对同一流的 `d_crc` 序列**逐帧相等**（这是"两端语义一致"的硬证据）。
   > 落地时修正：`fr_render` 回放 stdout 的 D_CRC 是**画布像素** CRC，流内 `d_crc` 是
   > **out 行文本** CRC，两域不可互比（与 dream runner 的口径注意同源）；跨机像素 CRC
   > 也不可比（本节"风险"第二条自己就说过）。实际落的验收是**行级**：回放器 `executed`
   > == 流的绘制行（逐行按序）+ 流内 d_crc 自洽。这条口径写进计划时就想错了，记在这里。
3. **捕获**：包 Phaser 渲染入口产行。验收两条：
   - 同参双跑**逐字节相同**（确定性前置：固定步长 + 无随机 + 无输入）
   - 同一帧，捕获产的行 == **独立手算**的期望行（按场景配置算，与捕获器零共享）
4. 跑通后把靶游戏的 golden 流回填主仓 `tests/golden/`，纳入契约。**（未做，见落地记录）**

**风险（先说在前面）**：
- 注意 `Phaser.HEADLESS` 是"不渲染"，拿不到绘制调用；FR 式捕获要的是"渲染但不显示"
  （无头 Chrome + 真 WebGL），两者别混。
- WebGL 后端差异（软件 GL/真 GPU）可能让像素级 `D_CRC`（画布 CRC）跨机不可比；
  判据主力仍应是**行级符号比较**（流自带的 `d_crc`/锚行），不是画布像素。
- ~~Phaser 的 `TimeStep` 能否钉成固定步长——未实测~~ → **已实测，见下节"时间基准"**。

## 通道选择：已实测（2026-11-27）

浏览器没有文件系统，"捕获"要选一条把行送出来的通道。用无头 Edge + 真 `codec.renderLine`
造 60000 行（500 行/帧 × 120 帧，draw/print/rect 混合比例）量了三条：

| 通道 | 耗时 | 吞吐 | 说明 |
|---|---|---|---|
| 构造 + `renderLine` + `d_crc`（无传输） | 163 ms | **368k 行/秒** | 这是真正的上限 |
| 逐行 `console.log` | 345 ms | 174k 行/秒 | 500 行/帧 ≈ 348 fps |
| 每帧一次 `console.log`（批量串） | 19 ms | 3.17M 行/秒 | 比逐行快 17× |
| 每帧一次 `fetch POST` | 173 ms | 347k 行/秒 | 仅比纯构造多 6% |

**结论**：
1. **通道不是瓶颈，字符构造才是**（368k 行/秒）。先别为传输做架构。
2. **选 `console.log` + Node 侧收**（不选 HTTP POST）：与 LÖVE 侧"父进程持有句柄"同构，
   游戏侧零网络代码，不占端口、不碰 CSP/防火墙。HTTP POST 性能上不吃亏，但它为
   一个不存在的问题引入了网络栈。
3. **必须攒到帧边界再发**（19 ms vs 345 ms）。逐行 `console.log` 也不至于撑不住，
   但没有理由选它。

踩坑记录：探针早期把 `times()` 用在 async 函数上，量到的是"发起耗时"而非往返——
异步路径必须显式 `await` 后计时。这类"看起来在测、其实没测到"的错，和判据本身
一样需要反例对照。

## 时间基准：已实测（2026-11-27，Phaser 4.2.1 + 无头 Edge + WebGL）

**问题**：捕获要双跑逐字节相同，前提是每帧 `dt` 恒定且 `update(time, delta)` 的序列可复现。

**结论：可以钉死。** 配方四步，缺一不可：

```js
// ① 等游戏循环**真的跑起来**再停（以状态为准，不靠事件时序）
const waitRunning = () => (game.loop.started && game.loop.running)
  ? begin() : requestAnimationFrame(waitRunning);
// ② 停 rAF（此时 running=true，sleep 才不是空操作）
game.loop.sleep();
// ③ 关平滑器：它按 targetFps 截断 delta，重置后还有 120 拍冷却期
game.loop.smoothStep = false;
// ④ 虚拟时钟原点钉 0，每拍 vt = k × STEP（乘法，不累加）
game.loop.lastTime = 0; game.loop.time = 0;
game.loop.step(++k * STEP);
```

实测（240 帧；"序列哈希"= 逐帧 `(time, delta)` 的 FNV-1a）：

| 模式 | 步长 | 帧数 | delta 取值 | time 最大偏差 | 两次运行序列哈希 | 两次运行墙钟峰值 |
|---|---|---|---|---|---|---|
| 手动 | 60Hz | 240 | 1 种 | 0 | `ad3a82b0` / `ad3a82b0` | 26.5 / 29.2 ms |
| 手动 | 15Hz | 240 | 1 种 | 0 | `7889f70a` / `7889f70a` | 27.1 / 21.7 ms |
| 手动 | 144Hz | 240 | 1 种 | 0 | `c0d76425` | 27.2 ms |
| 自动（rAF） | — | 241 | 6 种 | — | — | 88.8 ms |

**两次运行哈希相同、墙钟不同**——这就是"运行确定"的直接证据。自动模式帧数都对不上。

**四个坑（每个都踩过，都会产出"看似合法"的坏数据）**：
1. `READY` 事件早于循环启动——在 `READY` 里 `sleep()` 时 `running` 还是 false，
   `sleep` 的 `running && …` 直接短路等于没调，随后 Phaser 照常开 rAF。
2. `TimeStep.step(time)` **只有一个参数**，传第二个会被忽略；delta 永远由
   `time − lastTime` 算出。（社区文章里的 `step(0, 16.6)` 不适用于 4.2.1。）
3. 虚拟时钟原点若取真实 `lastTime`，传给 `update` 的 `time` 每次运行都不同——
   步长恒定 ≠ 运行确定。原点必须钉 0。
4. `vt += STEP` 累加 240 次会漂出舍入误差；用 `k × STEP`。

## 捕获挂点：已实测（2026-11-27，同一环境）

Phaser 4 不是 3.x 的 `renderer.pipelines`，而是**渲染节点图**
（`renderer.renderNodes._nodes`，节点**按类型共享实例**）：

```
ListCompositor → Camera → [每个游戏对象] renderWebGLStep(renderer, go, …)
  ├─ 带纹理：SubmitterQuad.run(…, go, …, TexturerImage节点, TransformerImage节点)
  │            → BatchHandlerQuad.batch / batchTextures
  └─ 无纹理：FillRect / FillPath / FillTri / DrawLine / StrokePath
               → BatchHandlerTriFlat.batch
```

两层各能看见什么（实测，11 笔绘制逐笔对账）：

| 层 | 有身份（类型/名字/文字/纹理/帧） | 有最终屏幕几何 | 备注 |
|---|---|---|---|
| 游戏对象 `renderWebGLStep` | ✅ 第 2 个参数就是对象 | ❌ 要自己乘矩阵 | 每对象每帧恰一次，顺序=显示列表 |
| 节点 `SubmitterQuad.run` | ✅ 参数带对象 | ✅ **返回后**读变换节点的 `quad` | 带纹理对象的最优挂点 |
| 节点 `FillRect` / `FillPath` 等 | ❌ **没有对象参数** | ⚠️ `FillRect.run` 返回后有；`FillPath` 的顶点不在 `quad` 里 | 形状类是硬伤 |
| 处理器 `batch` | ❌ 只有 GL 纹理对象 | ✅ 已是屏幕坐标 | 语义太低，不可用 |

**陷阱：渲染节点按类型共享实例**（`_nodes` 的键是节点类型）。读几何的时机错一格就会
整体错位，而且产出的流**完全合法、过得了 lint**：

| 读法 | image 读到的 quad | 对不对 |
|---|---|---|
| 进入 `SubmitterQuad.run` 时读 | `289.5,99.5`（上一个对象） | ❌ |
| `TransformerImage.run` 返回后读 | 仍差一格 | ❌ |
| **`SubmitterQuad.run` 返回后读参数节点** | `29.5,19.5…30.5,20.5` | ✅ |

四个带纹理对象 + 两个 `FillRect` 逐笔核对通过（含相机滚动 10,20、缩放 2×1、容器嵌套）。

**形状类的身份问题**：无纹理形状在节点层没有身份。`rect`/`circle`/`line`/`poly`
这些 FR 行需要「身份 + 几何 + 颜色」，节点层给不出身份；且 `Graphics` 是一对多
（一个对象、多笔绘制），`FillPath` 的顶点不经过 `quad`。解法是"对象层设上下文、
节点层取几何"——见下一段实测。

### 追加实测（同日）：对象层上下文方案成立

上面的"可行方向"已验证。做法：在游戏对象原型的 `renderWebGLStep` 外包一层，进入时
把 `this` 记为"当前对象"（嵌套时保存/恢复），节点层在 `run` **返回后**读几何时取用。

**判定不靠"看起来对"**：每笔都用对象的**独立属性**（`x/y/width/height/scaleX/父容器位置`）
算出期望的屏幕几何，与节点层读到的 `quad` 逐笔对账。

| 节点 | 对象 | 身份来自 | 几何（got） | 几何（exp） | 结果 |
|---|---|---|---|---|---|
| `FillRect` | Rectangle:rect | **上下文** | `174,12,206,28` | 同 | OK |
| `FillRect` | Rectangle:rect2 | **上下文** | `238,-4,262,44` | 同 | OK |
| `SubmitterQuad` | Image:image | 参数 | `29.5,19.5,30.5,20.5` | 同 | OK |
| `SubmitterQuad` | Sprite:sprite（2×1） | 参数 | `109,19.5,111,20.5` | 同 | OK |
| `SubmitterQuad` | Text:"HP 87" | 参数 | `30,70,70,86` | 同 | OK |
| `SubmitterQuad` | Image:容器子图 | 参数 | `289.5,99.5,290.5,100.5` | 同 | OK |

稳态 48 条记录，**失配 0**。

**一个反向教训**：第一轮报 7 条失配，全在"容器子图"上——**错的是我的期望值，不是读法**。
我把相机滚动扣了两次（子对象的 `x,y` 已相对父容器，不该再减滚动）。对账失配时，
先怀疑期望值的算法，再怀疑被测对象；否则会把正确的读法"修"坏。

**仍未覆盖**：`Graphics`（一对多，一个对象多笔绘制）与 `FillPath`（顶点不经过 `quad`）、
`Line`/`StrokePath`、相机旋转/缩放下的几何、`roundPixels` 的半像素舍入对 `%.6f` 的影响。
这些进 P1 的任务清单，每项都要有独立期望值。

## P1 落地记录（2026-11-28，前端仓提交 `3ea222f`）

**交付**（`wangeek/phaser-fr`，`npm test` 四段全绿）：`src/capture.mjs`（捕获）、`src/stepper.mjs`
（虚拟时钟四步配方）、`src/session.mjs`（会话封装）、`src/replay.mjs`（回放 11 op）、
`test/run.mjs`（零 npm 依赖的无头浏览器驱动）、`test/{capture,replay,semantics}.html`。

**对照 P1 验收标准**：

| 标准 | 结果 |
|---|---|
| 靶游戏产流能被主仓 `fr_lint` 判全绿 | ✅ `fr_lint` exit 0、`fr_check` OK、`fr_dump --geo` 派生矩形正确（主仓工具零改动） |
| 同参双跑逐字节相同 | ✅ 同页两实例逐字节相同；跨进程两次独立浏览器启动流指纹相同 |
| 回放：行级对账 | ✅ 回放器 `executed` == 流的绘制行（golden 4 帧、全 op 流 23 行/帧、捕获流） |
| 捕获：行 == 独立手算期望 | ✅ `test/capture.html` 8 条（C0–C6，见前端仓 README） |
| 靶流回填主仓 golden | ⬜ **未做** |

**本轮新增实测（Phaser 4.2.1，勿再凭记忆）**：

1. **描边矩形不走 `FillRect`**：`StrokePath.run` 每个描边形状一次，内部**同步**调 `DrawLine`
   4 次（每边一次，端点是相对形状中心的局部坐标）。只包 `FillRect` 的捕获器会把描边
   静默丢掉——是验收页里那个 Graphics 哨兵（"unsupported 里只许有 Graphics"）把它抓出来的。
2. **同一个变换节点，`matrix` 是新的、`quad` 是旧的**：`StrokePath` 参数里的变换节点，
   `matrix`（`[a,b,c,d,tx,ty]`）是当前形状的（tx/ty = 屏幕中心、a/d = 含相机 zoom 的有效
   缩放），`quad` 却是上一个对象的。"返回后读就对"只对 `quad` 被重算的路径成立
   （SubmitterQuad / FillRect），不能一概而论。描边的几何因此取 `matrix` + 对象宽高。
3. `game.config.backgroundColor` 是 Color 对象：自有键 `r/g/b/a` 四个都是 **0–255**，
   `alpha` getter 也返回 0–255。按 3.x 记忆当 0–1 乘 255，产出 `clear 0 0 0 65025` 的错行。
4. `FillCamera.run` 只在相机设了底色时才调，透明底色下不调（所以纳入登记面不会误报）。
5. Text：`style.color` 是 CSS 串（`"#fff"` 三位形式）；`resolution` 属性不存在（按 1）；
   `font: "16px monospace"` 简写被解析成 `fontSize "16px"` + `fontFamily "monospace"`。
6. `Frame` 有 `x/y/width/height`，`source` 是数组（`source[0].width/height`）。
7. 捕获流的形状与 LÖVE golden 一致（帧 → dt → 资产（首帧）→ clear → 绘制 → s_crc/d_crc），
   资产载荷 1 字节占位、尺寸真。

**捕获器口径（写死在前端仓 README，这里记决定）**：不支持的**不静默丢**——进
`Capture.unsupported`（带原因），验收判 FAIL；`s_crc` 固定 0（浏览器侧没有 Lua 堆），
`d_crc` 真算；`scissor` 回放为已知缺口（Phaser 4 WebGL 下对象级 `setMask` 空操作），
用了就红，直到修好。

**未做项（按优先级）**：Graphics 路径捕获（fill/stroke → line/poly/circle/arc/points，
命令缓冲操作码已量过）、旋转对象、atlas 切片（需 quad 资产）、相机底色、scissor 回放、
靶流回填主仓 golden 并纳入 pytest（纯 Python 可验）。
