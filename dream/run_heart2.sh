#!/bin/bash
# 像素心跳 v2（自由创作版）：无 ASCII 参照——心形、格子坐标、行数全由 LLM 自定
set -e
cd /d/Lab/AgentLove2d
export LLM_BASE_URL=http://192.168.101.88:8020/no-thinking/v1
export LLM_MODEL=Qwen3.8-Flash-Next-FP8-no-thinking
export LLM_API_KEY=sk-local

DIRECTIVE='像素心跳动画：用 rect 行在屏幕中央逐格画一颗跳动的像素心。像素画规则：每个亮格是一行 R，格子统一 10x10（R 的 w=10 h=10，坐标是格子左上角，取 10 的倍数）。两态交替：帧 N mod 4 < 2 画大心（宽 8~12 格、高 6~10 格），否则画小心（整体收缩约三成，位置居中于大心）。心的形状自己创作：上缘两个圆弧凸起、下缘收尖的经典心形，边缘可以有阶梯感。每帧行序：
C 16 12 20 255
R 0 0 0 640 40 0 0 1 24 20 30 255
PR 1 "HEARTBEAT" 12 8 0 1 1 255 80 120 255
PR 1 "BPM <大心写 90 小心写 75>" 540 8 0 1 1 200 200 200 200
<该帧所有亮格的 R 行>
要求：心的区域约 x 260-380、y 180-320；大心每帧 40~70 行 R、小心 20~40 行；颜色用红粉系（如 255 60 100 255 与 255 130 160 255，各自恒定）；相邻行的格子要贴合（x/y 相差 10 的倍数），拼出来的轮廓要能看出是心。禁止连续两帧完全相同。'

python -m dream.run --frames 36 --out dream/dream_heart2.fr --llm \
  --kit dream/kit_font --chunk-frames 3 --directive "$DIRECTIVE"

python tools/fr_check.py dream/dream_heart2.fr --strict
python tools/fr_render.py dream/dream_heart2.fr --record dream/dream_heart2.mp4 2>&1 | tail -1
ls -la dream/dream_heart2.mp4
