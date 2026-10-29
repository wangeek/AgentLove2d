# tools/fr_session.py
"""会话级封装（B1 封版）：.fr canonical 文本 ↔ Session ↔ .frb 二进制。

Session = dict(width, height, sha, loglvl, seed,
               entries=[("cmnt", text) | ("frame", [(op, fields), ...]), ...])

本模块处理的是**结构性行**（会话头 / cmnt / frame 定界），不随 cmd.tbl 变化，
是手写库——**不随 cmd.tbl 重新生成**（行级编解码才由 fr-gen 从表生成，
见 tools/fr_codec_gen.py）。封装布局与错误口径见 docs/plans/2026-10-27-fr-as-b1.md
"会话封装 v1"（fr-spec §6.3 由 B1 Task 6 回写）。

错误口径：文本侧 SessionError 含行号（1 起计，头为第 1 行）；二进制侧含偏移
（0 起计）；行级错误包装 row codec 的 ValueError 透传。
"""
import binascii, re
from tools import fr_codec_gen as _rc

MAGIC = b"FRB1"
VERSION = 1
_HEADER_LEN = 4 + 1 + 2 + 2 + 32 + 1 + 8  # magic+version+w+h+sha+loglvl+seed = 50
TAG_FRAME = 0x01
TAG_CMNT = 0xFF
_LOGLVL = {"off": 0, "base": 1, "full": 2}
_LOGLVL_NAME = {v: k for k, v in _LOGLVL.items()}
# B14 精度档（head 可选尾列 :prec；缺省 full=旧流兼容）。q64 档位名预留
#（本批转换器只实现 px；q64 渲染待动画域需求落地）。
_PREC = ("full", "px", "q64")


class SessionError(Exception):
    """会话级封装错误（文本含行号 / 二进制含偏移）。"""


# ---------- 文本（.fr canonical：LF 结尾、无空行） ----------

