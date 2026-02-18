"""
LLM Provider 统一接口
支持多个LLM服务商：DeepSeek、OpenRouter、Anthropic
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import requests

logger = logging.getLogger("materialhub.llm_provider")


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
        """调用DeepSeek Chat API"""
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

        try:
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

            logger.info(f"DeepSeek API success: {len(content)} chars")
            return content

        except requests.exceptions.Timeout:
            logger.error("DeepSeek API timeout")
            raise Exception("DeepSeek API timeout")
        except requests.exceptions.RequestException as e:
            logger.error(f"DeepSeek API error: {e}")
            raise Exception(f"DeepSeek API error: {e}")
        except (KeyError, IndexError) as e:
            logger.error(f"DeepSeek API response parsing error: {e}")
            raise Exception(f"Invalid DeepSeek API response: {e}")


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
        """调用OpenRouter API"""
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

        try:
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

            logger.info(f"OpenRouter API success: {len(content)} chars")
            return content

        except requests.exceptions.Timeout:
            logger.error("OpenRouter API timeout")
            raise Exception("OpenRouter API timeout")
        except requests.exceptions.RequestException as e:
            logger.error(f"OpenRouter API error: {e}")
            raise Exception(f"OpenRouter API error: {e}")
        except (KeyError, IndexError) as e:
            logger.error(f"OpenRouter API response parsing error: {e}")
            raise Exception(f"Invalid OpenRouter API response: {e}")


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
        """调用Anthropic API"""
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

        try:
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

            logger.info(f"Anthropic API success: {len(content)} chars")
            return content

        except requests.exceptions.Timeout:
            logger.error("Anthropic API timeout")
            raise Exception("Anthropic API timeout")
        except requests.exceptions.RequestException as e:
            logger.error(f"Anthropic API error: {e}")
            raise Exception(f"Anthropic API error: {e}")
        except (KeyError, IndexError) as e:
            logger.error(f"Anthropic API response parsing error: {e}")
            raise Exception(f"Invalid Anthropic API response: {e}")


def get_llm_provider() -> LLMProvider:
    """
    根据环境变量创建LLM Provider实例

    环境变量：
        LLM_PROVIDER: deepseek|openrouter|anthropic (默认: deepseek)

        DeepSeek:
            DEEPSEEK_API_KEY: API密钥
            DEEPSEEK_BASE_URL: API地址 (可选，默认官方地址)
            DEEPSEEK_MODEL: 模型名称 (可选，默认 deepseek-chat)

        OpenRouter:
            OPENROUTER_API_KEY: API密钥
            OPENROUTER_MODEL: 模型名称 (可选，默认 anthropic/claude-3.5-sonnet)
            OPENROUTER_SITE_URL: 站点URL (可选)
            OPENROUTER_APP_NAME: 应用名称 (可选)

        Anthropic:
            ANTHROPIC_API_KEY: API密钥
            ANTHROPIC_MODEL: 模型名称 (可选，默认 claude-3-5-sonnet-20241022)

    Returns:
        LLMProvider实例
    """
    provider_name = os.getenv("LLM_PROVIDER", "deepseek").lower()

    if provider_name == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY environment variable is required")

        return DeepSeekProvider(
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        )

    elif provider_name == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable is required")

        return OpenRouterProvider(
            api_key=api_key,
            model=os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
        )

    elif provider_name == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")

        return AnthropicProvider(
            api_key=api_key,
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
        )

    else:
        raise ValueError(
            f"Unknown LLM provider: {provider_name}. "
            f"Supported providers: deepseek, openrouter, anthropic"
        )
