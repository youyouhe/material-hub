"""人员管理API"""

import logging
from fastapi import APIRouter, HTTPException

from database import get_session, Person, Material

logger = logging.getLogger("materialhub.routers.persons")

router = APIRouter(prefix="/api/persons", tags=["persons"])


@router.get("")
async def list_persons(company_id: int = None):
    """列出人员"""
    with get_session() as session:
        query = session.query(Person)

        if company_id:
            query = query.filter(Person.company_id == company_id)

        persons = query.order_by(Person.created_at.desc()).all()

        # 为每个人员添加材料统计
        result = []
        for person in persons:
            person_dict = person.to_dict()
            material_count = session.query(Material).filter(Material.person_id == person.id).count()
            person_dict['material_count'] = material_count
            result.append(person_dict)

        return {"persons": result}


@router.get("/{person_id}")
async def get_person(person_id: int):
    """获取人员详情"""
    with get_session() as session:
        person = session.query(Person).filter(Person.id == person_id).first()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")

        # 统计素材数
        material_count = session.query(Material).filter(Material.person_id == person_id).count()

        result = person.to_dict()
        result['material_count'] = material_count

        return result


@router.get("/{person_id}/materials")
async def get_person_materials(person_id: int):
    """获取人员的所有素材"""
    with get_session() as session:
        person = session.query(Person).filter(Person.id == person_id).first()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")

        materials = session.query(Material).filter(
            Material.person_id == person_id
        ).order_by(Material.created_at.desc()).all()

        return {
            "person": person.to_dict(),
            "materials": [m.to_dict() for m in materials]
        }
