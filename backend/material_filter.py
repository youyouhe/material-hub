"""
材料OCR预筛选器 - 使用LLM智能判断哪些材料需要OCR
"""

import os
import json
import logging
from typing import List, Dict
from llm_provider import get_llm_provider

logger = logging.getLogger("materialhub.material_filter")

# 是否启用LLM智能筛选
ENABLE_LLM_FILTER = os.getenv("ENABLE_LLM_FILTER", "true").lower() == "true"


FILTER_PROMPT = """你是一个文档管理专家，需要判断哪些材料图片需要进行OCR文字识别。

**OCR的目的：**
1. 提取公司信息（名称、法人、信用代码、地址）
2. 提取资质证书的有效期（用于到期提醒）
3. 注意：个人信息（身份证、学历等）已在Word表格中提供，不需要OCR

**需要OCR的材料类型：**
- ✅ 营业执照、组织机构代码证 → 提取公司信息
- ✅ 法定代表人证明、授权书 → 提取公司/法人信息
- ✅ ISO认证证书（ISO9001、ISO14001等）→ 提取有效期
- ✅ 资质证书、许可证、安全生产许可证 → 提取有效期
- ✅ 行业认证、专业资质 → 提取有效期

**不需要OCR的材料（应跳过）：**
- ❌ 身份证、护照、驾驶证 → 个人信息在Word表格中
- ❌ 学历证书、学位证书、毕业证 → 个人信息在Word表格中
- ❌ 职业资格证书（个人的）→ 个人信息在Word表格中
- ❌ 封面、封底、目录页 → 无关内容
- ❌ 纯图表、示意图、流程图、架构图 → 无文字信息
- ❌ Logo、装饰图、分隔线 → 装饰元素
- ❌ 空白页、页眉、页脚 → 无内容
- ❌ 照片、宣传图 → 非证明文件
- ❌ 合同、协议 → 通常不需要结构化提取

**判断原则：**
- 如果标题包含"身份证"、"学历"、"毕业证"、"个人"等关键词 → 跳过
- 如果标题包含"营业执照"、"ISO"、"资质"、"许可证" → 需要OCR
- 如果标题是装饰性内容（封面、目录、Logo等）→ 跳过
- 不确定时，倾向于跳过（减少无用OCR）

现在给你一批材料标题，请判断每个材料是否需要OCR。

**输入格式：**
```json
[
  {"id": 1, "title": "营业执照"},
  {"id": 2, "title": "封面"},
  ...
]
```

**输出格式（JSON）：**
```json
{
  "need_ocr": [1, 3, 5],
  "skip_ocr": [2, 4, 6]
}
```

**严格要求：**
1. 只返回JSON，不要其他文字
2. need_ocr数组包含需要OCR的材料ID
3. skip_ocr数组包含应跳过的材料ID
4. JSON必须格式正确，不要包含注释或额外字段
5. 确保JSON中的所有字符串都正确转义

现在请判断以下材料：
"""


