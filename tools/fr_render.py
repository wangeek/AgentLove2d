# tools/fr_render.py
"""fr-render —— 拓扑 B 离线回放驱动（B4 阶段三 Task 3，薄 CLI）。

用法：python tools/fr_render.py <in.fr|in.frb>

驱动 fork 构建 love.exe 的 demo `--offline-replay` 模式（fr_offline_replay：
读流 → 会话解包/解析 → capture_exec_row 同路径执行 → 真 Canvas 回读 →
CRC32），取 stdout 的 `D_CRC <n> <crc>`（n = 已执行帧块数）与末帧
`PIXEL x y r g b` 采样行打印；stderr 透传（含 off 偏移）；rc 透传。
"""
import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORK_LOVE = os.path.join(_ROOT, "megasource", "build115", "love", "Release", "love.exe")
DEMO = os.path.join(_ROOT, "megasource", "libs", "love", "demo")
TIMEOUT = 60


def render(path, timeout=TIMEOUT):
    """离线回放一次：返回 CompletedProcess（bytes 纪律——显式 utf-8 解码归调用方）。"""
    if not os.path.isfile(FORK_LOVE):
        raise SystemExit("fr-render: fork love.exe 不存在：%s（先增量构建 megasource）" % FORK_LOVE)
    env = os.environ.copy()
    env.pop("FR_CAPTURE", None)  # 离线回放消费流不捕获，与开关解耦
    return subprocess.run([FORK_LOVE, DEMO, "--offline-replay", os.path.abspath(path)],
                          capture_output=True, timeout=timeout, env=env, cwd=_ROOT)


def main(argv):
    if len(argv) != 2:
        print("用法: python tools/fr_render.py <in.fr|in.frb>", file=sys.stderr)
        return 2
    path = argv[1]
    if not os.path.isfile(path):
        print("fr-render: 流文件不存在：%s" % path, file=sys.stderr)
        return 2

    r = render(path)
    err = r.stderr.decode("utf-8", "replace")
    if err:
        sys.stderr.write(err)
    for ln in r.stdout.decode("utf-8", "replace").splitlines():
        t = ln.split()
        if t[:1] == ["D_CRC"] or t[:1] == ["PIXEL"]:
            print(ln)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv))
