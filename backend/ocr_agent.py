"""
智能OCR解析Agent
使用LLM解析OCR文本，提取结构化数据
"""

import json
import logging
from typing import Dict, Any, Optional, List
from llm_provider import get_llm_provider

logger = logging.getLogger("materialhub.ocr_agent")


EXTRACTION_PROMPT = """你是一个专业的文档信息提取助手。请仔细分析以下OCR识别的文本内容，完成信息提取任务。

## 任务要求
1. **识别材料类型**：用简短的中文描述这是什么类型的文档。
   不要受限于预设分类，请根据文档实际内容自由判断，例如：
   "营业执照"、"身份证"、"合同"、"产品说明书"、"公司简介"、
   "ISO认证证书"、"资质证书"、"荣誉证书"、"验收报告"、"发票"、
   "投标文件"、"授权书"、"技术方案"、"学历证书"、"职称证书"等。
   如果文档不属于常见类别，直接用最准确的中文名称描述即可。

2. **提取结构化信息**：根据文档内容，尽可能提取所有有价值的结构化字段，包括但不限于：
   - 名称类：公司名称、人员姓名、文档名称、产品名称、项目名称等
   - 编号类：统一社会信用代码、证书编号、合同编号、身份证号、发票号码等
   - 日期类：发证日期、有效期、签订日期、开票日期等
   - 金额类：合同金额、注册资本、发票金额等
   - 机构类：发证机关、认证机构、甲方、乙方等
   - 其他：地址、经营范围、认证范围、资质等级、学历、专业、职称等

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
  "material_type": "文档类型的中文描述",
  "confidence": 0.95,
  "extracted_data": {{
    // 根据文档内容提取所有有价值的字段
    // 字段名使用英文小写下划线格式
    // 常用字段名参考：
    //   company_name, legal_person, credit_code, address, registered_capital,
    //   name, id_number, gender, birth_date, education, major,
    //   cert_name, cert_number, issue_date, expiry_date, issue_authority, scope,
    //   contract_name, party_a, party_b, contract_amount, sign_date, project_name,
    //   product_name, manufacturer, model, description,
    //   invoice_number, amount, buyer, seller
  }},
  "summary": "简短总结这份材料的主要内容（1-2句话）"
}}
```

注意事项：
1. material_type 必须是准确的中文描述，反映文档的真实类型
2. 所有字段尽量提取，如果OCR文本中没有该字段信息，则不要包含该字段
3. 日期格式统一为 YYYY-MM-DD
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


def create_entities_from_extraction(
    material_type: str,
    extracted_data: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Extract MULTIPLE entities from all eligible fields in extracted_data.

    Unlike create_entity_from_extraction (returns first match only),
    this returns all entity-worthy fields, up to 5 entities.
    """
    # Pattern-based field → entity type inference (LLM field names vary each run)
    # Matches by substring, so "instructor_name" and "trainer_name" both match
    # Order matters: more specific patterns first ("accounting" before "system")
    _TYPE_PATTERNS = [
        (["accounting", "principle", "element", "equation", "concept",
          "framework", "basis", "standard", "rule", "policy"], "concept"),
        (["person", "trainer", "speaker", "instructor", "presenter", "teacher",
          "author", "legal_person", "representative", "officer",
          "character", "protagonist", "antagonist",
          "_name"], "person"),  # any *_name field → person
        (["project_name", "project_title"], "project"),
        (["certificate", "cert", "license", "permit"], "certificate"),
        (["system", "platform", "software", "product", "app_name", "app_title"], "product"),
        (["topic", "training", "subject", "course", "curriculum"], "topic"),
        (["location", "site", "address", "place"], "location"),
        (["contract", "agreement", "deal"], "contract"),
    ]

    # Person/company field keys (from create_entity_from_extraction)
    person_fields = {'name', 'id_number', 'id_card_number', 'education', 'degree', 'major'}
    company_name_keys = {'supplier_name', 'service_party', 'party_b', 'company_name',
                         'manufacturer', 'client_party', 'client_name', 'party_a'}
    company_field_mapping = {'legal_person', 'legal_representative', 'credit_code',
                             'unified_social_credit_code', 'address', 'registered_address',
                             'contact_address'}

    entities = []
    for field_key, field_value in extracted_data.items():
        if not field_value or not isinstance(field_value, str) or len(field_value) < 2:
            continue
        if field_key in person_fields or field_key in company_name_keys or field_key in company_field_mapping:
            continue
        # Skip structural/metadata keys
        if any(skip in field_key for skip in
               ["document_", "training_title", "chapters", "chapter", "department", "date", "amount",
                "confidence", "valid_", "establishment", "business_", "issue_",
                "framework_module"]):
            continue

        # Pattern-match field name to entity type
        etype = "topic"  # default
        for keywords, mapped_type in _TYPE_PATTERNS:
            if any(kw in field_key for kw in keywords):
                etype = mapped_type
                break

        entities.append({"entity_type": etype, "entity_data": {"name": field_value}})

    # Also extract from list fields (first 3 items each)
    for field_key, field_value in extracted_data.items():
        if not isinstance(field_value, list) or len(field_value) == 0:
            continue
        if any(skip in field_key for skip in
               ["document_", "training_title", "chapters", "chapter", "department", "date", "amount",
                "confidence", "valid_", "establishment", "business_", "issue_",
                "framework_module"]):
            continue
        etype = "topic"
        for keywords, mapped_type in _TYPE_PATTERNS:
            if any(kw in field_key for kw in keywords):
                etype = mapped_type
                break
        for item in field_value[:3]:
            if isinstance(item, str) and len(item) >= 2:
                entities.append({"entity_type": etype, "entity_data": {"name": item}})
                # No limit — LLM decides what's important

    return entities


