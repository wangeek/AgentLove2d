#!/bin/bash
# 像素动画用例：8 帧爆炸序列帧循环（D 换图/帧动画语义），本地 Qwen 直出
# kit_pixel：资产 1-8 = 32×32 爆炸帧（程序生成 tools/gen_pixel_frames.py），9 = 字体
set -e
cd /d/Lab/AgentLove2d
export LLM_BASE_URL=http://192.168.101.88:8020/no-thinking/v1
export LLM_MODEL=Qwen3.8-Flash-Next-FP8-no-thinking
export LLM_API_KEY=sk-local

DIRECTIVE='像素爆炸动画：中央一个 32x32 精灵按 8 帧循环播放爆炸序列（帧 N 显示资产号 1+(N mod 8)，即 frame0→frame7→frame0 循环），2 倍缩放画在屏幕中央。每帧按顺序写这些行（静态行逐字照抄）：
C 24 20 28 255
R 0 0 420 640 60 0 0 1 40 36 44 255
R 1 0 420 640 60 0 0 1 90 80 100 255
D <资产号> 0 288 208 0 2 2
PR 9 "PIXEL EXPLOSION" 200 8 0 1 1 255 160 0 255
PR 9 "FRAME <N mod 8>" 12 12 0 1 1 200 200 200 255
动态行说明：
- D 行的资产号 = 1 + (N 除以 8 的余数)，N 是当前帧号，自己算好写成数（帧 0 用 1、帧 1 用 2……帧 7 用 8、帧 8 又用 1 循环）；
- 第二条 PR 的文本写成 FRAME 加 N 除以 8 的余数，如帧 13 写 "FRAME 5"；
- D 行放在 R 行之后、PR 行之前。'

python -m dream.run --frames 60 --out dream/dream_pixel.fr --llm \
  --kit dream/kit_pixel --chunk-frames 10 --directive "$DIRECTIVE"

echo '--- op 覆盖统计 ---'
grep -oE '^(C|D|PR|R|LN|PY|CI|AR|PT|rt|SC|CP|SET|INS|DEL|MOVE|PLACE|POSE|ENTER|EXIT)( |$)' dream/dream_pixel.fr \
  | sed 's/ $//' | sort | uniq -c | sort -rn
echo '--- D 行资产号分布（帧动画换图验证） ---'
grep -oE '^D [0-9]+' dream/dream_pixel.fr | sort | uniq -c
