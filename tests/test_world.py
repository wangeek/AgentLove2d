# tests/test_world.py —— 无限流地牢 world runner（信令/比例/状态机）
import re

import pytest


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
