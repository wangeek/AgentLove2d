# dream/run.py
"""dream runner CLI（B18 M1）。

用法：python -m dream.run --frames 60 --out dream_session.fr [--kit <dir>]
                       [--from-file <chunks.txt> | --llm]
                       [--dt 0.066667] [--seed 1] [--width 640] [--height 480]
                       [--window-k 8] [--directive "<剧本>"] [--max-retry 2]

生成循环：prompt（词汇+目录单+滑窗+指令）→ driver chunk → parse_chunk（帧号
连续+白名单）→ 增量 seal → lint 语义闸（dream 口径）→ 通过才计入流；重试
上限内带诊断打回。LLM env：LLM_BASE_URL / LLM_MODEL / LLM_API_KEY（可空）。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dream import driver as ddrv
from dream import prompt as dprompt
from dream import session as dsession
from tools import fr_codec_gen as _rc
from tools import fr_lint


def load_kit_rows(kit_dir):
    """kit assets.txt → [("asset", parsed_fields)]（parse 形态，px 渲染器可画回）。"""
    p = os.path.join(kit_dir, "assets.txt")
    if not os.path.isfile(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [("asset", _rc.parse_line(l)[1]) for l in f.read().splitlines() if l.strip()]


def _semantic_guard(text):
    """chunk 级语义闸：对已 seal 的增量流全文跑 lint（dream 口径）。"""
    return fr_lint.lint_text(text, dream=True)


def _chatlog_sanitize(text):
    """会话日志清洗：长 hex 串折叠（LLM 面本无字节体——防御反馈串与未来扩展）。"""
    import re
    text = re.sub(r"[0-9a-fA-F]{32,}",
                  lambda m: "<hex %d chars>" % len(m.group(0)), text)
    return text


def _parse_ev(spec):
    """--ev "10:mousepressed 320 240" → (帧号, type, args 裸数列表)。"""
    head, _, rest = spec.partition(":")
    toks = rest.split()
    if not toks:
        raise ValueError("--ev 缺 type: %r" % spec)
    return int(head), toks[0], [float(t) for t in toks[1:]]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dream.run")
    ap.add_argument("--frames", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--kit", default="dream")
    ap.add_argument("--from-file")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--dt", type=float, default=1.0 / 15.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--directive", default="一个方块从屏幕左侧匀速走到右侧，顶栏显示进度")
    ap.add_argument("--max-retry", type=int, default=2)
    ap.add_argument("--chunk-frames", type=int, default=0,
                    help="每次生成请求的帧数上限（0=不限；网关超时建议 10）")
    ap.add_argument("--chatlog", default="",
                    help="LLM 会话日志路径（缺省 <out>.chatlog；只记每次追加的提示词与回应）")
    ap.add_argument("--ev", action="append", default=[], metavar='"<帧号>:<type> <args...>"',
                    help='脚本化事件（可多次）：如 --ev "10:mousepressed 320 240"'
                         '——ev 行入流该帧 in 段 + 注入提示词，LLM 续写须响应（M2 第一步）')
    a = ap.parse_args(argv)
    if bool(a.from_file) == a.llm:
        print("dream.run: --from-file 与 --llm 二选一", file=sys.stderr)
        return 2
    drv = ddrv.FromFileDriver(a.from_file) if a.from_file else ddrv.LlmDriver()
    kit_rows = load_kit_rows(a.kit)
    # LLM 模式：append-only messages（system 静态件 + 逐 chunk 追加 turn 对）
    # ——前缀缓存要求从第 0 字节起逐字节相同，滑窗改写中段是反缓存优化
    #（2026-10-31 用户缓存洞察；设计 §5 已同步）。from-file 忽略消息内容。
    messages = []
    if a.llm:
        messages.append({"role": "system", "content": dprompt.build_system(
            dprompt.load_vocab(), dprompt.load_catalog(a.kit), a.width, a.height)})
    frames, stream_text, retry, feedback = [], "", 0, ""
    import time
    chunk_times = []
    # M2 第一步：脚本化 ev——帧号 → [("ev", fields)]（seal 落 in 段）+ 注入提示词
    pending = {}
    for spec in a.ev:
        fno, etype, eargs = _parse_ev(spec)
        pending.setdefault(fno, []).append(
            ("ev", {"slot": 0, "type": etype, "src": 0, "args": eargs}))
    # 会话日志：只记每次追加的 user（剧本前缀首回合后折叠）与 assistant 原文
    # ——append-only 下请求会重发全史，日志按增量记，避免重复与冗长
    log_path = a.chatlog or (a.out + ".chatlog")
    chatlog = open(log_path, "w", encoding="utf-8", newline="\n")
    chatlog.write("# dream 会话日志 %s（model=%s）\n"
                  % (time.strftime("%Y-%m-%d %H:%M:%S"),
                     os.environ.get("LLM_MODEL", "from-file")))

    def _log(tag, text):
        chatlog.write("\n===== %s =====\n%s\n" % (tag, _chatlog_sanitize(text)))
        chatlog.flush()

    if a.llm:
        _log("SYSTEM（静态件，每次请求同文重发——仅记一次）", messages[0]["content"])
    turn_seq = 0
    while len(frames) < a.frames:
        n_left = min(a.chunk_frames, a.frames - len(frames)) if a.chunk_frames \
            else a.frames - len(frames)
        base = len(messages)
        turn_seq += 1
        if a.llm:
            ev_note = ""
            hit = [f for f in pending
                   if len(frames) <= f < len(frames) + n_left]
            if hit:
                ev_note = "\n【用户事件】" + "；".join(
                    "frame %d：%s(%s)——流中已记录该事件，此帧照常书写，"
                    "下一帧起让画面对此做出明确可见的视觉响应"
                    % (f, pending[f][0][1]["type"],
                       ", ".join(str(int(v)) for v in pending[f][0][1]["args"]))
                    for f in sorted(hit))
            messages.append({"role": "user", "content": dprompt.build_turn(
                a.directive, len(frames), n_left, feedback) + ev_note})
            shown = messages[base]["content"]
            if turn_seq > 1 and shown.startswith(a.directive):
                shown = "<剧本同前，略>" + shown[len(a.directive):]
            _log("TURN %d · user（本次追加）" % turn_seq, shown)
        usage_before = dict(drv.usage_totals)
        try:
            t0 = time.perf_counter()
            raw = drv.generate(messages)
            if not a.llm:
                _log("CHUNK %d（from-file）" % turn_seq, raw)
            else:
                _log("TURN %d · assistant（LLM 回应）" % turn_seq, raw)
                du = {k: drv.usage_totals[k] - usage_before.get(k, 0)
                      for k in drv.usage_totals}
                if du:
                    chatlog.write("（本回合 usage 增量: %s）\n" % du)
                    chatlog.flush()
            messages.append({"role": "assistant", "content": raw})
            chunk_frames = dsession.parse_chunk(raw)
            dt_chunk = time.perf_counter() - t0
            chunk_times.append(dt_chunk)
            print("dream.run: chunk %d → %d 帧，%.1fs" %
                  (len(chunk_times), len(chunk_frames), dt_chunk), file=sys.stderr)
            if chunk_frames[0][0] != len(frames):
                raise ValueError("chunk 起始帧号 %d ≠ 期望 %d"
                                 % (chunk_frames[0][0], len(frames)))
            if a.llm and len(chunk_frames) < n_left:
                # 帧数不足打回：短输出进 assistant 历史会成为"少写也行"的
                # 自我示范（心跳 v2 实证：逐帧单写滑坡 28 request/36 帧）
                raise ValueError("要求 %d 帧实得 %d 帧——请按要求的帧数一次写全"
                                 % (n_left, len(chunk_frames)))
            frames += chunk_frames
        except (ValueError, RuntimeError) as e:
            del messages[base:]  # 回滚本轮 user(+assistant)——前缀保持已验状态
            retry += 1
            feedback = "上次输出被拒：%s——请严格按词汇表修正后重出" % str(e)[:300]
            if retry > a.max_retry:
                print("dream.run: 重试上限（%d）：%s" % (a.max_retry, e), file=sys.stderr)
                return 1
            continue
        # 展开降级（Tier2→Tier1）→ seal → 语义闸 → 通过才计入流
        try:
            canon, expanded, dcrcs = dsession.resolve_frames(frames)
            entries = dsession.seal_frames(canon, kit_rows, a.dt, dcrcs,
                                           ev_by_frame=pending)
            has_same = any(op in dsession.TIER1 for _n, rows in canon
                           for op, _ in rows)
            probe = dsession.write_session(
                dsession.build_session(entries, seed=a.seed, has_same=has_same),
                a.out)
        except ValueError as e:
            frames = frames[:len(frames) - len(chunk_frames)]
            del messages[base:]
            retry += 1
            feedback = "上次输出被拒（展开失败）：%s" % str(e)[:300]
            if retry > a.max_retry:
                print("dream.run: 展开重试上限：%s" % e, file=sys.stderr)
                return 1
            continue
        bad = _semantic_guard(probe)
        if bad:
            frames = frames[:len(frames) - len(chunk_frames)]
            del messages[base:]
            retry += 1
            feedback = "上次输出被 lint 拒绝：%s——资产只可引用目录单内的 id" \
                       % "; ".join(bad[:5])[:300]
            if retry > a.max_retry:
                print("dream.run: 语义闸重试上限：%s" % "; ".join(bad), file=sys.stderr)
                return 1
            continue
        stream_text = probe
        retry, feedback = 0, ""
    frames = frames[:a.frames]
    canon, expanded, dcrcs = dsession.resolve_frames(frames)
    entries = dsession.seal_frames(canon, kit_rows, a.dt, dcrcs,
                                   ev_by_frame=pending)
    has_same = any(op in dsession.TIER1 for _n, rows in canon for op, _ in rows)
    text = dsession.write_session(
        dsession.build_session(entries, seed=a.seed, width=a.width,
                               height=a.height, has_same=has_same), a.out)
    diags = fr_lint.lint_text(text, dream=True)
    for d in diags:
        print("lint:", d, file=sys.stderr)
    print("dream.run: %d 帧 → %s（lint %s；chunk 均时 %.1fs）"
          % (len(frames), a.out,
             "全绿" if not diags else "%d 条诊断" % len(diags),
             (sum(chunk_times) / len(chunk_times)) if chunk_times else 0.0))
    if drv.usage_totals:
        print("dream.run: usage %s" % drv.usage_totals, file=sys.stderr)
    _log("DONE", "%d 帧 → %s（lint %s；请求 %d 次）"
         % (len(frames), a.out, "全绿" if not diags else "%d 条诊断" % len(diags),
            turn_seq))
    chatlog.close()
    return 0 if not diags else 1


if __name__ == "__main__":
    sys.exit(main())
