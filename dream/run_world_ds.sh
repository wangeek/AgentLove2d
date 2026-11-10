#!/bin/bash
# 无限流地牢 DeepSeek 版：真交互会话（Runner 实时渲染 + 注入键盘当玩家操作）
set -e
cd /d/Lab/AgentLove2d
export LLM_BASE_URL=https://api.deepseek.com
export LLM_MODEL=deepseek-flash
export LLM_API_KEY="${LLM_API_KEY:?先 export LLM_API_KEY <DeepSeek key> 再跑}"   # key 不入库
export PYTHONIOENCODING=utf-8   # tee 管道下 python 缺省本地编码（GBK）→终端 UTF-8 乱码

# 清历史 love 进程（僵尸 Runner 防互踩）
taskkill //IM love.exe //F >/dev/null 2>&1 || true
sleep 1

python -m dream.world --llm --out dream/run_ds.fr --kit dream/kit_heroes \
  --rooms-max 999 --frames-initial 12 --frames-per-room 900 \
  --burst 6 --chunk-frames 3 2>&1 | tee _world_stdout.txt &
LOOP_PID=$!

EVINJ=""
for i in $(seq 1 300); do
  EVINJ=$(grep -oE 'EVINJ .*' _world_stdout.txt 2>/dev/null | head -1 | cut -d' ' -f2)
  [ -n "$EVINJ" ] && break
  kill -0 $LOOP_PID 2>/dev/null || break
  sleep 0.2
done
if [ -z "$EVINJ" ]; then
  echo "loop 未输出 EVINJ（初始段失败？）"
  tail -5 _world_err.txt
  kill $LOOP_PID 2>/dev/null || true
  exit 1
fi
echo "evinj path: $EVINJ"

# 等 Runner 渲染就绪（runnerdbg load 标记）
for i in $(seq 1 450); do
  grep -q "load title" dream/run_ds.fr.runnerdbg 2>/dev/null && break
  sleep 0.2
done
sleep 3

# 玩家操作：全局方向键（vocab 第 10 条——移动/跳跃/交互全映射方向键）
inject() { echo "keypressed $1 0" >> "$EVINJ"; echo "keyreleased $1 0" >> "$EVINJ"; }

inject right; sleep 2; inject right; sleep 2
inject up;    sleep 1; inject right; sleep 2      # up=跳跃/交互
inject right; sleep 2; inject up; sleep 3
inject right; sleep 2; inject down; sleep 2       # down=交互/拾取
inject left;  sleep 1; inject right; sleep 3

wait $LOOP_PID || true

echo '--- 信令核验 ---'
grep -n 'pass=\|over=' dream/run_ds.fr | head -12 || true
echo "--- 信令总数: $(grep -c 'pass=\|over=' dream/run_ds.fr || true) ---"
python tools/fr_check.py dream/run_ds.fr --strict
python tools/fr_render.py dream/run_ds.fr --record dream/run_ds.mp4 2>&1 | tail -1
ls -la dream/run_ds.mp4
