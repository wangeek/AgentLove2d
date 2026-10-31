# tools/fr_render.py
"""fr-render —— 拓扑 B 离线回放驱动（B4 阶段三 Task 3，薄 CLI）+ 严格档
注入回放（B5 Task 2）。

用法：python tools/fr_render.py <in.fr|in.frb> [--record out.mp4]   离线回放
      python tools/fr_render.py --sim <in.fr> [--api-parade]        严格档注入回放

--record out.mp4：离线回放逐帧像素（FR_VIDEO_OUT 倾倒，C 侧 FR_VIDEO_OUT
env 挂点）→ FFmpeg 封装 mp4（帧率=流尾 dt）。审看介质：不进判据。

离线回放：驱动 fork 构建 love.exe 的 demo `--offline-replay` 模式
（fr_offline_replay：读流 → 会话解包/解析 → capture_exec_row 同路径执行 →
真 Canvas 回读 → CRC32），取 stdout 的 `D_CRC <n> <crc>`（n = 已执行帧块数）
与末帧 `PIXEL x y r g b` 采样行打印；stderr 透传（含 off 偏移）；rc 透传。

严格档注入回放（--sim）：驱动 demo `--sim` 模式（内核重演——逐帧把录制 ev
行还原 push 进事件队列、同录制链路 poll 分发、kernel.update 吃录制 dt、
FR_CAPTURE=1 捕获再生 out 行与录制逐行比对）；stdout 全量透传（`SIM <n>
MATCH|MISMATCH` 帧行 + `SIM SUMMARY`）；rc 透传（全 MATCH=0，任一 MISMATCH=1）。
"""
import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# subprocess 超时：FR_RENDER_TIMEOUT 可调（秒，缺省 60）——大流播放
#（FR_PLAY，240 帧含每帧 Canvas 回读）实测超 60s，被工具层误杀（B11 实证）。
TIMEOUT = int(os.environ.get("FR_RENDER_TIMEOUT", "60"))
FORK_LOVE = os.path.join(_ROOT, "megasource", "build115", "love", "Release", "love.exe")
DEMO = os.path.join(_ROOT, "megasource", "libs", "love", "demo")
TIMEOUT = 60


def render(path, timeout=TIMEOUT, video_out=None):
    """离线回放一次：返回 CompletedProcess（bytes 纪律——显式 utf-8 解码归调用方）。

    video_out：非 None 时透传 FR_VIDEO_OUT（C 侧逐帧像素倾倒——--record 用）。
    """
    if not os.path.isfile(FORK_LOVE):
        raise SystemExit("fr-render: fork love.exe 不存在：%s（先增量构建 megasource）" % FORK_LOVE)
    env = os.environ.copy()
    env.pop("FR_CAPTURE", None)  # 离线回放消费流不捕获，与开关解耦
    if video_out:
        env["FR_VIDEO_OUT"] = video_out
    return subprocess.run([FORK_LOVE, DEMO, "--offline-replay", os.path.abspath(path)],
                          capture_output=True, timeout=timeout, env=env, cwd=_ROOT)


def sim(path, timeout=TIMEOUT, parade=False):
    """严格档注入回放一次（--sim）：FR_CAPTURE 必须=1（重演捕获再生 out 行，
    demo 侧另有自查），与 render 的开关口径相反。parade=True 透传
    --api-parade——录制 rig 用了该通道时重演必须同通道（内核路径须一致）。"""
    if not os.path.isfile(FORK_LOVE):
        raise SystemExit("fr-render: fork love.exe 不存在：%s（先增量构建 megasource）" % FORK_LOVE)
    env = os.environ.copy()
    env["FR_CAPTURE"] = "1"
    argv = [FORK_LOVE, DEMO, "--sim", os.path.abspath(path)]
    if parade:
        argv.append("--api-parade")
    return subprocess.run(argv, capture_output=True, timeout=timeout, env=env, cwd=_ROOT)


