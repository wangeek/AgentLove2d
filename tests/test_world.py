# tests/test_world.py —— 无限流地牢 world runner（信令/比例/状态机）
import os
import re

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 依赖声明：本文件里跑 world 的用例都用 dream/kit_heroes，其 assets.txt（字节体）
# 按设计不入库。缺它时 load_kit_rows 静默返回空 → 流里无 asset 行 → 信令被 lint
# 判 L001 不认 → 这些用例必然失败，所以缺 kit 跳过而不是硬跑。
# 历史：2026-11-24 修复前，缺 kit 还会让 headless 房内循环没有出口——测试线程
# 永不结束、pytest 进程退不出去（干净 clone 里 `pytest tests/` 挂死 900s+）；
# 该无界循环已修（见下"无界循环"一组用例），跳过标记仍然保留。
# 再生方法见 dream/.gitignore。
needs_kit = pytest.mark.skipif(
    not os.path.isfile(os.path.join(_ROOT, "dream", "kit_heroes", "assets.txt")),
    reason="缺 dream/kit_heroes/assets.txt（kit 字节不入库；再生见 dream/.gitignore）")


def test_ratio_math():
    from dream.world import ratio_for
    assert ratio_for(0, 0) == 0.5                       # 首房中庸
    assert ratio_for(1, 100) == pytest.approx(1.0)      # 完美 → 1:1
    assert ratio_for(1, 0) == pytest.approx(0.3)        # 零分 → 0.3:1
    assert ratio_for(2, 100) == pytest.approx(0.65)     # p=0.5 → 中点
    assert ratio_for(3, 999) == pytest.approx(1.0)      # 超写封顶


def _frame(no, texts):
    rows = []
    for t in texts:
        rows.append(("print", {"font": 4, "text": t, "x": 260.0, "y": 240.0,
                               "rot": 0.0, "sx": 1.0, "sy": 1.0,
                               "color": (255, 215, 0, 255)}))
    return (no, rows)


def test_signal_scan_triple():
    from dream.world import scan_signals
    # 三连同值 pass → 得分
    pv, ov = scan_signals([_frame(0, ["x"]), _frame(1, ["pass=98"]),
                           _frame(2, ["pass=98"]), _frame(3, ["pass=98"])])
    assert pv == 98 and ov is None
    # 两连不成
    pv, _ = scan_signals([_frame(0, ["pass=98"]), _frame(1, ["pass=98"])])
    assert pv is None
    # 异值断连
    pv, _ = scan_signals([_frame(0, ["pass=90"]), _frame(1, ["pass=98"]),
                          _frame(2, ["pass=98"])])
    assert pv is None
    # over 三连
    _, ov = scan_signals([_frame(0, ["over=142"]), _frame(1, ["over=142"]),
                          _frame(2, ["over=142"])])
    assert ov == 142


@needs_kit
def test_world_headless_state_machine(tmp_path, monkeypatch):
    """headless 三房+死亡：Fake LLM 脚本化——房 1/2 各 pass 三连，房 3 over。"""

    class Fake:
        def __init__(self):
            self.usage_totals = {}
            self.room = 0          # 由 system 状态行推断当前房
            self._n = 0

        def generate(self, messages):
            last = messages[-1]["content"]
            m = re.search(r"请从 frame (\d+) 开始，本次输出 (\d+) 帧", last)
            base, cnt = int(m.group(1)), int(m.group(2))
            # 当前房号从 system 状态行读
            sys_all = messages[0]["content"]
            n = int(re.search(r"已完成 (\d+) 个房间", sys_all).group(1))
            parts = []
            for i in range(base, base + cnt):
                rows = "C 8 8 20 255\nPR 4 \"ROOM HUD\" 8 8 0 1 1 255 255 255 255"
                if n == 0 and i >= 9:      # 房 1 尾部 pass 三连
                    rows += '\nPR 4 "pass=80" 260 240 0 1 1 255 215 0 255'
                elif n == 1 and i >= 9:    # 房 2 尾部 pass 三连
                    rows += '\nPR 4 "pass=100" 260 240 0 1 1 255 215 0 255'
                elif n == 2 and i >= 9:    # 房 3 死亡结算 + over 三连
                    rows += ('\nPR 4 "RUN SUMMARY" 260 200 0 1 1 255 255 255 255'
                             '\nPR 4 "over=180" 260 240 0 1 1 255 80 80 255')
                parts.append("frame %d\n%s" % (i, rows))
            return "\n".join(parts) + "\n"

    from dream import world as dw
    monkeypatch.setattr(dw.ddrv, "LlmDriver", Fake)
    out = tmp_path / "run.fr"
    rc = {}
    import threading

    def go():
        rc["code"] = dw.main([
            "--llm", "--headless", "--out", str(out), "--kit", "dream/kit_heroes",
            "--rooms-max", "5", "--frames-initial", "12", "--burst", "6",
            "--chunk-frames", "3", "--frames-per-room", "40",
            "--chatlog", str(tmp_path / "run.chatlog")])

    t = threading.Thread(target=go)
    t.start()
    t.join(timeout=60)
    assert not t.is_alive(), "world 未收束"
    assert rc["code"] == 0, rc

    text = out.read_text(encoding="utf-8")
    # 状态机断言：房 1 pass=80 → 房 2 pass=100 → over=180（S=180）
    assert text.count('"pass=80"') >= 3
    assert text.count('"pass=100"') >= 3
    assert text.count('"over=180"') >= 3
    chat = (tmp_path / "run.chatlog").read_text(encoding="utf-8")
    assert "n=2 S=180" in chat          # 第三房 system 状态行
    assert "RUN DONE" in chat
    # 比例传递断言：房 3 的 directive 应含 0.94（p=0.9 → 0.3+0.63）
    assert "0.94" in chat or "0.93" in chat


