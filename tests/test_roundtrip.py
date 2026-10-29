# tests/test_roundtrip.py
import os
from tools import fr_session as fs

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(_ROOT, "tests", "golden")

def test_golden_text_roundtrip():
    raw = open(os.path.join(GOLD, "sample.fr"), "rb").read()
    assert fs.dump_text(fs.parse_text(raw.decode("utf-8"))).encode("utf-8") == raw

def test_golden_binary_roundtrip():
    raw = open(os.path.join(GOLD, "sample.frb"), "rb").read()
    assert fs.dump_binary(fs.parse_binary(raw)) == raw

def test_golden_cross_identical():
    s = fs.parse_binary(open(os.path.join(GOLD, "sample.frb"), "rb").read())
    assert fs.dump_text(s).encode("utf-8") == open(os.path.join(GOLD, "sample.fr"), "rb").read()

def test_generated_sessions_roundtrip():
    from tools.fr_gen import tbl
    from tools import fr_codec_gen as fc
    sha = tbl.tbl_sha256(tbl.parse(open(os.path.join(_ROOT, "tables/cmd.tbl"), encoding="utf-8").read()))
    rows = [(op, dict(f)) for op, f in fc.self_test_samples()]
    for loglvl in ("off", "base", "full"):
        for seed in (0, 1, ((1 << 64) - 1)):
            s = dict(width=1, height=1, sha=sha, loglvl=loglvl, seed=seed, prec="full",
                     entries=[("cmnt", "fuzz"), ("frame", rows), ("frame", [])])
            assert fs.parse_binary(fs.dump_binary(s)) == s
            assert fs.parse_text(fs.dump_text(s)) == s
            assert fs.parse_text(fs.dump_text(fs.parse_binary(fs.dump_binary(s)))) == s
