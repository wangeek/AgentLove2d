#!/bin/bash
# 《渔舟》DeepSeek 对照：同剧本同 kit 同 chunk 配比
set -e
cd /d/Lab/AgentLove2d
export LLM_BASE_URL=https://api.deepseek.com
export LLM_MODEL=deepseek-flash
export LLM_API_KEY=***REDACTED***

DIRECTIVE='像素小剧场《渔舟》，36 帧，分四个阶段：第一阶段 frame 0-14 小渔船从左岸匀速划向右岸（船身 PY + 船夫 D 精灵每帧都在移动，每帧都要写它们的编辑行，动作重复也要写）；第二阶段 frame 15-19 船夫加速划桨（移动步子变大）；第三阶段 frame 20-29 天开始下雨（frame 20 起每帧多写 4 行 LN 短竖线当雨点，位置每帧变化，船继续走）；第四阶段 frame 30-35 船靠岸雨停，画面完全静止（每帧写裸 CP）。
后景在 frame 0 一次画完（总共不超过 16 行）：黄昏天空=2 个矩形（上深下浅）；落日=1 个扁矩形（橙色贴在天际线，不用圆形）；远山=2 个三角 PY（每座 3 个顶点）；湖面=1 个大矩形；落日倒影=1 个扁矩形；芦苇=每侧 3 行 LN。
禁止用大量多边形铺水面或天空；每个 frame 都必须恰好覆盖到对应的帧号，一个阶段没结束就不许停笔。'

python -m dream.run --frames 36 --out dream/dream_boat_ds.fr --llm \
  --kit dream/kit_heroes --chunk-frames 3 --directive "$DIRECTIVE"

echo '--- op 覆盖统计 ---'
grep -oE '^(C|D|PR|R|LN|PY|CI|AR|PT|rt|SC|CP|SET|INS|DEL|MOVE|PLACE|POSE|ENTER|EXIT)( |$)' dream/dream_boat_ds.fr \
  | sed 's/ $//' | sort | uniq -c | sort -rn

python tools/fr_check.py dream/dream_boat_ds.fr --strict
python tools/fr_render.py dream/dream_boat_ds.fr --record dream/dream_boat_ds.mp4 2>&1 | tail -1
ls -la dream/dream_boat_ds.mp4
