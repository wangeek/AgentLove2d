# dream/world.py
"""无限流地牢 world runner（M2+）。

用户规则（2026-11-01 拍板）：
- room = 上下文边界：每 room 重建 LLM 会话，只传两个数——已完成房间数 n、
  累积积分 S（进 system 状态行）；房间内容全由 LLM 自由发挥；
- 每 room 积分上限 100；奖励拾取:遇怪比例 = 0.3 + 0.7×完美度（0.3:1 ~ 1:1）；
- 通关信令 = 连续三帧 `PR 4 "pass=<本房得分>" …`（三连同值 + lint 全绿才认）；
- 死亡 = LLM 总结表现 + 结算画面 + 三连 `over=<总分>` → run 终结，保存 .fr；
- 房间帧数上限 → 直接进下一房（本房 0 分）；
- idle = Runner 反复绘制末帧，零 LLM 消耗。

流文件整个 run 连续 append（room 边界=信令帧，不是文件边界）——
保存 .fr 即保存整局。Runner 整 run 起一次。

用法：python -m dream.world --llm --out run.fr --kit dream [--headless]
            [--rooms-max N] [--frames-per-room 900] [--burst 6]
"""
import argparse
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dream import driver as ddrv
from dream import prompt as dprompt
from dream import session as dsession
from dream.loop import (_log, ev_fields, frame_block_text, gen_burst,
                        poll_evq)
from dream.run import load_kit_rows
from tools import fr_codec_gen as _rc
from tools import fr_lint

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PASS_RE = re.compile(r"^pass=(\d+)$")
_OVER_RE = re.compile(r"^over=(\d+)$")


def ratio_for(n, s):
    """奖励:遇怪比例 = 0.3 + 0.7×完美度。首房无历史取中庸 0.5。"""
    if n <= 0:
        return 0.5
    p = min(1.0, s / (100.0 * n))
    return 0.3 + 0.7 * p


def room_directive(n, s):
    ratio = ratio_for(n, s)
    return ("无限流地牢，第 %d 个房间。主题自选（自由发挥，可与任何前一房无关）。"
            "本房积分上限 100（什么行为得多少分你定，HUD 实时显示）；"
            "奖励拾取与遇怪的比例约 %.2f:1（按此密度布置）。"
            "玩家完成通关条件后连续三帧写 pass= 信令；玩家死亡先写 run 结算画面"
            "（总结表现）再连续三帧写 over= 信令。" % (n + 1, ratio))


def system_state_line(n, s):
    return "玩家状态：已完成 %d 个房间，累积积分 %d。" % (n, s)


def scan_signals(frames):
    """帧列表（词汇面）→ (pass 三连得分 | None, over 三连总分 | None)。

    三连=连续三帧各有同值信令 PR 行；两连/异值不成。
    """
    pass_run = []   # [(帧号, 值)]
    over_run = []
    pass_hit = over_hit = None
    for no, rows in frames:
        pv = ov = None
        for op, f in rows:
            if op != "print":
                continue
            m = _PASS_RE.match(str(f.get("text", "")))
            if m:
                pv = int(m.group(1))
                continue
            m = _OVER_RE.match(str(f.get("text", "")))
            if m:
                ov = int(m.group(1))
        # 三连检测（帧序列上同值连续）
        if pv is not None and pass_run and pass_run[-1][1] == pv:
            pass_run.append((no, pv))
        else:
            pass_run = [(no, pv)] if pv is not None else []
        if len(pass_run) >= 3:
            pass_hit = pv
        if ov is not None and over_run and over_run[-1][1] == ov:
            over_run.append((no, ov))
        else:
            over_run = [(no, ov)] if ov is not None else []
        if len(over_run) >= 3:
            over_hit = ov
    return pass_hit, over_hit


