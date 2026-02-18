"""
智能OCR解析Agent
使用LLM解析OCR文本，提取结构化数据
"""

import json
import logging
from typing import Dict, Any, Optional
from llm_provider import get_llm_provider

logger = logging.getLogger("materialhub.ocr_agent")


EXTRACTION_PROMPT = """你是一个专业的文档信息提取助手。请仔细分析以下OCR识别的文本内容，完成信息提取任务。

## 任务要求
1. **识别材料类型**：判断这是什么类型的文档
   - license: 营业执照
   - legal_person_cert: 法定代表人资格证明书
   - id_card: 身份证
   - education: 学历证书、毕业证、学位证
   - iso_cert: ISO认证证书（ISO9001、ISO14001、ISO27001等）
   - certificate: 其他各类证书
   - contract: 合同
   - authorization: 授权书、委托书
   - invoice: 发票
   - other: 其他类型

2. **提取结构化信息**：根据材料类型提取关键字段
   - 公司相关：公司名称、法定代表人、统一社会信用代码、地址、注册资本等
   - 人员相关：姓名、身份证号、性别、出生日期、学历、专业等
   - 证书相关：证书名称、持有人/单位、发证机构、证书编号、发证日期、有效期等

## 材料信息
- **文档标题**：{title}

## OCR识别文本
```
{ocr_text}
```

## 输出格式
请严格按照以下JSON格式输出，不要添加任何其他文字说明：

```json
{{
  "material_type": "类型代码",
  "confidence": 0.95,
  "extracted_data": {{
    // 根据材料类型提取的结构化字段
    // 营业执照示例：
    // "company_name": "公司名称",
    // "legal_person": "法定代表人",
    // "credit_code": "统一社会信用代码",
    // "address": "注册地址",
    // "registered_capital": "注册资本"

    // 身份证示例：
    // "name": "姓名",
    // "gender": "性别",
    // "nation": "民族",
    // "birth_date": "1990-01-01",
    // "id_number": "110101199001011234",
    // "address": "住址",
    // "issue_authority": "签发机关",
    // "valid_period": "2020-01-01至2030-01-01"

    // 证书示例：
    // "cert_name": "证书名称",
    // "holder": "持有人或单位",
    // "cert_number": "证书编号",
    // "issue_date": "2023-01-01",
    // "expiry_date": "2026-01-01",
    // "issue_authority": "发证机关",
    // "scope": "认证范围"
  }},
  "summary": "简短总结这份材料的主要内容（1-2句话）"
}}
```

注意事项：
1. 所有字段尽量提取，如果OCR文本中没有该字段信息，则不要包含该字段
2. 日期格式统一为 YYYY-MM-DD
3. 身份证号等敏感信息完整提取，系统会自动处理脱敏
4. confidence取值范围0.0-1.0，表示识别的置信度
5. 如果OCR文本质量差或无法识别，confidence应该较低（<0.5）
"""


def intelligent_extract(
    ocr_text: str,
    material_title: str = ""
) -> Dict[str, Any]:
    """
    使用LLM智能提取OCR文本中的结构化信息

    Args:
        ocr_text: OCR识别的文本
        material_title: 材料标题（如"营业执照"、"ISO9001质量管理体系"等）

    Returns:
        {
            "material_type": "类型",
            "confidence": 0.95,
            "extracted_data": {...},
            "summary": "总结"
        }
    """
    try:
        # 获取LLM provider
        llm = get_llm_provider()

        # 构建prompt
        prompt = EXTRACTION_PROMPT.format(
            title=material_title or "未知",
            ocr_text=ocr_text[:4000]  # 限制长度避免超过token限制
        )

        # 调用LLM
        messages = [
            {
                "role": "user",
                "content": prompt
            }
        ]

        logger.info(f"开始智能解析: {material_title}")
        response = llm.chat(messages, temperature=0.3, max_tokens=2000)

        # 解析JSON响应
        # 尝试提取JSON块（如果LLM返回了markdown代码块）
        json_text = response.strip()
        if "```json" in json_text:
            json_text = json_text.split("```json")[1].split("```")[0].strip()
        elif "```" in json_text:
            json_text = json_text.split("```")[1].split("```")[0].strip()

        result = json.loads(json_text)

        logger.info(
            f"✅ 智能解析成功: type={result.get('material_type')}, "
            f"confidence={result.get('confidence', 0):.2f}"
        )
        logger.info(f"提取字段: {list(result.get('extracted_data', {}).keys())}")

        return result

    except json.JSONDecodeError as e:
        logger.error(f"❌ LLM响应JSON解析失败: {e}")
        logger.error(f"响应内容: {response[:500]}...")
        return {
            "material_type": "unknown",
            "confidence": 0.0,
            "extracted_data": {},
            "error": f"JSON parsing error: {str(e)}"
        }

    except Exception as e:
        logger.error(f"❌ 智能解析失败: {e}", exc_info=True)
        return {
            "material_type": "unknown",
            "confidence": 0.0,
            "extracted_data": {},
            "error": str(e)
        }