def main(argv):
    if len(argv) >= 3 and argv[1] == "--sim":
        mode, path = "sim", argv[2]
        parade = "--api-parade" in argv[3:]  # 透传 demo 通道旗标（白名单制）
    elif len(argv) == 2:
        mode, path, parade = "render", argv[1], False
    else:
        print("用法: python tools/fr_render.py <in.fr|in.frb> | --sim <in.fr> [--api-parade]", file=sys.stderr)
        return 2
    if not os.path.isfile(path):
        print("fr-render: 流文件不存在：%s" % path, file=sys.stderr)
        return 2

def _record_mp4(raw_path, w, h, fps, mp4_path):
    """rawvideo(RGBA) → mp4（FFmpeg 8.0.1 @ D:/Lab/ffmpeg-8.0.1-essentials_build）。"""
    import subprocess
    ff = r"D:\Lab\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe"
    if not os.path.isfile(ff):
        raise SystemExit("fr-render: ffmpeg 不存在：%s" % ff)
    cmd = [ff, "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", "%dx%d" % (w, h),
           "-r", str(fps), "-i", raw_path,
           "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "18", mp4_path]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr.decode("utf-8", "replace")[-500:])
        raise SystemExit("fr-render: ffmpeg 编码失败")


def main(argv):
    path = None
    record = None
    rest = []
    i = 1
    while i < len(argv):
        if argv[i] == "--record" and i + 1 < len(argv):
            record = argv[i + 1]
            i += 2
            continue
        rest.append(argv[i])
        i += 1
    if len(rest) >= 2 and rest[0] == "--sim":
        mode, path = "sim", rest[1]
        parade = "--api-parade" in rest[2:]
    elif len(rest) == 1:
        mode, path, parade = "render", rest[0], False
    else:
        print("用法: python tools/fr_render.py <in.fr|in.frb> [--record out.mp4]"
              " | --sim <in.fr> [--api-parade]", file=sys.stderr)
        return 2

    if mode == "sim":
        r = sim(path, parade=parade)
        err = r.stderr.decode("utf-8", "replace")
        if err:
            sys.stderr.write(err)
        out = r.stdout.decode("utf-8", "replace")
        sys.stdout.write(out)  # 透传：SIM 帧行 + SUMMARY（判据归调用方）
        if out and not out.endswith("\n"):
            print()
    else:
        # --record：C 侧像素倾倒（FR_VIDEO_OUT）→ rawvideo → FFmpeg mp4
        raw_path = None
        if record is not None:
            import tempfile
            raw_fd, raw_path = tempfile.mkstemp(suffix=".raw")
            os.close(raw_fd)
            r = render(path, video_out=raw_path)
        else:
            r = render(path)
        err = r.stderr.decode("utf-8", "replace")
        if err:
            sys.stderr.write(err)
        out = r.stdout.decode("utf-8", "replace")
        n_frames = 0
        for ln in out.splitlines():
            t = ln.split()
            if t[:1] in (["D_CRC"], ["PIXEL"]):
                print(ln)
            if t[:1] == ["D_CRC"]:
                n_frames = int(t[1])
        if record is not None:
            import struct
            # 流尾 dt（帧率）与流头尺寸
            fps, w, h = 15.0, 0, 0
            try:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    for ln in f:
                        t = ln.split()
                        if t[0] == "frb1":
                            w, h = int(t[1]), int(t[2])
                        elif t[0] == "dt" and float(t[1]) > 0:
                            fps = max(1.0, min(60.0, 1.0 / float(t[1])))
            except Exception:
                pass
            import os as _os
            raw_size = _os.path.getsize(raw_path)
            if w and h and raw_size >= w * h * 4:
                _record_mp4(raw_path, w, h, fps, record)
                print("fr-render: %d 帧 → %s（%dfps，raw %d bytes）"
                      % (n_frames, record, int(fps), raw_size))
            else:
                print("fr-render: 像素倾倒不足（raw %d bytes，期待 %d）——未编码"
                      % (raw_size, w * h * 4), file=sys.stderr)
            _os.remove(raw_path)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv))
