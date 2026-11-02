# tools/fr_mcp.py
"""fr-mcp：FR 工具族 MCP 薄壳（stdio JSON-RPC 2.0，零依赖——纯标准库）。

fr-rationale §五 接口面的实装：每个 MCP 工具对应一个已有 CLI（fr_record
= love.exe + env），MCP 层只做参数组装/子进程调用/输出封顶——工具无状态，
状态全在流与判据文件里。**只流通文本与数字**（D10 符号结算律）。

工具面（tools/list 自描述）：
  fr_record(game_dir, out, frames?, dt?, seed?, timeout?) → headless 确定性录制
  fr_read(stream, frames?)            → canonical 文本（默认剥离资产 hex；全量走 CLI fr_dump）
  fr_diff(a, b, first_only?)          → 首分歧帧+行 diff（fr-diff）

裁撤记录（2026-11-02 用户精简）：fr_grep（read 后 agent 自过滤）、
fr_check（agent 对 read 结果自判）、fr_stats（无评价锚前暂缓）——MCP 面
只留 agent 自己做不方便的事（env 组装/大文件读/双流对齐）。

运行：python tools/fr_mcp.py（stdio；一行一条 JSON-RPC 消息）。
注册：工作区 .mcp.json（用户 MCP 作用域策略——全局禁用，工作区按需）。
"""
import json
import os
import re
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOVE = os.path.join(_ROOT, "megasource", "build115", "love", "Release", "love.exe")
_PY = sys.executable
_CAP = 100_000  # 单响应文本封顶（字节）——防 38MB 流灌爆上下文


def _tbl_sha():
    from tools.fr_gen import tbl
    with open(os.path.join(_ROOT, "tables", "cmd.tbl"), encoding="utf-8") as f:
        return tbl.tbl_sha256(tbl.parse(f.read()))


def _cli(script, *args, timeout=60):
    r = subprocess.run([_PY, os.path.join(_ROOT, "tools", script), *args],
                       capture_output=True, cwd=_ROOT, timeout=timeout)
    out = r.stdout.decode("utf-8", "replace")
    err = r.stderr.decode("utf-8", "replace")
    return r.returncode, out, err


def _cap(text):
    if len(text) > _CAP:
        return text[:_CAP] + "\n…（截断：共 %d 字节，用 frames/max_lines 收窄）" % len(text)
    return text


# ---- 工具实现（参数 dict → (ok, text)）----

def t_fr_record(p):
    out = os.path.abspath(p["out"])
    env = dict(os.environ, FR_CAPTURE="1", FR_OUT=out, FR_SHA=_tbl_sha(),
               FR_HEADLESS="1")
    if p.get("frames"):
        env["FR_FRAMES"] = str(int(p["frames"]))
    if p.get("dt"):
        env["FR_DT"] = str(float(p["dt"]))
    if p.get("seed"):
        env["FR_SEED"] = str(int(p["seed"]))
    try:
        r = subprocess.run([_LOVE, os.path.abspath(p["game_dir"])], env=env,
                           cwd=_ROOT, capture_output=True,
                           timeout=float(p.get("timeout", 120)))
    except subprocess.TimeoutExpired:
        return False, "录制超时（调大 timeout 或减 frames）"
    except OSError as e:
        return False, "love.exe 启动失败：%s" % e
    size = os.path.getsize(out) if os.path.isfile(out) else -1
    n = 0
    if size > 0:
        with open(out, "rb") as f:
            n = sum(1 for ln in f if ln.startswith(b"frame "))
    return r.returncode == 0 and size > 0, \
        "rc=%d out=%s bytes=%d frames=%d%s" % (
            r.returncode, out, size, n,
            "\nstderr 尾：" + r.stderr.decode("utf-8", "replace")[-400:]
            if r.returncode != 0 else "")


def t_fr_read(p):
    """读流 canonical 文本。默认剥离资产 hex（--strip-assets——观察面）；
    全量（含字节体，文件级再消费用）走 CLI：python tools/fr_dump.py <stream>。"""
    args = [p["stream"], "--strip-assets"]
    if p.get("frames"):
        args += ["--frames", str(p["frames"])]
    rc, out, err = _cli("fr_dump.py", *args)
    return rc == 0, _cap(out) if rc == 0 else err[-_CAP:]


def t_fr_diff(p):
    args = [p["a"], p["b"]]
    if p.get("first_only"):
        args.append("--first-only")
    rc, out, err = _cli("fr_diff.py", *args)
    return rc != 2, (out + err).strip()[-_CAP:]   # rc 0=全同 1=分歧（都算成功执行）


