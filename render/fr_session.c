/* fr_session.c — FR 会话封装解包（手写结构层；B4）。
 * 语义镜像 tools/fr_session.py::parse_binary（B1 封版 FRB1）；行级解码不在本层
 * （归 gen_c 生成的 fr_dec_*）。多字节量按宿主小端 memcpy 读入（目标 x86/x64，
 * 与生成编解码同口径；大端宿主由 selftest 字节比对当场暴露）。 */
#include "fr_session.h"
#include <string.h>

static uint16_t frs_rd_u16(const uint8_t *p)
{
    uint16_t v;
    memcpy(&v, p, 2);
    return v;
}

static uint32_t frs_rd_u32(const uint8_t *p)
{
    uint32_t v;
    memcpy(&v, p, 4);
    return v;
}

static uint64_t frs_rd_u64(const uint8_t *p)
{
    uint64_t v;
    memcpy(&v, p, 8);
    return v;
}

static int frs_fail(fr_session *s, int code, size_t off)
{
    if (s->err == 0) { /* 粘滞：首错为准 */
        s->err = code;
        s->err_off = off;
    }
    return s->err;
}

/* 严格 UTF-8 校验（镜像 Python bytes.decode("utf-8")：拒截断/续字节错/
 * 超长编码/代理区/超出 U+10FFFF） */
static int frs_utf8_valid(const uint8_t *s, size_t n)
{
    size_t i = 0;
    while (i < n) {
        uint8_t c = s[i];
        size_t need, j;
        uint32_t cp;
        if (c < 0x80) {
            i++;
            continue;
        }
        if ((c & 0xE0) == 0xC0) {
            need = 1;
            cp = c & 0x1Fu;
        } else if ((c & 0xF0) == 0xE0) {
            need = 2;
            cp = c & 0x0Fu;
        } else if ((c & 0xF8) == 0xF0) {
            need = 3;
            cp = c & 0x07u;
        } else {
            return 0; /* 0xF8..0xFF 起始字节 */
        }
        if (n - i - 1 < need) {
            return 0; /* 截断 */
        }
        for (j = 1; j <= need; j++) {
            if ((s[i + j] & 0xC0) != 0x80) {
                return 0; /* 续字节错 */
            }
            cp = (cp << 6) | (uint32_t)(s[i + j] & 0x3Fu);
        }
        if ((need == 1 && cp < 0x80) || (need == 2 && cp < 0x800) ||
            (need == 3 && cp < 0x10000) || cp > 0x10FFFF ||
            (cp >= 0xD800 && cp <= 0xDFFF)) {
            return 0; /* 超长 / 代理区 / 超值域 */
        }
        i += need + 1;
    }
    return 1;
}

int fr_session_open(fr_session *s, const uint8_t *buf, size_t len)
{
    memset(s, 0, sizeof *s);
    s->buf = buf;
    s->len = len;
    if (len < 4 || memcmp(buf, "FRB1", 4) != 0) {
        return frs_fail(s, FR_SESS_ERR_MAGIC, 0);
    }
    if (len < FR_SESSION_HEADER_LEN) {
        return frs_fail(s, FR_SESS_ERR_TRUNCATED, 0);
    }
    if (buf[4] != 1) {
        return frs_fail(s, FR_SESS_ERR_VERSION, 4);
    }
    s->hdr.width = frs_rd_u16(buf + 5);
    s->hdr.height = frs_rd_u16(buf + 7);
    memcpy(s->hdr.sha, buf + 9, 32);
    if (buf[41] > 2) {
        return frs_fail(s, FR_SESS_ERR_LOGLVL, 41);
    }
    s->hdr.loglvl = buf[41];
    s->hdr.seed = frs_rd_u64(buf + 42);
    s->off = FR_SESSION_HEADER_LEN;
    return 0;
}

int fr_session_next_entry(fr_session *s, fr_session_entry *e)
{
    uint8_t tag;
    size_t p;
    uint32_t n;
    if (s->err) {
        return s->err;
    }
    e->kind = 0;
    e->body = NULL;
    e->len = 0;
    if (s->off >= s->len) {
        return 0; /* EOF */
    }
    tag = s->buf[s->off];
    p = s->off + 1;
    if (tag != FR_SESSION_FRAME && tag != FR_SESSION_CMNT) {
        return frs_fail(s, FR_SESS_ERR_TAG, s->off);
    }
    if (s->len - p < 4) { /* 长度前缀截断（p ≤ len 恒成立） */
        return frs_fail(s, FR_SESS_ERR_TRUNCATED, p);
    }
    n = frs_rd_u32(s->buf + p);
    p += 4;
    if (n > s->len - p) {
        return frs_fail(s, FR_SESS_ERR_TRUNCATED, p);
    }
    if (tag == FR_SESSION_CMNT && !frs_utf8_valid(s->buf + p, n)) {
        return frs_fail(s, FR_SESS_ERR_UTF8, p);
    }
    e->kind = tag;
    e->body = s->buf + p;
    e->len = n;
    s->off = p + n;
    return 1;
}

void fr_session_free(fr_session *s)
{
    (void)s; /* 零分配：无资源可释 */
}