def create_entity_from_extraction(
    material_type: str,
    extracted_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    根据提取结果创建公司或人员实体信息。
    不依赖固定类型列表，而是根据 extracted_data 中的字段智能判断。
    """
    # 先尝试提取人员信息（身份证号是强信号）
    person_fields = {
        'name': 'name',
        'id_number': 'id_number',
        'id_card_number': 'id_number',
        'education': 'education',
        'degree': 'education',
        'major': 'major',
    }
    person_data = {}
    for extracted_key, db_key in person_fields.items():
        if extracted_key in extracted_data and extracted_data[extracted_key]:
            person_data[db_key] = extracted_data[extracted_key]

    # 如果有身份证号，优先认定为人员
    if person_data.get('id_number') and person_data.get('name'):
        return {"entity_type": "person", "entity_data": person_data}

    # 尝试提取公司信息
    company_name_keys = [
        'supplier_name', 'service_party', 'party_b',
        'company_name', 'manufacturer',
        'client_party', 'client_name', 'party_a',
    ]
    company_name = None
    for key in company_name_keys:
        if key in extracted_data and extracted_data[key]:
            company_name = extracted_data[key]
            break

    company_field_mapping = {
        'legal_person': 'legal_person',
        'legal_representative': 'legal_person',
        'credit_code': 'credit_code',
        'unified_social_credit_code': 'credit_code',
        'address': 'address',
        'registered_address': 'address',
        'contact_address': 'address',
    }
    company_data = {}
    if company_name:
        company_data['name'] = company_name
    for extracted_key, db_key in company_field_mapping.items():
        if extracted_key in extracted_data and extracted_data[extracted_key]:
            company_data[db_key] = extracted_data[extracted_key]

    if company_data.get('name'):
        return {"entity_type": "company", "entity_data": company_data}

    # 如果有人员名字但没有身份证号（如学历证书、职称证书）
    if person_data.get('name'):
        return {"entity_type": "person", "entity_data": person_data}

    # Generic entity extraction: pattern-match field names to entity types
    # (LLM field names vary each run, so we use substring matching)
    # Order matters: more specific patterns first ("accounting" before "system")
    _TYPE_PATTERNS = [
        (["accounting", "principle", "element", "equation", "concept",
          "framework", "basis", "standard", "rule", "policy"], "concept"),
        (["person", "trainer", "speaker", "instructor", "presenter", "teacher",
          "author", "legal_person", "representative", "officer",
          "character", "protagonist", "antagonist",
          "_name"], "person"),  # any *_name field → person
        (["project_name", "project_title"], "project"),
        (["certificate", "cert", "license", "permit"], "certificate"),
        (["system", "platform", "software", "product", "app_name", "app_title"], "product"),
        (["topic", "training", "subject", "course", "curriculum"], "topic"),
        (["location", "site", "address", "place"], "location"),
        (["contract", "agreement", "deal"], "contract"),
    ]

    for field_key, field_value in extracted_data.items():
        if not field_value or not isinstance(field_value, str) or len(field_value) < 2:
            continue
        if field_key in person_fields or field_key in company_name_keys or field_key in company_field_mapping:
            continue
        if any(skip in field_key for skip in
               ["document_", "training_title", "chapters", "chapter", "department", "date", "amount",
                "confidence", "valid_", "establishment", "business_", "issue_",
                "framework_module"]):
            continue
        etype = "topic"
        for keywords, mapped_type in _TYPE_PATTERNS:
            if any(kw in field_key for kw in keywords):
                etype = mapped_type
                break
        return {"entity_type": etype, "entity_data": {"name": field_value}}

    return {"entity_type": None, "entity_data": {}}
