"""
OCR服务客户端
调用DeepSeek-OCR-2服务进行图像文字识别
"""

import logging
import os
import requests
from typing import Optional, List, Dict
from pathlib import Path

logger = logging.getLogger("materialhub.ocr_client")

# 从环境变量获取OCR服务地址
# Docker容器中访问宿主机服务需要使用特殊地址：
# - Linux: host.docker.internal (需Docker 20.10+) 或 172.17.0.1 (默认网关)
# - Windows/Mac: host.docker.internal
OCR_SERVICE_URL = os.getenv("OCR_SERVICE_URL", "http://host.docker.internal:8010")

# OCR请求超时时间（秒），可通过环境变量配置
OCR_TIMEOUT = int(os.getenv("OCR_TIMEOUT", "120"))  # 默认120秒


def check_ocr_service() -> bool:
    """检查OCR服务是否可用"""
    try:
        response = requests.get(f"{OCR_SERVICE_URL}/health", timeout=30)
        return response.status_code == 200
    except Exception as e:
        logger.warning(f"OCR service not available: {e}")
        return False


def ocr_image(image_path: str, page_number: int = 1) -> Optional[str]:
    """
    对单个图像进行OCR识别

    Args:
        image_path: 图像文件路径
        page_number: 页码（用于记录）

    Returns:
        识别的Markdown文本，失败返回None
    """
    try:
        if not Path(image_path).exists():
            logger.error(f"Image file not found: {image_path}")
            return None

        with open(image_path, 'rb') as f:
            files = {'image': f}
            data = {'page_number': page_number}

            response = requests.post(
                f"{OCR_SERVICE_URL}/ocr/page",
                files=files,
                data=data,
                timeout=OCR_TIMEOUT
            )

        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                text = result.get('markdown_text', '')
                logger.info(f"OCR success for {Path(image_path).name}: {len(text)} chars")
                return text
            else:
                error = result.get('error', 'Unknown error')
                logger.error(f"OCR failed for {image_path}: {error}")
                return None
        else:
            logger.error(f"OCR service returned status {response.status_code}")
            return None

    except requests.exceptions.Timeout:
        logger.error(f"OCR request timeout for {image_path}")
        return None
    except Exception as e:
        logger.error(f"OCR error for {image_path}: {e}")
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
