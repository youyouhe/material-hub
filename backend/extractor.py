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

# A section with >= this many consecutive images is treated as a COMPOSITE
# document (audit report, contract, full proposal) rather than atomic materials.
# Atomic materials (single license, ID card) rarely exceed 2 images.
COMPOSITE_IMAGE_THRESHOLD = 5

# For composite docs, only OCR this many leading pages to extract metadata.
# Detailed reading is left to humans.
COMPOSITE_OCR_SAMPLE_PAGES = 3

# A text section with >= this many chars is worth extracting as a standalone
# text material (e.g. technical proposal narrative, commitment letter body).
TEXT_SECTION_MIN_CHARS = 200

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
class SectionInfo:
    """Heading detection result (a detected section title)."""
    section: str
    title: str
    level: int

@dataclass
class ExtractedImage:
    """A single embedded image extracted from a docx."""
    data: bytes
    ext: str
    filename: str = ""


@dataclass
class ExtractedMaterial:
    """A deconstructed material unit from a bid document.

    Three natures:
      - atomic:    a single reusable certificate/license (1-2 images), deep-OCR'd
      - composite: a multi-page doc kept whole (audit report, contract),
                   only leading pages OCR'd for metadata
      - text:      a pure-text section (technical narrative, commitment letter)
    """
    section: str
    title: str
    heading_level: int
    nature: str = "atomic"  # "atomic" | "composite" | "text"
    images: List["ExtractedImage"] = field(default_factory=list)
    text: str = ""
    expiry_date: Optional[str] = None


@dataclass
class SectionBundle:
    """Accumulates all elements under one heading before split decision."""
    section: str
    title: str
    level: int
    images: List[ExtractedImage] = field(default_factory=list)
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

def extract_materials(docx_path: str, output_dir: str = None) -> List[ExtractedMaterial]:
    """Deconstruct a bid .docx into atomic/composite/text material units.

    Phase 1: single-pass scan groups body elements under detected headings
             into SectionBundle objects (text + images accumulated per section).
    Phase 2: each bundle is classified by image count:
             - >= COMPOSITE_IMAGE_THRESHOLD images → composite (kept whole)
             - 1..threshold-1 images              → atomic (one material per image)
             - 0 images but enough text           → text material

    Args:
        docx_path: path to the .docx file
        output_dir: if given, image bytes are also written to disk (legacy compat);
                    if None, images stay in-memory only (caller persists them)

    Returns:
        List[ExtractedMaterial] — each has .nature, .images, .text, .expiry_date
    """
    doc = Document(docx_path)
    body = doc.element.body
    elements = list(body)

    # ── Phase 1: collect bundles ──
    bundles: List[SectionBundle] = []
    current: Optional[SectionBundle] = None

    for elem in elements:
        heading = _detect_heading(elem)
        if heading is not None:
            if current is not None and (current.images or current.text_buffer):
                bundles.append(current)
            current = SectionBundle(
                section=heading.section,
                title=heading.title,
                level=heading.level,
            )
            continue

        if current is None:
            continue

        # Accumulate paragraph text
        if elem.tag == qn("w:p"):
            text = _get_para_text(elem).strip()
            if text:
                current.text_buffer.append(text)

        # Accumulate images
        for img_data, img_ext in _extract_images_from_elem(elem, doc.part):
            current.images.append(ExtractedImage(data=img_data, ext=img_ext))

    # Flush last section
    if current is not None and (current.images or current.text_buffer):
        bundles.append(current)

    logger.info(
        "Phase 1: %d sections collected from %s",
        len(bundles), os.path.basename(docx_path),
    )

    # ── Phase 2: classify each bundle into materials ──
    results: List[ExtractedMaterial] = []
    image_seq = 0  # global counter for unique filenames

    for b in bundles:
        combined_text = " ".join(b.text_buffer)
        expiry = _detect_expiry_date(combined_text)
        base_name = _safe_filename(
            f"{b.section}-{b.title}" if b.section else b.title
        )
        n_images = len(b.images)

        if n_images >= COMPOSITE_IMAGE_THRESHOLD:
            # Composite: keep all images as ONE material, no per-image split
            for img in b.images:
                image_seq += 1
                img.filename = f"{base_name}-p{image_seq:03d}.{img.ext}"
                if output_dir:
                    _write_image(output_dir, img)
            results.append(ExtractedMaterial(
                section=b.section, title=b.title, heading_level=b.level,
                nature="composite", images=list(b.images),
                text=combined_text[:2000], expiry_date=expiry,
            ))
            logger.info("Composite: %s (%d images)", b.title, n_images)

        elif n_images > 0:
            # Atomic: each image becomes its own material
            for img in b.images:
                image_seq += 1
                img.filename = f"{base_name}-{image_seq:03d}.{img.ext}"
                if output_dir:
                    _write_image(output_dir, img)
                results.append(ExtractedMaterial(
                    section=b.section, title=b.title, heading_level=b.level,
                    nature="atomic", images=[img],
                    text="", expiry_date=expiry,
                ))
            logger.info("Atomic: %s (%d images → %d materials)", b.title, n_images, n_images)

        elif len(combined_text) >= TEXT_SECTION_MIN_CHARS:
            # Pure text section (no images, enough prose)
            results.append(ExtractedMaterial(
                section=b.section, title=b.title, heading_level=b.level,
                nature="text", images=[], text=combined_text, expiry_date=expiry,
            ))
            logger.info("Text: %s (%d chars)", b.title, len(combined_text))

    logger.info(
        "Phase 2: %d materials from %s (atomic/composite/text split)",
        len(results), os.path.basename(docx_path),
    )
    return results


def _write_image(output_dir: str, img: "ExtractedImage") -> None:
    """Write an ExtractedImage to disk (helper for legacy output_dir mode)."""
    os.makedirs(output_dir, exist_ok=True)
    full_path = os.path.join(output_dir, img.filename)
    # Deduplicate filename
    while os.path.exists(full_path):
        image_seq = int(img.filename.rsplit("-", 1)[-1].split(".")[0].replace("p", "")) + 1
        img.filename = f"{img.filename.rsplit('-', 1)[0]}-p{image_seq:03d}.{img.ext}"
        full_path = os.path.join(output_dir, img.filename)
    with open(full_path, "wb") as f:
        f.write(img.data)