@needs_kit
def test_world_idle_gate_ends_whole_run(tmp_path, monkeypatch):
    """静默收尾闸=整局 return，不是 break 开新房（2026-11-01 跳层 bug 回归）。

    真机形态（非 headless）：Fake Popen 顶替 Runner，LLM 静默（无信令无事件）
    ——max-idle=0 时闸应在房 1 内触发并结束整局；bug 形态（break 跳层）会
    无限换房（n 不增长），线程 30s 不收束即红。"""

    class Fake:
        def __init__(self):
            self.usage_totals = {}

        def generate(self, messages):
            m = re.search(r"请从 frame (\d+) 开始，本次输出 (\d+) 帧",
                          messages[-1]["content"])
            base, cnt = int(m.group(1)), int(m.group(2))
            parts = []
            for i in range(base, base + cnt):
                parts.append('frame %d\nC 8 8 20 255\n'
                             'PR 4 "ROOM HUD" 8 8 0 1 1 255 255 255 255' % i)
            return "\n".join(parts) + "\n"

    class FakeProc:
        returncode = None

        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    from dream import world as dw
    monkeypatch.setattr(dw.ddrv, "LlmDriver", Fake)
    monkeypatch.setattr(dw.subprocess, "Popen", lambda *a, **k: FakeProc())
    out = tmp_path / "run.fr"
    rc = {}
    import threading

    def go():
        rc["code"] = dw.main([
            "--llm", "--out", str(out), "--kit", "dream/kit_heroes",
            "--rooms-max", "3", "--frames-initial", "4", "--burst", "2",
            "--chunk-frames", "2", "--frames-per-room", "40",
            "--max-idle", "0.0",
            "--chatlog", str(tmp_path / "run.chatlog")])

    t = threading.Thread(target=go, daemon=True)
    t.start()
    t.join(timeout=30)
    assert not t.is_alive(), "静默闸未收束整局（break 换房死循环）"
    assert rc["code"] == 0, rc
    chat = (tmp_path / "run.chatlog").read_text(encoding="utf-8")
    assert "ROOM 1 SYSTEM" in chat
    assert "ROOM 2 SYSTEM" not in chat      # 闸=整局结束，不再开新房


# ── 无界循环（2026-11-24 修）───────────────────────────────────────
# 共同根因：房内循环的出口闸只在"窗口模式的无事件轮"里检查，headless 与
# 持续失败两类路径都绕开了它。挂死的表现是线程不返回，所以用例统一在
# 子线程里跑、限时收束——"到时间能停下"本身就是判据。

def _asked(messages):
    """本轮提示词里的 (起始帧号, 帧数)。"""
    m = re.search(r"请从 frame (\d+) 开始，本次输出 (\d+) 帧",
                  messages[-1]["content"])
    return int(m.group(1)), int(m.group(2))


def _hud(base, cnt):
    """合法回应：每帧一行 HUD（永不给信令）。"""
    return "".join('frame %d\nPR 4 "ROOM HUD" 8 8 0 1 1 255 255 255 255\n'
                   % i for i in range(base, base + cnt))


def _bad_move(base, cnt):
    """引用未登记资产 999 的回应。"""
    return "".join("frame %d\nMOVE 999 5 5\n" % i for i in range(base, base + cnt))


def _boom(base, cnt):
    raise RuntimeError("LLM 端点故障")


