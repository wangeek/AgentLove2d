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
    """kit assets.txt → [(op, fields)]（原样回放进首帧）。"""
    p = os.path.join(kit_dir, "assets.txt")
    if not os.path.isfile(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [_rc.parse_line(l) for l in f.read().splitlines() if l.strip()]


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
    ap.add_argument("--window-k", type=int, default=8)
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
    vocab = dprompt.load_vocab()
    catalog = dprompt.load_catalog(a.kit)
    frames, stream_text, retry = [], "", 0
    while len(frames) < a.frames:
        directive = a.directive
        if a.chunk_frames > 0:
            directive += "；本次只输出 %d 帧" % min(a.chunk_frames, a.frames - len(frames))
        prompt = dprompt.build_prompt(vocab, catalog,
                                      dprompt.sliding_window(stream_text, a.window_k),
                                      directive, len(frames))
        try:
            chunk_frames = dsession.parse_chunk(drv.generate(prompt))
            if chunk_frames[0][0] != len(frames):
                raise ValueError("chunk 起始帧号 %d ≠ 期望 %d"
                                 % (chunk_frames[0][0], len(frames)))
            frames += chunk_frames
        except (ValueError, RuntimeError) as e:
            retry += 1
            if retry > a.max_retry:
                print("dream.run: 重试上限（%d）：%s" % (a.max_retry, e), file=sys.stderr)
                return 1
            continue
        # 增量 seal → 语义闸 → 通过才计入流文本（窗口/最终输出一致）
        probe = dsession.write_session(
            dsession.build_session(dsession.seal_frames(frames, kit_rows, a.dt),
                                   seed=a.seed), a.out)
        bad = _semantic_guard(probe)
        if bad:
            frames = frames[:len(frames) - len(chunk_frames)]
            retry += 1
            if retry > a.max_retry:
                print("dream.run: 语义闸重试上限：%s" % "; ".join(bad), file=sys.stderr)
                return 1
            continue
        stream_text = probe
        retry = 0
    frames = frames[:a.frames]
    text = dsession.write_session(
        dsession.build_session(dsession.seal_frames(frames, kit_rows, a.dt),
                               seed=a.seed, width=a.width, height=a.height), a.out)
    diags = fr_lint.lint_text(text, dream=True)
    for d in diags:
        print("lint:", d, file=sys.stderr)
    print("dream.run: %d 帧 → %s（lint %s）" % (len(frames), a.out,
          "全绿" if not diags else "%d 条诊断" % len(diags)))
    return 0 if not diags else 1


if __name__ == "__main__":
    sys.exit(main())
