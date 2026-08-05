"""
Seed data for DMS: default folder structure and document types.
Runs on first startup when tables are empty.
"""

import json
import logging
from dms_models import get_dms_session, Folder, DocType

logger = logging.getLogger("materialhub.seed_data")


def seed_folders():
    """Create default folder hierarchy if folders table is empty."""
    with get_dms_session() as session:
        if session.query(Folder).count() > 0:
            logger.info("Folders already exist, skipping seed")
            return

        logger.info("Seeding default folder structure...")

        def create_folder(name, parent=None, sort_order=0, description=None):
            f = Folder(
                name=name,
                parent_id=parent.id if parent else None,
                description=description,
                sort_order=sort_order,
            )
            # Compute path manually since parent relationship may not be loaded
            if parent:
                f.path = f"{parent.path}{Folder._slugify_static(name)}/"
            else:
                f.path = f"/{Folder._slugify_static(name)}/"
            session.add(f)
            session.flush()
            return f

        # Use a simple slugify inline since we need it before the ORM relationship loads
        def slugify(name):
            import re
            slug = name.strip().lower()
            slug = re.sub(r'[^\w\u4e00-\u9fff-]', '-', slug)
            slug = re.sub(r'-+', '-', slug).strip('-')
            return slug or 'untitled'

        def make_folder(name, parent=None, sort_order=0, description=None):
            f = Folder(
                name=name,
                parent_id=parent.id if parent else None,
                description=description,
                sort_order=sort_order,
            )
            parent_path = parent.path if parent else ""
            f.path = f"{parent_path}{slugify(name)}/"
            if not f.path.startswith("/"):
                f.path = f"/{slugify(name)}/"
            session.add(f)
            session.flush()
            return f

        # Root folders
        company = make_folder("公司资质", sort_order=1, description="公司级资质证照材料")
        personnel = make_folder("人员资质", sort_order=2, description="人员资质证书材料")
        project = make_folder("业绩材料", sort_order=3, description="项目业绩相关材料")
        bid = make_folder("投标文件", sort_order=4, description="投标/响应文件")

        # Company subfolders
        make_folder("营业执照", parent=company, sort_order=1)
        make_folder("资质证书", parent=company, sort_order=2)
        make_folder("ISO认证", parent=company, sort_order=3)
        make_folder("荣誉奖项", parent=company, sort_order=4)

        # Personnel subfolders
        make_folder("身份证件", parent=personnel, sort_order=1)
        make_folder("学历证书", parent=personnel, sort_order=2)
        make_folder("职称证书", parent=personnel, sort_order=3)
        make_folder("职业资格", parent=personnel, sort_order=4)

        # Project subfolders
        make_folder("合同", parent=project, sort_order=1)
        make_folder("验收报告", parent=project, sort_order=2)

        # Bid subfolders
        make_folder("进行中", parent=bid, sort_order=1)
        make_folder("已归档", parent=bid, sort_order=2)

        # Additional company subfolders
        make_folder("授权文件", parent=company, sort_order=5)
        make_folder("产品资料", parent=company, sort_order=6)
        make_folder("公司简介", parent=company, sort_order=7)

        # Additional personnel subfolders (none needed)

        # Additional project subfolders
        make_folder("发票", parent=project, sort_order=3)
        make_folder("技术文档", parent=project, sort_order=4)

        session.commit()
        logger.info("Seeded %d folders", session.query(Folder).count())


