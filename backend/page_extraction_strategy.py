"""
不同材料类型的PNG页面提取策略
"""
from typing import List, Dict
import logging

logger = logging.getLogger("materialhub.page_extraction")


def get_pages_to_extract(material_type: str, total_pages: int, material_name: str = None) -> List[Dict[str, any]]:
    """
    根据材料类型和总页数，返回需要提取的页面列表

    Args:
        material_type: 材料类型
        total_pages: PDF总页数
        material_name: 材料名称（用于某些类型作为section名称）

    Returns:
        页面提取配置列表，每项包含：
        - page_num: 页码（从0开始，-1表示最后一页）
        - section: Material.section字段值
        - material_type: Material.material_type字段值
        - title_suffix: 标题后缀
    """

    if total_pages <= 0:
        return []

    pages_config = []

    # 1. 合同类 - 首页 + 签字页（使用合同全名作为section）
    if material_type == "contract":
        contract_section = material_name if material_name else "合同"

        pages_config.append({
            "page_num": 0,
            "section": contract_section,
            "material_type": "contract_first_page",
            "title_suffix": "首页"
        })
        if total_pages > 1:
            pages_config.append({
                "page_num": -1,
                "section": contract_section,
                "material_type": "contract_signature_page",
                "title_suffix": "签字页"
            })

    # 2. 公司资质证书 - 提取所有页（通常1-2页）
    elif material_type == "company_qualification":
        if total_pages == 1:
            pages_config.append({
                "page_num": 0,
                "section": "资质证书",
                "material_type": "qualification_page",
                "title_suffix": "证书"
            })
        elif total_pages == 2:
            pages_config.append({
                "page_num": 0,
                "section": "资质证书正面",
                "material_type": "qualification_front_page",
                "title_suffix": "证书正面"
            })
            pages_config.append({
                "page_num": 1,
                "section": "资质证书背面",
                "material_type": "qualification_back_page",
                "title_suffix": "证书背面"
            })
        else:
            # 多页资质证书，提取前2页
            pages_config.append({
                "page_num": 0,
                "section": "资质证书首页",
                "material_type": "qualification_first_page",
                "title_suffix": "首页"
            })
            pages_config.append({
                "page_num": 1,
                "section": "资质证书第二页",
                "material_type": "qualification_second_page",
                "title_suffix": "第二页"
            })

    # 3. 营业执照 - 通常只有1页，提取完整
    elif material_type == "company_business":
        pages_config.append({
            "page_num": 0,
            "section": "营业执照",
            "material_type": "business_license_page",
            "title_suffix": "营业执照"
        })
        if total_pages > 1:
            # 如果有多页（比如法人证明等），提取第二页
            pages_config.append({
                "page_num": 1,
                "section": "工商信息附页",
                "material_type": "business_attachment_page",
                "title_suffix": "附页"
            })

    # 4. ISO认证证书 - 提取前1-2页
    elif material_type == "iso_certificate":
        pages_config.append({
            "page_num": 0,
            "section": "ISO认证证书",
            "material_type": "iso_cert_page",
            "title_suffix": "认证证书"
        })
        if total_pages > 1:
            pages_config.append({
                "page_num": 1,
                "section": "ISO认证附录",
                "material_type": "iso_cert_appendix_page",
                "title_suffix": "认证附录"
            })

    # 5. 员工证件 - 根据页数判断
    elif material_type == "employee_document":
        if total_pages == 1:
            pages_config.append({
                "page_num": 0,
                "section": "员工证件",
                "material_type": "employee_cert_page",
                "title_suffix": "证件"
            })
        elif total_pages == 2:
            # 可能是身份证正反面，或证书正反面
            pages_config.append({
                "page_num": 0,
                "section": "员工证件正面",
                "material_type": "employee_cert_front_page",
                "title_suffix": "证件正面"
            })
            pages_config.append({
                "page_num": 1,
                "section": "员工证件反面",
                "material_type": "employee_cert_back_page",
                "title_suffix": "证件反面"
            })
        else:
            # 多页证件，提取前2页
            pages_config.append({
                "page_num": 0,
                "section": "员工证件第一页",
                "material_type": "employee_cert_page_1",
                "title_suffix": "第一页"
            })
            pages_config.append({
                "page_num": 1,
                "section": "员工证件第二页",
                "material_type": "employee_cert_page_2",
                "title_suffix": "第二页"
            })

    # 6. 项目业绩 - 类似合同，首页 + 签字页（使用项目名称作为section）
    elif material_type == "project_performance":
        performance_section = material_name if material_name else "项目业绩"

        pages_config.append({
            "page_num": 0,
            "section": performance_section,
            "material_type": "performance_first_page",
            "title_suffix": "首页"
        })
        if total_pages > 1:
            pages_config.append({
                "page_num": -1,
                "section": performance_section,
                "material_type": "performance_signature_page",
                "title_suffix": "签字页"
            })

    # 7. 财务票据 - 通常只有1页
    elif material_type == "financial_document":
        pages_config.append({
            "page_num": 0,
            "section": "财务票据",
            "material_type": "financial_page",
            "title_suffix": "票据"
        })

    # 8. 其他类型 - 保守策略，只提取首页
    elif material_type == "other":
        pages_config.append({
            "page_num": 0,
            "section": "文档首页",
            "material_type": "other_first_page",
            "title_suffix": "首页"
        })

    logger.info(f"材料类型: {material_type}, 总页数: {total_pages}, 计划提取: {len(pages_config)} 页")
    return pages_config
