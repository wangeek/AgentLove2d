# tests/test_tbl.py
import hashlib, pytest
from tools.fr_gen import tbl

TBL_TEXT = """# 注释行
op\tsection\tsignature\tsource\tstatus\tnotes
dt\thead\tval f32\trun loop\tsealed\t
draw\tout\ttex u32 quad u32 x f32 y f32\tdraw\tsealed\t备注
"""

def test_parse_rows():
    rows = tbl.parse(TBL_TEXT)
    assert [r["op"] for r in rows] == ["dt", "draw"]
    assert rows[0]["fields"] == [("val", "f32")]
    assert rows[1]["fields"] == [("tex", "u32"), ("quad", "u32"), ("x", "f32"), ("y", "f32")]
    assert rows[0]["variadic"] is None
    assert rows[0]["signature"] == "val f32"
    assert rows[0]["status"] == "sealed"

def test_column_header_skipped():
    rows = tbl.parse(TBL_TEXT)
    assert all(r["op"] not in ("op",) for r in rows)

def test_bad_section_rejected():
    with pytest.raises(tbl.TblError):
        tbl.parse("dt\twrong\tval f32\ts\tsealed\t\n")

def test_bad_type_rejected():
    with pytest.raises(tbl.TblError):
        tbl.parse("dt\thead\tval f64x\ts\tsealed\t\n")

def test_variadic_must_be_last():
    with pytest.raises(tbl.TblError):
        tbl.parse("ev\tin\tslot u32 args... src u8\ts\tsealed\t\n")

def test_variadic_accepted():
    rows = tbl.parse("ev\tin\tslot u32 type str src u8 args...\ts\tsealed\t\n")
    assert rows[0]["variadic"] == "args..."
    assert rows[0]["fields"] == [("slot", "u32"), ("type", "str"), ("src", "u8")]

def test_canonical_sha_stable():
    rows = tbl.parse(TBL_TEXT)
    expect = hashlib.sha256("dt\thead\tval f32\ndraw\tout\ttex u32 quad u32 x f32 y f32\n".encode()).hexdigest()
    assert tbl.tbl_sha256(rows) == expect

def test_real_table_parses():
    rows = tbl.parse(open("tables/cmd.tbl", encoding="utf-8").read())
    ops = [r["op"] for r in rows]
    assert len(ops) == 21 and len(set(ops)) == 21
    assert "draw" in ops and "s_crc" in ops and "ev" in ops
    ev = next(r for r in rows if r["op"] == "ev")
    assert ev["variadic"] == "args..."
    # 真实表的 f32[] 类型可用
    line = next(r for r in rows if r["op"] == "line")
    assert ("pts", "f32[]") in line["fields"]
