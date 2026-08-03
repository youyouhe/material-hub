"""
回填 mock 文档的实体↔文档关联（dms_document_entities），并修复人员被误注册为 org 的实体。

背景（SmartBid 修改需求 2026-08-04）：
1. generate-on-demand 生成的 mock 文档只在 meta.entity_names 里记录了主体名称，
   从未建立 DocumentEntity 关联 → search?entity_id= 查不到、entities 列表 document_count=0。
2. 人员类材料（id-card/education-cert/professional-cert）的 entity_name 是人名，
   但 _persist_entity_baseline 曾无条件创建 entity_type="org" 的实体 → 人员被注册为公司。

本脚本：
- 扫描所有 meta.mock=true 且 entity_names 非空的文档，按 document_type_code 判定实体类型
  （人员类→person，其余→org），find-or-create 实体并补建缺失的关联；
- 人员类 mock 文档涉及的同名 org 实体：若已存在同名 person 实体则把关联合并过去后删除
  org 实体，否则直接将其 entity_type 改为 person。

用法：
    python backfill_mock_entity_links.py            # 正式执行
    python backfill_mock_entity_links.py --dry-run  # 只预览，不写库
"""
import json
import logging
import sys

from dms_models import get_dms_session, DmsDocument, Entity, DocumentEntity
from mock_generator import _PERSONNEL_DOC_TYPES, _resolve_primary_entity

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

DRY_RUN = "--dry-run" in sys.argv


def _load_meta(doc) -> dict:
    try:
        return json.loads(doc.meta_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


def backfill_links(session) -> tuple:
    """补建 mock 文档的主实体关联。返回 (linked, skipped, errors)。"""
    docs = session.query(DmsDocument).filter(
        DmsDocument.status.in_(["active", "draft"]),
    ).all()

    linked = skipped = errors = 0
    for doc in docs:
        meta = _load_meta(doc)
        if not meta.get("mock"):
            continue
        entity_names = meta.get("entity_names") or []
        entity_name = entity_names[0] if entity_names else None
        if not entity_name:
            continue
        doc_type_code = meta.get("document_type_code") or ""
        try:
            entity = _resolve_primary_entity(session, doc_type_code, entity_name)
            existing = session.query(DocumentEntity).filter(
                DocumentEntity.document_id == doc.id,
                DocumentEntity.entity_id == entity.id,
            ).first()
            if existing:
                skipped += 1
                continue
            if not DRY_RUN:
                session.add(DocumentEntity(
                    document_id=doc.id,
                    entity_id=entity.id,
                    role="owner",
                ))
            logger.info("🔗 关联 doc %d (%s) → %s 实体 '%s' (id=%d)",
                        doc.id, doc_type_code, entity.entity_type, entity_name, entity.id)
            linked += 1
        except Exception as e:
            logger.error("❌ doc %d 关联失败: %s", doc.id, e)
            errors += 1
    return linked, skipped, errors


def fix_mistyped_persons(session) -> int:
    """把人员类 mock 文档涉及的、被误注册为 org 的实体修正为 person。返回修正数。"""
    person_names = set()
    docs = session.query(DmsDocument).filter(
        DmsDocument.status.in_(["active", "draft"]),
    ).all()
    for doc in docs:
        meta = _load_meta(doc)
        if not meta.get("mock"):
            continue
        if (meta.get("document_type_code") or "") not in _PERSONNEL_DOC_TYPES:
            continue
        entity_names = meta.get("entity_names") or []
        if entity_names:
            person_names.add(entity_names[0])

    fixed = 0
    for name in sorted(person_names):
        org = session.query(Entity).filter(
            Entity.entity_type == "org", Entity.name == name,
        ).first()
        if not org:
            continue
        person = session.query(Entity).filter(
            Entity.entity_type == "person", Entity.name == name,
        ).first()
        if person:
            # 合并：org 的文档关联改指 person（避免唯一约束冲突），然后删除 org
            moved = 0
            for link in list(org.document_links):
                dup = session.query(DocumentEntity).filter(
                    DocumentEntity.document_id == link.document_id,
                    DocumentEntity.entity_id == person.id,
                    DocumentEntity.role == link.role,
                ).first()
                if not DRY_RUN:
                    if dup:
                        session.delete(link)
                    else:
                        link.entity_id = person.id
                moved += 1
            logger.info("🔀 合并 org 实体 '%s' (id=%d) → person (id=%d)，迁移 %d 条关联",
                        name, org.id, person.id, moved)
            if not DRY_RUN:
                session.delete(org)
        else:
            logger.info("✏️ 实体 '%s' (id=%d) entity_type: org → person", name, org.id)
            if not DRY_RUN:
                org.entity_type = "person"
        fixed += 1
    return fixed


def main():
    logger.info("=" * 60)
    logger.info("mock 文档实体关联回填 %s", "(DRY-RUN)" if DRY_RUN else "")
    logger.info("=" * 60)

    with get_dms_session() as session:
        fixed = fix_mistyped_persons(session)
        linked, skipped, errors = backfill_links(session)

        logger.info("")
        logger.info("📊 误注册人员修正: %d | 新建关联: %d | 已存在跳过: %d | 失败: %d",
                    fixed, linked, skipped, errors)

        if DRY_RUN:
            session.rollback()
            logger.info("🔍 DRY-RUN：未写入任何修改")
            return

        try:
            session.commit()
            logger.info("🎉 回填完成，已提交")
        except Exception as e:
            session.rollback()
            logger.error("❌ 数据库提交失败: %s", e)
            sys.exit(1)

    # KB 同步（best-effort，与 _link_entities 行为一致）
    try:
        from kb_entity_sync import sync_entities_to_kb
        sync_entities_to_kb()
        logger.info("✅ KB 实体同步完成")
    except Exception as e:
        logger.warning("⚠️ KB 实体同步失败（非致命）: %s", e)


if __name__ == "__main__":
    main()
