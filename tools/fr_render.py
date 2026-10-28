# tools/fr_render.py
"""fr-render —— 拓扑 B 离线回放驱动（B4 阶段三 Task 3，薄 CLI）+ 严格档
注入回放（B5 Task 2）。

用法：python tools/fr_render.py <in.fr|in.frb>          离线回放（offline-replay）
      python tools/fr_render.py --sim <in.fr> [--api-parade]
                                                          严格档注入回放（demo --sim；
                                                          parade = 录制 rig 同通道重演）

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

    r = sim(path, parade=parade) if mode == "sim" else render(path)
    err = r.stderr.decode("utf-8", "replace")
    if err:
        sys.stderr.write(err)
    out = r.stdout.decode("utf-8", "replace")
    if mode == "sim":
        sys.stdout.write(out)  # 透传：SIM 帧行 + SUMMARY（判据归调用方）
        if out and not out.endswith("\n"):
            print()
    else:
        for ln in out.splitlines():
            t = ln.split()
            if t[:1] == ["D_CRC"] or t[:1] == ["PIXEL"]:
                print(ln)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv))
