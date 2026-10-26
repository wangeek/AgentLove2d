"""cmd.tbl 表解析器：把命令表 DSL 解析为行 dict 列表，并产出规范指纹。

cmd.tbl 是 FR 命令集的单一真源（6 列 TSV：op/section/signature/source/status/notes，
以 # 开头为注释行）。本模块只做解析与规范化，不做代码生成——生成器（后续任务）
以 parse() 的输出为输入。规范指纹 tbl_sha256 只含 op/section/signature，
改 source/status/notes 不破指纹，供 session header 登记与增量重生成判断。
"""

import hashlib

# 合法类型集（fr-spec v1.2，现代语义；f32[] = 点列类型，无裸 pts 类型）
TYPES = {"u8", "u32", "f32", "f64", "rgba8", "str", "variant", "f32[]"}

SECTIONS = {"head", "in", "log", "out", "end"}
STATUSES = {"sealed", "draft"}
VARIADIC_MARKS = {"args...", "payload..."}


class TblError(Exception):
    """表格式错误（列数/段/状态/签名不合法）。"""


def parse(text):
    """解析 cmd.tbl 文本 → 行 dict 列表。

    行 dict 键：op section signature fields variadic source status notes。
    signature 存原文；fields 为 (名, 类型) 序对列表；variadic 为
    'args...' / 'payload...'（仅允许出现在签名末位）或 None。
    """
    rows = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        # 注意：不能整行 strip 后再分列——尾随 \t 是空的 notes 列，
        # 剥掉会把 6 列误判成 5 列。strip 只用于空行/注释判断。
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        parts = raw.split("\t")
        if parts[0] == "op":
            continue  # 列头行（真实表首列为 op 的非注释行）
        if len(parts) < 6:
            raise TblError(f"第 {lineno} 行列数不足 6（实得 {len(parts)}）: {raw!r}")
        op, section, signature, source, status, notes = parts[:6]
        if section not in SECTIONS:
            raise TblError(f"第 {lineno} 行 section 非法 {section!r}: {raw!r}")
        if status not in STATUSES:
            raise TblError(f"第 {lineno} 行 status 非法 {status!r}: {raw!r}")
        fields, variadic = _parse_signature(signature, lineno, raw)
        rows.append({
            "op": op,
            "section": section,
            "signature": signature,
            "fields": fields,
            "variadic": variadic,
            "source": source,
            "status": status,
            "notes": notes,
        })
    return rows


def _parse_signature(signature, lineno, raw):
    """解析签名原文 → ((名, 类型) 序对列表, variadic 标记或 None)。"""
    tokens = signature.split()
    variadic = None
    if tokens and tokens[-1] in VARIADIC_MARKS:
        variadic = tokens[-1]
        tokens = tokens[:-1]
    for tok in tokens:
        if tok in VARIADIC_MARKS:
            raise TblError(f"第 {lineno} 行可变长标记 {tok!r} 只能在签名末位: {raw!r}")
    if len(tokens) % 2 != 0:
        raise TblError(f"第 {lineno} 行签名 token 数不是偶数: {raw!r}")
    fields = []
    for i in range(0, len(tokens), 2):
        name, typ = tokens[i], tokens[i + 1]
        if typ not in TYPES:
            raise TblError(f"第 {lineno} 行字段 {name!r} 类型非法 {typ!r}: {raw!r}")
        fields.append((name, typ))
    return fields, variadic


def canonical(rows):
    """规范形：每数据行 "op\\tsection\\tsignature"，以 \\n 连接且末尾带 \\n。"""
    return "".join(f"{r['op']}\t{r['section']}\t{r['signature']}\n" for r in rows)


def tbl_sha256(rows):
    """规范指纹：canonical 文本的 sha256 hexdigest（UTF-8 编码）。"""
    return hashlib.sha256(canonical(rows).encode("utf-8")).hexdigest()
