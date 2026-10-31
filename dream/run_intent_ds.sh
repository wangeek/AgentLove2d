#!/bin/bash
# 意图级剧本 DeepSeek 对照：同 run_intent.sh 剧本，测强模型的自发 Tier2 采用
set -e
cd /d/Lab/AgentLove2d
export LLM_BASE_URL=https://api.deepseek.com
export LLM_MODEL=deepseek-flash
export LLM_API_KEY=***REDACTED***

DIRECTIVE='像素小剧场《夜行》，36 帧。剧情：夜色里有一间小屋，头顶挂着月亮和几颗星；一个英雄（32x32 精灵，站立图资产 1、跑步图资产 2）从小屋旁出发，沿地面匀速跑到画面右侧边缘（frame 15 时他开始跑步，跑步姿势和站立不同），frame 20 时天空中飘来一朵云，frame 30 他跑到终点停下休息直到剧终。后景画一次就不要再动了，只写每一帧真正变化的东西。'

python -m dream.run --frames 36 --out dream/dream_intent_ds.fr --llm \
  --kit dream/kit_heroes --chunk-frames 6 --directive "$DIRECTIVE"

echo '--- op 覆盖统计 ---'
grep -oE '^(C|D|PR|R|LN|PY|CI|AR|PT|rt|SC|CP|SET|INS|DEL|MOVE|PLACE|POSE|ENTER|EXIT)( |$)' dream/dream_intent_ds.fr \
  | sed 's/ $//' | sort | uniq -c | sort -rn

python tools/fr_check.py dream/dream_intent_ds.fr --strict
python tools/fr_render.py dream/dream_intent_ds.fr --record dream/dream_intent_ds.mp4 2>&1 | tail -1
ls -la dream/dream_intent_ds.mp4