def extract_expiry_date(extracted_data: Dict[str, Any]) -> Optional[str]:
    """
    从提取的数据中获取有效期日期

    Args:
        extracted_data: 提取的结构化数据

    Returns:
        有效期日期字符串 (YYYY-MM-DD) 或 None
    """
    # 尝试多个可能的字段名
    date_fields = [
        'expiry_date',
        'valid_until',
        'expire_date',
        'end_date',
        'valid_period'
    ]

    for field in date_fields:
        value = extracted_data.get(field)
        if value:
            # 如果是"2020-01-01至2030-01-01"这种格式，取后面的日期
            if '至' in str(value):
                value = str(value).split('至')[1].strip()
            elif 'to' in str(value).lower():
                value = str(value).lower().split('to')[1].strip()

            # 验证日期格式
            if isinstance(value, str) and len(value) == 10 and value.count('-') == 2:
                return value

    return None


def create_entity_from_extraction(
    material_type: str,
    extracted_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    根据提取结果创建公司或人员实体信息

    Args:
        material_type: 材料类型
        extracted_data: 提取的数据

    Returns:
        {
            "entity_type": "company" | "person" | None,
            "entity_data": {...}
        }
    """
    if material_type in ['license', 'legal_person_cert', 'contract', 'agreement', 'other']:
        # 提取公司信息（营业执照、法人证明、合同等）
        company_data = {}

        # 对于合同类型，优先提取乙方（通常是供应商/服务商）
        # 优先级：supplier_name > service_party > party_b > company_name > name
        name_priority = [
            'supplier_name',  # 供应商名称（最高优先级）
            'service_party',  # 服务方/受托方（乙方的另一种表述）
            'party_b',        # 乙方（次优先级）
            'company_name',   # 公司名称
            'name',           # 通用名称
            'client_party',   # 委托方/客户方（甲方的另一种表述）
            'client_name',    # 客户名称
            'party_a',        # 甲方
        ]

        # 按优先级选择公司名称
        company_name = None
        for key in name_priority:
            if key in extracted_data and extracted_data[key]:
                company_name = extracted_data[key]
                break

        if company_name:
            company_data['name'] = company_name

        # 其他字段映射
        field_mapping = {
            'legal_person': 'legal_person',
            'legal_representative': 'legal_person',
            'credit_code': 'credit_code',
            'unified_social_credit_code': 'credit_code',
            'address': 'address',
            'registered_address': 'address',
            'contact_address': 'address',
        }

        for extracted_key, db_key in field_mapping.items():
            if extracted_key in extracted_data and extracted_data[extracted_key]:
                company_data[db_key] = extracted_data[extracted_key]

        if company_data.get('name'):
            return {
                "entity_type": "company",
                "entity_data": company_data
            }

    elif material_type in ['id_card', 'education']:
        # 提取人员信息
        person_data = {}

        field_mapping = {
            'name': 'name',
            'id_number': 'id_number',
            'id_card_number': 'id_number',
            'education': 'education',
            'degree': 'education',
            'major': 'major',
        }

        for extracted_key, db_key in field_mapping.items():
            if extracted_key in extracted_data and extracted_data[extracted_key]:
                person_data[db_key] = extracted_data[extracted_key]

        if person_data.get('name'):
            return {
                "entity_type": "person",
                "entity_data": person_data
            }

    return {
        "entity_type": None,
        "entity_data": {}
    }
