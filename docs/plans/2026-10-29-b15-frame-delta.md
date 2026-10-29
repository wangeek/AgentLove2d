# B15 帧间增量批 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增量形态落地（S/pd/rd 扩展集 + P1 落盘层 diff 编码器 + 双端解码），稳态体积 world_map 103.6KB/帧 → 目标 <5KB/帧、battle 等待帧 → ~30B。

**Architecture:** 增量=写出/传输/存储形态变换（行缓冲语义不变，录制端零改动纪律）。P1 路径：C tee writer 逐帧行集 diff（内存持 ref 行集）产增量行；解码=解引用展开全量行集→走既有 exec。设计真源：`docs/plans/2026-10-29-b15-frame-delta-design.md`（送审稿+评判补丁 a/b）。

**评判补丁落实：** a) 增量行型进 cmd.tbl 扩展段（指纹升版正确；golden 重锚）；能力协商=head :prec 复合（`:px+d`）。b) rd- 定位=帧内行序（构造性）；身份 (asset,k) 仅 pd 用。

---

### Task 1: cmd.tbl 扩展段 + 指纹升版 + golden 重锚

**Files:** tables/cmd.tbl、tests/golden/l0_session.fr、tests/test_l0.py（如断言 sha）

- [ ] cmd.tbl 追加增量扩展段行（status=ext，注明协商位）：
  `S	out	ref u32	frame-delta 扩展	ext	same：本帧行集与帧 ref 全同；d_crc=CRC("same:<ref>")`
  `pd	out	asset u32 k u32 param str val f32	frame-delta 扩展	ext	paramdelta：(asset,k) 行身份参数绝对值更新；身份配对失败编码器降级 rd`
  `rdp	out	pos u32 line str	frame-delta 扩展	ext	行插入（pos=帧内行序；line=完整 :px 行）`
  `rdm	out	pos u32	frame-delta 扩展	ext	行删除（pos=帧内行序——构造性定位，非跨帧身份）`
  + 表头注释：扩展集=能力协商（head `:prec` 复合 `+d`）；五端门槛与转正规则引用路线图 §5.3-4
- [ ] 重生成 fr-gen（`python -m tools.fr_gen.gen_python`）——扩展行不进 selftest 样本（C emit 不产增量，同 font 引用先例；round-trip 归 Python 测试+真流）
- [ ] golden 重锚：表 sha 变 → l0_session.fr 头行 sha 更新（重跑 L0 产流或脚本改头+验证 fr-check 过）
- [ ] 全量回归（sha 相关断言排查：`grep -rn "tbl_sha\|7f3427" tests/`）
- [ ] Commit

### Task 2: fr-gen 增量行型编解码（Python 目标，TDD）

**Files:** tools/fr_gen/gen_python.py、tests/test_codec_gen.py

- [ ] TDD 先行：S/pd/rdp/rdm 四行型 render/parse round-trip（pd param 名受控白名单：x/y/rot/sx/sy/ox/oy；rdp line 内嵌 :px 行递归解析）
- [ ] 实现（模板扩展，扩展集行型走独立函数段，不污染基座生成逻辑）
- [ ] Commit

### Task 3: C 侧展开器（生产路径）+ Python 对拍工具（用户架构修正 2026-10-29）

**Files:** fr_capture.cpp（fork，离线解析+展开）、tools/fr_delta_check.py（对拍工具）、tests

> 用户裁定：展开器=生产热路径，归 C（与 capture_exec_row 同地，零拷贝）；
> Python expand_delta 降级为双实现交叉验证工具（自检+独立重算范式），
> 不是生产路径。工具集 Python→C/Rust 重构：记账缓行——Python 全在离线
> 批处理（瓶颈=子进程启动，非解析），热路径录制/回放已在 C；串流落地
> 后按 benchmark 工具耗时行再定重构对象。

- [ ] C 离线解析器收容 S/pd/rdp/rdm + 帧展开（展开后行集走既有 exec；
      S 帧 D_CRC=解码后行集回读）
- [ ] tools/fr_delta_check.py：独立展开（纯 Python）→ 与 C 离线回放的
      D_CRC 对账（双实现交叉验证）
- [ ] TDD：构造 mini 增量流（I/S/pd/rdp/rdm）→ C 回放 rc=0 + py 展开
      行集相等 + d_crc 对账（same 帧=CRC("same:n")）
- [ ] Commit

### Task 4: C 侧 P1 编码器 + 离线解码（fork）

**Files:** fr_session.cpp（writer diff 编码器）、fr_capture.cpp（离线解析/展开）、构建

- [ ] writer：FR_DELTA=1 门控——冲帧时与本帧 ref 行集 diff（pd 身份配对（asset,k）：帧内引用计数器建 k；参数单变产 pd；多变/新增产 rdp；删除产 rdm；零变产 S）；事件谓词先验（无 ev 帧先试 S）+行集 diff 断言；d_crc 按增量语义重算；I 帧：FR_DELTA_I=N（缺省 32）周期 + ev 帧强制
- [ ] 离线解析器：S/pd/rdp/rdm 行型收容+展开（展开后走既有 capture_exec_row；S 帧 D_CRC=解码后行集回读——播放/判据路径统一）
- [ ] demo 验证流（FR_DELTA=1）→ 离线回放 D_CRC 与全量形态逐帧一致（渲染等价判据）
- [ ] Commit（fork+根仓）

### Task 5: 双场景实测 + 落册

- [ ] world_map/battle 各录两形态（full / :px+d）：稳态每帧字节对比（正确口径！）→ benchmarks 对照行（目标：world_map <5KB/帧、battle 等待帧 ~30B）
- [ ] spec v1.4 记账（扩展集行型/协商位/判据重述/rd 定位裁定）
- [ ] 全量回归绿 + AGENTS/design 行更新 + Commit

---

## Self-Review
- 设计覆盖：送审稿 §2 词汇→T1/T2；§3 P1→T4；§4 事件结构→T4（谓词先验+I 帧策略）；§6 验收→T4 demo 等价+T5 双场景；补丁 a→T1；补丁 b→T1/T2（rdm pos）。
- 风险最大项：T4 C diff 编码器与展开器对称性——判据锚 demo 双形态 D_CRC 一致 + T3 Python 展开器交叉验证（同一增量流两实现展开相等）。
