# tools/fr_gen/gen_js.py
"""生成 JS 表模块 render/js/fr_table.mjs（数据面由 cmd.tbl 驱动，不含逻辑）。

与 gen_c / gen_python 的分工：JS 前端 v0 只需要**文本**编解码——回放读 `.fr` 文本、
捕获写 `.fr` 文本；`.frb` 二进制容器留给以后。所以本生成器只产"表数据"：
每 op 的段、字段序（名+类型）、可变长标记、状态、是否增量动词，加表指纹。

渲染/解析逻辑在手写单源 `render/js/codec.mjs`——它逐字段驱动、不按 op 硬编码，
所以加 op 只改表 + 重生成，不必碰 JS 逻辑。

双路径再生（同 gen_c 约定，B4-2）：`../phaser-fr/src/` 在场时把 `fr_table.mjs`
与 `codec.mjs`、`conformance.mjs` 一并同步过去（逐字节一致），缺场跳过——
主仓单机可用性不受影响。

产出确定性：无时间戳/随机数，同表重复再生逐字节相等（UTF-8 + LF）。
用法：仓库根 `python -m tools.fr_gen.gen_js`
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from tools.fr_gen import tbl  # noqa: E402

HEADER = """\
// fr_table.mjs —— FR 命令表数据面（GENERATED，勿手改）
//
// 由 tools/fr_gen/gen_js.py 从 tables/cmd.tbl 生成。改表后重新生成：
//     python -m tools.fr_gen.gen_js
// 逻辑不在这里：渲染/解析见同目录 codec.mjs（逐字段驱动，不按 op 硬编码）。
//
// 段：head 资产与帧头 / in 输入 / log 观测 / out 绘制与编辑 / end 校验和
// delta: true 的 op 属帧间增量编辑动词（表里 status=ext）——它们不是"绘制行"，
//        算 d_crc 时不计入（与 Python 侧 fr_lint 的判据口径一致）。
"""


def _js_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _emit_fields(fields):
    return "[" + ", ".join("[%s, %s]" % (_js_str(n), _js_str(t))
                           for n, t in fields) + "]"


def render_module(rows):
    """rows（tbl.parse 输出）→ fr_table.mjs 文本。"""
    sha = tbl.tbl_sha256(rows)
    out = [HEADER]
    out.append("export const TBL_SHA256 = %s;\n" % _js_str(sha))

    # asset kind：数值口径与 fr_codec_gen 的 ASSET_KIND_* 同源（勿改数值）
    out.append("\nexport const ASSET_KIND = { IMAGE: 0, CANVAS: 1, QUAD: 2, FONT: 3 };\n")
    out.append("export const ASSET_KIND_NAMES = [\"image\", \"canvas\", \"quad\", \"font\"];\n")

    # variant 标签（与 gen_python 的 VARIANT_TAG_* 同值）
    out.append("export const VARIANT = { NUM: 1, STR: 2, BOOL: 3 };\n")

    out.append("\n// op → 规格（键序即表序 = opcode 序）\n")
    out.append("export const OPS = {\n")
    for r in rows:
        out.append("  %s: { section: %s, fields: %s, variadic: %s, status: %s, delta: %s },\n"
                   % (_js_str(r["op"]), _js_str(r["section"]),
                      _emit_fields(r["fields"]),
                      _js_str(r["variadic"]) if r["variadic"] else "null",
                      _js_str(r["status"]),
                      "true" if r["status"] == "ext" else "false"))
    out.append("};\n")

    out.append("\n// 表序（=二进制 opcode 序；v0 文本侧只需相对序稳定）\n")
    out.append("export const OP_ORDER = [%s];\n"
               % ", ".join(_js_str(r["op"]) for r in rows))
    return "".join(out)


def main():
    root = pathlib.Path(__file__).resolve().parents[2]
    rows = tbl.parse((root / "tables" / "cmd.tbl").read_text(encoding="utf-8"))
    text = render_module(rows)
    dst = root / "render" / "js" / "fr_table.mjs"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8", newline="\n")
    print("render/js/fr_table.mjs 已再生：%d op，TBL_SHA256 = %s"
          % (len(rows), tbl.tbl_sha256(rows)))

    # 双路径同步：前端仓库在场则推一份逐字节相同的副本（含手写 codec/conformance）
    front = root.parent / "phaser-fr" / "src"
    if front.is_dir():
        for name in ("fr_table.mjs", "codec.mjs", "conformance.mjs"):
            src = root / "render" / "js" / name
            if not src.is_file():
                print("跳过（缺手写源）：%s" % src.name)
                continue
            (front / name).write_bytes(src.read_bytes())
        print("前端副本已同步:", front)
    else:
        print("前端仓库不在场（%s），跳过副本同步" % front)


if __name__ == "__main__":
    main()
