# tests/test_interactive.py —— M2 §9 交互式会话端到端（Fake LLM + SendMessage）
# 判据（用户裁决①）：.fr 含 ev 行；事件帧后有绘制响应；chatlog 记录对话。
import ctypes
import os
import re
import threading
import time

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOVE = os.path.join(_ROOT, "megasource", "build115", "love", "Release", "love.exe")
pytestmark = pytest.mark.skipif(not os.path.isfile(LOVE),
                                reason="fork 运行时未构建")


class _FakeDriver:
    """脚本化 LLM：初始段背景帧 + CP；事件 chunk 在点击处画 CI（响应证据）。"""

    def __init__(self):
        self.usage_totals = {}
        self._ev_pending = False

    def generate(self, messages):
        last = messages[-1]["content"]
        m = re.search(r"请从 frame (\d+) 开始，本次输出 (\d+) 帧", last)
        base, n = int(m.group(1)), int(m.group(2))
        click = re.search(
            r"mousepressed.*?num (\d+) num (\d+)", last)
        parts = []
        for i in range(base, base + n):
            if i == 0:
                parts.append("frame 0\nC 0 0 0 255\n"
                             "R 0 0 0 640 480 0 0 1 10 20 40 255")
            elif click and i == base:
                x, y = click.group(1), click.group(2)
                parts.append("frame %d\nC 0 0 0 255\n"
                             "R 0 0 0 640 480 0 0 1 10 20 40 255\n"
                             "CI 1 %s %s 10 16 200 220 255 255" % (i, x, y))
            else:
                parts.append("frame %d\nCP" % i)
        return "\n".join(parts) + "\n"


def _sweep_zombies(keep_title):
    """清掉历史会话的 dream-runner-* 僵尸窗（防同位置顶层窗吃掉点击）。"""
    import ctypes.wintypes as wt
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    victims = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, _):
        n = ctypes.create_unicode_buffer(64)
        user32.GetWindowTextW(h, n, 64)
        if n.value.startswith("dream-runner-") and n.value != keep_title:
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            victims.append(pid.value)
        return True

    user32.EnumWindows(cb, 0)
    for pid in victims:
        h = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
        if h:
            kernel32.TerminateProcess(h, 1)
            kernel32.CloseHandle(h)


def _click_window(x=320, y=300, timeout=20.0, title=None, evq_path=None):
    """合成点击（UI 自动化）——物理注入 + 事件回执验证 + 失败重试。

    实现注记（三代方案实证史）：① 纯 PostMessage 按钮消息：位置取 SDL
    光标缓存，物理光标竞争覆盖（悬窗内/离窗钳位）必败；② 纯 PostMessage
    含 MOVE：无焦点窗的投递 move 被 SDL 丢弃（实测 pressed 落 (0,0)）；
    ③ 定案=物理注入（SetCursorPos+mouse_event，SDL 原生消费位置精确）
    + 前台/置顶 + .evq 回执轮询重试（顶层 z-order 竞争的自愈）+
     僵尸窗清扫（历史会话同位窗吃点击——实测根因）。
    """
    title = title or ("dream-runner-%d" % os.getpid())
    user32 = ctypes.windll.user32
    hwnd = 0
    t0 = time.time()
    while time.time() - t0 < timeout:
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            break
        time.sleep(0.1)
    if not hwnd:
        return False
    _sweep_zombies(title)
    time.sleep(1.0)  # 渲染就绪（至少一帧贴屏）

    class _POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    def _attempt():
        # 前台 + 置顶（物理点击落在光标处最顶层窗口——免遮挡/焦点争夺）
        fg = user32.GetForegroundWindow()
        if fg != hwnd:
            t1 = user32.GetWindowThreadProcessId(fg, None)
            t2 = user32.GetWindowThreadProcessId(hwnd, None)
            user32.AttachThreadInput(t1, t2, True)
            user32.SetForegroundWindow(hwnd)
            user32.AttachThreadInput(t1, t2, False)
            time.sleep(0.2)
        SWP = 0x0002 | 0x0001 | 0x0010  # NOMOVE | NOSIZE | NOACTIVATE
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, SWP)   # HWND_TOPMOST
        pt = _POINT(x, y)
        if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
            return False
        user32.SetCursorPos(pt.x, pt.y)
        time.sleep(0.15)
        # 现场取证：光标点命中的窗口（排查套件内点击被吃）
        hit = user32.WindowFromPoint(pt)
        if hit != hwnd:
            n = ctypes.create_unicode_buffer(128)
            user32.GetWindowTextW(hit, n, 128)
            hp = ctypes.c_uint32()
            user32.GetWindowThreadProcessId(hit, ctypes.byref(hp))
            print("click-pos hit=%s title=%r pid=%s (self=%s/%s)"
                  % (hit, n.value, hp.value, hwnd, os.getpid()),
                  file=sys.stderr)
        user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
        time.sleep(0.05)
        user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
        time.sleep(0.05)
        user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, SWP)   # NOTOPMOST
        return True

    def _receipt(n_before):
        try:
            with open(evq_path, "rb") as f:
                return f.read().count(b"\n") > n_before
        except OSError:
            return False

    n_before = 0
    if evq_path and os.path.isfile(evq_path):
        with open(evq_path, "rb") as f:
            n_before = f.read().count(b"\n")
    for _ in range(3):
        if not _attempt():
            return False
        for _ in range(40):  # 4s 回执窗（套件负载下事件可能晚到）
            if not evq_path or _receipt(n_before):
                return True
            time.sleep(0.1)
    for _ in range(60):  # 末击宽限 6s（末次点击恰在轮询尾落地的竞态）
        if not evq_path or _receipt(n_before):
            return True
        time.sleep(0.1)
    return not evq_path  # 无回执通道=尽力而为


