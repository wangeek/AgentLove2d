#!/bin/bash
# 雷达扫描用例 v5 DeepSeek 版：与本地 Qwen 同剧本对比（三角 cos/sin 漂移验证）
set -e
cd /d/Lab/AgentLove2d
export LLM_BASE_URL=https://api.deepseek.com
export LLM_MODEL=deepseek-flash
export LLM_API_KEY="${LLM_API_KEY:?先 export LLM_API_KEY <DeepSeek key> 再跑}"   # key 不入库

DIRECTIVE='雷达扫描动画，60 帧完成一次 360 度扫描（角度一律用弧度：帧 N 的扫描起始角 = 0.1047*N 弧度）。全部用矢量 op，位图不要用，文字必须用 print 引用 font 资产 4。每帧按顺序写这些行（静态行逐字照抄，一个字符都不要改）：
C 10 15 40 255
PT 1 45 60 2 200 200 200 255
PT 1 590 75 2 200 200 200 255
PT 1 120 300 2 200 200 200 255
PT 1 520 350 2 200 200 200 255
PT 1 200 90 3 255 255 255 255
PT 1 380 210 3 255 255 255 255
PT 1 610 430 3 255 255 255 255
PT 1 90 440 3 255 255 255 255
CI 1 320 260 180 32 0 180 216 255
CI 1 320 260 120 24 0 180 216 255
CI 1 320 260 60 16 0 180 216 255
LN 2 140 260 500 260 1 0 120 160 255
LN 2 320 80 320 440 1 0 120 160 255
R 0 0 0 640 28 0 0 1 20 24 36 255
R 1 0 0 640 28 0 0 1 0 180 216 255
PR 4 "RADAR SWEEP" 12 6 0 1 1 255 215 0 255
PR 4 "AZ <三位角度读数=6*N，自己算好填>" 540 6 0 1 1 0 220 255 255
AR 0 0 320 260 180 <0.1047*N> <0.1047*N+0.5236> 12 0 220 255 70
PY 0 3 <黄三角6坐标> 255 215 0 255
PY 0 3 <红三角6坐标> 255 80 80 255
PY 0 3 <绿三角6坐标> 80 220 120 255
PY 行说明：PY 0 3 后面恰好 6 个数（3 个顶点各 x y）。三角沿圆心 320,260 公转：黄 r=60 角速度每帧 0.0349 弧度、红 r=120 每帧 0.0227 弧度、绿 r=180 每帧 0.0140 弧度，帧 N 的角度 = 角速度乘 N。三个顶点这样算（只做加法，偏移是固定小量）：
- 顶点 1（轨道点）：x1 = 320 + r*cos(角度)，y1 = 260 + r*sin(角度)，自己算好；
- 顶点 2：x2 = x1 - 12，y2 = y1 - 8（就是顶点 1 减这两个固定数）；
- 顶点 3：x3 = x1 - 12，y3 = y1 + 8（就是顶点 1 加这两个固定数）；
三角形大小固定约 12x16，不随角度旋转，只随顶点 1 沿轨道移动。
所有动态行（AR/PY/PR 的 AZ 读数）每帧重算；静态行保持不变。禁止连续两帧完全相同。'

python -m dream.run --frames 60 --out dream/dream_radar_ds.fr --llm \
  --kit dream/kit_heroes --chunk-frames 10 --directive "$DIRECTIVE"

python tools/fr_check.py dream/dream_radar_ds.fr --strict
python tools/fr_render.py dream/dream_radar_ds.fr --record dream/dream_radar_ds.mp4 2>&1 | tail -1
ls -la dream/dream_radar_ds.mp4