_TOOLS = [
    ("fr_record", "确定性录制一段 LÖVE 游戏会话产出 .fr（零游戏侧改动；"
     "FR_CAPTURE/FR_OUT/FR_SHA/FR_HEADLESS env 通道；sha 自动算）",
     {"type": "object", "properties": {
        "game_dir": {"type": "string"}, "out": {"type": "string"},
        "frames": {"type": "integer"}, "dt": {"type": "number"},
        "seed": {"type": "integer"}, "timeout": {"type": "number"}},
      "required": ["game_dir", "out"]}, t_fr_record),
    ("fr_read", "读流的 canonical 文本（默认剥离资产 hex——帧内容/结构/事件；"
     "frames 选帧视图，如 \"0-5\"。全量含字节体走 CLI fr_dump）。\n"
     "op 词汇表 v1.2（真源 tables/cmd.tbl，sha256 入会话头；行=op 参数名…，"
     "f32 文本 %.6f，rgba8 四整数，str 带引号）：\n"
     "骨架：frb1 <w> <h> <sha> <档 base/full> <seed> 头行｜frame N 帧始｜"
     "cmnt 注释｜dt f 帧首步长｜s_crc u32 状态根CRC + d_crc u32 当帧out行CRC（帧尾双行）\n"
     "head：asset image <id> <w> <h> <hex> / canvas <id> <w> <h> / "
     "quad <id> <x> <y> <w> <h> <sw> <sh> / font <id> <size> <hex>（资产注册，首帧全量）\n"
     "in：ev <slot> <type> <src> args… 输入事件（签名=love.event.push 参数序，src 0=OS/1=合成/2=自定义）｜"
     "call <slot> <fn> <depth> args… 函数调用｜timer <slot> <id> 定时器到期\n"
     "log：rngc <seed> 随机数边界｜st <obj> \"key\" <val> 堆镜像diff（full 级）｜err \"what\" 未收录API/兜底\n"
     "out 绘制：clear <r g b a>｜draw <tex> <quad> <x> <y> <rot> <sx> <sy> <ox> <oy> <rgba>（quad 0=整图）｜"
     "print <font> \"text\" <x> <y> …｜rect <mode> <x> <y> <w> <h> <rx> <ry> <width>（mode 0=fill 1=line）｜"
     "line \"x y …\" <width>｜poly <mode> \"pts\"｜circle <mode> <x> <y> <r> <seg>｜"
     "arc <mode> <arctype> <x> <y> <r> <a1> <a2> <seg>｜points \"pts\" <size>｜"
     "rt <target> 画布切换（0=屏幕）｜scissor <x> <y> <w> <h> 裁剪\n"
     "out 编辑（frame-delta v1.5）：CP <ref> 本帧行集=ref 帧行集（ref 省=上一帧）｜"
     "SET <asset> <k> <param> <val> 单参绝对更新｜INS <pos> \"line\" 行插入｜DEL <pos> 删行｜"
     "MOVE <asset> <k> <dx> <dy> 相对位移｜PLACE <asset> <k> <x> <y> 绝对置位｜"
     "POSE <asset> <k> \"line\" 整行替换｜ENTER \"line\" 对象入场｜EXIT <asset> <k> 对象离场",
     {"type": "object", "properties": {
        "stream": {"type": "string"}, "frames": {"type": "string"}},
      "required": ["stream"]}, t_fr_read),
    ("fr_diff", "两流帧对齐 diff：首分歧帧 + 行级差异（回归定位/bisect 语义）；"
     "行内 op 词汇见 fr_read 描述的词汇表",
     {"type": "object", "properties": {
        "a": {"type": "string"}, "b": {"type": "string"},
        "first_only": {"type": "boolean"}},
      "required": ["a", "b"]}, t_fr_diff),
]


def _res(id_, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": id_, "result": result},
                                ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _err(id_, code, msg):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": id_,
                                 "error": {"code": code, "message": msg}},
                                ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    # Windows 管道下 stdio 缺省本地编码（GBK）——ensure_ascii=False 的中文
    # 消息会炸/乱（2026-11-01 同族教训）；强制 UTF-8 + 行缓冲
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stdin.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        m, id_ = msg.get("method"), msg.get("id")
        if m == "initialize":
            _res(id_, {"protocolVersion": msg.get("params", {}).get(
                "protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fr-tools", "version": "0.1.0"}})
        elif m == "notifications/initialized" or m.startswith("notifications/"):
            pass  # 通知无响应
        elif m == "ping":
            _res(id_, {})
        elif m == "tools/list":
            _res(id_, {"tools": [
                {"name": n, "description": d, "inputSchema": s}
                for n, d, s, _f in _TOOLS]})
        elif m == "tools/call":
            name = msg.get("params", {}).get("name")
            fn = next((f for n, _d, _s, f in _TOOLS if n == name), None)
            if fn is None:
                _err(id_, -32602, "未知工具: %r" % name)
                continue
            try:
                ok, text = fn(msg.get("params", {}).get("arguments", {}))
                _res(id_, {"content": [{"type": "text", "text": text}],
                           "isError": not ok})
            except Exception as e:  # 工具异常不炸服务
                _res(id_, {"content": [{"type": "text",
                                        "text": "工具异常: %s" % e}],
                           "isError": True})
        elif id_ is not None:
            _err(id_, -32601, "未知方法: %r" % m)


if __name__ == "__main__":
    main()
