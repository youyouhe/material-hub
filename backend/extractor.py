"""
Linear document extractor for MaterialHub.

Single-pass scan through .docx body elements:
- Detect section headings (Heading styles + numbered patterns)
- Extract images following each heading
- Auto-detect expiry dates from surrounding text
"""

import os
import re
import logging
from typing import Optional, List, Tuple
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

logger = logging.getLogger("materialhub.extractor")

MIN_IMAGE_BYTES = 5000
ALLOWED_EXTS = {"png", "jpg", "jpeg", "gif", "bmp", "tiff", "tif"}

# Patterns for numbered section headers
CHINESE_MAJOR_RE = re.compile(r"^([一二三四五六七八九十]+)、\s*(.+)")
ARABIC_SECTION_RE = re.compile(r"^(\d+(?:\.\d+)*)[\.\．\s]\s*(.+)")

# Patterns for expiry date detection
EXPIRY_PATTERNS = [
    # 有效期至：2025年12月31日 / 有效期至2025年12月31日
    re.compile(r"有效期[至到][:：]?\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"),
    # 有效期：2024.06.30 / 有效日期：2024-06-30
    re.compile(r"有效[期日][期]*[:：]\s*(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})"),
    # 至 2026年03月15日
    re.compile(r"至\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"),
    # Valid Until: 2025-12-31
    re.compile(r"[Vv]alid\s+[Uu]ntil[:：]?\s*(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})"),
    # 有效期至2025/12/31
    re.compile(r"有效期[至到]\s*(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})"),
]


@dataclass
class ExtractedMaterial:
    section: str
    title: str
    heading_level: int
    image_data: bytes
    image_ext: str
    image_filename: str  # Actual filename saved to disk
    expiry_date: Optional[str] = None  # ISO format YYYY-MM-DD


@dataclass
class SectionInfo:
    section: str
    title: str
    level: int
    text_buffer: List[str] = field(default_factory=list)


def _get_para_text(elem) -> str:
    """Get plain text from a w:p XML element."""
    texts = []
    for r in elem.iter(qn("w:t")):
        if r.text:
            texts.append(r.text)
    return "".join(texts)


def _detect_heading(elem) -> Optional[SectionInfo]:
    """Check if element is a heading (by style or numbered pattern)."""
    if elem.tag != qn("w:p"):
        return None

    text = _get_para_text(elem).strip()
    if not text:
        return None

    # Strategy 1: Chinese major numbering (一、报价部分)
    # Check first because it's most specific
    if len(text) <= 100:
        m = CHINESE_MAJOR_RE.match(text)
        if m:
            return SectionInfo(
                section=m.group(1) + "、",
                title=m.group(2).strip(),
                level=1,
            )

    # Strategy 2: Arabic numbered (10.1 营业执照)
    # Check before style because text numbering is more explicit
    if len(text) <= 200:
        m = ARABIC_SECTION_RE.match(text)
        if m:
            num = m.group(1)
            title = m.group(2).strip()
            top = int(num.split(".")[0])
            if top < 100 and len(title) < 150:
                return SectionInfo(
                    section=num,
                    title=title,
                    level=len(num.split(".")) + 1,
                )

    # Strategy 3: Heading style (including numeric styles)
    style_elem = elem.find(qn("w:pPr"))
    if style_elem is not None:
        style_ref = style_elem.find(qn("w:pStyle"))
        if style_ref is not None:
            style_val = style_ref.get(qn("w:val"), "")

            # Check for standard Heading styles
            if style_val.startswith("Heading") or style_val.startswith("heading"):
                try:
                    level = int(style_val.replace("Heading", "").replace("heading", "").strip())
                    if 1 <= level <= 9:
                        return SectionInfo(section="", title=text, level=level)
                except ValueError:
                    pass

            # Check for numeric styles (1, 2, 3, 4, etc.) used as heading levels
            # Common in Chinese documents
            if style_val.isdigit():
                try:
                    level = int(style_val)
                    if 1 <= level <= 9 and len(text) < 200:
                        return SectionInfo(section="", title=text, level=level)
                except ValueError:
                    pass

            # Check for custom heading styles like "a1", "af0", "af1" etc.
            # These might indicate headings in some templates
            if len(style_val) <= 10 and len(text) < 100 and text and not text.startswith("供应商") and not text.startswith("日期"):
                # Common heading patterns in Chinese documents
                common_headings = [
                    "承诺书", "证明", "授权", "说明", "声明", "情况表",
                    "基本情况", "管理体系", "资质", "证书", "执照"
                ]
                if any(keyword in text for keyword in common_headings):
                    # Estimate level based on context
                    if style_val in ["a1", "af1", "af0"]:
                        return SectionInfo(section="", title=text, level=3)

    return None