class _ScriptLLM:
    """按调用序给回应的假 LLM：第 n 次调用用 answers[n-1](base, cnt)，越界沿用
    最后一个。调用次数与"每次被要求从哪帧开始"只在这一处记。
    （先前的写法让子类和父类各自 +1：计数翻倍，"第 2 次给坏输出"的条件永不
    成立，那条测试静默失效。计数只许在一个地方。）"""
    usage_totals = {}

    def __init__(self, answers):
        self.answers = answers
        self.calls = 0
        self.bases = []

    def generate(self, messages):
        self.calls += 1
        base, cnt = _asked(messages)
        self.bases.append(base)
        return self.answers[min(self.calls, len(self.answers)) - 1](base, cnt)


def _headless(tmp_path, answers, argv, limit=25.0):
    """headless 跑 world；返回 (rc 或 None, 假 LLM, 是否仍存活)。"""
    import threading
    from dream import world as dw
    llm, rc = _ScriptLLM(answers), {}
    out = tmp_path / "run.fr"

    def go():
        dw.ddrv.LlmDriver = lambda: llm       # 测试进程内直接替换，finally 还原
        rc["code"] = dw.main(["--llm", "--headless", "--out", str(out),
                              "--kit", "dream/kit_heroes",
                              "--chatlog", str(tmp_path / "run.chatlog")] + argv)

    old = dw.ddrv.LlmDriver
    t = threading.Thread(target=go, daemon=True)
    try:
        t.start()
        t.join(timeout=limit)
    finally:
        dw.ddrv.LlmDriver = old
    return rc.get("code"), llm, t.is_alive()


@needs_kit
def test_headless_total_time_is_capped(tmp_path):
    """headless 下 --max-total 必须生效（原先两道闸只在非 headless 分支检查）。"""
    rc, llm, alive = _headless(
        tmp_path, [_hud],
        ["--frames-initial", "2", "--burst", "2", "--chunk-frames", "2",
         "--frames-per-room", "400", "--max-total", "0.5"])
    assert not alive, "超过 --max-total 仍在跑（无界循环）"
    assert (tmp_path / "run.chatlog").read_text(encoding="utf-8").count("RUN DONE") == 1
    assert llm.calls == 1, "收尾前调用了 %d 次 LLM" % llm.calls


@needs_kit
def test_headless_idle_timeout_ends_run(tmp_path):
    """headless 无事件且流不增长 → --max-idle 静默超时收尾（--max-total 设得很长，
    只留静默闸一条出路）。"""
    rc, llm, alive = _headless(
        tmp_path, [_hud],
        ["--frames-initial", "2", "--burst", "2", "--chunk-frames", "2",
         "--frames-per-room", "400", "--max-idle", "0.4",
         "--max-total", "60"])
    assert not alive, "静默超过 --max-idle 仍在跑（无界循环）"
    # 只应有初始 burst 的 2 帧：静默期间 headless 没有事件，不该再向 LLM 要帧
    assert llm.calls == 1, "静默期间仍在调用 LLM（%d 次）" % llm.calls
    assert (tmp_path / "run.fr").read_text(encoding="utf-8").count("\nframe ") == 2


class _FakeProc:
    """顶替 Runner 子进程：永远在跑。"""
    returncode = None

    def poll(self):
        return None

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


def _windowed(tmp_path, llm, argv, events, limit=25.0):
    """窗口模式跑 world（Fake Runner + 每轮固定上报 events）；返回 (rc, 是否仍存活)。"""
    import threading
    from dream import world as dw
    out, rc = tmp_path / "run.fr", {}

    def go():
        dw.ddrv.LlmDriver = lambda: llm
        dw.subprocess.Popen = lambda *a, **k: _FakeProc()
        dw.poll_evq = lambda path, off: (events, off)
        rc["code"] = dw.main(["--llm", "--out", str(out), "--kit", "dream/kit_heroes",
                              "--chatlog", str(tmp_path / "run.chatlog")] + argv)

    old = (dw.ddrv.LlmDriver, dw.subprocess.Popen, dw.poll_evq)
    t = threading.Thread(target=go, daemon=True)
    try:
        t.start()
        t.join(timeout=limit)
    finally:
        dw.ddrv.LlmDriver, dw.subprocess.Popen, dw.poll_evq = old
    return rc.get("code"), t.is_alive()


