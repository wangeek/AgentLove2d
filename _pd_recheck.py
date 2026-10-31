"""B15 pd (asset,k) 身份机制回检——三问逐层验证。

① 语义边界：身份只管 pd 配对（帧内出现序），rdp/rdm 是构造性 pos 定位——
   设计是否如 cmd.tbl 封版所述？
② 独立实现 vs 测试锚：delta_check 的 pd 消歧（seen 计数）在多 draw 同资产、
   k 越界、rdp 插入后的帧内序变化下是否正确？用真实对拍流（mini+双场景）
   逐条核。
③ React key 模型的边界真实性：身份配对失败→降级 rd（编码器侧），解码侧
   未配对→报告不炸——失败路径是否在位？
"""
import sys

sys.path.insert(0, ".")
from tools import fr_delta_check as fdc

print("== ① 多 draw 同资产消歧（k=1 命中第二个） ==")
# 帧 0：两个 draw 都引资产 7（同资产多实例——React key 的核心考验场景）
# 帧 1：pd 7 1 x 555（k=1 → 第二个 draw 的 x）+ 帧 2：pd 7 0 x 111（k=0 → 第一个）
text = ("frb1 640 480 1bd74035c2e8e25e4a6ab54bbb32c8ff59bfc3b16e21cf5b84c6d0094ec11292 base 1 :px +d\n"
        "frame 0\n"
        "D 7 0 100 200 0 1 1\n"
        "D 7 0 300 200 0 1 1\n"
        "frame 1\n"
        "pd 7 1 x 555\n"
        "frame 2\n"
        "pd 7 0 x 111\n")
r = fdc.expand_delta(text)
frames, warns = r["_rows"], r["warnings"]
f1 = [l for l in frames[1]]
f2 = [l for l in frames[2]]
print("帧1（pd k=1 改第二行）:", f1)
print("帧2（pd k=0 改第一行）:", f2)
tok1 = f1[1].split()
tok2 = f2[0].split()
tok3 = f2[1].split()
assert tok1[3] == "555.000000" and tok1[1] == "7", "k=1 应改第二行 x"
assert tok2[3] == "100.000000" and tok3[3] == "111.000000", "k=0 应改第一行 x，另一行不动"
print("→ k 消歧正确（k=1 改第二实例、k=0 改第一实例、互不串位）✓")

print()
print("== ② k 越界（不存在该出现序）→ 报告不炸 ==")
text_bad = text.replace("pd 7 0 x 111", "pd 7 5 x 111")
r2 = fdc.expand_delta(text_bad)
print("警告:", r2["warnings"])
assert any("身份未配对" in w for w in r2["warnings"]), "k 越界应进报告"
print("→ 解码侧失败路径在位（报告、不抛）✓")

print()
print("== ③ rdp 插入改变帧内序后，pd 出现序跟着变（身份语义=当前帧实况） ==")
# 帧 1：rdp 在最前面插一个 draw 7（k 序重排：原第一行变 k=1）→ pd 7 1 应改原第一行
text3 = ("frb1 640 480 1bd74035c2e8e25e4a6ab54bbb32c8ff59bfc3b16e21cf5b84c6d0094ec11292 base 1 :px +d\n"
         "frame 0\n"
         "D 7 0 100 200 0 1 1\n"
         "D 7 0 300 200 0 1 1\n"
         "frame 1\n"
         "rdp 0 \"D 7 0 500 200 0 1 1\"\n"
         "frame 2\n"
         "pd 7 1 x 777\n")
r3 = fdc.expand_delta(text3)
f2 = r3["_rows"][2]
toks = [l.split() for l in f2]
# 插入后序：[500(新), 100(原k0→k1), 300(原k1→k2)]；pd k=1 应改 x=100 那行
assert toks[1][3] == "777.000000" and toks[1][3] == toks[1][3], "k=1 应命中原第一行"
assert toks[2][3] == "300.000000", "第三行（原 k=1→k=2）不动"
print("插入后帧2:", f2)
print("→ 身份按当前帧出现序（React key 语义=渲染序而非创建序）✓")

print()
print("== ④ pd 白名单防御（codec 层） ==")
from tools import fr_codec_gen as fc
try:
    fc.parse_line("pd 7 2 bogus 1.000000")
    print("白名单漏！")
except ValueError as e:
    print("param 白名单拒收:", str(e)[:40], "✓")
