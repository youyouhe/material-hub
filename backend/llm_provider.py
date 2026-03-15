"""
LLM Provider 统一接口
支持多个LLM服务商：DeepSeek、OpenRouter、Anthropic
"""

import json
import os
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import requests

logger = logging.getLogger("materialhub.llm_provider")


class ToolCall:
    """Represents a tool call from the LLM."""
    def __init__(self, id: str, name: str, arguments: dict):
        self.id = id
        self.name = name
        self.arguments = arguments

    def __repr__(self):
        return f"ToolCall(id={self.id}, name={self.name}, args={self.arguments})"


class ChatResponse:
    """Structured response from chat_with_tools."""
    def __init__(self, content: Optional[str] = None, tool_calls: Optional[List['ToolCall']] = None,
                 raw_message: Optional[Dict] = None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.raw_message = raw_message  # full assistant message for re-feeding

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMProvider(ABC):
    """LLM Provider抽象基类"""

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        发送聊天请求

        Args:
            messages: [{"role": "user"|"assistant"|"system", "content": "..."}]
            **kwargs: 其他参数（temperature, max_tokens等）

        Returns:
            LLM响应文本
        """
        pass

    def chat_with_tools(self, messages: List[Dict], tools: List[Dict], **kwargs) -> ChatResponse:
        """
        Chat with tool/function calling support.

        Args:
            messages: conversation messages (may include tool results)
            tools: tool definitions in OpenAI format
            **kwargs: temperature, max_tokens, etc.

        Returns:
            ChatResponse with either content or tool_calls
        """
        raise NotImplementedError("This provider does not support tool calling")


def _openai_chat_with_tools(url: str, headers: dict, model: str, messages: List[Dict],
                             tools: List[Dict], timeout: int, provider_name: str, **kwargs) -> ChatResponse:
    """Shared OpenAI-compatible function calling for DeepSeek/OpenRouter."""
    import time

    payload = {
        "model": model,
        "messages": messages,
        "temperature": kwargs.get("temperature", 0.3),
        "max_tokens": kwargs.get("max_tokens", 4000),
        "tools": tools,
    }

    max_retries = 3
    retry_delays = [1, 2, 3]

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                logger.info(f"{provider_name} tool-call API retry {attempt}...")

            response = requests.post(url, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()
            result = response.json()

            choice = result["choices"][0]
            msg = choice["message"]

            content = msg.get("content")
            tool_calls = []

            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    func = tc.get("function", {})
                    args = func.get("arguments", "{}")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    tool_calls.append(ToolCall(
                        id=tc.get("id", ""),
                        name=func.get("name", ""),
                        arguments=args,
                    ))

            # raw_message for re-feeding into conversation
            raw_msg = {"role": "assistant"}
            if content:
                raw_msg["content"] = content
            if msg.get("tool_calls"):
                raw_msg["tool_calls"] = msg["tool_calls"]

            logger.info(f"{provider_name} tool-call API success: content={bool(content)}, tools={len(tool_calls)}")
            return ChatResponse(content=content, tool_calls=tool_calls, raw_message=raw_msg)

        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                time.sleep(retry_delays[attempt])
                continue
            raise Exception(f"{provider_name} API timeout after retries")
        except requests.exceptions.ConnectionError as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delays[attempt])
                continue
            raise Exception(f"{provider_name} API connection error: {e}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"{provider_name} API error: {e}")


class DeepSeekProvider(LLMProvider):
    """DeepSeek API Provider"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout: int = 60
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        logger.info(f"Initialized DeepSeek provider: {base_url}, model={model}")

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """调用DeepSeek Chat API（带重试机制）"""
        import time

        url = f"{self.base_url}/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2000),
        }

        max_retries = 3
        retry_delays = [1, 2, 3]  # 重试间隔：1秒、2秒、3秒

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(f"DeepSeek API 重试 {attempt}/{max_retries-1}...")
                else:
                    logger.debug(f"DeepSeek API request: {len(messages)} messages")

                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout
                )
                response.raise_for_status()

                result = response.json()
                content = result["choices"][0]["message"]["content"]

                if attempt > 0:
                    logger.info(f"DeepSeek API 重试成功！")
                logger.info(f"DeepSeek API success: {len(content)} chars")
                return content

            except requests.exceptions.Timeout as e:
                if attempt < max_retries - 1:
                    logger.warning(f"DeepSeek API timeout，{retry_delays[attempt]}秒后重试...")
                    time.sleep(retry_delays[attempt])
                    continue
                else:
                    logger.error("DeepSeek API timeout (已重试3次)")
                    raise Exception("DeepSeek API timeout after 3 retries")

            except requests.exceptions.ConnectionError as e:
                # 网络连接错误（包括DNS解析失败）
                if attempt < max_retries - 1:
                    logger.warning(f"DeepSeek API 连接失败：{e}，{retry_delays[attempt]}秒后重试...")
                    time.sleep(retry_delays[attempt])
                    continue
                else:
                    logger.error(f"DeepSeek API 连接失败 (已重试3次): {e}")
                    raise Exception(f"DeepSeek API connection error after 3 retries: {e}")

            except requests.exceptions.RequestException as e:
                # 其他请求异常（非网络问题，不重试）
                logger.error(f"DeepSeek API error: {e}")
                raise Exception(f"DeepSeek API error: {e}")

            except (KeyError, IndexError) as e:
                # 响应解析错误（不重试）
                logger.error(f"DeepSeek API response parsing error: {e}")
                raise Exception(f"Invalid DeepSeek API response: {e}")


    def chat_with_tools(self, messages: List[Dict], tools: List[Dict], **kwargs) -> ChatResponse:
        """DeepSeek supports OpenAI-compatible function calling."""
        return _openai_chat_with_tools(
            url=f"{self.base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            model=kwargs.get("model", self.model),
            messages=messages,
            tools=tools,
            timeout=self.timeout,
            provider_name="DeepSeek",
            **kwargs,
        )


