#!/bin/bash
# M2 真交互会话（v2）：evinj 路径从 loop 的 EVINJ 协议行读取；先清僵尸 love
set -e
cd /d/Lab/AgentLove2d
export LLM_BASE_URL=http://192.168.101.88:8020/no-thinking/v1
export LLM_MODEL=Qwen3.8-Flash-Next-FP8-no-thinking
export LLM_API_KEY=sk-local

# 清历史 love 进程（僵尸 Runner 会继续写 runnerdbg/吃注入）
taskkill //IM love.exe //F >/dev/null 2>&1 || true
sleep 1

python -m dream.loop --llm --out dream/dream_live.fr --kit dream/kit_heroes \
  --directive '像素小剧场《渔舟》，黄昏的湖面，一叶小舟载着船夫从左岸缓缓划向右岸，天边有落日，岸边有芦苇。观众可能随时与这个世界互动（届时告诉你发生了什么），世界要自然地回应。剧末画面归于平静。' \
  --frames-initial 9 --burst 6 --chunk-frames 3 --max-idle 10 --max-total 150 \
  > _loop_stdout.txt 2> _loop_err.txt &
LOOP_PID=$!

# 等 loop 打印 EVINJ 协议行（Runner 起前）
EVINJ=""
for i in $(seq 1 300); do
  EVINJ=$(grep -oE 'EVINJ .*' _loop_stdout.txt 2>/dev/null | head -1 | cut -d' ' -f2)
  [ -n "$EVINJ" ] && break
  # loop 若已退出（初始段失败）则提前收场
  kill -0 $LOOP_PID 2>/dev/null || break
  sleep 0.2
done
if [ -z "$EVINJ" ]; then
  echo "loop 未输出 EVINJ（初始段失败？）"
  tail -5 _loop_err.txt
  kill $LOOP_PID 2>/dev/null || true
  exit 1
fi
echo "evinj path: $EVINJ"

# 等 Runner 渲染就绪（runnerdbg load 标记）
for i in $(seq 1 450); do
  [ -f "$EVINJ" ] && true
  grep -q "load title" dream/dream_live.fr.runnerdbg 2>/dev/null && break
  sleep 0.2
done
sleep 3

echo "mousepressed 200 380 1 false" >> "$EVINJ"
echo "mousereleased 200 380 1 false" >> "$EVINJ"
sleep 20
echo "mousepressed 520 120 1 false" >> "$EVINJ"
echo "mousereleased 520 120 1 false" >> "$EVINJ"

wait $LOOP_PID || true

echo '--- ev 行核验 ---'
grep -n "^ev " dream/dream_live.fr | head -8 || true
echo "--- ev 总数: $(grep -c '^ev ' dream/dream_live.fr || true) ---"
python tools/fr_check.py dream/dream_live.fr --strict
python tools/fr_render.py dream/dream_live.fr --record dream/dream_live.mp4 2>&1 | tail -1
ls -la dream/dream_live.mp4
