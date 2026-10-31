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
    while len(frames) < a.frames:
        n_left = min(a.chunk_frames, a.frames - len(frames)) if a.chunk_frames \
            else a.frames - len(frames)
        base = len(messages)
        if a.llm:
            messages.append({"role": "user", "content": dprompt.build_turn(
                a.directive, len(frames), n_left, feedback)})
        try:
            t0 = time.perf_counter()
            raw = drv.generate(messages)
            messages.append({"role": "assistant", "content": raw})
            chunk_frames = dsession.parse_chunk(raw)
            dt_chunk = time.perf_counter() - t0
            chunk_times.append(dt_chunk)
            print("dream.run: chunk %d → %d 帧，%.1fs" %
                  (len(chunk_times), len(chunk_frames), dt_chunk), file=sys.stderr)
            if chunk_frames[0][0] != len(frames):
                raise ValueError("chunk 起始帧号 %d ≠ 期望 %d"
                                 % (chunk_frames[0][0], len(frames)))
            frames += chunk_frames
        except (ValueError, RuntimeError) as e:
            del messages[base:]  # 回滚本轮 user(+assistant)——前缀保持已验状态
            retry += 1
            feedback = "上次输出被拒：%s——请严格按词汇表修正后重出" % str(e)[:300]
            if retry > a.max_retry:
                print("dream.run: 重试上限（%d）：%s" % (a.max_retry, e), file=sys.stderr)
                return 1
            continue
        # 增量 seal → 语义闸 → 通过才计入流文本（窗口/最终输出一致）
        entries, has_same = dsession.seal_frames(frames, kit_rows, a.dt)
        probe = dsession.write_session(
            dsession.build_session(entries, seed=a.seed, has_same=has_same),
            a.out)
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
    entries, has_same = dsession.seal_frames(frames, kit_rows, a.dt)
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
    return 0 if not diags else 1


if __name__ == "__main__":
    sys.exit(main())