@needs_kit
def test_bad_bursts_are_capped(tmp_path):
    """缺陷 ②：事件不断、LLM 每次都给展开不了的输出 → 到 --max-bad-bursts 收尾。
    （原先 ValueError → 回滚 → continue：无计数，且 continue 绕过超时闸。）"""
    llm = _ScriptLLM([_hud, _bad_move])       # 初始 burst 合法，之后全是坏输出
    ev = [{"no": 1, "ev": "keypressed", "args": ["space"], "frame": 1}]
    rc, alive = _windowed(
        tmp_path, llm,
        ["--rooms-max", "999", "--frames-initial", "2", "--burst", "2",
         "--chunk-frames", "2", "--frames-per-room", "400",
         "--max-bad-bursts", "3", "--max-total", "60", "--max-idle", "60"], ev)
    assert not alive, "坏 burst 无上限（事件洪泛下无限调 LLM）"
    assert llm.calls == 4, "初始 1 次 + 坏 burst 3 次应共 4 次，实际 %d" % llm.calls
    chat = (tmp_path / "run.chatlog").read_text(encoding="utf-8")
    assert chat.count("RUN DONE") == 1 and "RUN ABORTED" not in chat
    # 坏帧不得进流：只有初始 burst 的 2 帧
    assert (tmp_path / "run.fr").read_text(encoding="utf-8").count("\nframe ") == 2
    # 每次失败后重新要帧，起始号必须仍是 2（已有 2 帧）——回滚不能动到好帧
    assert llm.bases == [0, 2, 2, 2], llm.bases


@needs_kit
def test_burst_runtime_error_ends_run_cleanly(tmp_path):
    """缺陷 ③：LLM 调用抛非 ValueError（端点故障/重试上限的 RuntimeError）→
    收尾保存已有流、返回非零；而不是异常穿出 run_rooms，流与日志半途而废。

    只有会再次调用 LLM 的路径才触发得到——即窗口模式的事件轮（headless 下
    初始 burst 之后不再调 LLM，走的是静默闸，此处实测不涉及本缺陷）。"""
    llm = _ScriptLLM([_hud, _boom])          # 初始 burst 合法；之后每次调用都炸
    ev = [{"no": 1, "ev": "keypressed", "args": ["space"], "frame": 1}]
    rc, alive = _windowed(
        tmp_path, llm,
        ["--frames-initial", "2", "--burst", "2", "--chunk-frames", "2",
         "--frames-per-room", "40", "--max-total", "20", "--max-idle", "20"], ev)
    assert not alive
    assert llm.calls == 4, (      # 初始 1 次 + 首试 1 次 + 重试 2 次（--max-retry 缺省 2）
        "端点故障应重试到上限后放弃，共 4 次调用，实际 %d" % llm.calls)
    # 初始 burst 成功（2 帧已落盘），事件后的调用炸——这两帧必须保住
    assert (tmp_path / "run.fr").read_text(encoding="utf-8").count("\nframe ") == 2
    chat = (tmp_path / "run.chatlog").read_text(encoding="utf-8")
    assert "RUN ABORTED" in chat, "异常直接穿出 run_rooms，收尾没执行"
    assert "RUN DONE" not in chat              # 中止不是正常结束，不能记成 DONE
    # 真实原因进了日志——不再被 UnboundLocalError 盖掉
    assert "LLM 调用重试上限" in chat and "LLM 端点故障" in chat
    assert rc == 3, "中止的退出码应为 3，实际 %r" % rc


@needs_kit
def test_failed_burst_rollback_keeps_good_frames(tmp_path):
    """回滚只撤本 burst：失败的事件 burst 不得连带删掉已落盘的帧。
    原先 room_frames 不含初始 burst → 房内第一次失败把初始帧也从内存删掉：
    内存与流文件脱节，下一次向 LLM 要帧的起始号偏小，随后那轮好帧被静默丢弃。"""
    # 初始合法 → 房内第一个事件 burst 失败 → 之后恢复合法
    llm = _ScriptLLM([_hud, _bad_move, _hud])
    ev = [{"no": 1, "ev": "keypressed", "args": ["space"], "frame": 1}]
    rc, alive = _windowed(
        tmp_path, llm,
        ["--rooms-max", "1", "--frames-initial", "2", "--burst", "2",
         "--chunk-frames", "2", "--frames-per-room", "4",
         "--max-total", "20", "--max-idle", "20"], ev)
    assert not alive
    chat = (tmp_path / "run.chatlog").read_text(encoding="utf-8")
    assert "RUN DONE" in chat and "RUN ABORTED" not in chat
    # 初始 2 帧 + 失败之后那一轮 2 帧 + 再一轮 2 帧 = 6；失败的那 2 帧不进流
    assert (tmp_path / "run.fr").read_text(encoding="utf-8").count("\nframe ") == 6
    # 失败后向 LLM 要的起始帧号必须接着已有帧（2），不能退回 0
    assert llm.bases == [0, 2, 2, 4], llm.bases
