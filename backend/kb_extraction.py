"""
Knowledge Base Extraction Engine.

LLM-powered event and entity extraction from document chunks.
Ports SAG's extraction prompts and logic (src/ai/llm-client.ts,
src/ingestion/extract/extractor.ts) to Python, using MaterialHub's
existing llm_provider.py.
"""

import json
import logging
from typing import List, Dict, Optional

from llm_provider import get_llm_provider

logger = logging.getLogger("materialhub.kb_extraction")

# Entity types matching SAG's benchmarkEntityTypes, adapted for Chinese documents
ENTITY_TYPES = [
    "person",        # 人员
    "organization",  # 组织/公司/机构
    "location",      # 地点
    "time",          # 时间/日期
    "product",       # 产品/系统/软件
    "metric",        # 指标/金额/数量
    "subject",       # 主题/概念/技术
    "certificate",   # 证书/资质
    "contract",      # 合同/协议
]

ENTITY_EXTRACTION_SYSTEM = """你是一个专业的文档实体抽取器。从文本中识别所有重要的命名实体。

## 实体类型
- person: 人物、法定代表人、负责人、联系人
- organization: 公司、机构、政府部门、学校
- location: 地址、地点、城市
- time: 日期、年份、有效期
- product: 产品名称、系统名称、软件名称、平台
- metric: 金额、注册资本、数量、百分比
- subject: 技术术语、专业概念、业务领域
- certificate: 证书名称、资质名称、许可证
- contract: 合同名称、协议名称

## 输出格式
严格返回 JSON: {"entities": [{"name": "...", "type": "...", "description": "在文中的角色说明"}]}

## 规则
- 每个实体的 name 取其全称
- description 说明该实体在当前文本中的具体角色
- 不要提取泛泛的通用词（如"系统"、"服务"）
- 如果实体类型不明确，使用 subject"""

EVENT_EXTRACTION_SYSTEM = """你是一个专业的文档事件抽取器。从文本中提取一个融合事件。

## 原则
- 必须融合为一个完整事件，不要拆分
- 覆盖所有关键信息：主体、动作、对象、时间、地点、数据
- 事件内容应是有机的叙述，不是列表
- 不编造事实，不遗漏核心事实

## 输出格式
严格返回 JSON:
{
  "event": {
    "title": "简洁的事件标题",
    "summary": "一句话摘要",
    "content": "完整的事件描述（融合文本中所有相关信息）",
    "event_type": "signing|expiration|certification|establishment|payment|tax_filing|registration|other",
    "event_date": "YYYY-MM-DD 或 null",
    "keywords": ["关键词1", "关键词2"],
    "entities": [{"name": "...", "type": "...", "description": "..."}]
  }
}

## 事件类型选择
- signing: 签署/签订合同、协议
- expiration: 到期/过期
- certification: 认证/获得证书/通过审核
- establishment: 成立/注册/设立
- payment: 付款/缴税/缴纳
- tax_filing: 完税/报税
- registration: 登记/注册/备案
- other: 其他"""


def extract_entities(text: str) -> List[Dict]:
    """Extract named entities from text using LLM.

    Args:
        text: chunk or document text (max ~3000 chars sent to LLM)

    Returns:
        List of entity dicts: {name, type, description}
    """
    text = text[:3000]  # Limit context window

    try:
        provider = get_llm_provider()
        messages = [
            {"role": "system", "content": ENTITY_EXTRACTION_SYSTEM},
            {"role": "user", "content": f"请从以下文本中抽取实体:\n\n{text}"},
        ]
        response = provider.chat(messages, temperature=0.1, max_tokens=1000)

        # Parse JSON from response
        result = _parse_json_response(response)
        entities = result.get("entities", [])
        return [
            {"name": e["name"].strip(), "type": e.get("type", "subject").strip(),
             "description": e.get("description", "").strip()}
            for e in entities
            if isinstance(e, dict) and e.get("name", "").strip()
        ]
    except Exception as e:
        logger.warning("Entity extraction failed, using local fallback: %s", e)
        return _local_extract_entities(text)


def extract_event(text: str, document_title: str = "") -> Optional[Dict]:
    """Extract a fused event from text using LLM.

    Following SAG's pattern: one event per chunk, fused from all information.

    Args:
        text: chunk or document text
        document_title: parent document title for context

    Returns:
        Event dict: {title, summary, content, event_type, event_date, keywords, entities}
        or None if extraction fails
    """
    text = text[:3000]

    try:
        provider = get_llm_provider()
        user_msg = f"文档标题: {document_title}\n\n文本内容:\n{text}" if document_title else text
        messages = [
            {"role": "system", "content": EVENT_EXTRACTION_SYSTEM},
            {"role": "user", "content": f"请从以下文本中提取事件:\n\n{user_msg}"},
        ]
        response = provider.chat(messages, temperature=0.1, max_tokens=1500)

        result = _parse_json_response(response)
        event = result.get("event", {})
        if not event or not event.get("title"):
            return None

        return {
            "title": event["title"].strip(),
            "summary": event.get("summary", "").strip(),
            "content": event.get("content", "").strip(),
            "event_type": event.get("event_type", "other").strip(),
            "event_date": event.get("event_date"),
            "keywords": event.get("keywords", [])[:10],
            "entities": [
                {"name": e["name"].strip(), "type": e.get("type", "subject").strip(),
                 "description": e.get("description", "").strip()}
                for e in event.get("entities", [])
                if isinstance(e, dict) and e.get("name", "").strip()
            ],
        }
    except Exception as e:
        logger.warning("Event extraction failed for '%s': %s", document_title, e)
        return _local_extract_event(text, document_title)


