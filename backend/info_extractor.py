"""
智能信息提取器
从OCR文本中提取结构化信息：公司、人员、有效期等
"""

import re
import logging
from typing import Optional, Dict, Any
from datetime import date

logger = logging.getLogger("materialhub.info_extractor")


# 材料类型关键词映射
# 注意：个人证件（身份证、学历等）不自动OCR，因为Word表格已有信息
MATERIAL_TYPE_KEYWORDS = {
    "license": ["营业执照", "执照"],
    "legal_person_cert": ["法定代表人", "法人资格", "法人证明", "授权书"],
    "qualification": ["资质证书", "资质", "许可证", "安全生产许可"],
    "iso_cert": ["ISO", "质量管理", "环境管理", "信息安全"],
    # 以下类型不再自动OCR（Word表格已有数据）
    # "id_card": ["身份证"],
    # "education": ["学历", "学位", "毕业证"],
    # "certificate": ["职业资格证"],  # 个人的证书
}

# 不需要OCR的材料关键词（黑名单）
SKIP_OCR_KEYWORDS = [
    "封面", "封底", "目录", "contents",
    "图表", "chart", "graph",
    "示意图", "流程图", "架构图",
    "logo", "标志", "装饰",
    "空白", "blank",
    "页眉", "页脚", "header", "footer",
    "分隔", "separator",
]


def should_skip_ocr(title: str) -> bool:
    """
    判断是否应该跳过OCR处理

    Returns:
        True: 跳过OCR
        False: 需要OCR
    """
    title_lower = title.lower()

    # 检查黑名单关键词
    for keyword in SKIP_OCR_KEYWORDS:
        if keyword.lower() in title_lower:
            logger.debug(f"⏭️ 跳过OCR (黑名单匹配): {title} [关键词: {keyword}]")
            return True

    return False


def detect_material_type(title: str) -> Optional[str]:
    """根据标题检测材料类型"""
    title_lower = title.lower()

    for mat_type, keywords in MATERIAL_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in title_lower:
                return mat_type

    return None


def extract_company_info(ocr_text: str) -> Dict[str, Any]:
    """
    从OCR文本提取公司信息

    Returns:
        {
            'name': 公司名称,
            'legal_person': 法定代表人,
            'credit_code': 统一社会信用代码,
            'address': 地址
        }
    """
    info = {}

    # 提取公司名称
    # 模式: "单位名称：XXX" or "企业名称：XXX" or "名称：XXX"
    name_patterns = [
        r'(?:单位|企业|公司)?名称[：:]\s*([^\n\r，。；]+)',
        r'(?:单位|企业)[：:]\s*([^\n\r，。；]+)',
    ]
    for pattern in name_patterns:
        match = re.search(pattern, ocr_text)
        if match:
            name = match.group(1).strip()
            # 清理名称中的下划线和多余空格
            name = re.sub(r'[_\s]+', '', name)
            if name and len(name) > 2:
                info['name'] = name
                logger.info(f"✓ 提取公司名称: {name}")
                break

    # 提取法定代表人
    # 模式: "法定代表人：XXX" or "姓名：XXX"
    legal_patterns = [
        r'法定代表人[：:]\s*([^\n\r，。；\s]{2,4})',
        r'(?:^|\n)姓名[：:]\s*([^\n\r，。；\s]{2,4})',
    ]
    for pattern in legal_patterns:
        match = re.search(pattern, ocr_text)
        if match:
            legal_person = match.group(1).strip()
            legal_person = re.sub(r'[_\s]+', '', legal_person)
            if legal_person and len(legal_person) >= 2:
                info['legal_person'] = legal_person
                logger.info(f"✓ 提取法定代表人: {legal_person}")
                break

    # 提取统一社会信用代码
    # 18位数字字母组合
    credit_code_pattern = r'(?:统一社会信用代码|信用代码)[：:]\s*([A-Z0-9]{18})'
    match = re.search(credit_code_pattern, ocr_text)
    if match:
        info['credit_code'] = match.group(1).strip()
        logger.info(f"✓ 提取信用代码: {info['credit_code']}")

    # 提取地址
    address_patterns = [
        r'(?:住所|地址)[：:]\s*([^\n\r；]+)',
        r'地址[：:]\s*([^\n\r；]+)',
    ]
    for pattern in address_patterns:
        match = re.search(pattern, ocr_text)
        if match:
            address = match.group(1).strip()
            address = re.sub(r'[_]{2,}', '', address)
            if address and len(address) > 5:
                info['address'] = address
                logger.info(f"✓ 提取地址: {address[:50]}...")
                break

    if info:
        logger.info(f"📋 公司信息提取完成: {info}")
    else:
        logger.warning("⚠ 未能提取到公司信息")

    return info


