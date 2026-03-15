"""
OCR服务客户端
支持多个OCR提供者：DeepSeek-OCR-2、BigModel (智谱) 和 PaddleOCR (本地)
"""

import logging
import os
import requests
import threading
from typing import Optional, List, Dict
from pathlib import Path

logger = logging.getLogger("materialhub.ocr_client")

# 从环境变量获取默认配置（可被系统设置覆盖）
OCR_SERVICE_URL = os.getenv("OCR_SERVICE_URL", "http://host.docker.internal:8010")
OCR_TIMEOUT = int(os.getenv("OCR_TIMEOUT", "120"))

BIGMODEL_API_URL = "https://open.bigmodel.cn/api/paas/v4/files/ocr"


# Thread-local provider override
_provider_override = threading.local()


def set_provider_override(provider: str):
    """Temporarily override OCR provider for the current thread."""
    _provider_override.value = provider


def clear_provider_override():
    """Clear the thread-local provider override."""
    _provider_override.value = None


def _get_ocr_provider() -> str:
    """获取当前OCR提供者设置。"""
    # Check thread-local override first
    override = getattr(_provider_override, 'value', None)
    if override:
        return override
    try:
        from dms_models import get_setting
        provider = get_setting("ocr_provider", "deepseek")
        return provider or "deepseek"
    except Exception:
        return "deepseek"


def _get_bigmodel_api_key() -> Optional[str]:
    """获取BigModel API密钥。"""
    # 优先从系统设置获取，其次从环境变量
    try:
        from dms_models import get_setting
        key = get_setting("bigmodel_api_key")
        if key:
            return key
    except Exception:
        pass
    return os.getenv("BIGMODEL_API_KEY")


def _get_deepseek_url() -> str:
    """获取DeepSeek OCR服务URL。"""
    try:
        from dms_models import get_setting
        url = get_setting("ocr_service_url")
        if url:
            return url
    except Exception:
        pass
    return OCR_SERVICE_URL


# ============================================================
# PaddleOCR singleton (lazy init, thread-safe)
# ============================================================

_paddle_ocr_instance = None
_paddle_ocr_lock = threading.Lock()


def _get_paddle_ocr():
    """Lazy-init PaddleOCR engine singleton."""
    global _paddle_ocr_instance
    if _paddle_ocr_instance is not None:
        return _paddle_ocr_instance

    with _paddle_ocr_lock:
        if _paddle_ocr_instance is not None:
            return _paddle_ocr_instance
        try:
            from paddleocr import PaddleOCR
            lang = "ch"
            try:
                from dms_models import get_setting
                lang = get_setting("paddleocr_lang", "ch") or "ch"
            except Exception:
                pass
            _paddle_ocr_instance = PaddleOCR(use_textline_orientation=True, lang=lang)
            logger.info(f"PaddleOCR engine initialized (lang={lang})")
            return _paddle_ocr_instance
        except ImportError:
            logger.error("PaddleOCR not installed. Run: pip install paddlepaddle paddleocr")
            return None
        except Exception as e:
            logger.error(f"PaddleOCR init failed: {e}")
            return None


def _parse_paddle_result(result, label: str = "") -> Optional[str]:
    """Parse PaddleOCR result into text string."""
    if not result:
        logger.warning(f"PaddleOCR returned empty result for {label}")
        return None

    lines = []
    for page in result:
        if not page:
            continue
        for line in page:
            # line format: [box_coords, (text, confidence)]
            if line and len(line) >= 2 and line[1]:
                text = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                lines.append(text)

    text = "\n".join(lines)
    if text:
        logger.info(f"PaddleOCR success for {label}: {len(text)} chars")
        return text
    else:
        logger.warning(f"PaddleOCR extracted no text from {label}")
        return None


def _ocr_paddleocr(image_path: str, page_number: int = 1) -> Optional[str]:
    """使用PaddleOCR进行本地OCR识别"""
    engine = _get_paddle_ocr()
    if engine is None:
        return None

    try:
        result = engine.ocr(image_path)
        return _parse_paddle_result(result, Path(image_path).name)
    except Exception as e:
        logger.error(f"PaddleOCR error for {image_path}: {e}")
        return None


def _ocr_paddleocr_bytes(image_bytes: bytes, label: str = "memory") -> Optional[str]:
    """使用PaddleOCR识别内存中的图片数据（避免临时文件锁问题）"""
    engine = _get_paddle_ocr()
    if engine is None:
        return None

    try:
        import numpy as np
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        img_array = np.array(img)
        result = engine.ocr(img_array)
        return _parse_paddle_result(result, label)
    except Exception as e:
        logger.error(f"PaddleOCR bytes error for {label}: {e}")
        return None


def check_ocr_service() -> bool:
    """检查OCR服务是否可用"""
    provider = _get_ocr_provider()

    if provider == "paddleocr":
        engine = _get_paddle_ocr()
        return engine is not None
    elif provider == "bigmodel":
        api_key = _get_bigmodel_api_key()
        if not api_key:
            logger.warning("BigModel API key not configured")
            return False
        return True
    else:
        # DeepSeek: health check
        try:
            url = _get_deepseek_url()
            response = requests.get(f"{url}/health", timeout=30)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"OCR service not available: {e}")
            return False