def run_rooms(a, drv, kit_rows, chatlog):
    """房间状态机（可 headless：不起 Runner，纯生成+流产出）。"""
    n, s = 0, 0
    frames_all = []          # 全 run 帧（词汇面）——流产出用
    stream_len = 0
    evq_off = 0
    proc = None
    state = {"turn_seq": 0, "last_feedback": ""}
    evq = a.out + ".evq"
    evinj = a.out + ".evinj"

    def _append_stream(new_frames, first_ev=None):
        """新帧 → 流 append。展开失败（对象寻址未配对等）抛 ValueError，
        由调用方丢弃该 burst 并打回——不炸整局。"""
        nonlocal stream_len
        canon, _exp, dcrcs = dsession.resolve_frames(frames_all)
        with open(a.out, "a", encoding="utf-8", newline="\n") as f:
            for i in range(stream_len, len(canon)):
                ev = first_ev if (first_ev and i == stream_len) else []
                # 首帧带 kit asset 行（dream 流形：帧内 dt 后；否则中途
                # 信令判定的 lint 报 L001 幻资产）
                ar = kit_rows if i == 0 else ()
                f.write(frame_block_text(canon[i][0], a.dt, ev,
                                         canon[i][1], dcrcs[i],
                                         asset_rows=ar))
        stream_len = len(frames_all)

    if not a.headless:
        if os.path.isfile(evq):
            os.remove(evq)
        if os.path.isfile(evinj):
            os.remove(evinj)
        env = dict(os.environ)
        env.update(FR_STREAM=os.path.abspath(a.out),
                   FR_EVQ=os.path.abspath(evq),
                   FR_W=str(a.width), FR_H=str(a.height),
                   FR_TITLE="dream-runner-%d" % os.getpid(),
                   FR_RUNNER_DBG=os.path.abspath(a.out + ".runnerdbg"),
                   FR_EV_INJECT=os.path.abspath(evinj))
        proc = subprocess.Popen(
            [a.love, os.path.join(_ROOT, "dream", "runner")], env=env, cwd=_ROOT)
        print("EVINJ %s" % os.path.abspath(evinj), flush=True)

    try:
        while n < a.rooms_max:
            # —— room 会话重建（上下文边界）：system 状态行 + 新 directive
            messages = [{"role": "system", "content": dprompt.build_system(
                dprompt.load_vocab(), dprompt.load_catalog(a.kit),
                a.width, a.height) + "\n" + system_state_line(n, s)}]
            _log(chatlog, "ROOM %d SYSTEM（会话重建：n=%d S=%d）" % (n + 1, n, s),
                 system_state_line(n, s))
            directive = room_directive(n, s)
            a.directive = directive   # gen_burst 读 a.directive（每房注入）
            _log(chatlog, "ROOM %d DIRECTIVE" % (n + 1), directive)
            room_start = len(frames_all)
            room_frames = 0
            got = gen_burst(drv, messages, a, len(frames_all),
                            a.frames_initial, "", chatlog, state)
            frames_all += got
            _append_stream(got)

            def _check_signals():
                """扫本房新帧信令：三连 + lint 全绿 → (pass, over)。"""
                pv, ov = scan_signals(frames_all[room_start:])
                if pv is None and ov is None:
                    return None, None
                text = open(a.out, encoding="utf-8").read()
                diags = fr_lint.lint_text(text, dream=True)
                if diags:
                    print("dream.world: 信令但 lint %d 条——不认" % len(diags),
                          file=sys.stderr)
                    return None, None
                return pv, ov

            pv, ov = _check_signals()
            if ov is not None:
                print("dream.world: RUN OVER（over=%d）——保存流" % ov,
                      file=sys.stderr)
                return n, s, frames_all
            if pv is not None:
                s += min(pv, 100)
                n += 1
                print("dream.world: room %d clear（pass=%d）→ n=%d S=%d"
                      % (n, pv, n, s), file=sys.stderr)
                continue
            deadline_frames = len(frames_all) + a.frames_per_room
            # —— room 内循环：事件 → burst → 信令/帧上限
            while True:
                if not a.headless:
                    if proc.poll() is not None:
                        print("dream.world: Runner 退出（rc=%s）"
                              % proc.returncode, file=sys.stderr)
                        return n, s, frames_all
                    evs, evq_off = poll_evq(evq, evq_off)
                else:
                    time.sleep(0.2)
                    evs = []
                if len(frames_all) >= deadline_frames:
                    print("dream.world: room %d 帧数上限→下一房（本房 0 分）"
                          % (n + 1), file=sys.stderr)
                    n += 1
                    break
                if evs:
                    ef = ev_fields(evs)
                    ev_rows_txt = "\n".join(
                        _rc.render_line_px("ev", e) for e in ef)
                    note = ("\n【用户操作】发生了用户操作事件，"
                            "注意是否需要给予反馈：\n" + ev_rows_txt)
                    _log(chatlog, "EVENT（Runner 上报）", ev_rows_txt)
                    try:
                        got = gen_burst(drv, messages, a, len(frames_all),
                                        a.burst, note, chatlog, state)
                        _append_stream(got, first_ev=ef)
                        room_frames += len(got)
                    except ValueError as e:
                        # 展开失败（对象寻址未配对/参数错）→ 丢整个 burst
                        # 打回重试——不炸整局（world 鲁棒性）
                        del frames_all[room_start + room_frames:]
                        messages[:] = messages[:1]   # 会话重建（干净重试）
                        state["last_feedback"] = ("上次 burst 被拒：%s——"
                            "注意 MOVE 常规形态恒三参数（资产 dx dy），"
                            "只有多实例才写 k" % str(e)[:240])
                        print("dream.world: burst 展开/生成失败→丢弃重试：%s"
                              % str(e)[:120], file=sys.stderr)
                        continue
                    # 信令扫描（复用初始 burst 后的同款判定）
                    pv, ov = _check_signals()
                    if ov is not None:
                        print("dream.world: RUN OVER（over=%d）——保存流" % ov,
                              file=sys.stderr)
                        return n, s, frames_all
                    if pv is not None:
                        s += min(pv, 100)   # 上限封顶（防 LLM 超写）
                        n += 1
                        print("dream.world: room %d clear（pass=%d）→ n=%d S=%d"
                              % (n, pv, n, s), file=sys.stderr)
                        break
                elif not a.headless:
                    time.sleep(0.2)
    finally:
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    return n, s, frames_all


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dream.world")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--out", required=True)
    ap.add_argument("--kit", default="dream")
    ap.add_argument("--headless", action="store_true",
                    help="不起 Runner（纯生成+流产出：测试/批量 demo）")
    ap.add_argument("--rooms-max", type=int, default=999)
    ap.add_argument("--frames-initial", type=int, default=12)
    ap.add_argument("--frames-per-room", type=int, default=900)
    ap.add_argument("--burst", type=int, default=6)
    ap.add_argument("--chunk-frames", type=int, default=3)
    ap.add_argument("--dt", type=float, default=1.0 / 15.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--max-retry", type=int, default=2)
    ap.add_argument("--love", default=os.path.join(
        _ROOT, "megasource", "build115", "love", "Release", "love.exe"))
    ap.add_argument("--chatlog", default="")
    a = ap.parse_args(argv)
    if not a.llm:
        print("dream.world: 无限地牢需 --llm", file=sys.stderr)
        return 2

    drv = ddrv.LlmDriver()
    kit_rows = load_kit_rows(a.kit)
    log_path = a.chatlog or (a.out + ".chatlog")
    chatlog = open(log_path, "w", encoding="utf-8", newline="\n")
    chatlog.write("# dream world 会话日志 %s（model=%s）\n"
                  % (time.strftime("%Y-%m-%d %H:%M:%S"),
                     os.environ.get("LLM_MODEL", "?")))

    # 初始流头（room 帧随后 append）
    open(a.out, "w", encoding="utf-8", newline="\n").close()
    dsession.write_session(
        dsession.build_session([], seed=a.seed, width=a.width,
                               height=a.height, has_same=True), a.out)
    # write_session 全量重写——空会话头后改为 append 模式由 _append_stream 续写
    n, s, frames = run_rooms(a, drv, kit_rows, chatlog)

    # 收尾：全文重 seal（含正确 head）+ lint + 判据
    canon, _exp, dcrcs = dsession.resolve_frames(frames)
    entries = dsession.seal_frames(canon, kit_rows, a.dt, dcrcs)
    text = dsession.write_session(
        dsession.build_session(entries, seed=a.seed, width=a.width,
                               height=a.height, has_same=True), a.out)
    diags = fr_lint.lint_text(text, dream=True)
    for d in diags:
        print("lint:", d, file=sys.stderr)
    _log(chatlog, "RUN DONE", "rooms=%d score=%d frames=%d" % (n, s, len(frames)))
    chatlog.close()
    print("dream.world: %d 房 / %d 分 / %d 帧 → %s（lint %s）"
          % (n, s, len(frames), a.out,
             "全绿" if not diags else "%d 条诊断" % len(diags)))
    if drv.usage_totals:
        print("dream.world: usage %s" % drv.usage_totals, file=sys.stderr)
    return 0 if not diags else 1


if __name__ == "__main__":
    sys.exit(main())