def parse_text(text):
    """canonical 文本 → Session；结构错误 raise SessionError 含行号。

    分列一律用原行、不做整行 strip（B0 尾随 tab 教训的一致性防御）；
    strip 只用于空行判断。canonical 以单个 LF 结尾：split("\\n") 后的
    末尾空串必须被消费，否则视为未以 LF 结尾。
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    else:
        raise SessionError("文本必须以单个 LF 结尾")
    if not lines:
        raise SessionError("空文本：缺会话头")
    hdr = lines[0].split(" ")
    if hdr[0] != "frb1" or len(hdr) not in (6, 7):
        raise SessionError("第 1 行：会话头必须为 'frb1 w h sha loglvl seed [:prec]'")
    prec = hdr[6] if len(hdr) == 7 else "full"
    if prec.lstrip(":") not in _PREC:
        raise SessionError("第 1 行：精度档非法 %r（合法：%s）"
                           % (prec, "|".join(":" + p for p in _PREC)))
    prec = prec.lstrip(":")
    w, h, sha, loglvl, seed = hdr[1], hdr[2], hdr[3], hdr[4], hdr[5]
    if not (w.isdigit() and h.isdigit() and 0 < int(w) <= 65535 and 0 < int(h) <= 65535):
        raise SessionError("第 1 行：几何非法")
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise SessionError("第 1 行：sha 必须为 64 位小写十六进制")
    if loglvl not in _LOGLVL:
        raise SessionError("第 1 行：loglvl 非法 %r" % loglvl)
    if not seed.isdigit() or int(seed) >= 1 << 64:
        raise SessionError("第 1 行：seed 非法")
    s = dict(width=int(w), height=int(h), sha=sha, loglvl=loglvl, seed=int(seed),
             prec=prec, entries=[])
    cur = None  # 当前帧的 rows 列表（None = 帧外）
    for no, line in enumerate(lines[1:], start=2):
        if not line.strip():  # 空行（含纯空白行）禁入 canonical
            raise SessionError("第 %d 行：空行禁入 canonical" % no)
        if line.startswith("cmnt "):
            body = line[5:]  # "cmnt " 之后逐字保留
            if "\r" in body:
                raise SessionError("第 %d 行：cmnt 禁含 \\r" % no)
            # cmnt 可在任意两帧之间（含首帧前/末帧后）；cmnt 行即宣告帧块结束
            #（"帧内禁 CMNT"由二进制帧体保证：0xFF 非 row codec 合法 opcode）
            cur = None
            s["entries"].append(("cmnt", body))
        elif line.startswith("frame "):
            n = line[6:]
            idx = sum(1 for k, _ in s["entries"] if k == "frame")
            if not n.isdigit() or int(n) != idx:
                raise SessionError("第 %d 行：帧号必须为 %d（连续）" % (no, idx))
            cur = []
            s["entries"].append(("frame", cur))
        else:
            if cur is None:
                raise SessionError("第 %d 行：行必须位于 frame 块内" % no)
            try:
                # B14：按档分派（:px 流行=短名/省略形，parse_line_px 回填默认
                # 后与 full 字段等价——Session 内部表示与档位无关）。
                cur.append(_rc.parse_line_px(line) if prec != "full"
                           else _rc.parse_line(line))
            except ValueError as e:
                raise SessionError("第 %d 行：%s" % (no, e)) from e
    return s


def _validate_session(s):
    """dump 前共享校验（文本/二进制两出口同一口径）；非法 raise SessionError。

    只查头字段域与 entries 结构，不做行级校验（render/encode 的 ValueError
    由 dump 调用处包装 entry 序号透传）；对合法 Session 无副作用，
    不改变 canonical 输出（全量回归守护）。
    """
    if not (isinstance(s.get("width"), int) and 1 <= s["width"] <= 65535
            and isinstance(s.get("height"), int) and 1 <= s["height"] <= 65535):
        raise SessionError("width/height 须为 [1,65535] 整数")
    if not (isinstance(s.get("sha"), str) and re.fullmatch(r"[0-9a-f]{64}", s["sha"])):
        raise SessionError("sha 须为 64 位小写十六进制")
    if s.get("loglvl") not in _LOGLVL:
        raise SessionError("loglvl 非法 %r" % (s.get("loglvl"),))
    if not (isinstance(s.get("seed"), int) and 0 <= s["seed"] < (1 << 64)):
        raise SessionError("seed 须为 [0,2^64) 整数")
    if s.get("prec", "full") not in _PREC:
        raise SessionError("精度档非法 %r" % (s.get("prec"),))
    for no, entry in enumerate(s["entries"]):
        if not (isinstance(entry, tuple) and len(entry) == 2):
            raise SessionError("entry %d：须为 (kind, payload) 二元组" % no)
        kind, payload = entry
        if kind == "cmnt":
            if "\r" in payload or "\n" in payload:
                raise SessionError("entry %d：cmnt 禁含 \\r \\n" % no)
        elif kind == "frame":
            for row in payload:
                if not (isinstance(row, tuple) and len(row) == 2):
                    raise SessionError("entry %d：frame 元素须为 (op, fields) 二元组" % no)
        else:
            raise SessionError("entry %d：kind 非法 %r" % (no, kind))


def dump_text(s):
    """Session → canonical 文本（"\\n".join + 尾部单 LF）；cmnt 禁含 \\r \\n。

    头部 loglvl 写名字（off|base|full，与 parse_text 校验对称）；
    二进制形态才写数字（见 dump_binary）。
    """
    _validate_session(s)
    head = "frb1 %d %d %s %s %d" % (s["width"], s["height"], s["sha"],
                                     s["loglvl"], s["seed"])
    prec = s.get("prec", "full")
    if prec != "full":  # B14：非缺省档显式标注（旧流头形零变化）
        head += " :" + prec
    out = [head]
    idx = 0
    render = _rc.render_line_px if prec != "full" else _rc.render_line
    for entry_no, (kind, payload) in enumerate(s["entries"]):
        if kind == "cmnt":
            out.append("cmnt " + payload)
        else:
            out.append("frame %d" % idx); idx += 1
            for op, fields in payload:
                try:
                    out.append(render(op, fields))
                except ValueError as e:
                    raise SessionError("entry %d：%s" % (entry_no, e)) from e
    return "\n".join(out) + "\n"


# ---------- 二进制（.frb，小端） ----------

def parse_binary(data):
    """二进制 → Session；结构错误 raise SessionError 含偏移（0 起计）。"""
    if data[:4] != MAGIC:
        raise SessionError("off 0：magic 错误（需 FRB1）")
    if len(data) < _HEADER_LEN:
        raise SessionError("off 0：头部截断（需 %d 字节，得 %d）" % (_HEADER_LEN, len(data)))
    if data[4] != VERSION:
        raise SessionError("off 4：版本不支持 %d" % data[4])
    off = 5
    w = int.from_bytes(data[off:off + 2], "little"); off += 2
    h = int.from_bytes(data[off:off + 2], "little"); off += 2
    sha = data[off:off + 32].hex(); off += 32
    lvl = data[off]; off += 1
    if lvl not in _LOGLVL_NAME:
        raise SessionError("off %d：loglvl 非法 %d" % (off - 1, lvl))
    seed = int.from_bytes(data[off:off + 8], "little"); off += 8
    s = dict(width=w, height=h, sha=sha, loglvl=_LOGLVL_NAME[lvl], seed=seed,
             prec="full", entries=[])
    while off < len(data):
        tag = data[off]; off += 1
        if tag == TAG_CMNT:
            n = int.from_bytes(data[off:off + 4], "little"); off += 4
            if off + n > len(data):
                raise SessionError("off %d：cmnt 截断（需 %d 字节，余 %d）"
                                   % (off, n, len(data) - off))
            try:
                body = data[off:off + n].decode("utf-8")
            except UnicodeDecodeError as e:
                raise SessionError("off %d：cmnt UTF-8 非法" % off) from e
            off += n
            s["entries"].append(("cmnt", body))
        elif tag == TAG_FRAME:
            n = int.from_bytes(data[off:off + 4], "little"); off += 4
            if off + n > len(data):
                raise SessionError("off %d：帧体截断（需 %d 字节，余 %d）"
                                   % (off, n, len(data) - off))
            body = data[off:off + n]; off += n
            s["entries"].append(("frame", _parse_frame_body(body)))
        else:
            raise SessionError("off %d：entry tag 非法 0x%02X" % (off - 1, tag))
    return s


def _parse_frame_body(body):
    """帧体 bytes → rows 列表。

    行长求解：B0 的 decode_row 严格校验整段消费（行尾冗余即 ValueError），
    无法对"剩余帧体"直接解码；故对每个行起点以尝试长度自 2 起递增逼近（O(L²)——cursor 变体即消除），
    decode_row 只在恰好行长处成功（短则截断、长则冗余，成功点唯一），
    成功后按计划口径用"重编码长度"推进游标——B0 无 cursor 变体的务实解。
    代价：每帧 O(行长²) 次解码尝试（B1 规模的样例帧毫无压力）；B1 之后
    若需流式/大帧可给 decode_row 加 cursor 变体（B1 终审建议②），
    届时本函数只改游标推进一行。正确性由 round-trip 测试保证。
    """
    rows, mv, i = [], memoryview(body), 0
    while i < len(body):
        for end in range(2, len(mv) - i + 1):
            try:
                op, fields = _rc.decode_row(mv[i:i + end])
                break
            except ValueError:
                continue
        else:
            raise SessionError("帧内 off %d：行解码失败（截断或编解码不一致）" % i)
        rows.append((op, fields))
        i += len(_rc.encode_row(op, fields))
    return rows


def dump_binary(s):
    """Session → 二进制（header 50B + entries 按 entries 列表序原样重复至 EOF）。"""
    _validate_session(s)
    out = [MAGIC, bytes([VERSION]),
           s["width"].to_bytes(2, "little"), s["height"].to_bytes(2, "little"),
           binascii.unhexlify(s["sha"]),
           bytes([_LOGLVL[s["loglvl"]]]), s["seed"].to_bytes(8, "little")]
    for entry_no, (kind, payload) in enumerate(s["entries"]):
        if kind == "cmnt":
            b = payload.encode("utf-8")
            out.append(bytes([TAG_CMNT]) + len(b).to_bytes(4, "little") + b)
        else:
            try:
                body = b"".join(_rc.encode_row(op, f) for op, f in payload)
            except ValueError as e:
                raise SessionError("entry %d：%s" % (entry_no, e)) from e
            out.append(bytes([TAG_FRAME]) + len(body).to_bytes(4, "little") + body)
    return b"".join(out)
