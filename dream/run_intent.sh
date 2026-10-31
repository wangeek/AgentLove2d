#!/bin/bash
# 意图级剧本实验：只给剧情目标，不给任何指令行——测模型自发展开 Tier2 的真实能力
# 与分镜版（run_scene.sh）对照：同样 36 帧剧情，directive 零指令词汇
set -e
cd /d/Lab/AgentLove2d
export LLM_BASE_URL=http://192.168.101.88:8020/no-thinking/v1
export LLM_MODEL=Qwen3.8-Flash-Next-FP8-no-thinking
export LLM_API_KEY=sk-local

DIRECTIVE='像素小剧场《夜行》，36 帧。剧情：夜色里有一间小屋，头顶挂着月亮和几颗星；一个英雄（32x32 精灵，站立图资产 1、跑步图资产 2）从小屋旁出发，沿地面匀速跑到画面右侧边缘（frame 15 时他开始跑步，跑步姿势和站立不同），frame 20 时天空中飘来一朵云，frame 30 他跑到终点停下休息直到剧终。后景画一次就不要再动了，只写每一帧真正变化的东西。'

python -m dream.run --frames 36 --out dream/dream_intent.fr --llm \
  --kit dream/kit_heroes --chunk-frames 6 --directive "$DIRECTIVE"

echo '--- op 覆盖统计 ---'
grep -oE '^(C|D|PR|R|LN|PY|CI|AR|PT|rt|SC|CP|SET|INS|DEL|MOVE|PLACE|POSE|ENTER|EXIT)( |$)' dream/dream_intent.fr \
  | sed 's/ $//' | sort | uniq -c | sort -rn