class OpenRouterProvider(LLMProvider):
    """OpenRouter API Provider"""

    def __init__(
        self,
        api_key: str,
        model: str = "anthropic/claude-3.5-sonnet",
        site_url: Optional[str] = None,
        app_name: Optional[str] = None,
        timeout: int = 60
    ):
        self.api_key = api_key
        self.model = model
        self.site_url = site_url or os.getenv("OPENROUTER_SITE_URL", "https://materialhub.local")
        self.app_name = app_name or os.getenv("OPENROUTER_APP_NAME", "MaterialHub")
        self.timeout = timeout
        logger.info(f"Initialized OpenRouter provider: model={model}")

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """调用OpenRouter API（带重试机制）"""
        import time

        url = "https://openrouter.ai/api/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url,
            "X-Title": self.app_name
        }

        payload = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2000),
        }

        max_retries = 3
        retry_delays = [1, 2, 3]

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(f"OpenRouter API 重试 {attempt}/{max_retries-1}...")
                else:
                    logger.debug(f"OpenRouter API request: {len(messages)} messages, model={payload['model']}")

                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout
                )
                response.raise_for_status()

                result = response.json()
                content = result["choices"][0]["message"]["content"]

                if attempt > 0:
                    logger.info(f"OpenRouter API 重试成功！")
                logger.info(f"OpenRouter API success: {len(content)} chars")
                return content

            except requests.exceptions.Timeout as e:
                if attempt < max_retries - 1:
                    logger.warning(f"OpenRouter API timeout，{retry_delays[attempt]}秒后重试...")
                    time.sleep(retry_delays[attempt])
                    continue
                else:
                    logger.error("OpenRouter API timeout (已重试3次)")
                    raise Exception("OpenRouter API timeout after 3 retries")

            except requests.exceptions.ConnectionError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"OpenRouter API 连接失败：{e}，{retry_delays[attempt]}秒后重试...")
                    time.sleep(retry_delays[attempt])
                    continue
                else:
                    logger.error(f"OpenRouter API 连接失败 (已重试3次): {e}")
                    raise Exception(f"OpenRouter API connection error after 3 retries: {e}")

            except requests.exceptions.RequestException as e:
                logger.error(f"OpenRouter API error: {e}")
                raise Exception(f"OpenRouter API error: {e}")

            except (KeyError, IndexError) as e:
                logger.error(f"OpenRouter API response parsing error: {e}")
                raise Exception(f"Invalid OpenRouter API response: {e}")


    def chat_with_tools(self, messages: List[Dict], tools: List[Dict], **kwargs) -> ChatResponse:
        """OpenRouter supports OpenAI-compatible function calling."""
        return _openai_chat_with_tools(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": self.site_url,
                "X-Title": self.app_name,
            },
            model=kwargs.get("model", self.model),
            messages=messages,
            tools=tools,
            timeout=self.timeout,
            provider_name="OpenRouter",
            **kwargs,
        )


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API Provider"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-20241022",
        timeout: int = 60
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        logger.info(f"Initialized Anthropic provider: model={model}")

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """调用Anthropic API（带重试机制）"""
        import time

        url = "https://api.anthropic.com/v1/messages"

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }

        # Anthropic API需要system message单独处理
        system_message = None
        filtered_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                filtered_messages.append(msg)

        payload = {
            "model": kwargs.get("model", self.model),
            "messages": filtered_messages,
            "max_tokens": kwargs.get("max_tokens", 2000),
            "temperature": kwargs.get("temperature", 0.7),
        }

        if system_message:
            payload["system"] = system_message

        max_retries = 3
        retry_delays = [1, 2, 3]

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(f"Anthropic API 重试 {attempt}/{max_retries-1}...")
                else:
                    logger.debug(f"Anthropic API request: {len(filtered_messages)} messages")

                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout
                )
                response.raise_for_status()

                result = response.json()
                content = result["content"][0]["text"]

                if attempt > 0:
                    logger.info(f"Anthropic API 重试成功！")
                logger.info(f"Anthropic API success: {len(content)} chars")
                return content

            except requests.exceptions.Timeout as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Anthropic API timeout，{retry_delays[attempt]}秒后重试...")
                    time.sleep(retry_delays[attempt])
                    continue
                else:
                    logger.error("Anthropic API timeout (已重试3次)")
                    raise Exception("Anthropic API timeout after 3 retries")

            except requests.exceptions.ConnectionError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Anthropic API 连接失败：{e}，{retry_delays[attempt]}秒后重试...")
                    time.sleep(retry_delays[attempt])
                    continue
                else:
                    logger.error(f"Anthropic API 连接失败 (已重试3次): {e}")
                    raise Exception(f"Anthropic API connection error after 3 retries: {e}")

            except requests.exceptions.RequestException as e:
                logger.error(f"Anthropic API error: {e}")
                raise Exception(f"Anthropic API error: {e}")

            except (KeyError, IndexError) as e:
                logger.error(f"Anthropic API response parsing error: {e}")
                raise Exception(f"Invalid Anthropic API response: {e}")


    def chat_with_tools(self, messages: List[Dict], tools: List[Dict], **kwargs) -> ChatResponse:
        """Anthropic uses its own tool_use format."""
        import time

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        # Convert OpenAI tool format to Anthropic format
        anthropic_tools = []
        for t in tools:
            func = t.get("function", {})
            anthropic_tools.append({
                "name": func["name"],
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            })

        # Separate system message
        system_message = None
        filtered_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                filtered_messages.append(msg)

        payload = {
            "model": kwargs.get("model", self.model),
            "messages": filtered_messages,
            "max_tokens": kwargs.get("max_tokens", 4000),
            "temperature": kwargs.get("temperature", 0.3),
            "tools": anthropic_tools,
        }
        if system_message:
            payload["system"] = system_message

        max_retries = 3
        retry_delays = [1, 2, 3]

        for attempt in range(max_retries):
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
                response.raise_for_status()
                result = response.json()

                # Parse Anthropic response
                content_text = ""
                tool_calls = []
                raw_content = result.get("content", [])

                for block in raw_content:
                    if block["type"] == "text":
                        content_text += block["text"]
                    elif block["type"] == "tool_use":
                        tool_calls.append(ToolCall(
                            id=block["id"],
                            name=block["name"],
                            arguments=block.get("input", {}),
                        ))

                # Build raw_message for re-feeding
                raw_msg = {"role": "assistant", "content": raw_content}

                return ChatResponse(
                    content=content_text if content_text else None,
                    tool_calls=tool_calls,
                    raw_message=raw_msg,
                )

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    time.sleep(retry_delays[attempt])
                    continue
                raise Exception("Anthropic API timeout after retries")
            except requests.exceptions.ConnectionError as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delays[attempt])
                    continue
                raise Exception(f"Anthropic API connection error: {e}")
            except requests.exceptions.RequestException as e:
                raise Exception(f"Anthropic API error: {e}")


