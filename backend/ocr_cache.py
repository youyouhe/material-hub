"""
OCR结果缓存模块
使用文件hash + 页码作为缓存key，避免重复OCR
"""

import os
import json
import hashlib
import logging
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger("materialhub.ocr_cache")

# 缓存目录
CACHE_DIR = Path(os.getenv("DATA_DIR", "data")) / "ocr_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_file_hash(file_path: str, chunk_size: int = 8192) -> str:
    """
    计算文件的MD5 hash（内存友好，分块读取）

    Args:
        file_path: 文件路径
        chunk_size: 读取块大小（默认8KB）

    Returns:
        文件的MD5 hash（16进制字符串）
    """
    md5_hash = hashlib.md5()

    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()
    except Exception as e:
        logger.error(f"计算文件hash失败: {e}")
        return ""


def get_cache_key(file_path: str, page_num: int) -> str:
    """
    生成OCR缓存key

    Args:
        file_path: 文件路径
        page_num: 页码（从0开始）

    Returns:
        缓存key格式: {file_hash}_{page_num}
    """
    file_hash = get_file_hash(file_path)
    if not file_hash:
        return ""
    return f"{file_hash}_{page_num}"


def get_cached_ocr(file_path: str, page_num: int) -> Optional[Dict]:
    """
    从缓存获取OCR结果

    Args:
        file_path: 文件路径
        page_num: 页码（从0开始）

    Returns:
        OCR结果字典，包含text和metadata，如果缓存不存在返回None
    """
    cache_key = get_cache_key(file_path, page_num)
    if not cache_key:
        return None

    cache_file = CACHE_DIR / f"{cache_key}.json"

    if not cache_file.exists():
        return None

    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            cached_data = json.load(f)
        logger.debug(f"✅ OCR缓存命中: 页{page_num + 1}")
        return cached_data
    except Exception as e:
        logger.warning(f"读取OCR缓存失败: {e}")
        return None


def save_ocr_to_cache(file_path: str, page_num: int, ocr_text: str, metadata: Dict = None) -> bool:
    """
    保存OCR结果到缓存

    Args:
        file_path: 文件路径
        page_num: 页码（从0开始）
        ocr_text: OCR识别的文本
        metadata: 可选的元数据（如字符数、状态等）

    Returns:
        是否保存成功
    """
    cache_key = get_cache_key(file_path, page_num)
    if not cache_key:
        return False

    cache_file = CACHE_DIR / f"{cache_key}.json"

    cache_data = {
        "text": ocr_text,
        "page_num": page_num,
        "char_count": len(ocr_text),
        "metadata": metadata or {},
        "cached_at": datetime.utcnow().isoformat()
    }

    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        logger.debug(f"💾 OCR结果已缓存: 页{page_num + 1}")
        return True
    except Exception as e:
        logger.error(f"保存OCR缓存失败: {e}")
        return False


def clear_cache_for_file(file_path: str) -> int:
    """
    清除某个文件的所有OCR缓存

    Args:
        file_path: 文件路径

    Returns:
        删除的缓存数量
    """
    file_hash = get_file_hash(file_path)
    if not file_hash:
        return 0

    pattern = f"{file_hash}_*.json"
    deleted_count = 0

    for cache_file in CACHE_DIR.glob(pattern):
        try:
            cache_file.unlink()
            deleted_count += 1
        except Exception as e:
            logger.warning(f"删除缓存文件失败: {cache_file}, {e}")

    if deleted_count > 0:
        logger.info(f"🗑️ 清除OCR缓存: {deleted_count} 个")

    return deleted_count


def get_cache_stats() -> Dict:
    """
    获取缓存统计信息

    Returns:
        包含缓存文件数量和总大小的字典
    """
    cache_files = list(CACHE_DIR.glob("*.json"))
    total_size = sum(f.stat().st_size for f in cache_files)

    return {
        "cache_count": len(cache_files),
        "total_size_mb": round(total_size / 1024 / 1024, 2),
        "cache_dir": str(CACHE_DIR)
    }


# 需要在文件开头导入datetime
from datetime import datetime
