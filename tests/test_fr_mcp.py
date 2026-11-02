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


def _tiny_stream(tmp_path, with_asset=False):
    from tools import fr_session as fs
    from tools.fr_gen import tbl
    sha = tbl.tbl_sha256(tbl.parse(
        open(os.path.join(_ROOT, "tables/cmd.tbl"), encoding="utf-8").read()))
    blk = [("dt", {"val": 0.016})]
    if with_asset:
        blk.append(("asset", {"kind": 0, "id": 7, "w": 4, "h": 4,
                              "data": bytes.fromhex("00ff00ff" * 8)}))
    blk += [("clear", {"color": (0, 0, 0, 255)}),
            ("s_crc", {"crc": 0}), ("d_crc", {"crc": 7})]
    s = dict(width=64, height=48, sha=sha, loglvl="base", seed=1,
             entries=[("frame", blk)])
    p = tmp_path / "s.fr"
    p.write_text(fs.dump_text(s), encoding="utf-8", newline="\n")
    return str(p)


def test_mcp_three_tools_and_read_strip(tmp_path):
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
        assert names == ["fr_record", "fr_read", "fr_diff"]   # 精简三件
        st = _tiny_stream(tmp_path, with_asset=True)
        r = _rpc(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": "fr_read",
                                   "arguments": {"stream": st}}})
        text = r["result"]["content"][0]["text"]
        assert "frame 0" in text and "clear 0 0 0 255" in text
        # 资产 hex 剥离：摘要行在（参数原样+真字节数）、原始 hex 不在
        assert "asset image 7 4 4 (+32B hex)" in text
        assert "00ff00ff" not in text
    finally:
        proc.kill()


def test_mcp_vocab_in_read_description(tmp_path):
    """fr_read description 内含 op 词汇表，版本号与 cmd.tbl 表头一致（防漂移）。"""
    proc = _srv()
    try:
        r = _rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        desc = {t["name"]: t["description"]
                for t in r["result"]["tools"]}["fr_read"]
        head = open(os.path.join(_ROOT, "tables/cmd.tbl"),
                    encoding="utf-8").readline()
        ver = head.split("v", 2)[-1].strip()          # 表头 "… v1.2"
        assert ("v%s" % ver) in desc                   # 版本随表走
        for op in ("dt", "asset", "ev", "st", "clear", "draw", "print",
                   "rect", "rt", "scissor", "d_crc",       # 基础面代表
                   "CP", "SET", "INS", "DEL", "MOVE", "POSE", "ENTER",
                   "EXIT"):                                # delta 编辑面代表
            assert op in desc, op
    finally:
        proc.kill()


def test_mcp_diff(tmp_path):
    proc = _srv()
    try:
        st = _tiny_stream(tmp_path)
        st2 = tmp_path / "s2.fr"
        st2.write_text(open(st, encoding="utf-8").read().replace(
            "clear 0 0 0 255", "clear 1 1 1 255"), encoding="utf-8",
            newline="\n")
        r = _rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                        "params": {"name": "fr_diff",
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
