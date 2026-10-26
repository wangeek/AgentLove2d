# tools/fr_gen/quantize.py
"""数值域量化：%.6f 语义，round-trip 字节相等的基石。

文本形态浮点定长 %.6f（fr-spec §6）；所有数值写入（二进制与文本）前先经
qf() 量化到同一语义域，使两种编码在该域上互为双射——这是 .fr↔.frb
round-trip 逐字节相等的数学前提。
"""

def qf(v):
    """量化到 %.6f 语义域；NaN/Inf 拒收（不稳定成分禁入判据）。"""
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError("NaN/Inf 禁入数值域: %r" % v)
    return float(f"{v:.6f}")
