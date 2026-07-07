#!/usr/bin/env python3
"""
Document structure analyzer using LLM for intelligent parsing.
This extracts document structure and uses LLM to understand section hierarchy.
"""

import os
import re
from dataclasses import dataclass
from typing import Optional

from docx import Document
from docx.oxml.ns import qn


@dataclass
class DocumentElement:
    """Represents a document element with its position."""
    index: int
    type: str  # 'paragraph', 'table', 'image'
    text: str
    style: str
    has_image: bool
    image_count: int = 0


def get_para_text(elem) -> str:
    """Get plain text from a w:p XML element."""
    texts = []
    for r in elem.iter(qn("w:t")):
        if r.text:
            texts.append(r.text)
    return "".join(texts)


def count_images_in_elem(elem, doc_part) -> int:
    """Count images in an element."""
    count = 0
    seen = set()
    for blip in elem.iter(qn("a:blip")):
        r_id = blip.get(qn("r:embed"))
        if r_id and r_id not in seen and r_id in doc_part.rels:
            seen.add(r_id)
            count += 1
    return count


def extract_document_structure(docx_path: str) -> list[DocumentElement]:
    """Extract all elements from document with their structure info."""
    doc = Document(docx_path)
    body = doc.element.body
    elements = []

    for i, elem in enumerate(body):
        if elem.tag == qn("w:p"):
            text = get_para_text(elem).strip()

            # Get style
            style_val = ""
            style_elem = elem.find(qn("w:pPr"))
            if style_elem is not None:
                style_ref = style_elem.find(qn("w:pStyle"))
                if style_ref is not None:
                    style_val = style_ref.get(qn("w:val"), "")

            # Count images
            img_count = count_images_in_elem(elem, doc.part)

            elements.append(DocumentElement(
                index=i,
                type='paragraph',
                text=text,
                style=style_val,
                has_image=img_count > 0,
                image_count=img_count
            ))

        elif elem.tag == qn("w:tbl"):
            elements.append(DocumentElement(
                index=i,
                type='table',
                text='[TABLE]',
                style='',
                has_image=False
            ))

    return elements


def generate_structure_prompt(elements: list[DocumentElement], max_elements: int = 200) -> str:
    """Generate a prompt for LLM to analyze document structure."""
    # Sample elements if too many
    sample = elements[:max_elements]

    lines = []
    lines.append("请分析以下Word文档的结构，识别出所有的标题（section/heading）及其层级。")
    lines.append("文档元素如下（格式：索引 | 样式 | 图片数 | 文本内容）：")
    lines.append("")

    for elem in sample:
        style_marker = f"[{elem.style}]" if elem.style else ""
        img_marker = f"[{elem.image_count}图]" if elem.has_image else ""
        text_preview = elem.text[:80] if elem.text else "(空)"

        lines.append(f"{elem.index:4d} | {style_marker:20s} | {img_marker:8s} | {text_preview}")

    lines.append("")
    lines.append("请以JSON格式返回标题列表，格式如下：")
    lines.append('[')
    lines.append('  {"index": 5, "level": 1, "section": "一", "title": "报价部分"},')
    lines.append('  {"index": 15, "level": 2, "section": "1.1", "title": "营业执照"},')
    lines.append('  ...')
    lines.append(']')
    lines.append("")
    lines.append("注意：")
    lines.append("- level表示标题层级（1=一级标题，2=二级标题，以此类推）")
    lines.append("- section是编号（如\"一\"、\"1.1\"、\"2.3.4\"），如果没有编号则留空")
    lines.append("- title是标题文本")
    lines.append("- 只返回JSON数组，不要其他解释")

    return "\n".join(lines)


def print_document_structure(docx_path: str, output_file: Optional[str] = None):
    """Print document structure for analysis."""
    elements = extract_document_structure(docx_path)

    output_lines = []
    output_lines.append(f"📄 Document Analysis: {os.path.basename(docx_path)}")
    output_lines.append(f"Total elements: {len(elements)}")
    output_lines.append("=" * 100)
    output_lines.append("")

    # Summary
    para_count = sum(1 for e in elements if e.type == 'paragraph')
    table_count = sum(1 for e in elements if e.type == 'table')
    image_count = sum(e.image_count for e in elements)
    text_elements = sum(1 for e in elements if e.text and e.type == 'paragraph')

    output_lines.append(f"📊 Summary:")
    output_lines.append(f"  - Paragraphs: {para_count}")
    output_lines.append(f"  - Tables: {table_count}")
    output_lines.append(f"  - Paragraphs with text: {text_elements}")
    output_lines.append(f"  - Total images: {image_count}")
    output_lines.append("")
    output_lines.append("=" * 100)
    output_lines.append("")

    # First 100 elements
    output_lines.append("📑 First 100 elements:")
    output_lines.append("")
    output_lines.append(f"{'Idx':>4} | {'Style':<20} | {'Img':>6} | {'Text'}")
    output_lines.append("-" * 100)

    for elem in elements[:100]:
        style_marker = f"[{elem.style}]" if elem.style else ""
        img_marker = f"[{elem.image_count}图]" if elem.has_image else ""
        text_preview = elem.text[:70] if elem.text else ""

        output_lines.append(f"{elem.index:4d} | {style_marker:<20} | {img_marker:>6} | {text_preview}")

    # LLM prompt
    output_lines.append("")
    output_lines.append("=" * 100)
    output_lines.append("")
    output_lines.append("🤖 LLM Analysis Prompt:")
    output_lines.append("")
    output_lines.append(generate_structure_prompt(elements))

    output = "\n".join(output_lines)

    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"Analysis written to: {output_file}")
    else:
        print(output)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python document_analyzer.py <docx_file> [output_file]")
        sys.exit(1)

    docx_path = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    print_document_structure(docx_path, output_file)
