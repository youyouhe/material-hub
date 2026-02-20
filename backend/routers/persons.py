"""人员管理API"""

import json
import logging
from datetime import date
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_session, Person, Material, Company

logger = logging.getLogger("materialhub.routers.persons")


class PersonUpdate(BaseModel):
    """人员更新模型"""
    name: Optional[str] = None
    id_number: Optional[str] = None
    education: Optional[str] = None
    position: Optional[str] = None
    company_id: Optional[int] = None


class BatchLinkRequest(BaseModel):
    """批量关联请求模型"""
    person_ids: List[int]
    company_id: int

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


@router.patch("/{person_id}")
async def update_person(person_id: int, update: PersonUpdate):
    """
    更新人员信息

    可更新字段：
    - name: 姓名
    - id_number: 身份证号
    - education: 学历
    - position: 职位
    - company_id: 所属公司ID（设置为 null 取消关联）
    """
    with get_session() as session:
        person = session.query(Person).filter(Person.id == person_id).first()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")

        # 验证 company_id 是否存在
        if update.company_id is not None:
            company = session.query(Company).filter(Company.id == update.company_id).first()
            if not company:
                raise HTTPException(status_code=404, detail=f"Company {update.company_id} not found")

        # 获取只包含已设置字段的数据
        update_data = update.model_dump(exclude_unset=True)

        # 更新字段
        for field, value in update_data.items():
            setattr(person, field, value)

        session.flush()

        result = person.to_dict()
        logger.info(f"✅ 人员已更新: ID={person_id}, fields={list(update_data.keys())}")

        return result


@router.post("/batch-link")
async def batch_link_persons(request: BatchLinkRequest):
    """
    批量关联人员到公司

    Args:
        person_ids: 人员ID列表
        company_id: 公司ID

    Returns:
        更新结果统计
    """
    with get_session() as session:
        # 验证公司是否存在
        company = session.query(Company).filter(Company.id == request.company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {request.company_id} not found")

        # 批量更新人员
        updated_count = 0
        not_found = []

        for person_id in request.person_ids:
            person = session.query(Person).filter(Person.id == person_id).first()
            if not person:
                not_found.append(person_id)
                continue

            person.company_id = request.company_id
            updated_count += 1

        session.flush()

        result = {
            "success": True,
            "company": company.to_dict(),
            "updated_count": updated_count,
            "total_requested": len(request.person_ids),
            "not_found": not_found
        }

        logger.info(
            f"✅ 批量关联完成: {updated_count}/{len(request.person_ids)} 个人员 → 公司 {company.name}"
        )

        return result


@router.get("/{person_id}/complete")
async def get_person_complete(person_id: int):
    """
    获取人员完整信息（聚合API）

    返回：
    - 人员基本信息
    - 所属公司信息
    - 人员所有材料（包含完整的 extracted_data）
    - 聚合的扩展信息（从材料中提取：性别、出生日期、年龄、民族、住址等）
    - 证书列表
    """
    with get_session() as session:
        person = session.query(Person).filter(Person.id == person_id).first()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")

        # 1. 获取所属公司信息
        company_data = None
        if person.company_id:
            company = session.query(Company).filter(Company.id == person.company_id).first()
            if company:
                company_data = company.to_dict()

        # 2. 获取人员所有材料
        materials = session.query(Material).filter(
            Material.person_id == person_id
        ).order_by(Material.created_at.desc()).all()

        materials_data = []
        for mat in materials:
            mat_dict = mat.to_dict()
            materials_data.append(mat_dict)

        # 3. 聚合扩展信息（从身份证、学历证书等材料中提取）
        aggregated_info = {}
        certificates = []

        for mat in materials:
            if not mat.extracted_json:
                continue

            try:
                data = json.loads(mat.extracted_json)
                extracted = data.get('extracted_data', {})

                # 从身份证提取基本信息
                if mat.material_type == 'id_card':
                    if 'gender' in extracted:
                        aggregated_info['gender'] = extracted['gender']
                    if 'birth_date' in extracted:
                        aggregated_info['birth_date'] = extracted['birth_date']
                        # 计算年龄
                        try:
                            birth_year, birth_month, birth_day = extracted['birth_date'].split('-')
                            today_date = date.today()
                            age = today_date.year - int(birth_year)
                            if today_date.month < int(birth_month) or (
                                today_date.month == int(birth_month) and today_date.day < int(birth_day)
                            ):
                                age -= 1
                            aggregated_info['age'] = age
                        except:
                            pass
                    if 'nation' in extracted:
                        aggregated_info['nation'] = extracted['nation']
                    if 'address' in extracted:
                        aggregated_info['address'] = extracted['address']

                # 从学历证书提取专业信息
                if mat.material_type == 'education':
                    if 'major' in extracted:
                        aggregated_info['major'] = extracted['major']
                    if 'degree' in extracted:
                        aggregated_info['degree'] = extracted['degree']
                    if 'university' in extracted:
                        aggregated_info['university'] = extracted['university']
                    if 'graduation_date' in extracted:
                        aggregated_info['graduation_date'] = extracted['graduation_date']

                # 收集所有证书
                if mat.material_type in ['certificate', 'iso_cert', 'education']:
                    cert_info = {
                        "material_id": mat.id,
                        "title": mat.title,
                        "type": mat.material_type,
                        "cert_number": extracted.get('cert_number') or extracted.get('certificate_number'),
                        "issue_date": extracted.get('issue_date'),
                        "expiry_date": mat.expiry_date.isoformat() if mat.expiry_date else None,
                        "issue_authority": extracted.get('issue_authority'),
                        "is_expired": mat.to_dict()['is_expired']
                    }
                    certificates.append(cert_info)

            except Exception as e:
                logger.warning(f"Failed to parse extracted_json for material {mat.id}: {e}")
                continue

        # 4. 统计信息
        today = date.today()
        expired_certs = sum(
            1 for cert in certificates
            if cert['is_expired'] is True
        )

        statistics = {
            "total_materials": len(materials),
            "total_certificates": len(certificates),
            "expired_certificates": expired_certs,
            "valid_certificates": len(certificates) - expired_certs
        }

        return {
            "person": person.to_dict(),
            "company": company_data,
            "materials": materials_data,
            "aggregated_info": aggregated_info,
            "certificates": certificates,
            "statistics": statistics
        }