def _extract_images_from_elem(elem, doc_part) -> List[Tuple[bytes, str]]:
    """Extract embedded images from a single XML element."""
    images = []
    seen = set()

    for blip in elem.iter(qn("a:blip")):
        r_id = blip.get(qn("r:embed"))
        if not r_id or r_id in seen:
            continue
        if r_id not in doc_part.rels:
            continue
        seen.add(r_id)

        try:
            part = doc_part.rels[r_id].target_part
            data = part.blob
            ext = part.partname.split(".")[-1].lower()

            if ext not in ALLOWED_EXTS:
                continue
            if len(data) < MIN_IMAGE_BYTES:
                continue

            images.append((data, ext))
        except Exception:
            pass

    return images


def _detect_expiry_date(text: str) -> Optional[str]:
    """Try to extract an expiry date from text."""
    for pattern in EXPIRY_PATTERNS:
        m = pattern.search(text)
        if m:
            try:
                year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if 2000 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                    return f"{year:04d}-{month:02d}-{day:02d}"
            except (ValueError, IndexError):
                continue
    return None


def _safe_filename(s: str) -> str:
    """Make string safe for filenames."""
    s = re.sub(r'[\\/:*?"<>|\u201c\u201d\u2018\u2019]', "_", s)
    s = re.sub(r"[（）()\[\]【】]", "_", s)
    s = re.sub(r"\s+", "_", s)
    s = s.strip("_.")
    return s[:80]


def extract_materials(docx_path: str, output_dir: str) -> List[ExtractedMaterial]:
    """
    Linear scan through a .docx file.
    Returns list of extracted materials (section + image pairs).
    """
    os.makedirs(output_dir, exist_ok=True)
    doc = Document(docx_path)
    body = doc.element.body
    elements = list(body)

    current_section: Optional[SectionInfo] = None
    results: List[ExtractedMaterial] = []
    image_counter: dict = {}  # track per-section image count

    for elem in elements:
        # Check if this element is a heading
        heading = _detect_heading(elem)
        if heading is not None:
            current_section = heading
            continue

        if current_section is None:
            continue

        # Accumulate text for expiry date detection
        if elem.tag == qn("w:p"):
            text = _get_para_text(elem).strip()
            if text:
                current_section.text_buffer.append(text)

        # Extract images from this element
        images = _extract_images_from_elem(elem, doc.part)
        if not images:
            continue

        # Detect expiry date from accumulated text
        combined_text = " ".join(current_section.text_buffer)
        expiry = _detect_expiry_date(combined_text)

        section_key = current_section.section or current_section.title
        base_name = _safe_filename(
            f"{current_section.section}-{current_section.title}"
            if current_section.section
            else current_section.title
        )

        for img_data, img_ext in images:
            # Generate unique filename
            count = image_counter.get(section_key, 0) + 1
            image_counter[section_key] = count

            if count == 1 and len(images) == 1:
                fname = f"{base_name}.{img_ext}"
            else:
                fname = f"{base_name}-{count:02d}.{img_ext}"

            # Deduplicate filename
            full_path = os.path.join(output_dir, fname)
            while os.path.exists(full_path):
                count += 1
                image_counter[section_key] = count
                fname = f"{base_name}-{count:02d}.{img_ext}"
                full_path = os.path.join(output_dir, fname)

            # Save image
            with open(full_path, "wb") as f:
                f.write(img_data)

            results.append(
                ExtractedMaterial(
                    section=current_section.section,
                    title=current_section.title,
                    heading_level=current_section.level,
                    image_data=img_data,
                    image_ext=img_ext,
                    image_filename=fname,
                    expiry_date=expiry,
                )
            )

            logger.info(
                "Extracted: %s (%d bytes, expiry=%s)",
                fname,
                len(img_data),
                expiry or "N/A",
            )

    logger.info(
        "Extraction complete: %d images from %s",
        len(results),
        os.path.basename(docx_path),
    )
    return results
