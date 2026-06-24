"""三维空间建模多智能体系统 - 主入口"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from chainlit.cli import run_chainlit

# 确保项目根目录在 Python 路径中
sys.path.insert(0, str(Path(__file__).parent))

from config import LANGGRAPH_RECURSION_LIMIT
from database import db
from utils.dt_runtime import import_dt_runtime

logger = logging.getLogger(__name__)

# ─── provider → 环境变量名 & 申请地址 ────────────────────────────────────────
_PROVIDER_META: dict[str, dict[str, str]] = {
    "anthropic": {
        "env":  "ANTHROPIC_API_KEY",
        "url":  "https://console.anthropic.com/settings/keys",
    },
    "openai": {
        "env":  "OPENAI_API_KEY",
        "url":  "https://platform.openai.com/api-keys",
    },
    "deepseek": {
        "env":  "DEEPSEEK_API_KEY",
        "url":  "https://platform.deepseek.com/api_keys",
    },
    "qwen": {
        "env":  "DASHSCOPE_API_KEY",
        "url":  "https://bailian.console.aliyun.com/",
    },
    "gemini": {
        "env":  "GOOGLE_API_KEY",
        "url":  "https://aistudio.google.com/app/apikey",
    },
    "ollama": {
        "env":  "",   # 本地服务，无需 API Key
        "url":  "",
    },
}

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="三维空间建模多智能体系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 命令行模式（默认，Anthropic Claude）
  python main.py

  # Chainlit 网页界面
  python main.py --ui
  python main.py --ui --port 8080

  # 显式指定 provider / 模型
  python main.py --provider anthropic --model claude-opus-4-6
  python main.py --provider openai --model gpt-4o
  python main.py --provider deepseek
  python main.py --provider qwen --model qwen-max
  python main.py --provider gemini --model gemini-2.0-flash

  # 直接传入 API Key（优先级高于环境变量）
  python main.py --provider deepseek --api-key sk-...
  python main.py --ui --provider gemini --api-key AIza...

  # 本地 Ollama（无需 API Key）
  python main.py --provider ollama --model llama3.2
  python main.py --provider ollama --model qwen2.5:14b --base-url http://192.168.1.100:11434
""",
    )
    parser.add_argument(
        "--provider",
        choices=list(_PROVIDER_META),
        default=None,
        help=(
            "LLM 服务商（默认读取 LLM_PROVIDER 环境变量，未设置则为 anthropic）\n"
            "可选: anthropic | openai | deepseek | qwen | gemini | ollama"
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "模型名称，不传则使用各 provider 默认值：\n"
            "  anthropic=claude-opus-4-6, openai=gpt-4o,\n"
            "  deepseek=deepseek-chat,    qwen=qwen-plus,\n"
            "  gemini=gemini-2.0-flash,   ollama=llama3.2"
        ),
    )
    parser.add_argument(
        "--api-key",
        default=None,
        dest="api_key",
        help="API 密钥（优先级高于环境变量；ollama 本地服务无需此参数）",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        dest="base_url",
        help="服务地址（仅 ollama 需要，默认 http://localhost:11434；也可用于自定义 OpenAI 兼容端点）",
    )
    parser.add_argument(
        "--reasoning",
        default=None,
        choices=["true", "false"],
        help="ollama 推理模式：true=开启，false=关闭（默认使用模型自身行为）",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="启动 Chainlit 网页界面（默认为命令行模式）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8555,
        help="Chainlit 监听端口（仅 --ui 模式有效，默认 8555）",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别（默认 INFO）",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="开启 LLM 调试模式：打印每次大模型调用的完整 messages",
    )
    return parser.parse_args()


def _resolve_provider(args: argparse.Namespace) -> str:
    """CLI 参数 > 环境变量 > 默认值"""
    if args.provider:
        return args.provider
    return os.environ.get("LLM_PROVIDER", "anthropic").lower()


def _check_api_key(provider: str, api_key: str | None) -> str:
    """确保 API Key 存在，否则打印提示并退出。ollama 本地服务返回空字符串。"""
    if provider == "ollama":
        return ""   # 本地服务，无需 API Key
    if api_key:
        return api_key
    meta = _PROVIDER_META.get(provider, {"env": "API_KEY", "url": ""})
    env_var = meta["env"]
    key = os.environ.get(env_var, "")
    if not key:
        msg = f"未设置 {env_var} 环境变量，也未通过 --api-key 传入"
        if meta["url"]:
            msg += f"\n  获取地址：{meta['url']}"
        msg += f"\n  PowerShell 设置方法：$env:{env_var}='your_key_here'"
        msg += f"\n  CMD 设置方法：set {env_var}=your_key_here"
        msg += f"\n  Linux/Mac 设置方法：export {env_var}=your_key_here"
        msg += "\n  也可以启动时指定服务商，例如：python main.py --ui --provider deepseek --api-key sk-..."
        msg += "\n  本地 Ollama 无需 API Key，例如：python main.py --ui --provider ollama --model llama3.2"
        logger.error(msg)
        sys.exit(1)
    return key