def extract_events_from_document(doc_id: int) -> List[Dict]:
    """Extract events from all chunks of a document.

    Aggregates chunk-level events and deduplicates by title similarity.
    """
    try:
        # Get chunks from KB
        from kb_database import get_session_local
        from kb_models import KbChunk
        from dms_models import get_dms_session, DmsDocument

        # Get document title
        doc_title = ""
        with get_dms_session() as db:
            doc = db.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
            if doc:
                doc_title = doc.title

        SessionLocal = get_session_local()
        session = SessionLocal()
        try:
            chunks = session.query(KbChunk).filter(
                KbChunk.doc_id == doc_id
            ).order_by(KbChunk.chunk_index).all()

            all_events = []
            for chunk in chunks[:20]:  # Max 20 chunks to control LLM cost
                text = f"{chunk.heading_path or ''}\n{chunk.content}" if chunk.heading_path else chunk.content
                event = extract_event(text[:2000], doc_title)
                if event:
                    event["_chunk_index"] = chunk.chunk_index
                    event["_chunk_id"] = chunk.id
                    all_events.append(event)

            # Deduplicate by title similarity
            unique_events = _deduplicate_events(all_events)
            return unique_events
        finally:
            session.close()
    except Exception as e:
        logger.error("Document-level event extraction failed for doc %d: %s", doc_id, e)
        return []


def _deduplicate_events(events: List[Dict]) -> List[Dict]:
    """Deduplicate events by title and date similarity."""
    if len(events) <= 1:
        return events

    unique = []
    seen_titles = set()

    for event in sorted(events, key=lambda e: len(e.get("content", "")), reverse=True):
        title = event.get("title", "").lower()
        # Check if title is substantially similar to any already-kept event
        is_dup = False
        for seen in seen_titles:
            if title in seen or seen in title:
                is_dup = True
                break
        if not is_dup:
            seen_titles.add(title)
            event.pop("_chunk_index", None)
            event.pop("_chunk_id", None)
            unique.append(event)

    return unique


def _parse_json_response(response: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = response.strip()
    # Remove markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the response
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {}


def _local_extract_entities(text: str) -> List[Dict]:
    """Deterministic entity extraction fallback using regex patterns.

    Ported from SAG's localNamedEntities() in llm-client.ts.
    """
    import re
    entities = []

    # Chinese company/org pattern
    patterns = [
        (r'[一-龥]{2,24}(?:公司|集团|大学|机构|部门|中心|事务所|研究院)', "organization"),
        (r'[一-龥]{2,6}(?:证书|许可证|执照|登记证|认证|体系)', "certificate"),
        (r'[一-龥]{2,24}(?:系统|平台|软件|产品|数据库)', "product"),
        (r'(?:合同|协议|项目)[一-龥A-Za-z0-9_-]{2,30}', "contract"),
        (r'\d{4}[-年]\d{1,2}[-月]\d{1,2}[日号]?', "time"),
        (r'(?:[一-龥]{2,4}[一-龥]{2,8})', "person"),
        # Amount/money
        (r'\d+(?:\.\d+)?\s*万?\s*元', "metric"),
        (r'\d+(?:\.\d+)?%', "metric"),
    ]

    seen = set()
    for pattern, etype in patterns:
        for match in re.finditer(pattern, text):
            name = match.group().strip()
            if name not in seen and len(name) > 1:
                seen.add(name)
                entities.append({"name": name, "type": etype, "description": ""})

    return entities[:12]


def _local_extract_event(text: str, doc_title: str = "") -> Optional[Dict]:
    """Deterministic event extraction fallback."""
    import re

    # Extract first meaningful sentence as title
    sentences = re.split(r'[。！？\n]', text[:500])
    title = ""
    for s in sentences:
        s = s.strip()
        if len(s) > 10:
            title = s[:120]
            break

    if not title:
        title = doc_title or "文档事件"

    # Extract date
    date_match = re.search(r'(\d{4})[-年](\d{1,2})[-月](\d{1,2})[日号]?', text)
    event_date = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}" if date_match else None

    # Determine event type
    if re.search(r'证书|认证|许可|登记', text):
        event_type = "certification"
    elif re.search(r'合同|协议|签署|签订', text):
        event_type = "signing"
    elif re.search(r'完税|缴税|纳税|税务', text):
        event_type = "tax_filing"
    elif re.search(r'成立|注册|设立', text):
        event_type = "establishment"
    else:
        event_type = "other"

    entities = _local_extract_entities(text)

    return {
        "title": title,
        "summary": title,
        "content": text[:500].strip(),
        "event_type": event_type,
        "event_date": event_date,
        "keywords": [w for w in re.findall(r'[一-龥]{2,6}', text[:200]) if len(w) >= 2][:8],
        "entities": entities,
    }
