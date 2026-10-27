# tests/test_c_decode.py
"""B4 行解码 + C 会话层：API 面 / golden 解码-重编码闭环锚 / 再生确定性。

锚定实现所选 API 面（形态决策记录在实现处注释）：
- 会话层（手写 render/fr_session.h/.c）：fr_session_open / fr_session_next_entry /
  fr_session_free，1=取到 entry / 0=EOF / <0=错误（现场 s->err_off）
- 行级解码（gen_c 生成）：fr_dec_init / fr_dec_next（1=取到行，op 在 d->op /
  0=流结束 / <0=错误——FR_OP_DT=0x00 与"0=结束"冲突，故 op 不走返回值）+
  类型访问器 fr_dec_u8/u32/f32/f64/rgba8/str/pts/data/variant/args
- golden 闭环：fr_selftest.c 内嵌 tests/golden/sample.frb 全部字节，解码→按
  字段重编码（B3a fr_encode_* 系）→与原始行字节 memcmp；帧/行/cmnt 计数锚
  取自 Python 侧 tools.fr_session.parse_binary（跨语言同一字节流）
"""
import os

from tools.fr_gen import tbl, gen_c
from tools import fr_codec_gen as fc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    return open(os.path.join(_ROOT, "render", name), encoding="utf-8").read()


def test_session_and_decode_api_face():
    # 会话层 API 面（手写 fr_session.h）
    sess = _read("fr_session.h")
    for sym in ("fr_session_open(fr_session *", "fr_session_next_entry(fr_session *",
                "fr_session_free(fr_session *", "fr_session_hdr;", "fr_session_entry;",
                "FR_SESSION_HEADER_LEN", "FR_SESSION_FRAME", "FR_SESSION_CMNT",
                "#ifdef __cplusplus"):
        assert sym in sess, sym
    # 行级解码 API 面（生成 fr_codec.h）
    h = _read("fr_codec.h")
    for sym in ("fr_dec_init(", "fr_dec_next(", "fr_dec_u8(", "fr_dec_u32(",
                "fr_dec_f32(", "fr_dec_f64(", "fr_dec_rgba8(", "fr_dec_str(",
                "fr_dec_pts(", "fr_dec_data(", "fr_dec_variant(", "fr_dec_args("):
        assert sym in h, sym
    # 形状锚：游标契约与拷贝出参口径
    assert "void fr_dec_init(fr_dec *d, const uint8_t *buf, size_t len);" in h
    assert "int fr_dec_next(fr_dec *d);" in h
    assert "int fr_dec_str(fr_dec *d, char *out, uint32_t cap);" in h
    assert "int fr_dec_pts(fr_dec *d, float *out, uint32_t cap, uint32_t *n);" in h
    assert "int fr_dec_variant(fr_dec *d, fr_variant *out, char *sbuf, uint32_t scap);" in h
    assert "int fr_dec_data(fr_dec *d, const uint8_t **out, uint32_t *n);" in h


def test_selftest_golden_embed_and_closed_loop():
    src = _read("fr_selftest.c")
    golden = open(os.path.join(_ROOT, "tests", "golden", "sample.frb"), "rb").read()
    assert golden.hex() in src.replace(" ", "")      # 全部 728B 已嵌入（去空白比对）
    # 闭环设施：会话解包 + 行游标 + 重编码 + 字节比对
    for sym in ("fr_session_open", "fr_session_next_entry", "fr_dec_init", "fr_dec_next",
                "fr_encode_", "memcmp"):
        assert sym in src, sym
    # 计数锚：帧数 / 首帧行数 / cmnt 数——真值取自 Python 侧 parse_binary
    from tools import fr_session as fs

    s = fs.parse_binary(golden)
    frames = [p for k, p in s["entries"] if k == "frame"]
    ncmnt = sum(1 for k, _ in s["entries"] if k == "cmnt")
    assert "nframes != %d" % len(frames) in src
    assert "first_rows != %d" % len(frames[0]) in src
    assert "ncmnt != %d" % ncmnt in src


def test_regen_deterministic_all_generated(tmp_path):
    d = tmp_path / "render"
    d.mkdir()
    rows = tbl.parse(open(os.path.join(_ROOT, "tables", "cmd.tbl"), encoding="utf-8").read())
    gen_c.generate(rows, str(d))
    # 全部生成文件与提交版一致（fr_session.h/.c 为手写结构层，不参与再生比对）
    for name in ("fr_codec.h", "fr_codec.c", "fr_selftest.c"):
        assert (d / name).read_text(encoding="utf-8") == _read(name)
    assert os.path.exists(os.path.join(_ROOT, "render", "fr_session.h"))
    assert os.path.exists(os.path.join(_ROOT, "render", "fr_session.c"))
