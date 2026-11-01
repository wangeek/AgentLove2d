#!/bin/bash
# 像素网格动画用例：LLM 用 R 指令逐格画心跳（无 PIL 位图——矩形即像素）
# 图案参照用 ASCII 给出；LLM 做格子→坐标行的空间翻译；两档图案交替=心跳
set -e
cd /d/Lab/AgentLove2d
export LLM_BASE_URL=http://192.168.101.88:8020/no-thinking/v1
export LLM_MODEL=Qwen3.8-Flash-Next-FP8-no-thinking
export LLM_API_KEY=sk-local

DIRECTIVE='像素心跳动画：在 20x20 的格子上用 rect 行逐格画一颗跳动的像素心（每个亮格一行 R，格子 10x10 像素）。图案参照如下——X 是亮格、. 是空格，你只输出 R 行，输出里严禁出现图案行本身：
大心（9 列宽 9 行高，出现在帧 N mod 4 < 2 时）：
.XX...XX.
XXXXXXXXX
XXXXXXXXX
XXXXXXXXX
XXXXXXXXX
.XXXXXXX.
..XXXXX..
...XXX...
....X....
小心（7 列宽 6 行高，出现在帧 N mod 4 >= 2 时）：
.XX.XX.
XXXXXXX
XXXXXXX
.XXXXX.
..XXX..
...X...
坐标换算（照公式逐格算好写数）：
- 大心跳过每个 . 后，第 r 行（从 0 起）第 c 列（从 0 起）的 X 写成：R 0 <280+c*10> <190+r*10> 10 10 0 0 1 255 60 100 255
- 小心同样跳过每个 . 后：R 0 <285+c*10> <215+r*10> 10 10 0 0 1 255 130 160 255
每帧完整行序：
C 16 12 20 255
R 0 0 0 640 40 0 0 1 24 20 30 255
PR 1 "HEARTBEAT" 12 8 0 1 1 255 80 120 255
PR 1 "BPM <90 或 75，随大小心切换>" 540 8 0 1 1 200 200 200 255
<按当前帧是大心还是小心，写该图案的全部亮格 R 行>
说明：R 行顺序随意；大心 53 行、小心 27 行，一行都不能少；颜色字节照抄公式里的。禁止连续两帧完全相同。'

python -m dream.run --frames 36 --out dream/dream_heart.fr --llm \
  --kit dream/kit_font --chunk-frames 3 --directive "$DIRECTIVE"

echo '--- op 覆盖统计 ---'
grep -oE '^(C|D|PR|R|LN|PY|CI|AR|PT|rt|SC|CP|SET|INS|DEL|MOVE|PLACE|POSE|ENTER|EXIT)( |$)' dream/dream_heart.fr \
  | sed 's/ $//' | sort | uniq -c | sort -rn
echo '--- R 行 x 坐标分布（应集中在心形区域 280-460） ---'
grep -oE '^R 0 [0-9]+' dream/dream_heart.fr | awk '{print $3}' | sort -n | uniq -c | head -20
