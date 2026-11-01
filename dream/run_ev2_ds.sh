#!/bin/bash
# M2 ev 协议式实验 DeepSeek 对照：同轻剧本同事件（frame 10 点击 320,300）
set -e
cd /d/Lab/AgentLove2d
export LLM_BASE_URL=https://api.deepseek.com
export LLM_MODEL=deepseek-flash
export LLM_API_KEY=***REDACTED***

DIRECTIVE='像素小剧场《渔舟》，36 帧。黄昏的湖面，一叶小舟载着船夫从左岸缓缓划向右岸，天边有落日，岸边有芦苇。frame 10 附近观众会与这个世界互动（届时告诉你发生了什么）。剧末画面归于平静。'

python -m dream.run --frames 36 --out dream/dream_ev2_ds.fr --llm \
  --kit dream/kit_heroes --chunk-frames 3 --directive "$DIRECTIVE" \
  --ev "10:mousepressed 320 300 1 0"

echo '--- ev 行核验 ---'
grep -n "^ev " dream/dream_ev2_ds.fr
echo '--- op 覆盖统计 ---'
grep -oE '^(C|D|PR|R|LN|PY|CI|AR|PT|rt|SC|CP|SET|INS|DEL|MOVE|PLACE|POSE|ENTER|EXIT)( |$)' dream/dream_ev2_ds.fr \
  | sed 's/ $//' | sort | uniq -c | sort -rn

python tools/fr_check.py dream/dream_ev2_ds.fr --strict
python tools/fr_render.py dream/dream_ev2_ds.fr --record dream/dream_ev2_ds.mp4 2>&1 | tail -1
ls -la dream/dream_ev2_ds.mp4