def seed_doc_types():
    """Create default document types if doc_types table is empty."""
    with get_dms_session() as session:
        if session.query(DocType).count() > 0:
            logger.info("DocTypes already exist, skipping seed")
            return

        logger.info("Seeding default document types...")

        doc_types = [
            {
                "name": "营业执照",
                "code": "business-license",
                "category": "company",
                "icon": "building",
                "description": "企业营业执照",
                "metadata_schema": [
                    {"key": "registration_number", "type": "string", "label": "注册号"},
                    {"key": "legal_person", "type": "string", "label": "法定代表人"},
                    {"key": "registered_capital", "type": "string", "label": "注册资本"},
                    {"key": "business_scope", "type": "text", "label": "经营范围"},
                    {"key": "issue_date", "type": "date", "label": "发证日期"},
                    {"key": "valid_to", "type": "date", "label": "有效期至"},
                ],
            },
            {
                "name": "资质证书",
                "code": "qualification-cert",
                "category": "company",
                "icon": "award",
                "description": "企业资质等级证书",
                "metadata_schema": [
                    {"key": "cert_number", "type": "string", "label": "证书编号"},
                    {"key": "cert_level", "type": "string", "label": "资质等级"},
                    {"key": "issuing_authority", "type": "string", "label": "发证机关"},
                    {"key": "valid_from", "type": "date", "label": "有效期起"},
                    {"key": "valid_to", "type": "date", "label": "有效期止"},
                ],
            },
            {
                "name": "ISO认证",
                "code": "iso-cert",
                "category": "company",
                "icon": "check-circle",
                "description": "ISO体系认证证书",
                "metadata_schema": [
                    {"key": "cert_number", "type": "string", "label": "证书编号"},
                    {"key": "standard", "type": "string", "label": "认证标准"},
                    {"key": "scope", "type": "text", "label": "认证范围"},
                    {"key": "issuing_authority", "type": "string", "label": "认证机构"},
                    {"key": "valid_from", "type": "date", "label": "有效期起"},
                    {"key": "valid_to", "type": "date", "label": "有效期止"},
                ],
            },
            {
                "name": "荣誉奖项",
                "code": "honor-award",
                "category": "company",
                "icon": "trophy",
                "description": "企业荣誉证书和奖项",
                "metadata_schema": [
                    {"key": "award_name", "type": "string", "label": "奖项名称"},
                    {"key": "issuing_authority", "type": "string", "label": "颁发机构"},
                    {"key": "award_date", "type": "date", "label": "获奖日期"},
                    {"key": "level", "type": "string", "label": "奖项级别"},
                ],
            },
            {
                "name": "身份证",
                "code": "id-card",
                "category": "personnel",
                "icon": "user",
                "description": "人员身份证件",
                "metadata_schema": [
                    {"key": "id_number", "type": "string", "label": "身份证号"},
                    {"key": "gender", "type": "string", "label": "性别"},
                    {"key": "birth_date", "type": "date", "label": "出生日期"},
                    {"key": "address", "type": "string", "label": "住址"},
                ],
            },
            {
                "name": "学历证书",
                "code": "education-cert",
                "category": "personnel",
                "icon": "graduation-cap",
                "description": "学历学位证书",
                "metadata_schema": [
                    {"key": "school", "type": "string", "label": "毕业院校"},
                    {"key": "major", "type": "string", "label": "专业"},
                    {"key": "degree", "type": "string", "label": "学位"},
                    {"key": "graduation_date", "type": "date", "label": "毕业日期"},
                ],
            },
            {
                "name": "职称证书",
                "code": "professional-cert",
                "category": "personnel",
                "icon": "briefcase",
                "description": "专业技术职称证书",
                "metadata_schema": [
                    {"key": "cert_name", "type": "string", "label": "证书名称"},
                    {"key": "cert_number", "type": "string", "label": "证书编号"},
                    {"key": "cert_level", "type": "string", "label": "职称级别"},
                    {"key": "issuing_authority", "type": "string", "label": "发证机关"},
                    {"key": "valid_from", "type": "date", "label": "有效期起"},
                    {"key": "valid_to", "type": "date", "label": "有效期止"},
                ],
            },
            {
                "name": "合同",
                "code": "contract",
                "category": "project",
                "icon": "file-text",
                "description": "项目合同",
                "metadata_schema": [
                    {"key": "contract_number", "type": "string", "label": "合同编号"},
                    {"key": "party_a", "type": "string", "label": "甲方"},
                    {"key": "party_b", "type": "string", "label": "乙方"},
                    {"key": "contract_amount", "type": "string", "label": "合同金额"},
                    {"key": "sign_date", "type": "date", "label": "签订日期"},
                    {"key": "start_date", "type": "date", "label": "开始日期"},
                    {"key": "end_date", "type": "date", "label": "结束日期"},
                ],
            },
            {
                "name": "验收报告",
                "code": "acceptance-report",
                "category": "project",
                "icon": "clipboard-check",
                "description": "项目验收报告",
                "metadata_schema": [
                    {"key": "project_name", "type": "string", "label": "项目名称"},
                    {"key": "acceptance_date", "type": "date", "label": "验收日期"},
                    {"key": "acceptance_result", "type": "string", "label": "验收结论"},
                    {"key": "participants", "type": "text", "label": "参与人员"},
                ],
            },
            {
                "name": "投标文件",
                "code": "bid-document",
                "category": "bid",
                "icon": "file-badge",
                "description": "投标/响应文件",
                "metadata_schema": [
                    {"key": "project_name", "type": "string", "label": "项目名称"},
                    {"key": "bid_number", "type": "string", "label": "招标编号"},
                    {"key": "submission_date", "type": "date", "label": "递交日期"},
                    {"key": "bid_amount", "type": "string", "label": "投标报价"},
                    {"key": "result", "type": "string", "label": "中标结果"},
                ],
            },
            {
                "name": "授权文件",
                "code": "authorization",
                "category": "company",
                "icon": "stamp",
                "description": "授权书、委托书、代理证明",
                "metadata_schema": [
                    {"key": "authorization_type", "type": "string", "label": "授权类型"},
                    {"key": "authorizer", "type": "string", "label": "授权方"},
                    {"key": "authorized_party", "type": "string", "label": "被授权方"},
                    {"key": "scope", "type": "text", "label": "授权范围"},
                    {"key": "valid_from", "type": "date", "label": "有效期起"},
                    {"key": "valid_to", "type": "date", "label": "有效期止"},
                ],
            },
            {
                "name": "发票",
                "code": "invoice",
                "category": "project",
                "icon": "receipt",
                "description": "发票、收据",
                "metadata_schema": [
                    {"key": "invoice_number", "type": "string", "label": "发票号码"},
                    {"key": "amount", "type": "string", "label": "金额"},
                    {"key": "buyer", "type": "string", "label": "购方"},
                    {"key": "seller", "type": "string", "label": "销方"},
                    {"key": "invoice_date", "type": "date", "label": "开票日期"},
                ],
            },
            {
                "name": "产品资料",
                "code": "product-brochure",
                "category": "company",
                "icon": "package",
                "description": "产品说明书、产品手册、技术参数表",
                "metadata_schema": [
                    {"key": "product_name", "type": "string", "label": "产品名称"},
                    {"key": "manufacturer", "type": "string", "label": "生产厂商"},
                    {"key": "model", "type": "string", "label": "型号规格"},
                    {"key": "version", "type": "string", "label": "版本"},
                ],
            },
            {
                "name": "公司简介",
                "code": "company-profile",
                "category": "company",
                "icon": "building-2",
                "description": "公司简介、企业宣传册",
                "metadata_schema": [
                    {"key": "company_name", "type": "string", "label": "公司名称"},
                    {"key": "industry", "type": "string", "label": "行业领域"},
                    {"key": "established_date", "type": "date", "label": "成立日期"},
                ],
            },
            {
                "name": "技术文档",
                "code": "technical-doc",
                "category": "project",
                "icon": "file-code",
                "description": "技术方案、实施方案、技术文档",
                "metadata_schema": [
                    {"key": "doc_title", "type": "string", "label": "文档标题"},
                    {"key": "project_name", "type": "string", "label": "项目名称"},
                    {"key": "version", "type": "string", "label": "版本号"},
                    {"key": "author", "type": "string", "label": "编写人"},
                ],
            },
        ]

        for dt_data in doc_types:
            dt = DocType(
                name=dt_data["name"],
                code=dt_data["code"],
                category=dt_data["category"],
                icon=dt_data.get("icon"),
                description=dt_data.get("description"),
                metadata_schema=json.dumps(dt_data["metadata_schema"], ensure_ascii=False),
                is_system=True,
            )
            session.add(dt)

        session.commit()
        logger.info("Seeded %d document types", len(doc_types))


