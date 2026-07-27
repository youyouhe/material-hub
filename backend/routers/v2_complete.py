"""Aggregated "complete" profile endpoints (company / person).

One-call聚合视图，供 BidSmart 的 bid-material-search skill（extract.py）使用：
  GET /api/v2/companies/{entity_id}/complete
  GET /api/v2/persons/{entity_id}/complete

为什么需要这个端点：完整信息分散在两套表里，任何一套单独都不全——
  - dms_entities.attributes 目前只有 credit_code（org）/ id_number（person）
  - 旧 companies/persons 表有 legal_person/address/education/position
  - dms_entity_relations 未填充，雇佣关系来自 persons.company_id
  - 材料在旧 materials 表（company_id/person_id 外键）
"""

import json
import logging
import re
from typing import Optional, Any

from fastapi import APIRouter, HTTPException

from database import get_session, Company, Person, Material
from dms_models import get_dms_session, Entity

logger = logging.getLogger("materialhub.routers.v2_complete")

router = APIRouter(prefix="/api/v2", tags=["complete-profiles"])


def _normalize_name(name: str) -> str:
    """名称归一化：全角括号→半角、去空白，用于跨表匹配实体名与公司名。"""
    if not name:
        return ""
    return re.sub(r"\s+", "", name).replace("（", "(").replace("）", ")")


def _find_legacy_company(session, entity_name: str):
    """按归一化名称在旧 companies 表中找匹配行（总公司/分公司只命中存在的记录）。"""
    target = _normalize_name(entity_name)
    for c in session.query(Company).all():
        if _normalize_name(c.name) == target:
            return c
    return None


def _material_to_complete_shape(m: Material) -> dict:
    """把旧 Material 行映射为 extract.py 期望的结构：
    doc_type.code ← material_type；metadata.extracted_data ← extracted_json。"""
    extracted: Any = None
    if m.extracted_json:
        try:
            extracted = json.loads(m.extracted_json)
        except (json.JSONDecodeError, TypeError):
            pass
    return {
        "id": m.id,
        "title": m.title,
        "material_type": m.material_type,
        "doc_type": {"code": m.material_type or ""},
        "metadata": {"extracted_data": extracted or {}},
        "expiry_date": m.expiry_date.isoformat() if m.expiry_date else None,
        "image_url": f"/api/v2/files/{m.document_id}" if m.document_id else None,
        "source_filename": m.document.filename if m.document else None,
    }


def _entity_attrs(entity: Optional[Entity]) -> dict:
    if not entity or not entity.attributes:
        return {}
    try:
        return json.loads(entity.attributes)
    except (json.JSONDecodeError, TypeError):
        return {}


