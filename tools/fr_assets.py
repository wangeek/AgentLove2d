# tools/fr_assets.py
"""fr-assets —— 流 → 资产 kit 抽取（B18 M1 最小面；工具族地图挂名兑现）。

用法：python tools/fr_assets.py <in.fr|in.frb> -o <kit_dir>
产出：assets.json（目录单——id/kind/desc/尺寸，喂 LLM 的引用面，LLM 永不碰字节）
      assets.txt（canonical asset 行，renumber 后——runner 首帧原样回放）
renumber：按出现序重编 1..M（原流资产号只在本流内稳定，跨流须重编）。
image 行形 `asset image <id> <w> <h> <hex>`；font 行形 `asset font <id> <size> <hex>`
（B12 池化引用形不在本面——kit 只收独立字节资产；canvas/quad 纯数据照收）。
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


def extract(path, kit_dir):
    text = _read_text(path)
    os.makedirs(kit_dir, exist_ok=True)
    assets, new_id = [], 0
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
        new_id += 1
        t[2] = str(new_id)
        assets.append((new_id, " ".join(t), desc))
    with open(os.path.join(kit_dir, "assets.txt"), "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(a[1] for a in assets) + ("\n" if assets else ""))
    man = {"assets": [dict(id=i, **d) for i, _l, d in assets]}
    with open(os.path.join(kit_dir, "assets.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    return len(assets)


def main(argv):
    if len(argv) != 4 or argv[2] != "-o":
        print("用法: python tools/fr_assets.py <in.fr|in.frb> -o <kit_dir>", file=sys.stderr)
        return 2
    n = extract(argv[1], argv[3])
    print("fr-assets: %d 个资产 → %s（assets.json 目录单 + assets.txt 行）" % (n, argv[3]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