def _get_setting(key: str, default: str = None) -> Optional[str]:
    """Try to get a setting from SystemSettings DB, fallback to None."""
    try:
        from dms_models import get_setting
        val = get_setting(key)
        if val:
            return val
    except Exception:
        pass
    return default


# Default models per provider
_DEFAULT_MODELS = {
    "deepseek": "deepseek-chat",
    "openrouter": "anthropic/claude-3.5-sonnet",
    "anthropic": "claude-3-5-sonnet-20241022",
}

# Default base URLs per provider
_DEFAULT_BASE_URLS = {
    "deepseek": "https://api.deepseek.com",
}

# Env var name mapping per provider (for backward compat)
_ENV_API_KEY = {
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}
_ENV_MODEL = {
    "deepseek": "DEEPSEEK_MODEL",
    "openrouter": "OPENROUTER_MODEL",
    "anthropic": "ANTHROPIC_MODEL",
}
_ENV_BASE_URL = {
    "deepseek": "DEEPSEEK_BASE_URL",
}


def get_llm_provider() -> LLMProvider:
    """
    创建LLM Provider实例。

    优先从数据库 SystemSettings 读取配置（管理页面设置），
    如果没有，回退到环境变量。

    数据库设置键：
        llm_provider: deepseek|openrouter|anthropic (默认: deepseek)
        llm_api_key: API密钥
        llm_base_url: API地址 (可选)
        llm_model: 模型名称 (可选)

    环境变量回退：
        LLM_PROVIDER, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
        OPENROUTER_API_KEY, OPENROUTER_MODEL,
        ANTHROPIC_API_KEY, ANTHROPIC_MODEL

    Returns:
        LLMProvider实例
    """
    # 1. Determine provider
    provider_name = (
        _get_setting("llm_provider")
        or os.getenv("LLM_PROVIDER", "deepseek")
    ).lower()

    # 2. Determine API key: DB setting > provider-specific env var
    api_key = _get_setting("llm_api_key")
    if not api_key:
        env_key = _ENV_API_KEY.get(provider_name)
        if env_key:
            api_key = os.getenv(env_key)
    if not api_key:
        raise ValueError(
            f"LLM API密钥未配置。请在系统设置页面设置，或设置环境变量 "
            f"{_ENV_API_KEY.get(provider_name, 'LLM_API_KEY')}"
        )

    # 3. Determine model: DB setting > provider-specific env var > default
    model = _get_setting("llm_model")
    if not model:
        env_model = _ENV_MODEL.get(provider_name)
        if env_model:
            model = os.getenv(env_model)
    if not model:
        model = _DEFAULT_MODELS.get(provider_name, "deepseek-chat")

    # 4. Determine base URL: DB setting > provider-specific env var > default
    base_url = _get_setting("llm_base_url")
    if not base_url:
        env_url = _ENV_BASE_URL.get(provider_name)
        if env_url:
            base_url = os.getenv(env_url)
    if not base_url:
        base_url = _DEFAULT_BASE_URLS.get(provider_name)

    # 5. Create provider
    if provider_name == "deepseek":
        return DeepSeekProvider(
            api_key=api_key,
            base_url=base_url or "https://api.deepseek.com",
            model=model,
        )
    elif provider_name == "openrouter":
        return OpenRouterProvider(
            api_key=api_key,
            model=model,
        )
    elif provider_name == "anthropic":
        return AnthropicProvider(
            api_key=api_key,
            model=model,
        )
    else:
        raise ValueError(
            f"Unknown LLM provider: {provider_name}. "
            f"Supported providers: deepseek, openrouter, anthropic"
        )