@router.get("/companies/{entity_id}/complete")
async def get_company_complete(entity_id: int):
    """公司完整画像：实体 + 工商信息（法人/地址/信用代码）+ 员工 + 材料 + 统计。"""
    with get_dms_session() as dms:
        entity = dms.query(Entity).filter(Entity.id == entity_id).first()
        if not entity or entity.entity_type != "org":
            raise HTTPException(status_code=404, detail=f"公司实体不存在: {entity_id}")
        entity_attrs = _entity_attrs(entity)
        entity_name = entity.name

        # 人员实体（按名字补充 id_number 等属性）
        person_entities = {
            _normalize_name(e.name): _entity_attrs(e)
            for e in dms.query(Entity).filter(Entity.entity_type == "person").all()
        }

    with get_session() as session:
        company = _find_legacy_company(session, entity_name)

        # license：旧 companies 表为准，实体 attributes 补充
        license_info = {}
        if company:
            license_info = {
                "credit_code": company.credit_code or "",
                "legal_person": company.legal_person or "",
                "address": company.address or "",
            }
        for k in ("credit_code", "legal_person", "address"):
            if not license_info.get(k) and entity_attrs.get(k):
                license_info[k] = entity_attrs[k]

        # 营业执照材料的提取数据补充（有效期等）
        materials = []
        if company:
            materials = (
                session.query(Material)
                .filter(Material.company_id == company.id)
                .order_by(Material.id)
                .all()
            )
            for m in materials:
                if m.material_type == "license" and m.extracted_json:
                    try:
                        blob = json.loads(m.extracted_json)
                        # extracted_json 可能是 {extracted_data: {...}} 包装，取内层
                        inner = blob.get("extracted_data") if isinstance(blob.get("extracted_data"), dict) else blob
                        for k, v in inner.items():
                            license_info.setdefault(k, v)
                    except (json.JSONDecodeError, TypeError):
                        pass
                    break

        # 员工：旧 persons 表（company_id），按名字合并人员实体的 id_number
        employees = []
        if company:
            persons = (
                session.query(Person)
                .filter(Person.company_id == company.id)
                .order_by(Person.id)
                .all()
            )
            for p in persons:
                attrs = person_entities.get(_normalize_name(p.name), {}).copy()
                if p.education:
                    attrs.setdefault("education", p.education)
                if p.position:
                    attrs.setdefault("position", p.position)
                employees.append({"id": p.id, "name": p.name, "attributes": attrs})

        material_list = [_material_to_complete_shape(m) for m in materials]

    cert_count = sum(
        1 for m in material_list if "cert" in (m["doc_type"]["code"] or "")
    )
    contract_count = sum(
        1 for m in material_list if (m["doc_type"]["code"] or "").startswith("contract")
    )

    return {
        "company": {
            "id": entity_id,
            "name": entity_name,
            "entity_type": "org",
            "attributes": {**entity_attrs, **{k: v for k, v in license_info.items() if v}},
        },
        "license": license_info,
        "employees": employees,
        "materials": material_list,
        "aggregated_info": {k: v for k, v in license_info.items() if v},
        "statistics": {
            "total_materials": len(material_list),
            "total_employees": len(employees),
            "total_certificates": cert_count,
            "total_contracts": contract_count,
        },
    }


@router.get("/persons/{entity_id}/complete")
async def get_person_complete(entity_id: int):
    """人员完整画像：实体 + 所属公司 + 证书 + 材料。"""
    with get_dms_session() as dms:
        entity = dms.query(Entity).filter(Entity.id == entity_id).first()
        if not entity or entity.entity_type != "person":
            raise HTTPException(status_code=404, detail=f"人员实体不存在: {entity_id}")
        entity_attrs = _entity_attrs(entity)
        entity_name = entity.name

    with get_session() as session:
        person = None
        target = _normalize_name(entity_name)
        for p in session.query(Person).all():
            if _normalize_name(p.name) == target:
                person = p
                break

        company_info = None
        materials: list[Material] = []
        if person:
            if person.company_id:
                comp = session.query(Company).filter(Company.id == person.company_id).first()
                if comp:
                    company_info = {"id": comp.id, "name": comp.name}
            materials = (
                session.query(Material)
                .filter(Material.person_id == person.id)
                .order_by(Material.id)
                .all()
            )

        attrs = dict(entity_attrs)
        if person:
            if person.id_number:
                attrs.setdefault("id_number", person.id_number)
            if person.education:
                attrs.setdefault("education", person.education)
            if person.position:
                attrs.setdefault("position", person.position)

        material_list = [_material_to_complete_shape(m) for m in materials]

    certificates = [
        {
            "title": m["title"],
            "cert_name": m["metadata"]["extracted_data"].get("cert_name", ""),
            "cert_number": m["metadata"]["extracted_data"].get("cert_number", ""),
            "expiry_date": m["expiry_date"],
        }
        for m in material_list
        if "cert" in (m["doc_type"]["code"] or "")
    ]

    return {
        "person": {"id": entity_id, "name": entity_name, "attributes": attrs},
        "company": company_info,
        "certificates": certificates,
        "materials": material_list,
        "aggregated_info": attrs,
    }
