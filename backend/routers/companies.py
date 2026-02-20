"""公司管理API"""

import json
import logging
from datetime import date
from fastapi import APIRouter, HTTPException

from database import get_session, Company, Document, Material, Person

logger = logging.getLogger("materialhub.routers.companies")

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("")
async def list_companies():
    """列出所有公司"""
    with get_session() as session:
        companies = session.query(Company).order_by(Company.created_at.desc()).all()

        # 为每个公司添加文档和材料统计
        result = []
        for company in companies:
            company_dict = company.to_dict()
            doc_count = session.query(Document).filter(Document.company_id == company.id).count()
            material_count = session.query(Material).filter(Material.company_id == company.id).count()
            company_dict['document_count'] = doc_count
            company_dict['material_count'] = material_count
            result.append(company_dict)

        return {"companies": result}


@router.get("/{company_id}")
async def get_company(company_id: int):
    """获取公司详情"""
    with get_session() as session:
        company = session.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # 统计文档数和素材数
        doc_count = session.query(Document).filter(Document.company_id == company_id).count()
        material_count = session.query(Material).filter(Material.company_id == company_id).count()

        result = company.to_dict()
        result['document_count'] = doc_count
        result['material_count'] = material_count

        return result


@router.get("/{company_id}/materials")
async def get_company_materials(company_id: int):
    """获取公司的所有素材"""
    with get_session() as session:
        company = session.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        materials = session.query(Material).filter(
            Material.company_id == company_id
        ).order_by(Material.created_at.desc()).all()

        return {
            "company": company.to_dict(),
            "materials": [m.to_dict() for m in materials]
        }


@router.get("/{company_id}/complete")
async def get_company_complete(company_id: int):
    """
    获取公司完整信息（聚合API）

    返回：
    - 公司基本信息
    - 公司员工列表
    - 公司所有材料（包含完整的 extracted_data）
    - 统计信息
    - 聚合的扩展信息（从材料中提取）
    """
    with get_session() as session:
        company = session.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # 1. 获取员工列表
        employees = session.query(Person).filter(
            Person.company_id == company_id
        ).order_by(Person.created_at.desc()).all()

        employees_data = []
        for emp in employees:
            emp_dict = emp.to_dict()
            # 统计该员工的材料数
            material_count = session.query(Material).filter(
                Material.person_id == emp.id
            ).count()
            emp_dict['material_count'] = material_count
            employees_data.append(emp_dict)

        # 2. 获取公司所有材料
        materials = session.query(Material).filter(
            Material.company_id == company_id
        ).order_by(Material.created_at.desc()).all()

        materials_data = []
        for mat in materials:
            mat_dict = mat.to_dict()
            materials_data.append(mat_dict)

        # 3. 统计信息
        today = date.today()
        expired_count = sum(
            1 for m in materials
            if m.expiry_date and m.expiry_date < today
        )

        statistics = {
            "total_materials": len(materials),
            "total_employees": len(employees),
            "expired_materials": expired_count,
            "valid_materials": len(materials) - expired_count
        }

        # 4. 聚合扩展信息（从营业执照材料中提取）
        aggregated_info = {}
        for mat in materials:
            if mat.material_type == 'license' and mat.extracted_json:
                try:
                    data = json.loads(mat.extracted_json)
                    extracted = data.get('extracted_data', {})

                    # 提取扩展字段
                    if 'registered_capital' in extracted:
                        aggregated_info['registered_capital'] = extracted['registered_capital']
                    if 'establishment_date' in extracted:
                        aggregated_info['establishment_date'] = extracted['establishment_date']
                    if 'company_type' in extracted:
                        aggregated_info['company_type'] = extracted['company_type']
                    if 'business_scope' in extracted:
                        aggregated_info['business_scope'] = extracted['business_scope']
                    if 'operating_period' in extracted:
                        aggregated_info['operating_period'] = extracted['operating_period']

                    break  # 只需要一个营业执照的信息
                except:
                    pass

        return {
            "company": company.to_dict(),
            "employees": employees_data,
            "materials": materials_data,
            "statistics": statistics,
            "aggregated_info": aggregated_info
        }