def filter_materials_for_ocr(materials: List[Dict[str, any]]) -> Dict[str, List[int]]:
    """
    使用LLM批量判断哪些材料需要OCR

    Args:
        materials: [{"id": 1, "title": "营业执照"}, ...]

    Returns:
        {
            "need_ocr": [1, 3, 5],  # 需要OCR的材料ID列表
            "skip_ocr": [2, 4, 6],   # 跳过OCR的材料ID列表
        }
    """
    if not materials:
        return {"need_ocr": [], "skip_ocr": []}

    # 检查是否启用LLM筛选
    if not ENABLE_LLM_FILTER:
        logger.info("⚙️ LLM筛选已禁用，使用关键词过滤")
        need_ocr = []
        skip_ocr = []
        for mat in materials:
            if simple_keyword_filter(mat["title"]):
                need_ocr.append(mat["id"])
            else:
                skip_ocr.append(mat["id"])
        return {"need_ocr": need_ocr, "skip_ocr": skip_ocr}

    try:
        llm = get_llm_provider()

        # 构造输入
        materials_json = json.dumps(materials, ensure_ascii=False, indent=2)
        prompt = FILTER_PROMPT + "\n```json\n" + materials_json + "\n```"

        logger.info(f"🤖 LLM预筛选: {len(materials)} 个材料")

        # 调用LLM（使用messages格式）
        # 增加max_tokens以支持大量材料（每个ID约占10个token，185个材料需要~2000+ tokens）
        messages = [{"role": "user", "content": prompt}]
        response = llm.chat(messages, max_tokens=4000)

        # 解析JSON响应
        # 提取JSON部分（可能包含markdown代码块）
        response_text = response.strip()

        # 尝试多种提取方式
        if "```json" in response_text:
            # 提取```json ... ```之间的内容
            parts = response_text.split("```json", 1)
            if len(parts) > 1:
                response_text = parts[1].split("```", 1)[0]
        elif "```" in response_text:
            # 提取``` ... ```之间的内容
            parts = response_text.split("```", 1)
            if len(parts) > 1:
                response_text = parts[1].split("```", 1)[0]

        # 尝试查找第一个{和最后一个}来提取JSON对象
        first_brace = response_text.find("{")
        last_brace = response_text.rfind("}")

        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            response_text = response_text[first_brace:last_brace + 1]

        response_text = response_text.strip()

        # 尝试解析JSON
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError as json_err:
            logger.error(f"❌ JSON解析失败: {json_err}")
            logger.error(f"原始响应（前500字符）: {response[:500]}")
            logger.error(f"提取的JSON（前500字符）: {response_text[:500]}")

            # 保存完整响应到临时文件以便调试
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
                f.write(response)
                logger.error(f"完整响应已保存到: {f.name}")

            raise json_err

        need_ocr = result.get("need_ocr", [])
        skip_ocr = result.get("skip_ocr", [])

        logger.info(f"✅ LLM判断完成: 需要OCR {len(need_ocr)}个, 跳过 {len(skip_ocr)}个")

        # 输出部分推理过程（如果有）
        if "reasoning" in result and logger.isEnabledFor(logging.DEBUG):
            for mat_id, reason in list(result["reasoning"].items())[:5]:  # 只显示前5个
                logger.debug(f"  - ID {mat_id}: {reason}")

        return {
            "need_ocr": need_ocr,
            "skip_ocr": skip_ocr,
        }

    except Exception as e:
        logger.error(f"❌ LLM预筛选失败: {e}")
        logger.warning("⚠️ 回退到保守策略：所有材料都尝试OCR")

        # 失败时回退：所有材料都尝试OCR（保守策略）
        all_ids = [m["id"] for m in materials]
        return {
            "need_ocr": all_ids,
            "skip_ocr": [],
        }


def simple_keyword_filter(title: str) -> bool:
    """
    简单关键词过滤（备用方案）

    目标：
    1. 提取公司信息（营业执照、法人证明）
    2. 提取资质有效期（ISO认证、资质证书）
    3. 跳过个人证件（身份证、学历等，Word表格已有）

    Returns:
        True: 需要OCR
        False: 跳过OCR
    """
    title_lower = title.lower()

    # 优先跳过：个人证件（Word表格已有信息）
    personal_skip_keywords = [
        "身份证", "id card", "idcard",
        "学历", "学位", "毕业证", "diploma", "degree",
        "护照", "passport",
        "驾驶证", "driver",
        "职业资格证", "技能证书",  # 个人的
    ]
    for keyword in personal_skip_keywords:
        if keyword.lower() in title_lower:
            return False

    # 明确跳过：装饰性内容
    skip_keywords = [
        "封面", "封底", "目录", "contents",
        "图表", "chart", "graph",
        "示意图", "流程图", "架构图",
        "logo", "标志", "装饰",
        "空白", "blank",
        "页眉", "页脚", "header", "footer",
        "分隔", "separator",
        "照片", "photo",
        "宣传", "广告",
    ]
    for keyword in skip_keywords:
        if keyword.lower() in title_lower:
            return False

    # 需要OCR：公司信息
    company_keywords = [
        "营业执照", "执照", "license",
        "组织机构", "organization",
        "法定代表人", "法人", "legal person",
        "授权书", "委托书", "authorization",
    ]
    for keyword in company_keywords:
        if keyword.lower() in title_lower:
            return True

    # 需要OCR：资质有效期
    qualification_keywords = [
        "iso", "认证", "certification",
        "资质", "qualification",
        "许可证", "permit", "license",
        "安全生产",
        "质量管理", "环境管理",
    ]
    for keyword in qualification_keywords:
        if keyword.lower() in title_lower:
            return True

    # 默认：不确定时跳过（减少无用OCR）
    return False