def main() -> None:
    """系统主入口。"""
    args = _parse_args()

    # 配置日志（尽早初始化，确保后续所有 logger 均已生效）
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s  %(levelname)-7s  %(name)s  |  %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        dtpr = import_dt_runtime()
        logger.info("DTGeoStudio 建模工具集初始化完成")
    except Exception as e:
        logger.error("智能体服务必须与 DTGeoStudio 配合使用: %s", e)
        # exit()

    provider = _resolve_provider(args)
    api_key = _check_api_key(provider, args.api_key)

    # ── Chainlit 网页界面模式 ──────────────────────────────────────────────────
    if args.ui:
        # 通过环境变量将配置传递给 chainlit_app.py
        os.environ["DTG_PROVIDER"] = provider
        os.environ["DTG_API_KEY"]  = api_key
        os.environ["CHAINLIT_PORT"] = str(args.port)
        if args.model:
            os.environ["DTG_MODEL"] = args.model
        if args.base_url:
            os.environ["DTG_BASE_URL"] = args.base_url
        if args.reasoning is not None:
            os.environ["DTG_REASONING"] = args.reasoning
        if args.debug:
            os.environ["LLM_DEBUG"] = "true"

        # blocked
        run_chainlit(str(Path(__file__).parent / "chainlit_app.py"))

        return

    # 初始化数据库
    db.connect()
    logger.info("数据库初始化完成")

    # 构建 LLM 实例
    from llm_factory import create_llm
    from config import LLM_MAX_TOKENS, LLM_TEMPERATURE

    reasoning: bool | None = None
    if args.reasoning == "true":
        reasoning = True
    elif args.reasoning == "false":
        reasoning = False

    llm = create_llm(
        provider=provider,
        model=args.model or None,
        api_key=api_key or None,
        base_url=args.base_url or None,
        max_tokens=LLM_MAX_TOKENS,
        temperature=LLM_TEMPERATURE,
        reasoning=reasoning,
        debug=args.debug,
    )
    model_name = getattr(llm, "model_name", None) or getattr(llm, "model", "unknown")
    logger.info("LLM: %s / %s", provider, model_name)

    # 构建多智能体系统（延迟导入）
    logger.info("正在初始化多智能体系统...")
    from agents.planner import create_geo_modeling_system

    app = create_geo_modeling_system(llm=llm)
    logger.info("系统就绪，请输入建模指令（输入 'exit' 退出）")

    from langchain_core.messages import AIMessage, HumanMessage
    from utils.message_compress import compress_history_sync, estimate_tokens

    history: list = []   # 多轮对话历史

    # 交互式运行循环
    while True:
        try:
            user_input = input(">>> ").strip()
            if user_input.lower() in ("exit", "quit", "q"):
                logger.info("已退出")
                break
            if not user_input:
                continue

            # ── 压缩检查 ──────────────────────────────────────
            token_before = estimate_tokens(history)
            history = compress_history_sync(llm, history)
            token_after = estimate_tokens(history)
            if token_after < token_before:
                logger.info("历史已压缩 | token %d → %d", token_before, token_after)

            # ── 构造本轮输入 ───────────────────────────────────
            input_messages = history + [{"role": "user", "content": user_input}]

            logger.info(
                "正在处理... | 历史条数=%d, 估算token=%d",
                len(history), estimate_tokens(input_messages),
            )
            result = app.invoke(
                {"messages": input_messages},
                config={"recursion_limit": LANGGRAPH_RECURSION_LIMIT},
            )

            # ── 提取并显示结果 ─────────────────────────────────
            result_messages = result.get("messages", [])
            assistant_content = ""
            if result_messages:
                last = result_messages[-1]
                assistant_content = getattr(last, "content", str(last))
                logger.info("结果:\n%s", assistant_content)

            # ── 更新历史 ───────────────────────────────────────
            history.append(HumanMessage(content=user_input))
            if assistant_content:
                history.append(AIMessage(content=assistant_content))

        except KeyboardInterrupt:
            logger.info("已中断")
            break
        except Exception as e:
            logger.error("运行异常: %s", e, exc_info=True)

    db.close()


if __name__ == "__main__":
    main()
