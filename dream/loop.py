# dream/loop.py
"""M2 §9 交互式会话驱动：LLM + Runner 游戏子进程（love.exe dream/runner）。

拓扑（docs/plans/2026-11-01-m2-interactive-dream.md §9）：
- .fr（Python→Runner，append-only 文本）与 .evq（Runner→Python，JSON 行）
  两个文件即通道，无 stdio 协议；
- 初始段一次生成 N 帧 → 起 Runner → 轮询 .evq：事件 →（ev 行落新 burst 首帧
  in 段 + 协议行注入提示词）→ LLM 生成响应 burst → append .fr → 续播；
- 空闲不增帧（Runner 末帧反复绘制；LLM 上下文只随真实事件增长——用户裁决③）；
- 会话终：关窗 / 事件后静默超时 / 总超时 → 收尾 lint/check + chatlog。

用法：python -m dream.loop --llm --out <s.fr> --kit dream --directive "..."
            [--frames-initial 12 --burst 6 --chunk-frames 3]
            [--max-idle 120 --max-total 600 --love <love.exe>]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dream import driver as ddrv
from dream import prompt as dprompt
from dream import session as dsession
from dream.run import _chatlog_sanitize, load_kit_rows
from tools import fr_codec_gen as _rc
from tools import fr_lint

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def frame_block_text(no, dt, ev_rows, rows, dcrc, asset_rows=()):
    """追加帧块文本（行序=seal_frames：dt→ev→asset(可选,首帧)→rows→end）。"""
    out = ["frame %d" % no]
    seq = [("dt", {"val": dt})]
    seq += [("ev", e) for e in ev_rows]
    seq += list(asset_rows)
    seq += rows
    seq += [("s_crc", {"crc": 0}), ("d_crc", {"crc": dcrc})]
    for op, f in seq:
        out.append(_rc.render_line_px(op, f))
    return "\n".join(out) + "\n"


def poll_evq(path, off):
    """读 .evq 新完整行 → (事件列表, 新偏移)。"""
    if not os.path.isfile(path):
        return [], off
    with open(path, "rb") as f:
        f.seek(off)
        data = f.read()
    last_nl = data.rfind(b"\n")
    if last_nl < 0:
        return [], off
    evs = []
    for ln in data[:last_nl + 1].decode("utf-8", "replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            evs.append(json.loads(ln))
        except ValueError:
            print("dream.loop: 坏 evq 行略过: %r" % ln[:80], file=sys.stderr)
    return evs, off + last_nl + 1


def ev_fields(evs):
    """.evq JSON 列表 → [ev fields dict]（args 数值→float，字符串→单元 tuple）。

    slot=事件槽号（流内从 0 起，vocab 第 9 条）；.evq 的 no 从 1 起（Runner
    计数器）——此处换算。
    """
    out = []
    for e in evs:
        args = []
        for a in e.get("args", []):
            args.append(float(a) if isinstance(a, (int, float)) else (a,))
        out.append({"slot": max(0, int(e.get("no", 1)) - 1), "type": e["ev"],
                    "src": 0, "args": args})
    return out


def gen_burst(drv, messages, a, base_frame, n_want, ev_note, chatlog, state):
    """生成 n_want 帧（LLM 多 chunk + 打回，镜像 run.py 纪律）→ [(no, rows)]。

    base_frame=本 burst 起始帧号；state：retry/feedback/turn_seq 跨 burst 保持。
    """
    got, retry, feedback = [], 0, state.get("last_feedback", "")
    while len(got) < n_want:
        n_left = min(a.chunk_frames, n_want - len(got))
        base = len(messages)
        note = ev_note if not got else ""
        state["turn_seq"] += 1
        messages.append({"role": "user", "content": dprompt.build_turn(
            a.directive, base_frame + len(got), n_left, feedback) + note})
        shown = messages[base]["content"]
        if state["turn_seq"] > 1 and shown.startswith(a.directive):
            shown = "<剧本同前，略>" + shown[len(a.directive):]
        _log(chatlog, "TURN %d · user（本次追加）" % state["turn_seq"], shown)
        usage_before = dict(drv.usage_totals)
        try:
            raw = drv.generate(messages)
            _log(chatlog, "TURN %d · assistant（LLM 回应）" % state["turn_seq"], raw)
            du = {k: drv.usage_totals[k] - usage_before.get(k, 0)
                  for k in drv.usage_totals}
            if du:
                chatlog.write("（本回合 usage 增量: %s）\n" % du)
                chatlog.flush()
            chunk = dsession.parse_chunk(raw)
            if chunk[0][0] != base_frame + len(got):
                raise ValueError("chunk 起始帧号 %d ≠ 期望 %d"
                                 % (chunk[0][0], base_frame + len(got)))
            if len(chunk) < n_left:
                raise ValueError("要求 %d 帧实得 %d 帧——请按要求的帧数一次写全"
                                 % (n_left, len(chunk)))
            messages.append({"role": "assistant", "content": raw})
            got += chunk
            retry, feedback = 0, ""
        except (ValueError, RuntimeError) as e:
            # 失败样本保留进历史（LLM 看到自己错在哪——删掉它会原样重犯，
            # 渔舟/地牢实测死循环根因）；feedback user 追加在失败之后
            retry += 1
            feedback = "上次输出被拒：%s——请逐 token 对照词汇表检查每行的参数个数后重出" \
                       % str(e)[:300]
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": feedback})
            if retry > a.max_retry:
                raise RuntimeError("burst 重试上限：%s" % e) from None
    state["last_feedback"] = feedback
    return got


def _log(chatlog, tag, text):
    chatlog.write("\n===== %s =====\n%s\n" % (tag, _chatlog_sanitize(text)))
    chatlog.flush()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dream.loop")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--out", required=True)
    ap.add_argument("--kit", default="dream")
    ap.add_argument("--directive", required=True)
    ap.add_argument("--frames-initial", type=int, default=12)
    ap.add_argument("--burst", type=int, default=6)
    ap.add_argument("--chunk-frames", type=int, default=3)
    ap.add_argument("--dt", type=float, default=1.0 / 15.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--max-retry", type=int, default=2)
    ap.add_argument("--max-idle", type=float, default=120.0,
                    help="事件后静默超时（秒）——会话终")
    ap.add_argument("--max-total", type=float, default=600.0)
    ap.add_argument("--love", default=os.path.join(
        _ROOT, "megasource", "build115", "love", "Release", "love.exe"))
    ap.add_argument("--chatlog", default="")
    a = ap.parse_args(argv)
    if not a.llm:
        print("dream.loop: 交互会话需 --llm", file=sys.stderr)
        return 2

    drv = ddrv.LlmDriver()
    kit_rows = load_kit_rows(a.kit)
    out_abs = os.path.abspath(a.out)
    evq = a.out + ".evq"
    log_path = a.chatlog or (a.out + ".chatlog")
    chatlog = open(log_path, "w", encoding="utf-8", newline="\n")
    chatlog.write("# dream 交互会话日志 %s（model=%s）\n"
                  % (time.strftime("%Y-%m-%d %H:%M:%S"),
                     os.environ.get("LLM_MODEL", "?")))
    state = {"turn_seq": 0, "last_feedback": ""}

    messages = [{"role": "system", "content": dprompt.build_system(
        dprompt.load_vocab(), dprompt.load_catalog(a.kit), a.width, a.height)}]
    _log(chatlog, "SYSTEM（静态件，仅记一次）", messages[0]["content"])

    frames = []  # 全部已落流帧（词汇面）
    try:
        # 初始段
        got = gen_burst(drv, messages, a, 0, a.frames_initial,
                        "", chatlog, state)
        frames += got
        canon, _exp, dcrcs = dsession.resolve_frames(frames)
        entries = dsession.seal_frames(canon, kit_rows, a.dt, dcrcs)
        # 交互会话恒 +d（后续 burst 可能引入 CP；协商写一次不能改）
        dsession.write_session(
            dsession.build_session(entries, seed=a.seed, width=a.width,
                                   height=a.height, has_same=True), a.out)
        stream_len = len(frames)

        # 起 Runner 子进程
        if os.path.isfile(evq):
            os.remove(evq)
        env = dict(os.environ)
        env.update(FR_STREAM=out_abs, FR_EVQ=os.path.abspath(evq),
                   FR_W=str(a.width), FR_H=str(a.height),
                   FR_TITLE="dream-runner-%d" % os.getpid(),
                   FR_RUNNER_DBG=os.path.abspath(a.out + ".runnerdbg"),
                   FR_EV_INJECT=os.path.abspath(a.out + ".evinj"))
        runner_dir = os.path.join(_ROOT, "dream", "runner")
        evinj = a.out + ".evinj"
        if os.path.isfile(evinj):
            os.remove(evinj)
        # 协议通告：evinj 路径打到 stdout（会话脚本从这里读——路径唯一化
        # 防多会话互踩；脚本侧注入前先读此行）
        print("EVINJ %s" % os.path.abspath(evinj), flush=True)
        proc = subprocess.Popen([a.love, runner_dir], env=env, cwd=_ROOT)

        t_total = time.time() + a.max_total
        # 活性=事件或 Runner 渲染证据（runnerdbg 增长=子进程活着在画）；
        # 初始段 LLM 生成可能 25s+——idle 计时必须排除生成/启动耗时，
        # 否则点击在生成期到达时，第一轮轮询即误判静默超时（实测）
        dbg_path = a.out + ".runnerdbg"

        def _dbg_mtime():
            try:
                return os.path.getmtime(dbg_path)
            except OSError:
                return 0.0

        last_active = max(time.time(), _dbg_mtime())
        evq_off = 0
        while True:
            if proc.poll() is not None:
                print("dream.loop: Runner 退出（rc=%s）" % proc.returncode,
                      file=sys.stderr)
                break
            if time.time() > t_total:
                proc.terminate()
                print("dream.loop: 总超时", file=sys.stderr)
                break
            evs, evq_off = poll_evq(evq, evq_off)
            if evs:
                ef = ev_fields(evs)
                ev_rows_txt = "\n".join(_rc.render_line_px("ev", e) for e in ef)
                note = ("\n【用户操作】发生了用户操作事件，注意是否需要给予反馈：\n"
                        + ev_rows_txt)
                _log(chatlog, "EVENT（Runner 上报）", ev_rows_txt)
                got = gen_burst(drv, messages, a, len(frames), a.burst,
                                note, chatlog, state)
                frames += got
                canon, _exp, dcrcs = dsession.resolve_frames(frames)
                with open(a.out, "a", encoding="utf-8", newline="\n") as f:
                    for i in range(stream_len, len(canon)):
                        first_ev = ef if i == stream_len else []
                        f.write(frame_block_text(
                            canon[i][0], a.dt, first_ev,
                            canon[i][1], dcrcs[i]))
                stream_len = len(frames)
                last_active = time.time()
            elif (time.time() - last_active > a.max_idle
                  and time.time() - _dbg_mtime() > a.max_idle):
                # 双信号：本进程无事件 且 Runner 停止渲染——才是真静默
                print("dream.loop: 静默超时（%.0fs 无事件且 Runner 无渲染）"
                      % a.max_idle, file=sys.stderr)
                proc.terminate()
                break
            else:
                if _dbg_mtime() > last_active:
                    last_active = _dbg_mtime()  # Runner 在画=活着
                time.sleep(0.2)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    finally:
        _log(chatlog, "DONE", "%d 帧 → %s" % (len(frames), a.out))
        chatlog.close()

    text = open(a.out, encoding="utf-8").read()
    diags = fr_lint.lint_text(text, dream=True)
    for d in diags:
        print("lint:", d, file=sys.stderr)
    print("dream.loop: %d 帧 → %s（lint %s）"
          % (len(frames), a.out, "全绿" if not diags else
             "%d 条诊断" % len(diags)))
    if drv.usage_totals:
        print("dream.loop: usage %s" % drv.usage_totals, file=sys.stderr)
    return 0 if not diags else 1


if __name__ == "__main__":
    sys.exit(main())
