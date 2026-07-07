"""
Knowledge Base Chunking Engine.

Ports SAG's chunking logic (src/ingestion/chunking/markdown.ts) to Python.
Two strategies:
  1. token  — sliding window with tiktoken (primary, for OCR/text without structure)
  2. heading — regex-based Chinese structure detection (secondary)

For OCR text (MaterialHub's primary input), token-based chunking is the default.
"""

import re
import logging
from typing import List, Dict, Optional

try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False

logger = logging.getLogger("materialhub.kb_chunking")

# Default chunking parameters (matching SAG's defaults)
DEFAULT_CHUNK_SIZE = 512   # tokens
DEFAULT_OVERLAP = 64       # tokens
MIN_CHUNK_SIZE = 64
MAX_CHUNK_SIZE = 8192


# Chinese document structure markers (equivalent to markdown headings)
_CHINESE_HEADING_PATTERNS = [
    # Numbered sections: 一、二、三、 or 1. 2. 3.
    re.compile(r'^[一二三四五六七八九十]+、'),
    re.compile(r'^第[一二三四五六七八九十\d]+[章节条款]'),
    # Latin numbered: 1. 2. 3. or 1) 2) 3)
    re.compile(r'^\d+[\.\)、]\s'),
    # Common document field markers
    re.compile(r'^(项目名称|合同编号|甲方|乙方|供应商|采购人|项目编号|招标编号|投标人|中标人)[：:]'),
    re.compile(r'^(法定代表人|注册资本|成立日期|营业期限|经营范围|统一社会信用代码)[：:]'),
    re.compile(r'^(公司名称|企业名称|单位名称|机构名称|地址|电话|传真|邮编)[：:]'),
    re.compile(r'^(签订日期|生效日期|到期日期|签署日期|发布日期|开标日期)[：:]'),
    # English-like headings
    re.compile(r'^[A-Z][A-Za-z\s]{2,60}$'),
]


def _detect_headings(text: str) -> List[Dict]:
    """Detect Chinese document structure markers as pseudo-headings.

    Returns list of {line_index, heading_text, char_position}.
    """
    lines = text.split('\n')
    headings = []
    char_pos = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or len(stripped) > 120:
            char_pos += len(line) + 1
            continue

        for pattern in _CHINESE_HEADING_PATTERNS:
            if pattern.match(stripped):
                headings.append({
                    "line_index": i,
                    "heading_text": stripped[:80],
                    "char_position": char_pos,
                })
                break

        char_pos += len(line) + 1

    return headings


def _token_count(text: str, encoding) -> int:
    """Count tokens in text using tiktoken."""
    return len(encoding.encode(text))


def _chunk_by_token_sliding(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> List[Dict]:
    """Token-based sliding window chunking (primary strategy).

    Ported from SAG's token mode in chunking/markdown.ts.
    """
    if not _TIKTOKEN_AVAILABLE:
        # Fallback: character-based chunking
        return _chunk_by_char_sliding(text, chunk_size * 2, overlap * 2)

    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(text)
    total_tokens = len(tokens)

    if total_tokens <= chunk_size:
        decoded = encoding.decode(tokens)
        return [{
            "chunk_index": 0,
            "content": decoded,
            "token_count": total_tokens,
            "heading_path": None,
        }]

    chunks = []
    stride = max(1, chunk_size - overlap)
    chunk_index = 0

    start = 0
    while start < total_tokens:
        end = min(start + chunk_size, total_tokens)
        chunk_tokens = tokens[start:end]
        decoded = encoding.decode(chunk_tokens)

        # Find heading for this chunk (first detected marker in chunk)
        heading = None
        lines = decoded.split('\n')
        for line in lines[:3]:
            stripped = line.strip()
            if stripped and any(p.match(stripped) for p in _CHINESE_HEADING_PATTERNS):
                heading = stripped[:80]
                break

        chunks.append({
            "chunk_index": chunk_index,
            "content": decoded.strip(),
            "token_count": len(chunk_tokens),
            "heading_path": heading,
        })

        chunk_index += 1
        start += stride

    return chunks


def _chunk_by_char_sliding(
    text: str,
    chunk_size: int = 1024,
    overlap: int = 128,
) -> List[Dict]:
    """Character-based sliding window (fallback when tiktoken unavailable)."""
    if len(text) <= chunk_size:
        return [{"chunk_index": 0, "content": text, "token_count": len(text), "heading_path": None}]

    chunks = []
    stride = max(1, chunk_size - overlap)
    chunk_index = 0
    pos = 0

    while pos < len(text):
        end = min(pos + chunk_size, len(text))
        content = text[pos:end].strip()
        if content:
            chunks.append({
                "chunk_index": chunk_index,
                "content": content,
                "token_count": len(content),
                "heading_path": None,
            })
            chunk_index += 1
        pos += stride

    return chunks


def _chunk_by_heading(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> List[Dict]:
    """Heading-aware chunking for structured documents.

    Splits text at detected Chinese structure markers, then sub-chunks
    large sections with token-based sliding window.
    """
    headings = _detect_headings(text)

    if len(headings) <= 1:
        # No clear structure — fall back to token-based
        return _chunk_by_token_sliding(text, chunk_size, overlap)

    # Build sections between headings
    sections = []
    for i, h in enumerate(headings):
        start = h["char_position"]
        end = headings[i + 1]["char_position"] if i + 1 < len(headings) else len(text)
        section_text = text[start:end].strip()
        if section_text:
            sections.append({
                "heading": h["heading_text"],
                "content": section_text,
            })

    # For each section, sub-chunk if too large
    chunks = []
    chunk_index = 0
    for section in sections:
        if _TIKTOKEN_AVAILABLE:
            encoding = tiktoken.get_encoding("cl100k_base")
            token_count_val = _token_count(section["content"], encoding)
        else:
            token_count_val = len(section["content"])

        if token_count_val <= chunk_size:
            chunks.append({
                "chunk_index": chunk_index,
                "content": section["content"],
                "token_count": token_count_val,
                "heading_path": section["heading"],
            })
            chunk_index += 1
        else:
            sub_chunks = _chunk_by_token_sliding(section["content"], chunk_size, overlap)
            for sc in sub_chunks:
                sc["chunk_index"] = chunk_index
                sc["heading_path"] = section["heading"]
                chunks.append(sc)
                chunk_index += 1

    return chunks


def chunk_text(
    text: str,
    strategy: str = "token",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> List[Dict]:
    """Chunk text for KB ingestion.

    Args:
        text: The document text (OCR output, markdown, or plain text)
        strategy: "token" (default, sliding window) or "heading" (structure-aware)
        chunk_size: max tokens per chunk (64-8192)
        overlap: overlap tokens between chunks (0-4096)

    Returns:
        List of chunk dicts with: chunk_index, content, token_count, heading_path
    """
    # Clamp parameters
    chunk_size = max(MIN_CHUNK_SIZE, min(MAX_CHUNK_SIZE, chunk_size))
    overlap = max(0, min(chunk_size // 2, overlap))

    if not text or not text.strip():
        return []

    if strategy == "heading":
        chunks = _chunk_by_heading(text, chunk_size, overlap)
        if chunks:
            return chunks
        # Fallback
        logger.debug("Heading strategy produced no chunks, falling back to token")

    return _chunk_by_token_sliding(text, chunk_size, overlap)
