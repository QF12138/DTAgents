"""LLM 工厂 - 按 provider 创建对应的 LangChain Chat 模型"""
from __future__ import annotations

import json
from langchain_core.language_models import BaseChatModel
from langchain_core.callbacks import BaseCallbackHandler


class DebugCallbackHandler(BaseCallbackHandler):
    """打印每次 LLM 调用的完整 messages，开启 LLM_DEBUG 时使用。"""

    def on_chat_model_start(self, serialized: dict, messages: list, **kwargs) -> None:
        model_name = (serialized or {}).get("name", "unknown")
        print(f"\n{'='*70}")
        print(f"[LLM DEBUG] model={model_name}")
        for turn in messages:
            for msg in turn:
                role = getattr(msg, "type", type(msg).__name__)
                content = getattr(msg, "content", "")
                if isinstance(content, list):
                    # tool result / multipart content
                    content_str = json.dumps(content, ensure_ascii=False)
                else:
                    content_str = str(content)
                if len(content_str) > 2000:
                    content_str = content_str[:2000] + f"... [truncated {len(content_str)-2000} chars]"
                print(f"  [{role}] {content_str}")
        print(f"{'='*70}\n")

# ─── provider 元数据 ──────────────────────────────────────────────────────────
# base_url=None 表示使用 SDK 默认地址
_PROVIDER_CONFIG: dict[str, dict] = {
    "anthropic": {
        "default_model": "claude-opus-4-6",
        "base_url": None,
        "backend": "anthropic",
    },
    "openai": {
        "default_model": "gpt-4o",
        "base_url": None,
        "backend": "openai",
    },
    "deepseek": {
        "default_model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
        "backend": "openai",   # 兼容 OpenAI 接口
    },
    "qwen": {
        "default_model": "qwen-plus",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "backend": "openai",   # 兼容 OpenAI 接口
    },
    "gemini": {
        "default_model": "gemini-2.0-flash",
        "base_url": None,
        "backend": "google",
    },
    "ollama": {
        "default_model": "llama3.2",
        "base_url": "http://localhost:11434",
        "backend": "ollama",   # 本地 Ollama 服务，无需 API Key
    },
}


def _bypass_proxy_for_ollama(base_url: str) -> None:
    """将 Ollama 服务地址加入 NO_PROXY，避免系统代理（Clash/V2Ray 等）拦截本地请求。"""
    import os
    from urllib.parse import urlparse

    host = urlparse(base_url).hostname or "localhost"
    for key in ("NO_PROXY", "no_proxy"):
        existing = os.environ.get(key, "")
        entries = [e.strip() for e in existing.split(",") if e.strip()]
        if host not in entries:
            entries.append(host)
            os.environ[key] = ",".join(entries)


def _check_ollama(base_url: str, model: str) -> None:
    """预检 Ollama 服务可达性与模型可用性，给出清晰错误提示。"""
    import urllib.request
    import urllib.error
    import json

    # 用无代理 opener，防止系统代理（Clash/V2Ray 等）返回 502
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    tags_url = base_url.rstrip("/") + "/api/tags"
    try:
        with opener.open(tags_url, timeout=5) as resp:
            data = json.loads(resp.read())
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"无法连接 Ollama 服务（{base_url}）：{e.reason}\n"
            "  请确认 Ollama 已启动：ollama serve"
        ) from None
    except Exception as e:
        raise RuntimeError(f"Ollama 服务异常（{base_url}）：{e}") from None

    available = [m["name"] for m in data.get("models", [])]
    # 匹配时忽略 tag（如 llama3.2 匹配 llama3.2:latest）
    model_base = model.split(":")[0]
    matched = any(
        m == model or m.startswith(model_base + ":") or m.startswith(model + ":")
        for m in available
    )
    if not matched:
        avail_str = "\n  ".join(available) if available else "（无已拉取模型）"
        raise RuntimeError(
            f"Ollama 中未找到模型 '{model}'。\n"
            f"  请先拉取：ollama pull {model}\n"
            f"  当前可用模型：\n  {avail_str}"
        )


def create_llm(
    provider: str,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0,
    reasoning: bool | None = None,
    debug: bool = False,
) -> BaseChatModel:
    """
    创建指定 provider 的 LLM 实例。

    Args:
        provider:    "anthropic" | "openai" | "gemini" | "deepseek" | "qwen" | "ollama"
        model:       模型名称，None 时使用 provider 默认值
        api_key:     API 密钥，None 时从环境变量读取（ollama 无需此参数）
        base_url:    服务地址，主要用于覆盖 ollama 默认地址（http://localhost:11434）
        max_tokens:  最大输出 token 数
        temperature: 采样温度
        reasoning:   仅 ollama 有效。True=开启推理模式，False=关闭，None=使用模型默认行为
        debug:       True 时打印每次 LLM 调用的完整 messages

    Returns:
        BaseChatModel 实例
    """
    provider = provider.lower()
    _callbacks = [DebugCallbackHandler()] if debug else []
    cfg = _PROVIDER_CONFIG.get(provider)
    if cfg is None:
        raise ValueError(
            f"未知 provider: {provider!r}，支持：{list(_PROVIDER_CONFIG)}"
        )

    resolved_model = model or cfg["default_model"]
    resolved_base_url = base_url or cfg["base_url"]

    if cfg["backend"] == "anthropic":
        from langchain_anthropic import ChatAnthropic

        kwargs: dict = {
            "model": resolved_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "streaming": True,
        }
        if api_key:
            kwargs["api_key"] = api_key
        if _callbacks:
            kwargs["callbacks"] = _callbacks
        return ChatAnthropic(**kwargs)  # type: ignore[arg-type]

    if cfg["backend"] == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        kwargs = {
            "model": resolved_model,
            "max_output_tokens": max_tokens,
            "temperature": temperature,
        }
        if api_key:
            kwargs["google_api_key"] = api_key
        if _callbacks:
            kwargs["callbacks"] = _callbacks
        return ChatGoogleGenerativeAI(**kwargs)  # type: ignore[arg-type]

    if cfg["backend"] == "ollama":
        from langchain_ollama import ChatOllama

        ollama_base = resolved_base_url or "http://localhost:11434"
        _bypass_proxy_for_ollama(ollama_base)
        _check_ollama(ollama_base, resolved_model)
        return ChatOllama(
            model=resolved_model,
            base_url=ollama_base,
            num_predict=max_tokens,
            temperature=temperature,
            reasoning=reasoning,
            callbacks=_callbacks or None,
        )

    # openai-compatible（openai / deepseek / qwen）
    from langchain_openai import ChatOpenAI

    kwargs = {
        "model": resolved_model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "streaming": True,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if resolved_base_url:
        kwargs["base_url"] = resolved_base_url
    if _callbacks:
        kwargs["callbacks"] = _callbacks
    return ChatOpenAI(**kwargs)  # type: ignore[arg-type]
