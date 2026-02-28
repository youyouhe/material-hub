"""
合同关键页面智能识别模块
扫描合同所有页面，识别首页、金额/服务范围页、签字盖章页
"""
import logging
from typing import List, Dict
from llm_provider import get_llm_provider

logger = logging.getLogger("materialhub.contract_page_analyzer")


async def analyze_contract_key_pages(ocr_texts: List[Dict], total_pages: int) -> Dict:
    """
    分析合同所有页面，识别关键页面

    Args:
        ocr_texts: 每页的OCR文本列表，格式: [{"page": 1, "text": "..."}, ...]
        total_pages: 总页数

    Returns:
        {
            "key_pages": [
                {
                    "page_num": 0,  # 页码（从0开始）
                    "page_type": "first_page",  # first_page | content_page | signature_page
                    "reason": "包含合同标题、甲乙方信息",
                    "title_suffix": "首页"
                },
                ...
            ],
            "analysis_summary": "识别到首页、2个内容页、签字页"
        }
    """

    if not ocr_texts or len(ocr_texts) == 0:
        logger.warning("没有OCR文本，无法分析关键页面")
        return {
            "key_pages": [],
            "analysis_summary": "无OCR文本"
        }

    # 如果页数太多，智能筛选关键区域（前10页 + 后5页）
    # 避免context过大，同时覆盖首页和签字页
    if len(ocr_texts) > 30:
        logger.info(f"合同页数较多({len(ocr_texts)}页)，智能筛选关键区域：前10页+后5页")
        selected_texts = ocr_texts[:10] + ocr_texts[-5:]
        logger.info(f"筛选后分析{len(selected_texts)}页")
        ocr_texts = selected_texts

    # 准备每页的内容摘要（前800字符，兼顾context大小和信息完整性）
    pages_summary = []
    max_chars_per_page = 800

    for item in ocr_texts:
        page_num = item.get("page", 0)
        text = item.get("text", "")
        # 每页最多800字符
        preview = text[:max_chars_per_page] if text else ""
        pages_summary.append(f"【第{page_num}页】（共{len(text)}字符）\n{preview}\n{'...(后续内容省略)' if len(text) > max_chars_per_page else ''}")

    pages_text = "\n\n---分页线---\n\n".join(pages_summary)

    # 检查总长度，如果太大需要警告
    total_chars = sum(len(item.get("text", "")) for item in ocr_texts)
    logger.info(f"准备分析{len(ocr_texts)}页内容，总字符数: {total_chars}，发送摘要字符数: {len(pages_text)}")

    # 构建LLM提示词
    prompt = f"""你是合同文档分析专家。现在有一份{total_pages}页的合同，需要你识别出3-5个关键页面用于存档。

## 📄 合同内容（按页展示）
{pages_text}

## 🎯 识别任务

请从上述{total_pages}页中识别以下关键页面：

### 1️⃣ 首页（必选，1页）
- **识别标志**：合同标题、合同编号、甲乙方全称、签订日期
- **位置**：通常是第1页
- **示例**：第1页包含"XX采购合同"、"合同编号：XXX"、"甲方：XXX"、"乙方：XXX"

### 2️⃣ 金额/服务范围页（建议1-2页）
- **识别标志**：
  * 合同总价、金额、价款（如"合同总价：999,900元"）
  * 服务范围、采购清单、货物明细
  * 付款方式、付款比例（如"预付30%"）
  * 交付时间、验收标准
- **位置**：通常在前3-5页
- **注意**：优先选择包含金额的页面

### 3️⃣ 签字盖章页（必选，1页）
- **识别标志**：
  * 包含"甲方（盖章）"、"乙方（盖章）"
  * 有签署日期、签字栏位
  * 可能有"法定代表人"、"委托代理人"字样
- **位置**：通常是最后1-2页
- **注意**：不要选择正文内容页

## 📋 输出格式

严格按以下JSON格式返回（不要用```包裹）：

{{
    "key_pages": [
        {{"page_num": 1, "page_type": "first_page", "reason": "包含合同标题、合同编号21000520220402082100186、甲方南方电网、乙方琪信通达", "title_suffix": "首页"}},
        {{"page_num": 3, "page_type": "content_page", "reason": "包含合同总价999,900元、付款方式一次性付款", "title_suffix": "合同金额"}},
        {{"page_num": 10, "page_type": "signature_page", "reason": "包含甲方盖章、乙方盖章、签署日期2022年", "title_suffix": "签字页"}}
    ],
    "analysis_summary": "识别到首页(第1页)、金额页(第3页)、签字页(第10页)，共3个关键页面"
}}

## ⚠️ 重要提示

1. **page_num必须精确**：从上面【第X页】中提取准确的页码
2. **首页和签字页必选**：即使内容不完整也要选择最接近的页面
3. **reason要具体**：说明该页包含什么关键信息（如具体金额、公司名称）
4. **title_suffix简洁**：用"首页"、"合同金额"、"服务范围"、"签字页"等
5. **总共选择3-5页**：首页(1) + 内容页(1-3) + 签字页(1)
6. **只返回JSON**：不要添加任何解释文字
"""

    try:
        llm = get_llm_provider()
        response = llm.chat([{"role": "user", "content": prompt}])

        # 清理响应（移除可能的markdown代码块）
        response_clean = response.strip()
        if response_clean.startswith("```json"):
            response_clean = response_clean[7:]
        if response_clean.startswith("```"):
            response_clean = response_clean[3:]
        if response_clean.endswith("```"):
            response_clean = response_clean[:-3]
        response_clean = response_clean.strip()

        import json
        result = json.loads(response_clean)

        # 转换page_num从1-based到0-based（内部使用）
        key_pages = result.get("key_pages", [])
        for page in key_pages:
            if "page_num" in page:
                page["page_num"] = page["page_num"] - 1  # 转换为0-based

        logger.info(f"✅ 识别到 {len(key_pages)} 个关键页面: {result.get('analysis_summary', '')}")

        return result

    except Exception as e:
        logger.error(f"❌ LLM识别关键页面失败: {e}")
        # 降级方案：选择首页和最后一页
        return {
            "key_pages": [
                {
                    "page_num": 0,
                    "page_type": "first_page",
                    "reason": "默认选择首页",
                    "title_suffix": "首页"
                },
                {
                    "page_num": total_pages - 1,
                    "page_type": "signature_page",
                    "reason": "默认选择最后一页",
                    "title_suffix": "签字页"
                }
            ],
            "analysis_summary": "LLM分析失败，使用默认策略（首页+最后一页）"
        }
