# tools/fr_assets.py
"""fr-assets —— 资产 kit 工具（B18 M1：流抽取 + 文件建 kit；工具族地图挂名兑现）。

用法：
  python tools/fr_assets.py <in.fr|in.frb> -o <kit_dir>          从流抽取
  python tools/fr_assets.py --from-files <kit_dir> <a.png> [b.ttf ...]

流抽取产出：assets.json（目录单——id/kind/尺寸，喂 LLM 的引用面，LLM 永不碰
字节）+ assets.txt（canonical asset 行，renumber 后——runner 首帧原样回放）。
renumber：按出现序重编 1..M（原流资产号只在本流内稳定，跨流须重编）。
image 行形 `asset image <id> <w> <h> <hex>`；font 行形 `asset font <id> <size> <hex>`
（B12 池化引用形不在本面——kit 只收独立字节资产；canvas/quad 纯数据照收）。

从文件建 kit（spec v1.2.6 路径资产口径）：image=PNG 头解析 w/h、**编码文件
字节原样 hex**（魔数判别、物化端解码）；font=字节原样 hex（size 记 14.000000
缺省——字号是 print 行的引用参数，不属资产身份）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import fr_session


def _read_text(path):
    with open(path, "rb") as f:
        head = f.read(4)
    if head == b"FRB1":
        with open(path, "rb") as f:
            return fr_session.dump_text(fr_session.parse_binary(f.read()))
    with open(path, encoding="utf-8") as f:
        return f.read()


def _png_size(data):
    """PNG 签名校验 + IHDR 宽高（字节 16-23，大端）。"""
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("不是合法 PNG（缺签名/IHDR）")
    return (int.from_bytes(data[16:20], "big"),
            int.from_bytes(data[20:24], "big"))


def _write_kit(kit_dir, assets, rows):
    with open(os.path.join(kit_dir, "assets.txt"), "w", newline="\n",
              encoding="utf-8") as f:
        f.write("\n".join(rows) + ("\n" if rows else ""))
    with open(os.path.join(kit_dir, "assets.json"), "w", encoding="utf-8") as f:
        json.dump({"assets": assets}, f, ensure_ascii=False, indent=1)


def extract(path, kit_dir):
    """流 → kit：抽 asset 行、renumber 1..M。返回资产数。"""
    text = _read_text(path)
    os.makedirs(kit_dir, exist_ok=True)
    assets, rows = [], []
    for line in text.split("\n"):
        if not line.startswith("asset "):
            continue
        t = line.split(" ")
        kind = t[1]
        if kind == "image":
            desc = dict(kind="image", w=int(t[3]), h=int(t[4]))
        elif kind == "font":
            desc = dict(kind="font", size=t[3])
        else:  # canvas/quad 纯数据无字节——照收不描述
            desc = dict(kind=kind)
        t[2] = str(len(assets) + 1)
        assets.append(dict(id=int(t[2]), **desc))
        rows.append(" ".join(t))
    _write_kit(kit_dir, assets, rows)
    return len(assets)


def build_from_files(kit_dir, items):
    """items=[(path, kind)] → kit；返回资产数。kind: image|font。"""
    os.makedirs(kit_dir, exist_ok=True)
    assets, rows = [], []
    for path, kind in items:
        with open(path, "rb") as f:
            data = f.read()
        if kind == "image":
            w, h = _png_size(data)
            assets.append(dict(id=len(assets) + 1, kind="image", w=w, h=h,
                               src=os.path.basename(path)))
            rows.append("asset image %d %d %d %s" % (len(assets), w, h, data.hex()))
        elif kind == "font":
            assets.append(dict(id=len(assets) + 1, kind="font", size="14.000000",
                               src=os.path.basename(path)))
            rows.append("asset font %d 14.000000 %s" % (len(assets), data.hex()))
        else:
            raise ValueError("kind 非法 %r（image|font）" % (kind,))
    _write_kit(kit_dir, assets, rows)
    return len(assets)


def main(argv):
    if len(argv) >= 3 and argv[1] == "--from-files":
        kit_dir, files = argv[2], argv[3:]
        if not files:
            print("用法: python tools/fr_assets.py --from-files <kit_dir> <a.png> [b.ttf ...]",
                  file=sys.stderr)
            return 2
        items = [(p, "font" if p.lower().endswith((".ttf", ".otf")) else "image")
                 for p in files]
        n = build_from_files(kit_dir, items)
        print("fr-assets: %d assets -> %s (assets.json + assets.txt)" % (n, kit_dir))
        return 0
    if len(argv) != 4 or argv[2] != "-o":
        print("用法: python tools/fr_assets.py <in.fr|in.frb> -o <kit_dir>\n"
              "      python tools/fr_assets.py --from-files <kit_dir> <a.png> [b.ttf ...]",
              file=sys.stderr)
        return 2
    n = extract(argv[1], argv[3])
    print("fr-assets: %d 个资产 → %s（assets.json 目录单 + assets.txt 行）" % (n, argv[3]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
