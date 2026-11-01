# tools/gen_pixel_frames.py —— 像素动画序列帧生成（dream kit 用例，B18+）
"""程序生成 8 帧 32×32 爆炸动画 PNG（kit_pixel 用）：闪光小球 → 膨胀火球 →
碎片环消散。纯几何逐帧画，无手绘素材依赖。产物不入库按需再生。

用法：python tools/gen_pixel_frames.py <out_dir>   （写 frame0.png … frame7.png）
"""
import math
import os
import sys

from PIL import Image

W = H = 32
# 帧 → (外圈半径, 内核半径, 是否画碎片, 透明度 0-255)
TIMELINE = [
    (3, 2, False, 255),   # frame0: 起爆闪光
    (6, 4, False, 255),   # frame1: 膨胀
    (9, 6, False, 255),   # frame2: 火球
    (12, 7, True, 255),   # frame3: 火球+碎片
    (14, 6, True, 220),   # frame4: 消散开始
    (15, 4, True, 170),   # frame5
    (16, 2, True, 110),   # frame6
    (16, 0, True, 60),    # frame7: 余烬
]
ORANGE = (255, 160, 0)
YELLOW = (255, 230, 120)
RED = (220, 60, 20)


def lerp(a, b, t):
    return a + (b - a) * t


def draw_frame(idx, r_out, r_core, shards, alpha):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = img.load()
    cx = cy = (W - 1) / 2.0
    t = idx / 7.0
    # 火球体：外圈橙红 → 内核亮黄，径向渐变（逐像素判定）
    for y in range(H):
        for x in range(W):
            d = math.hypot(x - cx, y - cy)
            if d <= r_out:
                if r_core > 0 and d <= r_core:
                    c = YELLOW
                elif d <= r_out * 0.7:
                    c = ORANGE
                else:
                    c = RED
                px[x, y] = (c[0], c[1], c[2], alpha)
    # 碎片：8 颗沿半径 r_shard 的方点（角度均分+帧相位旋转）
    if shards:
        r_shard = lerp(12, 17, t)
        for k in range(8):
            a = k * math.pi / 4 + t * 0.8
            sx = int(round(cx + r_shard * math.cos(a)))
            sy = int(round(cy + r_shard * math.sin(a)))
            if 0 <= sx < W and 0 <= sy < H:
                px[sx, sy] = (255, 200, 80, alpha)
    return img


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for i, (ro, rc, sh, al) in enumerate(TIMELINE):
        p = os.path.join(out_dir, "frame%d.png" % i)
        draw_frame(i, ro, rc, sh, al).save(p)
        print("wrote", p)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dream/kit_pixel")
