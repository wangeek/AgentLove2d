# tools/fr_dis.py
"""fr-dis：.frb 二进制 → .fr canonical 文本（反汇编方向，会话双形态互转薄壳）。

用法：
    python tools/fr_dis.py <input.frb> [-o <out.fr>]

  input      输入 .frb 二进制会话
  -o out     输出 .fr 文本路径；缺省打印 stdout（两种去向都写 UTF-8 字节、
             单 LF 结尾，不随终端编码/换行风格变化）

退出码：0 成功；1 输入失败（SessionError / ValueError / OSError，
含 UnicodeDecodeError，消息前缀 "fr-dis: " 到 stderr）；2 用法错误。
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import fr_session as fs


def main(argv):
    ap = argparse.ArgumentParser(
        prog="fr-dis", description="把 .frb 二进制会话反汇编为 .fr canonical 文本")
    ap.add_argument("input", help="输入 .frb 二进制文件")
    ap.add_argument("-o", "--out", metavar="out",
                    help="输出 .fr 文本文件（缺省打印 stdout）")
    args = ap.parse_args(argv)
    try:
        with open(args.input, "rb") as f:
            data = f.read()
        text = fs.dump_text(fs.parse_binary(data))
        if args.out:
            with open(args.out, "wb") as f:
                f.write(text.encode("utf-8"))
        else:
            sys.stdout.buffer.write(text.encode("utf-8"))
    except (fs.SessionError, ValueError, OSError) as e:
        # 错误消息 UTF-8 输出（tests/test_cli._run 按 utf-8 解码；Windows 管道
        # 缺省 GBK 会把中文打成乱码——显式字节写，B1 字节纪律）
        sys.stderr.buffer.write(("fr-dis: %s\n" % e).encode("utf-8"))
        sys.stderr.flush()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
