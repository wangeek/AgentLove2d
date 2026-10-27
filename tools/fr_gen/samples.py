# tools/fr_gen/samples.py
"""self_test_samples 的共享样本数据：gen_python 与 gen_c 的单一来源。

此前样本内嵌在 gen_python 模板里；C 自检生成（render/fr_selftest.c，嵌入
Python 编码的期望字节）需要同一批字段值，故抽到本模块。gen_python 生成的
self_test_samples() 改为转调本模块（tools/fr_codec_gen.py 公共 API 不变），
gen_c 生成期从 samples() 取字段值做 C 字面量并注入期望字节。

variant 规范形（解码不动点）：num=裸数（call 的 args）、str/bool=单元素
tuple（ev 的 args）；st 的 val 按裸数直接给。
asset kind 口径值与 tools/fr_codec_gen.py 的 ASSET_KIND_* 同值（跨目标相等
由 tests/test_regen_and_c.py::test_cross_target_constants 锚定）。
"""

KIND_IMAGE, KIND_CANVAS, KIND_QUAD, KIND_FONT = 0, 1, 2, 3


def samples():
    """每 op 至少一条自检样本（encode→decode round-trip 基准；asset 按 kind 各一）。"""
    return [
        ("dt", {"val": 0.016667}),
        ("asset", {"kind": KIND_IMAGE, "id": 1, "w": 2, "h": 2,
                   "data": b"\x00\x01\x02\x03" * 4}),
        ("asset", {"kind": KIND_CANVAS, "id": 2, "w": 640, "h": 480}),
        ("asset", {"kind": KIND_QUAD, "id": 3, "x": 0.0, "y": 0.0, "w": 16.0, "h": 16.0,
                   "sw": 256.0, "sh": 256.0}),
        ("asset", {"kind": KIND_FONT, "id": 4, "size": 12.0, "data": b"fake-ttf"}),
        ("ev", {"slot": 0, "type": "keypressed", "src": 0, "args": [("return",), (False,)]}),
        ("call", {"slot": 1, "fn": "hit", "depth": 1, "args": [203.0, 88.0]}),
        ("timer", {"slot": 2, "id": 1}),
        ("rngc", {"seed_after": 3056735}),
        ("st", {"obj": 7, "key": "hp", "val": 84.0}),
        ("err", {"what": "unmapped call"}),
        ("clear", {"color": (0, 0, 0, 255)}),
        ("draw", {"tex": 1, "quad": 3, "x": 34.0, "y": 56.0, "rot": 0.0, "sx": -1.0, "sy": 1.0,
                  "ox": 0.0, "oy": 0.0, "color": (255, 255, 0, 255)}),
        ("print", {"font": 2, "text": "HELLO", "x": 12.0, "y": 340.0, "rot": 0.0, "sx": 1.0,
                   "sy": 1.0, "color": (255, 255, 0, 255)}),
        ("rect", {"mode": 0, "x": 0.0, "y": 0.0, "w": 640.0, "h": 480.0, "rx": 0.0, "ry": 0.0,
                  "width": 1.0, "color": (0, 0, 0, 255)}),
        ("line", {"pts": [(0.0, 0.0), (1.0, 1.0)], "width": 1.0, "color": (0, 0, 0, 255)}),
        ("poly", {"mode": 0, "pts": [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], "color": (0, 0, 0, 255)}),
        ("circle", {"mode": 0, "x": 0.0, "y": 0.0, "r": 5.0, "seg": 24, "color": (0, 0, 0, 255)}),
        ("arc", {"mode": 0, "arctype": 0, "x": 0.0, "y": 0.0, "r": 5.0, "a1": 0.0,
                 "a2": 1.570796, "seg": 8, "color": (0, 0, 0, 255)}),
        ("points", {"pts": [(1.0, 2.0), (3.0, 4.0)], "size": 1.0, "color": (0, 0, 0, 255)}),
        ("rt", {"target": 0}),
        ("scissor", {"x": 0.0, "y": 0.0, "w": 100.0, "h": 100.0}),
        ("s_crc", {"crc": 1123456}),
        ("d_crc", {"crc": 654321}),
    ]
