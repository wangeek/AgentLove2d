# tests/test_fr_mcp.py —— MCP 薄壳协议测试（真子进程 stdio JSON-RPC）
import json
import os
import subprocess
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)


def _srv():
    return subprocess.Popen(
        [sys.executable, os.path.join(_ROOT, "tools", "fr_mcp.py")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, cwd=_ROOT, text=True, encoding="utf-8")


def _rpc(proc, obj):
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    return json.loads(line)


def _tiny_stream(tmp_path):
    from tools import fr_session as fs
    from tools.fr_gen import tbl
    sha = tbl.tbl_sha256(tbl.parse(
        open(os.path.join(_ROOT, "tables/cmd.tbl"), encoding="utf-8").read()))
    blk = [("dt", {"val": 0.016}), ("clear", {"color": (0, 0, 0, 255)}),
           ("s_crc", {"crc": 0}), ("d_crc", {"crc": 7})]
    s = dict(width=64, height=48, sha=sha, loglvl="base", seed=1,
             entries=[("frame", blk)])
    p = tmp_path / "s.fr"
    p.write_text(fs.dump_text(s), encoding="utf-8")
    return str(p)


def test_mcp_initialize_list_read(tmp_path):
    proc = _srv()
    try:
        r = _rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05"}})
        assert r["result"]["serverInfo"]["name"] == "fr-tools"
        proc.stdin.write(json.dumps({"jsonrpc": "2.0",
                                     "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()
        r = _rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [t["name"] for t in r["result"]["tools"]]
        assert "fr_read" in names and "fr_check" in names and "fr_diff" in names
        st = _tiny_stream(tmp_path)
        r = _rpc(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": "fr_read",
                                   "arguments": {"stream": st}}})
        text = r["result"]["content"][0]["text"]
        assert "frame 0" in text and "clear 0 0 0 255" in text
        assert r["result"]["isError"] is False
        # fr_grep：命中行 + 帧头上下文
        r = _rpc(proc, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                        "params": {"name": "fr_grep",
                                   "arguments": {"stream": st,
                                                 "pattern": "clear"}}})
        assert "frame 0" in r["result"]["content"][0]["text"]
    finally:
        proc.kill()


def test_mcp_check_and_diff(tmp_path):
    proc = _srv()
    try:
        st = _tiny_stream(tmp_path)
        st2 = tmp_path / "s2.fr"
        st2.write_text(open(st, encoding="utf-8").read().replace(
            "clear 0 0 0 255", "clear 1 1 1 255"), encoding="utf-8")
        r = _rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                        "params": {"name": "fr_check",
                                   "arguments": {"stream": st}}})
        assert "CHECK OK" in r["result"]["content"][0]["text"]
        r = _rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                        "params": {"name": "fr_diff", "strict": False,
                                   "arguments": {"a": st, "b": str(st2),
                                                 "first_only": True}}})
        text = r["result"]["content"][0]["text"]
        assert "FIRST-DIVERGENCE 0" in text and "- clear 0 0 0" in text
    finally:
        proc.kill()


def test_mcp_unknown_tool_error():
    proc = _srv()
    try:
        r = _rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                        "params": {"name": "nope", "arguments": {}}})
        assert r["error"]["code"] == -32602
    finally:
        proc.kill()
