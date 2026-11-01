#!/bin/bash
# M2 ev 实验第二轮：概念教学（vocab 第 9 条）+ 轻剧本 + 开放响应
# 对照第一轮（指令式注入+四件套剧本）：本轮测"教会概念后的自由创作响应"
set -e
cd /d/Lab/AgentLove2d
export LLM_BASE_URL=http://192.168.101.88:8020/no-thinking/v1
export LLM_MODEL=Qwen3.8-Flash-Next-FP8-no-thinking
export LLM_API_KEY=sk-local

DIRECTIVE='像素小剧场《渔舟》，36 帧。黄昏的湖面，一叶小舟载着船夫从左岸缓缓划向右岸，天边有落日，岸边有芦苇。frame 10 附近观众会与这个世界互动（届时告诉你发生了什么）。剧末画面归于平静。'

python -m dream.run --frames 36 --out dream/dream_ev2.fr --llm \
  --kit dream/kit_heroes --chunk-frames 3 --directive "$DIRECTIVE" \
  --ev "10:mousepressed 320 300 1 0"

echo '--- ev 行核验 ---'
grep -n "^ev " dream/dream_ev2.fr
echo '--- op 覆盖统计 ---'
grep -oE '^(C|D|PR|R|LN|PY|CI|AR|PT|rt|SC|CP|SET|INS|DEL|MOVE|PLACE|POSE|ENTER|EXIT)( |$)' dream/dream_ev2.fr \
  | sed 's/ $//' | sort | uniq -c | sort -rn

python tools/fr_check.py dream/dream_ev2.fr --strict
python tools/fr_render.py dream/dream_ev2.fr --record dream/dream_ev2.mp4 2>&1 | tail -1
ls -la dream/dream_ev2.mp4
