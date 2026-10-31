# dream/driver.py
"""LLM 适配（B18）：FromFile（确定性，CI 零 token）+ LlmDriver（OpenAI 兼容）。

接口统一 generate(messages)——messages 为 OpenAI chat 数组
（[{"role", "content"}, ...]；FromFile 忽略内容按文件顺序吐 chunk）。

LlmDriver 走标准库 urllib——零第三方依赖；配置全 env：
LLM_BASE_URL（OpenAI 兼容根，如 https://api.deepseek.com）、LLM_API_KEY（可空）、
LLM_MODEL。**usage 记账**：响应 usage 的数值字段累加进 usage_totals
（prompt_tokens / completion_tokens / prompt_cache_hit_tokens 等，厂商各异
按键名透传）——计费口径的真实数字，进 benchmarks 用。
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
        self.usage_totals = {}

    def generate(self, messages):
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
        self.usage_totals = {}

    def generate(self, messages):
        req = urllib.request.Request(
            self.base.rstrip("/") + "/chat/completions",
            data=json.dumps({"model": self.model, "temperature": 0,
                             "messages": messages}).encode(),
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
        for k, v in (data.get("usage") or {}).items():
            if isinstance(v, (int, float)):
                self.usage_totals[k] = self.usage_totals.get(k, 0) + v
        return data["choices"][0]["message"]["content"] or ""
