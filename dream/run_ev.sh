#!/bin/bash
# M2 第一步：虚拟 ev 实验——渔舟 + frame 10 用户点击水面，测 LLM 对 ev 的叙事响应
set -e
cd /d/Lab/AgentLove2d
export LLM_BASE_URL=http://192.168.101.88:8020/no-thinking/v1
export LLM_MODEL=Qwen3.8-Flash-Next-FP8-no-thinking
export LLM_API_KEY=sk-local

DIRECTIVE='像素小剧场《渔舟》，36 帧，分四个阶段：第一阶段 frame 0-14 小渔船从左岸匀速划向右岸；第二阶段 frame 15-19 船夫加速划桨（移动步子变大）；第三阶段 frame 20-29 天开始下雨（frame 20 起画面多 4 行 LN 短竖线当雨点，位置每帧变化，船继续走）；第四阶段 frame 30-35 船靠岸雨停，画面完全静止（每帧只写一行裸 CP）。
写法（重要）：阶段 1-3 每帧写全量行——静态后景（天空/落日/山/湖面/倒影/芦苇）每帧原样照抄，船身 PY 和船夫 D 每帧用新坐标整行重写，雨点 LN 每帧换位置。阶段 4 每帧只写一行 CP。
后景在 frame 0 一次画完（总共不超过 16 行）：黄昏天空=2 个矩形（上深下浅）；落日=1 个扁矩形（橙色贴在天际线，不用圆形）；远山=2 个三角 PY（每座 3 个顶点）；湖面=1 个大矩形；落日倒影=1 个扁矩形；芦苇=每侧 3 行 LN。'

python -m dream.run --frames 36 --out dream/dream_ev.fr --llm \
  --kit dream/kit_heroes --chunk-frames 3 --directive "$DIRECTIVE" \
  --ev "10:mousepressed 320 300"

echo '--- ev 行核验 ---'
grep -n "^ev " dream/dream_ev.fr
echo '--- op 覆盖统计 ---'
grep -oE '^(C|D|PR|R|LN|PY|CI|AR|PT|rt|SC|CP|SET|INS|DEL|MOVE|PLACE|POSE|ENTER|EXIT)( |$)' dream/dream_ev.fr \
  | sed 's/ $//' | sort | uniq -c | sort -rn

python tools/fr_check.py dream/dream_ev.fr --strict
python tools/fr_render.py dream/dream_ev.fr --record dream/dream_ev.mp4 2>&1 | tail -1
ls -la dream/dream_ev.mp4