def ensure_new_types():
    """Add any missing DocTypes and Folders that were added after initial seed.
    Safe to call on every startup — only inserts what's missing."""
    with get_dms_session() as session:
        # New folders to ensure exist (parent_name -> list of child names)
        folder_additions = {
            "公司资质": ["授权文件", "产品资料", "公司简介", "审计报告", "完税证明", "服务网点证明"],
            "人员资质": ["社保证明"],
            "业绩材料": ["发票", "技术文档", "进账凭证"],
            "投标文件": ["投标保证金"],
        }
        for parent_name, children in folder_additions.items():
            parent = session.query(Folder).filter(Folder.name == parent_name, Folder.parent_id == None).first()
            if not parent:
                continue
            existing_children = {f.name for f in session.query(Folder).filter(Folder.parent_id == parent.id).all()}
            max_sort = session.query(Folder).filter(Folder.parent_id == parent.id).count()
            for child_name in children:
                if child_name not in existing_children:
                    import re
                    slug = child_name.strip().lower()
                    slug = re.sub(r'[^\w\u4e00-\u9fff-]', '-', slug)
                    slug = re.sub(r'-+', '-', slug).strip('-') or 'untitled'
                    max_sort += 1
                    f = Folder(
                        name=child_name,
                        parent_id=parent.id,
                        sort_order=max_sort,
                    )
                    f.path = f"{parent.path}{slug}/"
                    session.add(f)
                    logger.info(f"Added missing folder: {f.path}")

        # New DocTypes to ensure exist
        new_doc_types = [
            {"name": "授权文件", "code": "authorization", "category": "company", "icon": "stamp",
             "description": "授权书、委托书、代理证明", "metadata_schema": [
                {"key": "authorization_type", "type": "string", "label": "授权类型"},
                {"key": "authorizer", "type": "string", "label": "授权方"},
                {"key": "authorized_party", "type": "string", "label": "被授权方"},
             ]},
            {"name": "发票", "code": "invoice", "category": "project", "icon": "receipt",
             "description": "发票、收据", "metadata_schema": [
                {"key": "invoice_number", "type": "string", "label": "发票号码"},
                {"key": "amount", "type": "string", "label": "金额"},
             ]},
            {"name": "产品资料", "code": "product-brochure", "category": "company", "icon": "package",
             "description": "产品说明书、产品手册、技术参数表", "metadata_schema": [
                {"key": "product_name", "type": "string", "label": "产品名称"},
                {"key": "manufacturer", "type": "string", "label": "生产厂商"},
                {"key": "model", "type": "string", "label": "型号规格"},
             ]},
            {"name": "公司简介", "code": "company-profile", "category": "company", "icon": "building-2",
             "description": "公司简介、企业宣传册", "metadata_schema": [
                {"key": "company_name", "type": "string", "label": "公司名称"},
                {"key": "industry", "type": "string", "label": "行业领域"},
             ]},
            {"name": "技术文档", "code": "technical-doc", "category": "project", "icon": "file-code",
             "description": "技术方案、实施方案、技术文档", "metadata_schema": [
                {"key": "doc_title", "type": "string", "label": "文档标题"},
                {"key": "project_name", "type": "string", "label": "项目名称"},
             ]},
            {"name": "审计报告", "code": "audit-report", "category": "company", "icon": "file-text",
             "description": "财务审计报告、验资报告（多页复合文档，整体复用）", "metadata_schema": [
                {"key": "report_type", "type": "string", "label": "报告类型"},
                {"key": "period", "type": "string", "label": "报告期间"},
                {"key": "issuer", "type": "string", "label": "出具机构"},
            ]},
            # ── 资格必查/评分材料（SmartBid TYPECODE_EXPANSION_20260805）──
            {"name": "银行进账凭证", "code": "bank-receipt", "category": "project", "icon": "credit-card",
             "description": "业绩三件套之一：合同+银行进账凭证+发票的银行进账佐证", "metadata_schema": [
                {"key": "payee", "type": "string", "label": "收款方"},
                {"key": "payer", "type": "string", "label": "付款方"},
                {"key": "amount", "type": "string", "label": "进账金额"},
                {"key": "receipt_date", "type": "date", "label": "到账日期"},
                {"key": "contract_number", "type": "string", "label": "关联合同编号"},
                {"key": "voucher_number", "type": "string", "label": "银行回单号"},
            ]},
            {"name": "社保证明", "code": "social-insurance", "category": "personnel", "icon": "shield",
             "description": "授权代表/团队人员连续缴纳社保证明（资格必查）", "metadata_schema": [
                {"key": "name", "type": "string", "label": "参保人"},
                {"key": "company_name", "type": "string", "label": "缴纳单位"},
                {"key": "social_security_agency", "type": "string", "label": "社保经办机构"},
                {"key": "insurance_type", "type": "string", "label": "险种"},
                {"key": "consecutive_months", "type": "string", "label": "连续缴纳月数"},
                {"key": "payment_base", "type": "string", "label": "缴纳基数"},
            ]},
            {"name": "完税证明", "code": "tax-payment", "category": "company", "icon": "landmark",
             "description": "完税/纳税证明（实际缴税记录，区别于纳税信用A级证书）", "metadata_schema": [
                {"key": "taxpayer", "type": "string", "label": "纳税人"},
                {"key": "tax_type", "type": "string", "label": "税种"},
                {"key": "tax_period", "type": "string", "label": "税款所属期"},
                {"key": "tax_amount", "type": "string", "label": "实缴税额"},
                {"key": "tax_authority", "type": "string", "label": "主管税务机关"},
            ]},
            {"name": "投标保证金", "code": "bid-bond", "category": "bid", "icon": "lock",
             "description": "投标保证金缴纳证明（资格必查，未交直接废标）", "metadata_schema": [
                {"key": "bidder_name", "type": "string", "label": "投标人"},
                {"key": "payee", "type": "string", "label": "收款方(采购代理)"},
                {"key": "amount", "type": "string", "label": "保证金金额"},
                {"key": "payment_date", "type": "date", "label": "到账时间"},
                {"key": "voucher_number", "type": "string", "label": "银行回单号"},
                {"key": "tender_project", "type": "string", "label": "招标项目"},
            ]},
            {"name": "服务网点证明", "code": "service-point-proof", "category": "company", "icon": "map-pin",
             "description": "本地服务网点证明（租赁合同/营业执照/产权，服务网点评分项）", "metadata_schema": [
                {"key": "company_name", "type": "string", "label": "投标主体"},
                {"key": "branch", "type": "string", "label": "网点/分公司"},
                {"key": "service_address", "type": "string", "label": "网点地址"},
                {"key": "lease_period", "type": "string", "label": "租赁期限"},
                {"key": "contact_person", "type": "string", "label": "联系人"},
                {"key": "contact_phone", "type": "string", "label": "联系电话"},
            ]},
        ]
        existing_codes = {dt.code for dt in session.query(DocType).all()}
        for dt_data in new_doc_types:
            if dt_data["code"] not in existing_codes:
                dt = DocType(
                    name=dt_data["name"],
                    code=dt_data["code"],
                    category=dt_data["category"],
                    icon=dt_data.get("icon"),
                    description=dt_data.get("description"),
                    metadata_schema=json.dumps(dt_data["metadata_schema"], ensure_ascii=False),
                    is_system=True,
                )
                session.add(dt)
                logger.info(f"Added missing DocType: {dt_data['code']}")

        session.commit()


def seed_all():
    """Run all seed functions."""
    seed_folders()
    seed_doc_types()
    ensure_new_types()
