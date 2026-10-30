"""一次性补丁：parse_line 返回元组，取 [1]。"""
p = "dream/run.py"
s = open(p, encoding="utf-8").read()
old = 'return [("asset", _rc.parse_line(l)) for l in f.read().splitlines() if l.strip()]'
new = 'return [("asset", _rc.parse_line(l)[1]) for l in f.read().splitlines() if l.strip()]'
assert old in s, "run.py pattern missing"
s = s.replace(old, new)
open(p, "w", newline="\n", encoding="utf-8").write(s)

p = "tests/test_dream.py"
s = open(p, encoding="utf-8").read()
old1 = 'kit_rows = [("asset", fc.parse_line("asset font 1 14.000000 00010203"))]'
new1 = 'kit_rows = [("asset", fc.parse_line("asset font 1 14.000000 00010203")[1])]'
assert old1 in s, "test pattern 1 missing"
s = s.replace(old1, new1)
old2 = 'kit_rows=[("asset", fc.parse_line(a)) for a in asset_rows]'
new2 = 'kit_rows=[("asset", fc.parse_line(a)[1]) for a in asset_rows]'
assert old2 in s, "test pattern 2 missing"
s = s.replace(old2, new2)
open(p, "w", newline="\n", encoding="utf-8").write(s)
print("patched ok")
