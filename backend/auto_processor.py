"""
自动处理服务
上传文档后自动OCR关键图片，提取并关联公司和人员信息
"""

import logging
from typing import List, Optional
from pathlib import Path

from database import get_session, Company, Person, Material
from ocr_client import check_ocr_service, ocr_image
from info_extractor import extract_all_info, detect_material_type, should_skip_ocr
from material_filter import filter_materials_for_ocr

logger = logging.getLogger("materialhub.auto_processor")


def get_or_create_company(company_info: dict) -> Optional[int]:
    """
    获取或创建公司记录

    Args:
        company_info: {'name', 'legal_person', 'credit_code', 'address'}

    Returns:
        company_id 或 None
    """
    if not company_info or not company_info.get('name'):
        return None

    name = company_info['name']

    with get_session() as session:
        # 尝试通过名称查找现有公司
        company = session.query(Company).filter(Company.name == name).first()

        if company:
            # 更新公司信息
            updated = False
            if company_info.get('legal_person') and not company.legal_person:
                company.legal_person = company_info['legal_person']
                updated = True
            if company_info.get('credit_code') and not company.credit_code:
                company.credit_code = company_info['credit_code']
                updated = True
            if company_info.get('address') and not company.address:
                company.address = company_info['address']
                updated = True

            if updated:
                session.commit()
                logger.info(f"Updated company: {company.name}")

            return company.id
        else:
            # 创建新公司
            new_company = Company(
                name=name,
                legal_person=company_info.get('legal_person'),
                credit_code=company_info.get('credit_code'),
                address=company_info.get('address'),
            )
            session.add(new_company)
            session.commit()
            logger.info(f"Created new company: {new_company.name}")
            return new_company.id


def get_or_create_person(person_info: dict, company_id: Optional[int] = None) -> Optional[int]:
    """
    获取或创建人员记录

    Args:
        person_info: {'name', 'id_number', 'education'}
        company_id: 所属公司ID

    Returns:
        person_id 或 None
    """
    if not person_info or not person_info.get('name'):
        return None

    name = person_info['name']
    id_number = person_info.get('id_number')

    with get_session() as session:
        # 尝试通过姓名或身份证号查找
        query = session.query(Person)

        if id_number:
            person = query.filter(Person.id_number == id_number).first()
        else:
            # 如果没有身份证号，通过姓名和公司查找
            if company_id:
                person = query.filter(
                    Person.name == name,
                    Person.company_id == company_id
                ).first()
            else:
                person = query.filter(Person.name == name).first()

        if person:
            # 更新人员信息
            updated = False
            if person_info.get('id_number') and not person.id_number:
                person.id_number = person_info['id_number']
                updated = True
            if person_info.get('education') and not person.education:
                person.education = person_info['education']
                updated = True
            if company_id and not person.company_id:
                person.company_id = company_id
                updated = True

            if updated:
                session.commit()
                logger.info(f"Updated person: {person.name}")

            return person.id
        else:
            # 创建新人员
            new_person = Person(
                name=name,
                id_number=id_number,
                education=person_info.get('education'),
                company_id=company_id,
            )
            session.add(new_person)
            session.commit()
            logger.info(f"Created new person: {new_person.name}")
            return new_person.id