def _ocr_deepseek(image_path: str, page_number: int = 1, image_bytes: bytes = None) -> Optional[str]:
    """使用DeepSeek-OCR-2进行OCR识别。支持文件路径或直接传入字节数据。"""
    url = _get_deepseek_url()

    if image_bytes is not None:
        files = {'image': ('page.png', image_bytes, 'image/png')}
    else:
        files = {'image': open(image_path, 'rb')}

    try:
        data = {'page_number': page_number}
        response = requests.post(
            f"{url}/ocr/page",
            files=files,
            data=data,
            timeout=OCR_TIMEOUT
        )
    finally:
        if image_bytes is None:
            files['image'].close()

    if response.status_code == 200:
        result = response.json()
        if result.get('success'):
            text = result.get('markdown_text', '')
            logger.info(f"DeepSeek OCR success: {len(text)} chars")
            return text
        else:
            error = result.get('error', 'Unknown error')
            logger.error(f"DeepSeek OCR failed: {error}")
            return None
    else:
        logger.error(f"DeepSeek OCR service returned status {response.status_code}")
        return None


def _ocr_bigmodel(image_path: str, page_number: int = 1, image_bytes: bytes = None) -> Optional[str]:
    """使用BigModel (智谱) 进行OCR识别。支持文件路径或直接传入字节数据。"""
    api_key = _get_bigmodel_api_key()
    if not api_key:
        logger.error("BigModel API key not configured")
        return None

    # 读取BigModel特定设置
    tool_type = "hand_write"
    language_type = "CHN_ENG"
    try:
        from dms_models import get_setting
        tool_type = get_setting("bigmodel_tool_type", "hand_write") or "hand_write"
        language_type = get_setting("bigmodel_language_type", "CHN_ENG") or "CHN_ENG"
    except Exception:
        pass

    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    if image_bytes is not None:
        filename = "page.png"
        file_tuple = ('file', (filename, image_bytes, 'image/png'))
    else:
        f = open(image_path, 'rb')
        file_tuple = ('file', (Path(image_path).name, f))

    try:
        data = {
            'tool_type': tool_type,
            'language_type': language_type,
            'probability': 'false',
        }

        response = requests.post(
            BIGMODEL_API_URL,
            headers=headers,
            files=[file_tuple],
            data=data,
            timeout=OCR_TIMEOUT
        )
    finally:
        if image_bytes is None:
            f.close()

    if response.status_code == 200:
        result = response.json()
        logger.info(f"BigModel OCR response: status={result.get('status')}, keys={list(result.keys())}")

        # 判断是否成功: status=="succeeded" 或 code==200 或有data字段
        is_success = (
            result.get("status") == "succeeded"
            or result.get("code") == 200
            or "data" in result
        )

        if is_success:
            text = ""

            # 格式1: words_result 数组 (百度兼容格式)
            words_result = result.get("words_result")
            if isinstance(words_result, list) and words_result:
                text = "\n".join(item.get("words", "") for item in words_result if item.get("words"))

            # 格式2: data.content / data.text / data.markdown
            if not text:
                data_obj = result.get("data") or result.get("result") or {}
                if isinstance(data_obj, dict):
                    text = data_obj.get("content", "") or data_obj.get("text", "") or data_obj.get("markdown", "")
                elif isinstance(data_obj, str):
                    text = data_obj

            if text:
                logger.info(f"BigModel OCR success for {Path(image_path).name}: {len(text)} chars")
                return text
            else:
                logger.warning(f"BigModel OCR returned empty text for {image_path}, response keys: {list(result.keys())}")
                return None
        else:
            error = result.get("message", result.get("msg", "Unknown error"))
            logger.error(f"BigModel OCR failed for {image_path}: {error}")
            return None
    else:
        logger.error(f"BigModel OCR returned status {response.status_code}: {response.text[:200]}")
        return None


def ocr_image(image_path: str, page_number: int = 1) -> Optional[str]:
    """
    对单个图像进行OCR识别（自动选择提供者）

    Args:
        image_path: 图像文件路径
        page_number: 页码（用于记录）

    Returns:
        识别的文本，失败返回None
    """
    try:
        if not Path(image_path).exists():
            logger.error(f"Image file not found: {image_path}")
            return None

        provider = _get_ocr_provider()

        if provider == "paddleocr":
            return _ocr_paddleocr(image_path, page_number)
        elif provider == "bigmodel":
            return _ocr_bigmodel(image_path, page_number)
        else:
            return _ocr_deepseek(image_path, page_number)

    except requests.exceptions.Timeout:
        logger.error(f"OCR request timeout for {image_path}")
        return None
    except Exception as e:
        logger.error(f"OCR error for {image_path}: {e}")
        return None


def ocr_image_bytes(image_bytes: bytes, page_number: int = 1, label: str = "memory") -> Optional[str]:
    """
    对内存中的图像字节数据进行OCR识别（避免临时文件，解决Windows文件锁问题）

    所有提供者都支持直接内存输入。
    """
    try:
        provider = _get_ocr_provider()

        if provider == "paddleocr":
            return _ocr_paddleocr_bytes(image_bytes, label)
        elif provider == "bigmodel":
            return _ocr_bigmodel("", page_number, image_bytes=image_bytes)
        else:
            return _ocr_deepseek("", page_number, image_bytes=image_bytes)

    except Exception as e:
        logger.error(f"OCR bytes error for {label}: {e}")
        return None


def batch_ocr_images(image_paths: List[str]) -> Dict[str, str]:
    """
    批量OCR多个图像

    Args:
        image_paths: 图像文件路径列表

    Returns:
        {image_path: ocr_text} 字典
    """
    results = {}

    for i, image_path in enumerate(image_paths, 1):
        text = ocr_image(image_path, page_number=i)
        if text:
            results[image_path] = text

    logger.info(f"Batch OCR completed: {len(results)}/{len(image_paths)} succeeded")
    return results