def _inject_click(x=320, y=300, timeout=20.0, evq_path=None, evinj_path=None):
    """注入点击事件（CI 确定性通道）。

    OS 级合成点击（SendMessage/PostMessage/物理注入五代方案）在套件负载下
    被 Windows 输入路由吞掉（实证：光标命中窗口无误而 handler 不触发）。
    定案通道=Runner 的 FR_EV_INJECT 文件：写一行 → Runner 在 love.update
    经 love.event.push 进 love 事件队列 → 走与 OS 输入完全相同的 Lua 捕获
    回调管线（D14 双生产者的合成口径）。物理注入路径保留于 _click_window
    供手动验证。
    """
    t0 = time.time()
    # 就绪信号：Runner 的 runnerdbg 出现 load 标记（.evinj 由本函数创建）；
    # 套件负载下 love 冷启动可达 20s+——45s 上限
    dbg_path = evinj_path.replace(".evinj", ".runnerdbg") \
        if evinj_path.endswith(".evinj") else evinj_path + ".runnerdbg"
    while time.time() - t0 < 45:
        try:
            with open(dbg_path, "r", encoding="utf-8") as f:
                if "load title=" in f.read():
                    break
        except OSError:
            pass
        time.sleep(0.1)
    else:
        return False
    time.sleep(0.3)  # 首帧 update 已跑
    with open(evinj_path, "a", encoding="utf-8") as f:
        f.write("mousepressed %d %d 1 false\n" % (x, y))
        f.write("mousereleased %d %d 1 false\n" % (x, y))
    if not evq_path:
        return True
    for _ in range(50):  # 5s 回执
        try:
            with open(evq_path, "rb") as f:
                if f.read().count(b"\n") >= 1:
                    return True
        except OSError:
            pass
        time.sleep(0.1)
    return False


def test_interactive_sendmessage(tmp_path, monkeypatch):
    from dream import loop as dloop
    monkeypatch.setattr(dloop.ddrv, "LlmDriver", _FakeDriver)

    out = tmp_path / "sess.fr"
    clog = tmp_path / "sess.chatlog"
    rc = {}

    def run():
        rc["code"] = dloop.main([
            "--llm", "--out", str(out), "--kit", "dream",
            "--directive", "像素小剧场（测试）", "--frames-initial", "6",
            "--burst", "6", "--chunk-frames", "3", "--max-idle", "20",
            "--max-total", "90", "--chatlog", str(clog)])

    t = threading.Thread(target=run)
    t.start()
    try:
        assert _inject_click(320, 300, evq_path=str(out) + ".evq",
                             evinj_path=str(out) + ".evinj"), \
            "注入通道无回执（.evq 无事件）"
    finally:
        t.join(timeout=120)
    assert not t.is_alive(), "loop 未在超时内结束"
    assert rc.get("code") == 0, rc

    text = out.read_text(encoding="utf-8")
    # ① ev 行存在（协议形：完整参数序 + :px 整数形）
    assert 'ev 0 "mousepressed" 0 4 num 320 num 300 num 1 num 0' in text
    # ② 事件帧后有绘制响应（Fake 在点击处画 CI）
    idx = text.index('ev 0 "mousepressed"')
    assert "CI 1 320 300" in text[idx:], "事件后无绘制响应"
    # ③ chatlog 记录了事件注入与对话
    chat = clog.read_text(encoding="utf-8")
    assert "【事件】" in chat and "SYSTEM" in chat and "DONE" in chat
