"""
证书版本管理 - 智能匹配和替换
识别同一证书的不同版本，实现平滑升级
"""
import logging
import json
from datetime import datetime, date
from typing import Optional, Dict, Tuple
from difflib import SequenceMatcher
from database import get_session, Material, MaterialVersion

logger = logging.getLogger("materialhub.certificate_matcher")


def find_existing_certificate(
    company_id: int,
    material_type: str,
    analysis: Dict,
    session
) -> Optional[Material]:
    """
    查找同一公司的同类证书（可能是旧版本）

    Args:
        company_id: 公司ID
        material_type: 材料类型
        analysis: LLM提取的分析结果
        session: 数据库session

    Returns:
        找到的旧证书Material对象，未找到返回None
    """

    if not company_id:
        return None

    # 不同材料类型的匹配策略
    if material_type == "iso_certificate":
        return _find_iso_certificate(company_id, analysis, session)

    elif material_type == "company_qualification":
        return _find_qualification(company_id, analysis, session)

    elif material_type == "company_business":
        return _find_business_license(company_id, analysis, session)

    elif material_type == "employee_document":
        # 员工证件不做版本管理（每个员工有多个证件）
        return None

    return None


def _find_iso_certificate(company_id: int, analysis: Dict, session) -> Optional[Material]:
    """查找ISO认证证书（匹配：公司 + ISO标准）"""

    certificate_info = analysis.get("certificate_info", {})
    iso_standard = certificate_info.get("iso_standard", "")

    if not iso_standard:
        logger.debug("ISO标准为空，无法匹配")
        return None

    # 提取ISO标准核心部分（如 ISO 9001:2015 -> ISO 9001）
    iso_core = iso_standard.split(":")[0].strip()

    logger.info(f"🔍 查找ISO证书: 公司ID={company_id}, ISO标准={iso_core}")

    # 查询同公司的所有ISO证书
    existing_materials = session.query(Material).filter(
        Material.company_id == company_id,
        Material.material_type == "iso_certificate"
    ).all()

    # 遍历匹配ISO标准
    for material in existing_materials:
        if not material.extracted_json:
            continue

        try:
            extracted = json.loads(material.extracted_json)
            existing_iso = extracted.get("certificate_info", {}).get("iso_standard", "")
            existing_core = existing_iso.split(":")[0].strip()

            # 匹配核心标准（忽略年份版本）
            if iso_core.lower() in existing_core.lower() or existing_core.lower() in iso_core.lower():
                logger.info(f"✅ 找到匹配的ISO证书: ID={material.id}, {material.title}")
                return material
        except:
            continue

    logger.info("未找到匹配的ISO证书")
    return None


def _find_qualification(company_id: int, analysis: Dict, session) -> Optional[Material]:
    """查找资质证书（匹配：公司 + 资质名称）"""

    certificate_info = analysis.get("certificate_info", {})
    cert_name = certificate_info.get("certificate_name", "")

    if not cert_name:
        logger.debug("资质名称为空，无法匹配")
        return None

    logger.info(f"🔍 查找资质证书: 公司ID={company_id}, 资质名称={cert_name}")

    # 查询同公司的所有资质证书
    existing_materials = session.query(Material).filter(
        Material.company_id == company_id,
        Material.material_type == "company_qualification"
    ).all()

    # 遍历匹配资质名称
    best_match = None
    best_similarity = 0.7  # 最低相似度阈值

    for material in existing_materials:
        if not material.extracted_json:
            continue

        try:
            extracted = json.loads(material.extracted_json)
            existing_name = extracted.get("certificate_info", {}).get("certificate_name", "")

            # 计算文本相似度
            similarity = SequenceMatcher(None, cert_name.lower(), existing_name.lower()).ratio()

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = material

        except:
            continue

    if best_match:
        logger.info(f"✅ 找到匹配的资质证书: ID={best_match.id}, {best_match.title}, 相似度={best_similarity:.2f}")
        return best_match

    logger.info("未找到匹配的资质证书")
    return None


def _find_business_license(company_id: int, analysis: Dict, session) -> Optional[Material]:
    """查找营业执照（匹配：统一社会信用代码）"""

    company_info = analysis.get("company_info", {})
    credit_code = company_info.get("credit_code", "")

    if not credit_code or len(credit_code) != 18:
        logger.debug("信用代码无效，无法匹配")
        return None

    logger.info(f"🔍 查找营业执照: 信用代码={credit_code}")

    # 查询相同信用代码的营业执照
    existing_materials = session.query(Material).filter(
        Material.material_type == "company_business"
    ).all()

    for material in existing_materials:
        if not material.extracted_json:
            continue

        try:
            extracted = json.loads(material.extracted_json)
            existing_code = extracted.get("company_info", {}).get("credit_code", "")

            if existing_code == credit_code:
                logger.info(f"✅ 找到匹配的营业执照: ID={material.id}, {material.title}")
                return material
        except:
            continue

    logger.info("未找到匹配的营业执照")
    return None


