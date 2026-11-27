# 2026-11-27 多前端：Phaser（web 2D）试点

决策：`docs/decisions.md` D17 ｜ 前端仓库：`git@github.com:wangeek/phaser-fr`（`<引擎>-fr` 命名）
状态：**v0 已交付（编解码 + 跨实现验收）；捕获与回放未做**

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
| 捕获（`capture.js`） | **未做** | 见下验收标准 |
| 回放（`replay.js`） | **未做** | 同上 |

## 下一步（P1）：捕获与回放

**为什么还没做**：这两件要接 Phaser 渲染入口，必须有真实 Phaser 靶游戏才能验；
没验过的代码不入库（本次只交了能自证的编解码与验收闸）。

**顺序**（每步都要能失败）：

1. **最小靶游戏**：一个单场景 Phaser 3 游戏，每帧固定 3-5 次绘制（含图片 + 文本 + 图形），
   固定步长、无随机、无墙钟。产出的流要能被主仓 `fr_lint` 判全绿。
2. **回放**（先于捕获）：读 golden 流 → 逐帧调 Phaser 绘制。验收：与主仓 Python 侧
   `fr_render` 对同一流的 `d_crc` 序列**逐帧相等**（这是"两端语义一致"的硬证据）。
3. **捕获**：包 Phaser 渲染入口产行。验收两条：
   - 同参双跑**逐字节相同**（确定性前置：固定步长 + 无随机 + 无输入）
   - 同一帧，捕获产的行 == Python 侧对等价调用的渲染结果（round-trip 级对齐）
4. 跑通后把靶游戏的 golden 流回填主仓 `tests/golden/`，纳入契约。

**风险（先说在前面）**：
- Phaser 的 `TimeStep` 是否真能钉成固定步长、以及 `loop.sleep()`+手动 `step()` 能否稳定冻结帧
  ——未实测，需先做探针再谈确定性。
- 注意 `Phaser.HEADLESS` 是"不渲染"，拿不到绘制调用；FR 式捕获要的是"渲染但不显示"
  （无头 Chrome + 真 WebGL），两者别混。
- WebGL 后端差异（软件 GL/真 GPU）可能让像素级 `D_CRC`（画布 CRC）跨机不可比；
  判据主力仍应是**行级符号比较**（流自带的 `d_crc`/锚行），不是画布像素。