def process_materials(material_ids: List[int], files_dir: str):
    """
    处理材料：OCR识别并提取信息

    Args:
        material_ids: 材料ID列表
        files_dir: 图片文件目录
    """
    # 检查OCR服务
    if not check_ocr_service():
        logger.warning("OCR service not available, skipping auto-processing")
        return

    with get_session() as session:
        materials = session.query(Material).filter(
            Material.id.in_(material_ids)
        ).all()

        logger.info(f"📋 开始处理 {len(materials)} 个材料")

        # ========== 步骤1: LLM预筛选 ==========
        materials_for_llm = [
            {"id": mat.id, "title": mat.title}
            for mat in materials
            if not mat.ocr_text  # 已有OCR文本的不需要判断
        ]

        if materials_for_llm:
            logger.info(f"🤖 使用LLM预筛选 {len(materials_for_llm)} 个材料...")
            filter_result = filter_materials_for_ocr(materials_for_llm)
            need_ocr_ids = set(filter_result["need_ocr"])
            skip_ocr_ids = set(filter_result["skip_ocr"])

            logger.info(f"✅ LLM判断: {len(need_ocr_ids)} 个需要OCR, {len(skip_ocr_ids)} 个跳过")
        else:
            need_ocr_ids = set()
            skip_ocr_ids = set()

        # ========== 步骤2: OCR处理和信息提取 ==========
        company_id = None
        ocr_count = 0
        skip_count = 0

        for material in materials:
            # 缓存检查：如果已经有OCR文本，跳过OCR但仍提取信息
            if material.ocr_text:
                skip_count += 1
                logger.debug(f"⏭️ 跳过 (已有OCR): {material.title}")
                # 如果有缓存的OCR文本，仍然需要提取公司信息
                mat_type = detect_material_type(material.title)
                if not company_id and mat_type in ['license', 'legal_person_cert']:
                    extracted_info = extract_all_info(material.ocr_text, material.title, mat_type)
                    if 'company_info' in extracted_info:
                        company_id = get_or_create_company(extracted_info['company_info'])
                continue

            # LLM判断：是否需要OCR
            if material.id in skip_ocr_ids:
                skip_count += 1
                logger.info(f"⏭️ 跳过 (LLM判断): {material.title}")
                continue

            if material.id not in need_ocr_ids:
                # 不在需要OCR的列表中（可能LLM判断失败，使用备用关键词过滤）
                mat_type = detect_material_type(material.title)
                if mat_type not in ['license', 'legal_person_cert', 'qualification', 'iso_cert']:
                    skip_count += 1
                    logger.debug(f"⏭️ 跳过 (关键词过滤): {material.title}")
                    continue

            # 检测材料类型
            mat_type = detect_material_type(material.title)

            # OCR识别
            image_path = Path(files_dir) / material.image_filename
            if not image_path.exists():
                continue

            logger.info(f"OCR processing [{ocr_count+1}]: {material.title} ({material.image_filename})")
            ocr_text = ocr_image(str(image_path))
            ocr_count += 1

            if not ocr_text:
                continue

            # 保存OCR文本
            material.ocr_text = ocr_text
            material.material_type = mat_type

            # 提取信息
            logger.info(f"📝 开始提取信息: {material.title}")
            logger.info(f"OCR文本预览 (前200字): {ocr_text[:200]}...")
            extracted_info = extract_all_info(ocr_text, material.title, mat_type)
            logger.info(f"提取结果: {extracted_info}")

            # 提取公司信息
            if 'company_info' in extracted_info and not company_id:
                company_id = get_or_create_company(extracted_info['company_info'])
                if company_id:
                    logger.info(f"✅ 公司记录已创建/更新，ID: {company_id}")

            # 提取有效期
            if 'expiry_date' in extracted_info:
                material.expiry_date = extracted_info['expiry_date']
                logger.info(f"✅ {material.title} 有效期已更新: {material.expiry_date}")

        session.commit()

        # 第二轮：关联公司
        # 注意：不再自动提取人员信息（Word表格已提供）
        for material in materials:
            if not material.material_type:
                continue

            # 关联公司到相关材料
            if company_id and material.material_type in ['license', 'legal_person_cert', 'qualification', 'iso_cert']:
                material.company_id = company_id
                logger.debug(f"✓ 材料已关联到公司: {material.title}")

        session.commit()

        # 统计信息
        total = len(materials)
        processed = ocr_count
        skipped = skip_count
        logger.info(f"✅ 自动处理完成:")
        logger.info(f"   总材料数: {total}")
        logger.info(f"   已处理OCR: {processed}")
        logger.info(f"   已跳过: {skipped}")
        if materials_for_llm:
            logger.info(f"   LLM判断需要OCR: {len(need_ocr_ids)}")
            logger.info(f"   LLM判断跳过: {len(skip_ocr_ids)}")