def is_newer_version(new_analysis: Dict, old_material: Material) -> Tuple[bool, float, str]:
    """
    判断新证书是否比旧证书更新

    Args:
        new_analysis: 新证书的分析结果
        old_material: 旧证书的Material对象

    Returns:
        (是否更新版本, 置信度, 判断依据)
    """

    try:
        old_data = json.loads(old_material.extracted_json) if old_material.extracted_json else {}
    except:
        old_data = {}

    # 1. 比较有效期
    new_expiry = new_analysis.get("key_dates", {}).get("expiry_date")
    old_expiry = old_data.get("key_dates", {}).get("expiry_date")

    if new_expiry and old_expiry:
        try:
            new_date = datetime.strptime(new_expiry, "%Y-%m-%d").date()
            old_date = datetime.strptime(old_expiry, "%Y-%m-%d").date() if isinstance(old_expiry, str) else old_material.expiry_date

            if new_date > old_date:
                days_diff = (new_date - old_date).days
                confidence = min(0.95, 0.8 + (days_diff / 365) * 0.15)  # 相差越久，置信度越高
                reason = f"有效期更新：{old_expiry} → {new_expiry}"
                logger.info(f"✅ 判断为更新版本（有效期）: {reason}, 置信度={confidence:.2f}")
                return True, confidence, reason
            elif new_date < old_date:
                confidence = 0.9
                reason = f"有效期更早：{new_expiry} < {old_expiry}，判定为旧版本"
                logger.info(f"⚠️ 判断为旧版本（有效期）: {reason}")
                return False, confidence, reason
        except:
            pass

    # 2. 比较颁发日期
    new_issue = new_analysis.get("key_dates", {}).get("issue_date")
    old_issue = old_data.get("key_dates", {}).get("issue_date")

    if new_issue and old_issue:
        try:
            new_date = datetime.strptime(new_issue, "%Y-%m-%d").date()
            old_date = datetime.strptime(old_issue, "%Y-%m-%d").date()

            if new_date > old_date:
                confidence = 0.85
                reason = f"颁发日期更新：{old_issue} → {new_issue}"
                logger.info(f"✅ 判断为更新版本（颁发日期）: {reason}, 置信度={confidence:.2f}")
                return True, confidence, reason
            elif new_date < old_date:
                confidence = 0.85
                reason = f"颁发日期更早：{new_issue} < {old_issue}，判定为旧版本"
                logger.info(f"⚠️ 判断为旧版本（颁发日期）: {reason}")
                return False, confidence, reason
        except:
            pass

    # 3. 比较证书编号（如果不同，可能是新版本）
    new_cert_num = new_analysis.get("certificate_info", {}).get("certificate_number", "")
    old_cert_num = old_data.get("certificate_info", {}).get("certificate_number", "")

    if new_cert_num and old_cert_num and new_cert_num != old_cert_num:
        confidence = 0.6  # 较低置信度，需要结合其他信息
        reason = f"证书编号不同：{old_cert_num} → {new_cert_num}"
        logger.info(f"⚠️ 证书编号不同，可能是更新版本: {reason}, 置信度={confidence:.2f}")
        return True, confidence, reason

    # 无法判断
    logger.warning("⚠️ 无法判断版本新旧，需要人工确认")
    return False, 0.5, "无法自动判断版本新旧"


async def replace_with_newer_version(
    old_material: Material,
    new_material_id: int,
    reason: str,
    session
) -> bool:
    """
    用新证书替换旧证书（标记旧证书为历史版本）

    Args:
        old_material: 旧证书Material对象
        new_material_id: 新证书Material ID
        reason: 替换原因
        session: 数据库session

    Returns:
        是否成功
    """

    try:
        # 1. 获取旧证书的版本号
        old_version = session.query(MaterialVersion).filter(
            MaterialVersion.material_id == old_material.id,
            MaterialVersion.is_current == True
        ).first()

        old_version_num = old_version.version_number if old_version else 1

        # 2. 标记旧版本为非当前
        if old_version:
            old_version.is_current = False

        # 3. 创建新版本记录
        new_version = MaterialVersion(
            material_id=new_material_id,
            previous_material_id=old_material.id,
            version_number=old_version_num + 1,
            is_current=True,
            replaced_at=datetime.utcnow(),
            replaced_reason=reason
        )
        session.add(new_version)

        # 4. 标记旧Material为已归档（但不删除，保留审计记录）
        # 注意：这里不直接删除，而是通过version关联保留历史
        logger.info(f"✅ 证书版本已更新: Material {old_material.id} (v{old_version_num}) → {new_material_id} (v{old_version_num + 1})")
        logger.info(f"   替换原因: {reason}")

        return True

    except Exception as e:
        logger.error(f"❌ 证书版本替换失败: {e}")
        return False


def get_version_history(material_id: int, session) -> list:
    """
    获取证书的版本历史

    Args:
        material_id: Material ID
        session: 数据库session

    Returns:
        版本历史列表（从新到旧）
    """

    versions = []
    current_id = material_id

    # 向前追溯历史版本
    while current_id:
        version = session.query(MaterialVersion).filter(
            MaterialVersion.material_id == current_id
        ).first()

        if version:
            material = session.query(Material).get(current_id)
            versions.append({
                "material_id": current_id,
                "version_number": version.version_number,
                "is_current": version.is_current,
                "title": material.title if material else None,
                "expiry_date": material.expiry_date.isoformat() if material and material.expiry_date else None,
                "replaced_at": version.replaced_at.isoformat() if version.replaced_at else None,
                "replaced_reason": version.replaced_reason
            })
            current_id = version.previous_material_id
        else:
            break

    return versions
