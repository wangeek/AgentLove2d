# dream/driver.py
"""LLM 适配（B18 M1）：FromFile（确定性，CI 零 token）+ LlmDriver（OpenAI 兼容）。

LlmDriver 走标准库 urllib——零第三方依赖；配置全 env：
LLM_BASE_URL（OpenAI 兼容根，如 http://host:port/v1）、LLM_API_KEY（可空）、
LLM_MODEL。实测端点（2026-10-30）：本地 Qwen3.8 thinking 网关，
content 可含前导空白（parse_chunk 空行宽松吸收）。
"""
import json
import os
import urllib.error
import urllib.request


class FromFileDriver:
    """按 `### CHUNK` 分隔的文本文件顺序吐 chunk——测试与离线确定性模式。"""

    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            self._chunks = [c for c in f.read().split("### CHUNK") if c.strip()]
        self._i = 0

    def generate(self, prompt):
        if self._i >= len(self._chunks):
            raise RuntimeError("from-file chunk 已耗尽（%d 段）" % len(self._chunks))
        c = self._chunks[self._i].strip() + "\n"
        self._i += 1
        return c


class LlmDriver:
    def __init__(self):
        self.base = os.environ.get("LLM_BASE_URL")
        self.key = os.environ.get("LLM_API_KEY", "")
        self.model = os.environ.get("LLM_MODEL", "")
        if not (self.base and self.model):
            raise RuntimeError("LLM_BASE_URL / LLM_MODEL 未配置（LLM_API_KEY 可空）")

    def generate(self, prompt):
        req = urllib.request.Request(
            self.base.rstrip("/") + "/chat/completions",
            data=json.dumps({"model": self.model, "temperature": 0,
                             "messages": [{"role": "user", "content": prompt}]}).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.key})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            raise RuntimeError("LLM HTTP %s（网关超时/限流/请求体拒绝——减小"
                               " --chunk-frames 重试）body=%s" % (e.code, body)) from e
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError("LLM 网络错误: %s" % e) from e
        return data["choices"][0]["message"]["content"]
