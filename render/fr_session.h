/* fr_session.h — FR 会话封装解包（.frb 结构层，手写；B4）。
 * 镜像 tools/fr_session.py::parse_binary 语义（B1 封版 FRB1）：
 *   header 50B = magic "FRB1"(4) + version u8=1 + width u16 + height u16 +
 *   sha 32B 原始摘要 + loglvl u8(0/1/2) + seed u64（小端）
 *   entries 至 EOF：tag u8 — 0x01=frame（u32 body_len + 行流 body）/
 *   0xFF=cmnt（u32 字节数 + UTF-8，严格校验）；其它 tag 错误。
 * 结构层只做头解析与 entry 定界；行级解码归 gen_c 生成的 fr_dec_*（fr_codec.h），
 * 调用方对 frame entry 自行 fr_dec_init(d, e.body, e.len)——与 Python 侧
 * fr_session.py↔fr_codec_gen.py 同构分层。
 * 零分配：全部状态在调用方结构体内，entry 字节指向输入缓冲（零拷贝，输入缓冲
 * 须在遍历期间保持有效）。C99、无依赖；多字节量按宿主小端 memcpy 读入
 * （目标 x86/x64，与生成编解码同口径）。 */
#ifndef FR_SESSION_H
#define FR_SESSION_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define FR_SESSION_HEADER_LEN 50

/* entry kind（= wire tag 值） */
#define FR_SESSION_FRAME 0x01
#define FR_SESSION_CMNT 0xFF

/* 错误码（负值；现场偏移在 fr_session.err_off，0 起计；粘滞——首错为准） */
enum {
    FR_SESS_OK = 0,
    FR_SESS_ERR_MAGIC = -1,     /* magic 非 FRB1（off 0） */
    FR_SESS_ERR_TRUNCATED = -2, /* 头部或 entry 截断 */
    FR_SESS_ERR_VERSION = -3,   /* 版本非 1（off 4） */
    FR_SESS_ERR_LOGLVL = -4,    /* loglvl 非 0/1/2（off 41） */
    FR_SESS_ERR_TAG = -5,       /* entry tag 非法 */
    FR_SESS_ERR_UTF8 = -6       /* cmnt 非合法 UTF-8 */
};

typedef struct {
    uint16_t width;
    uint16_t height;
    uint8_t sha[32]; /* 原始摘要（hex 化归调用方） */
    uint8_t loglvl;  /* 0=off 1=base 2=full */
    uint64_t seed;
} fr_session_hdr;

typedef struct {
    int kind;            /* FR_SESSION_FRAME / FR_SESSION_CMNT */
    const uint8_t *body; /* frame: 行流字节；cmnt: UTF-8 字节（指向输入缓冲，非 NUL 结尾） */
    uint32_t len;        /* body 字节数 */
} fr_session_entry;

typedef struct {
    fr_session_hdr hdr; /* fr_session_open 成功后有效 */
    const uint8_t *buf; /* 输入缓冲（只读，不改动） */
    size_t len;         /* 总长 */
    size_t off;         /* 游标：下一 entry 位置 */
    int err;            /* 粘滞错误（FR_SESS_ERR_*；0=无） */
    size_t err_off;     /* 错误现场偏移 */
} fr_session;

/* 解析 50B 头并就位 entry 游标：0 成功 / 负错误码（s->err_off 现场偏移）。
 * 校验序镜像 Python：magic → 头部截断 → version → loglvl（w/h/sha/seed 不做域
 * 检查，与 parse_binary 一致——域校验归文本侧/写入侧） */
int fr_session_open(fr_session *s, const uint8_t *buf, size_t len);

/* 迭代 entry：1=取到（e 填充，kind/body/len）/ 0=EOF / 负错误码（粘滞） */
int fr_session_next_entry(fr_session *s, fr_session_entry *e);

/* 零分配设计：空操作，保留 API 面（未来加状态可无迁移收口） */
void fr_session_free(fr_session *s);

#ifdef __cplusplus
}
#endif

#endif /* FR_SESSION_H */