def extract_person_info(ocr_text: str, title: str = "") -> Dict[str, Any]:
    """
    从OCR文本提取人员信息

    Returns:
        {
            'name': 姓名,
            'id_number': 身份证号,
            'education': 学历
        }
    """
    info = {}

    # 提取姓名
    # 从标题或文本中提取
    if title:
        # 如果标题是人名（2-4个中文字符）
        name_in_title = re.search(r'^([^\d\w]{2,4})$', title.strip())
        if name_in_title:
            info['name'] = name_in_title.group(1)

    if 'name' not in info:
        name_patterns = [
            r'姓名[：:]\s*([^\n\r，。；\s]{2,4})',
            r'(?:^|\n)([^\n\r，。；\s]{2,4})\s*(?:先生|女士|同志)',
        ]
        for pattern in name_patterns:
            match = re.search(pattern, ocr_text)
            if match:
                name = match.group(1).strip()
                if name and 2 <= len(name) <= 4:
                    info['name'] = name
                    break

    # 提取身份证号
    # 18位身份证号码
    id_pattern = r'\b([1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx])\b'
    match = re.search(id_pattern, ocr_text)
    if match:
        info['id_number'] = match.group(1).upper()
        # 脱敏显示
        masked = info['id_number'][:6] + '********' + info['id_number'][-4:]
        logger.info(f"✓ 提取身份证号: {masked}")

    # 提取学历
    education_keywords = ['博士', '硕士', '本科', '专科', '研究生', '学士', '大学']
    for keyword in education_keywords:
        if keyword in ocr_text:
            info['education'] = keyword
            logger.info(f"✓ 提取学历: {keyword}")
            break

    if info:
        logger.info(f"👤 人员信息提取完成: 姓名={info.get('name', '未知')}, 学历={info.get('education', '未知')}")
    else:
        logger.warning("⚠ 未能提取到人员信息")

    return info


def extract_expiry_date(ocr_text: str) -> Optional[date]:
    """
    从OCR文本提取有效期

    支持格式：
    - 有效期至：2025年12月31日
    - 有效期：2024-06-30
    - 至2026年3月15日
    """
    patterns = [
        # 有效期至：2025年12月31日
        r'有效期[至到][：:]\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日',
        # 有效期：2024.06.30 / 2024-06-30
        r'有效[期日期][：:]\s*(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})',
        # 至 2026年03月15日
        r'至\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日',
        # Valid Until: 2025-12-31
        r'[Vv]alid\s+[Uu]ntil[：:]\s*(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})',
        # 有效期至2025/12/31
        r'有效期[至到]\s*(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})',
        # 证书有效期：2024年1月1日 - 2027年1月1日 (取后面的日期)
        r'[-—至到]\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日',
    ]

    for pattern in patterns:
        match = re.search(pattern, ocr_text)
        if match:
            try:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3))

                if 2000 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                    expiry = date(year, month, day)
                    logger.info(f"✓ 提取有效期: {expiry} (匹配文本: {match.group(0)})")
                    return expiry
            except (ValueError, IndexError):
                continue

    logger.debug("未能提取到有效期")
    return None


def extract_all_info(ocr_text: str, title: str, material_type: Optional[str] = None) -> Dict[str, Any]:
    """
    综合提取所有信息

    Returns:
        {
            'material_type': 材料类型,
            'company_info': 公司信息 (如果有),
            'person_info': 人员信息 (如果有),
            'expiry_date': 有效期 (如果有)
        }
    """
    if not material_type:
        material_type = detect_material_type(title)

    result = {
        'material_type': material_type,
    }

    # 根据材料类型提取相应信息
    if material_type in ['license', 'legal_person_cert']:
        company_info = extract_company_info(ocr_text)
        if company_info:
            result['company_info'] = company_info

    if material_type in ['id_card', 'education']:
        person_info = extract_person_info(ocr_text, title)
        if person_info:
            result['person_info'] = person_info

    # 证书类材料提取有效期
    if material_type in ['certificate', 'iso_cert', 'license']:
        expiry_date = extract_expiry_date(ocr_text)
        if expiry_date:
            result['expiry_date'] = expiry_date

    return result
