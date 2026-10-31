# tools/fr_as.py
"""fr-as：.fr canonical 文本 → .frb 二进制（汇编方向，会话双形态互转薄壳）。

用法：
    python tools/fr_as.py <input.fr> -o <out.frb>

  input      输入 .fr canonical 文本（UTF-8；CRLF 容忍，读入即归一为 LF）
  -o out     输出 .frb 路径；缺省报用法错误（退出码 2）——二进制不能进终端

退出码：0 成功；1 输入/写出失败（SessionError / ValueError / OSError，
含 UnicodeDecodeError，消息前缀 "fr-as: " 到 stderr）；2 用法错误。
解析先于 -o 校验：坏输入行号信息优先于用法提示。
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import fr_session as fs


def main(argv):
    ap = argparse.ArgumentParser(
        prog="fr-as", description="把 .fr canonical 文本汇编为 .frb 二进制会话")
    ap.add_argument("input", help="输入 .fr 文本文件")
    ap.add_argument("-o", "--out", metavar="out",
                    help="输出 .frb 文件（缺省报用法错误：二进制不能进终端）")
    args = ap.parse_args(argv)
    try:
        with open(args.input, "r", encoding="utf-8") as f:
            text = f.read()
        blob = fs.dump_binary(fs.parse_text(text))
        if not args.out:
            ap.error("缺 -o <out.frb>：二进制不能进终端")
        with open(args.out, "wb") as f:
            f.write(blob)
    except (fs.SessionError, ValueError, OSError) as e:
        # 错误消息 UTF-8 输出（tests/test_cli._run 按 utf-8 解码；Windows 管道
        # 缺省 GBK 会把中文打成乱码——显式字节写，B1 字节纪律）
        sys.stderr.buffer.write(("fr-as: %s\n" % e).encode("utf-8"))
        sys.stderr.flush()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
