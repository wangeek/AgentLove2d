#!/bin/bash
# 分层像素场景用例：夜空小屋（矢量后景，画一次不动）+ 英雄行走（draw 精灵，编辑行组）
# 扩展指令集引导：MOVE（行走）/ POSE（换跑姿+身份转移）/ ENTER（云入场）/ CP（静止收尾）
set -e
cd /d/Lab/AgentLove2d
export LLM_BASE_URL=http://192.168.101.88:8020/no-thinking/v1
export LLM_MODEL=Qwen3.8-Flash-Next-FP8-no-thinking
export LLM_API_KEY=sk-local

DIRECTIVE='分层像素动画《夜行》：后景（夜空/月亮/星/地面/小屋）只在 frame 0 画一次、永远不动；前景英雄（32x32 精灵）沿地面从左向右行走。词汇表里的编辑行（MOVE/POSE/ENTER/CP）就是为"只写变化的部分"准备的——画面没变的层不要重写。frame 0 全量行（后景照抄）：
C 8 10 30 255
R 0 0 360 640 120 0 0 1 30 60 30 255
R 1 0 360 640 120 0 0 1 60 120 60 255
CI 0 560 80 36 16 255 240 180 255
CI 1 560 80 36 16 255 255 255 255
PT 1 100 80 2 200 200 200 255
PT 1 200 150 2 180 180 180 255
PT 1 320 60 3 220 220 220 255
R 0 80 260 100 100 0 0 1 90 70 60 255
R 1 80 260 100 100 0 0 1 120 90 70 255
D 1 0 60 328 0 1 1
PR 4 "NIGHT WALK" 12 8 0 1 1 255 200 100 255
之后 35 帧的剧本（英雄每帧右移 12px，站立图 1、跑图 2）：
- frame 1 到 frame 14：每帧一行 MOVE 1 12 0
- frame 15：英雄换跑姿——一行 POSE 1 "D 2 0 240 328 0 1 1"（240 = 60+15*12，自己算好）。注意换装后英雄的身份变成资产 2，之后 MOVE 要写 MOVE 2 12 0
- frame 16 到 frame 19：每帧一行 MOVE 2 12 0
- frame 20：天上一朵方块云入场（一行 ENTER，载荷是一行矢量 R：R 0 480 60 80 24 0 0 1 200 210 230 255）
- frame 21 到 frame 29：每帧一行 MOVE 2 12 0（英雄已行至 x=408）
- frame 30 到 frame 35：英雄停下休息，画面完全静止——每帧一行裸 CP
每帧只写编辑行（或 CP），不要重写后景。'

python -m dream.run --frames 36 --out dream/dream_scene.fr --llm \
  --kit dream/kit_heroes --chunk-frames 6 --directive "$DIRECTIVE"

echo '--- op 覆盖统计 ---'
grep -oE '^(C|D|PR|R|LN|PY|CI|AR|PT|rt|SC|CP|SET|INS|DEL|MOVE|PLACE|POSE|ENTER|EXIT)( |$)' dream/dream_scene.fr \
  | sed 's/ $//' | sort | uniq -c | sort -rn

python tools/fr_check.py dream/dream_scene.fr --strict
python tools/fr_render.py dream/dream_scene.fr --record dream/dream_scene.mp4 2>&1 | tail -1
ls -la dream/dream_scene.mp4
