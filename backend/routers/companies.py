"""公司管理API"""

import logging
from fastapi import APIRouter, HTTPException

from database import get_session, Company, Document, Material

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
