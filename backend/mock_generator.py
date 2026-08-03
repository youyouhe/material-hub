"""
Mock Document Generator — generates realistic mock data and PNG images
for document types defined in the DMS schema.

Integrated into the chat agent as `generate_mock_document` tool.
"""

import io
import json
import logging
import os
import random
import secrets
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

logger = logging.getLogger("materialhub.mock_generator")

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
MOCK_DIR = DATA_DIR / "dms_files" / "mock"
MOCK_DIR.mkdir(parents=True, exist_ok=True)

_TRUE_VALUES = ("true", "1", "yes", "on")


def is_mock_enabled() -> bool:
    """Check whether mock document generation is enabled.

    DB setting (dms_system_settings.mock_enabled) takes precedence;
    falls back to MOCK_ENABLED env var; defaults to disabled.
    """
    try:
        from dms_models import get_setting
        val = get_setting("mock_enabled")
        if val is not None:
            return val.strip().lower() in _TRUE_VALUES
    except Exception:
        pass
    return os.getenv("MOCK_ENABLED", "false").strip().lower() in _TRUE_VALUES

# ── Chinese resource pools ────────────────────────────────────────────

_SURNAMES = ["王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴",
             "徐", "孙", "马", "朱", "胡", "郭", "何", "高", "林", "罗"]
_GIVEN_NAMES = ["伟", "芳", "娜", "秀英", "敏", "静", "丽", "强", "磊", "洋",
                "勇", "艳", "杰", "娟", "涛", "明", "超", "秀兰", "霞", "平",
                "刚", "桂英", "文", "华", "飞", "玉兰", "斌", "玲", "军", "建华"]
_CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "西安", "重庆"]
_PROVINCES = ["北京市", "上海市", "广东省", "浙江省", "四川省", "湖北省", "江苏省", "陕西省"]
_DISTRICTS = ["朝阳区", "海淀区", "浦东新区", "天河区", "南山区", "西湖区", "武侯区", "洪山区", "鼓楼区", "雁塔区"]
_STREETS = ["中关村大街", "长安街", "南京路", "天河路", "深南大道", "湖滨路", "人民南路", "珞喻路", "中山路", "科技路"]
_COMPANY_SUFFIXES = ["科技有限公司", "信息技术有限公司", "网络科技有限公司", "软件有限公司",
                     "智能科技有限公司", "数据服务有限公司", "云计算有限公司", "系统工程有限公司"]
_COMPANY_PREFIXES = ["恒远", "中科", "华信", "鼎新", "锐思", "博雅", "启明", "珞信",
                     "通达", "智联", "云端", "星辰", "瀚海", "银河", "东方", "先锋"]
_INDUSTRIES = ["信息技术服务", "软件开发", "系统集成", "云计算与大数据", "人工智能",
               "物联网", "信息安全", "通信工程", "智能制造", "数字政务"]
_PROJECT_TYPES = ["智慧城市", "数字政务", "智慧园区", "智慧医疗", "智慧教育",
                  "智慧交通", "工业互联网", "数据中心", "网络安全", "云平台"]
_CERT_STANDARDS = {
    "iso-cert": ["ISO 9001:2015", "ISO 14001:2015", "ISO 27001:2022", "ISO 45001:2018",
                 "ISO 20000-1:2018", "ISO 22301:2019"],
    "qualification-cert": ["计算机信息系统集成一级", "计算机信息系统集成二级",
                           "电子与智能化工程专业承包一级", "建筑智能化系统设计专项甲级",
                           "CMMI 5级", "CMMI 3级", "国家高新技术企业"],
    "professional-cert": ["高级工程师", "中级工程师", "PMP项目管理", "信息系统项目管理师",
                          "系统架构设计师", "网络规划设计师", "注册建造师一级", "注册会计师"],
}
_CERT_ISSUERS = {
    "iso-cert": ["中国质量认证中心", "方圆标志认证集团", "SGS通标标准技术服务有限公司",
                 "BSI英标管理体系认证", "TÜV莱茵"],
    "qualification-cert": ["住房和城乡建设部", "工业和信息化部", "中国电子信息行业联合会",
                           "中国软件行业协会"],
    "professional-cert": ["人力资源和社会保障部", "工业和信息化部教育与考试中心",
                          "PMI项目管理协会"],
}
_AWARD_NAMES = ["国家科技进步奖", "省部级科技进步一等奖", "优秀软件产品奖",
                "科技创新企业", "信息技术应用创新优秀产品", "数字经济领军企业"]
_DEGREES = ["学士", "硕士", "博士"]
_MAJORS = ["计算机科学与技术", "软件工程", "信息管理与信息系统", "电子信息工程",
           "通信工程", "自动化", "网络工程", "信息安全", "数据科学与大数据技术", "人工智能"]
_SCHOOLS = ["清华大学", "北京大学", "浙江大学", "上海交通大学", "南京大学",
            "华中科技大学", "武汉大学", "西安交通大学", "哈尔滨工业大学", "北京航空航天大学"]

# ── Font discovery ────────────────────────────────────────────────────

def _find_chinese_font() -> Optional[ImageFont.FreeTypeFont]:
    """Find a Chinese-capable TrueType font on the system."""
    import subprocess
    candidates = [
        # Linux
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        # Windows
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, 18)
            except Exception:
                continue
    # Fallback: try fc-list
    try:
        result = subprocess.run(
            ["fc-list", ":lang=zh", "-f", "%{file}\n"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                try:
                    return ImageFont.truetype(line.strip(), 18)
                except Exception:
                    continue
    except Exception:
        pass
    logger.warning("No Chinese font found — mock images will lack Chinese text")
    return None


_FONT = _find_chinese_font()
_FONT_SMALL = None
_FONT_LARGE = None
if _FONT:
    try:
        _FONT_SMALL = ImageFont.truetype(_FONT.path, 14)
        _FONT_LARGE = ImageFont.truetype(_FONT.path, 24)
    except Exception:
        _FONT_SMALL = _FONT
        _FONT_LARGE = _FONT


# ── Random data generators per doc type ───────────────────────────────

def _random_credit_code() -> str:
    """Generate a fake but format-valid 18-char unified social credit code."""
    return "91" + "".join(str(random.randint(0, 9)) for _ in range(16))


def _random_company_name() -> str:
    return random.choice(_COMPANY_PREFIXES) + random.choice(_COMPANY_SUFFIXES)


def _random_person_name() -> str:
    return random.choice(_SURNAMES) + random.choice(_GIVEN_NAMES)


def _random_cert_number(prefix: str = "") -> str:
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    suffix = "".join(random.choice(chars) for _ in range(12))
    return f"{prefix}{suffix}" if prefix else suffix


def _random_date(start_days_ago: int = 365, end_days_ahead: int = 1095) -> str:
    d = datetime.utcnow() + timedelta(days=random.randint(-start_days_ago, end_days_ahead))
    return d.strftime("%Y-%m-%d")


def _random_dates_valid() -> tuple:
    """Return (valid_from, valid_to) where valid_to is after valid_from."""
    valid_from = datetime.utcnow() - timedelta(days=random.randint(0, 730))
    valid_to = valid_from + timedelta(days=random.randint(365, 1825))
    return valid_from.strftime("%Y-%m-%d"), valid_to.strftime("%Y-%m-%d")


def _random_id_number() -> tuple:
    """Generate fake 18-digit ID number with gender and birth date."""
    # Area code (6 digits)
    area = str(random.randint(110101, 659004))
    # Birth date
    birth = datetime.utcnow() - timedelta(days=random.randint(22 * 365, 60 * 365))
    birth_str = birth.strftime("%Y%m%d")
    # Sequence + gender
    seq = str(random.randint(1, 999)).zfill(3)
    gender = "女" if int(seq[-1]) % 2 == 0 else "男"
    # Checksum placeholder
    checksum = str(random.randint(0, 9)) + "X" if random.random() < 0.1 else str(random.randint(0, 9))
    id_num = area + birth_str + seq + checksum
    return id_num, gender, birth.strftime("%Y-%m-%d")


def _random_address() -> str:
    return (random.choice(_PROVINCES) + random.choice(_CITIES).rstrip("市") + "市"
            + random.choice(_DISTRICTS) + random.choice(_STREETS)
            + str(random.randint(1, 500)) + "号")


def _random_amount() -> str:
    """Amount in 万元."""
    amounts = [50, 80, 100, 150, 200, 280, 350, 500, 680, 800, 1000, 1500, 2000, 3000, 5000]
    return f"{random.choice(amounts)}万元"


def _random_scope() -> str:
    scopes = [
        "计算机软件技术开发、技术咨询、技术服务、技术转让",
        "计算机系统集成;数据处理;基础软件服务、应用软件服务",
        "计算机信息系统安全专用产品销售;互联网信息服务",
        "技术开发、技术推广、技术转让、技术咨询、技术服务",
        "计算机软硬件及辅助设备、电子产品、通讯设备的销售",
        "企业管理咨询;经济贸易咨询;市场调查;会议服务",
    ]
    k = random.randint(1, 3)
    return ";".join(random.sample(scopes, k))


MOCK_TEMPLATES: Dict[str, dict] = {
    "business-license": {
        "unified_social_credit_code": lambda: _random_credit_code(),
        "company_name": lambda: _random_company_name(),
        "legal_person": lambda: _random_person_name(),
        "registered_capital": lambda: f"{random.choice([100,200,500,1000,2000,5000,10000])}万元",
        "establishment_date": lambda: _random_date(5475, -1825),
        "business_scope": lambda: _random_scope(),
        "company_type": lambda: random.choice(["有限责任公司(自然人投资或控股)", "有限责任公司(法人独资)", "股份有限公司(非上市)", "其他有限责任公司"]),
        "address": lambda: _random_address(),
        "registration_authority": lambda: random.choice(["北京市市场监督管理局", "上海市市场监督管理局", "深圳市市场监督管理局", "杭州市市场监督管理局"]),
        "issue_date": lambda: _random_date(1095, 0),
        "valid_from": lambda: _random_dates_valid()[0],
        "valid_to": lambda: "2099-12-31",
        "business_term": lambda: "长期",
    },
    "qualification-cert": {
        "cert_name": lambda: random.choice(_CERT_STANDARDS["qualification-cert"]),
        "cert_number": lambda: _random_cert_number("Z"),
        "company_name": lambda: _random_company_name(),
        "cert_level": lambda: random.choice(["一级", "二级", "三级", "甲级", "乙级"]),
        "issuing_authority": lambda: random.choice(_CERT_ISSUERS["qualification-cert"]),
        "scope": lambda: "计算机信息系统集成、软件开发、运行维护及相关技术服务",
        "valid_from": lambda: _random_dates_valid()[0],
        "valid_to": lambda: _random_dates_valid()[1],
        "issue_date": lambda: _random_date(730, 0),
    },
    "iso-cert": {
        "cert_name": lambda: random.choice(["质量管理体系认证证书", "环境管理体系认证证书", "信息安全管理体系认证证书", "职业健康安全管理体系认证证书"]),
        "cert_number": lambda: _random_cert_number("016ZB"),
        "company_name": lambda: _random_company_name(),
        "standard": lambda: random.choice(_CERT_STANDARDS["iso-cert"]),
        "scope": lambda: _random_scope(),
        "issuing_authority": lambda: random.choice(_CERT_ISSUERS["iso-cert"]),
        "accreditation_body": lambda: random.choice(["CNAS", "UKAS", "ANAB"]),
        "issue_date": lambda: _random_dates_valid()[0],
        "valid_from": lambda: _random_dates_valid()[0],
        "valid_to": lambda: _random_dates_valid()[1],
    },
    "honor-award": {
        "award_name": lambda: random.choice(_AWARD_NAMES),
        "company_name": lambda: _random_company_name(),
        "award_category": lambda: random.choice(["科技进步奖", "创新产品奖", "优秀企业奖", "行业领军奖"]),
        "issuing_authority": lambda: random.choice(["科学技术部", "工业和信息化部", "中国软件行业协会", "省科技厅", "中国电子信息行业联合会"]),
        "award_date": lambda: _random_date(1095, 0),
        "level": lambda: random.choice(["国家级", "省部级", "市级", "行业级"]),
        "cert_number": lambda: _random_cert_number("AW"),
    },
    "audit-report": {
        "report_type": lambda: random.choice(["财务审计报告", "验资报告", "年度审计报告", "专项审计报告"]),
        "company_name": lambda: _random_company_name(),
        "period": lambda: f"{random.choice([2023, 2024, 2025])}年度",
        "issuer": lambda: random.choice(["普华永道中天会计师事务所", "德勤华永会计师事务所", "安永华明会计师事务所",
                                         "毕马威华振会计师事务所", "立信会计师事务所", "天健会计师事务所"]),
        "report_number": lambda: f"审字[{random.choice([2023,2024,2025])}]第{random.randint(1000,9999)}号",
        "audit_opinion": lambda: random.choice(["标准无保留意见", "无保留意见"]),
        "total_assets": lambda: _random_amount(),
        "net_profit": lambda: _random_amount(),
        "issue_date": lambda: _random_date(365, 0),
        "certified_public_accountant": lambda: _random_person_name() + "、" + _random_person_name(),
    },
    "id-card": {
        "name": lambda: _random_person_name(),
        "gender": lambda: _random_id_number()[1],
        "nationality": lambda: random.choice(["汉", "回", "满", "蒙古", "壮"]),
        "birth_date": lambda: _random_id_number()[2],
        "address": lambda: _random_address(),
        "id_number": lambda: _random_id_number()[0],
        "issuing_authority": lambda: random.choice(["北京市公安局朝阳分局", "上海市公安局浦东分局", "深圳市公安局南山分局"]),
        "valid_from": lambda: _random_date(3650, 0),
        "valid_to": lambda: _random_date(0, 7300),
    },
    "education-cert": {
        "name": lambda: _random_person_name(),
        "gender": lambda: random.choice(["男", "女"]),
        "birth_date": lambda: _random_date(10950, 7300),
        "education": lambda: random.choice(["本科", "硕士研究生", "博士研究生", "专科"]),
        "major": lambda: random.choice(_MAJORS),
        "school_name": lambda: random.choice(_SCHOOLS),
        "principal_name": lambda: _random_person_name(),
        "degree": lambda: random.choice(["工学学士", "理学学士", "管理学学士", "工学硕士", "理学硕士", "工学博士", "管理学博士"]),
        "degree_committee_chairman": lambda: _random_person_name(),
        "cert_name": lambda: "普通高等学校毕业证书",
        "cert_number": lambda: f"{random.randint(1000000,9999999)}{datetime.utcnow().year}{random.randint(10000,99999)}",
        "degree_cert_name": lambda: random.choice(["学士学位证书", "硕士学位证书", "博士学位证书"]),
        "degree_cert_number": lambda: f"{random.randint(100000,999999)}{datetime.utcnow().year}{random.randint(1000,9999)}",
        "issue_date": lambda: _random_date(3650, 0),
        "enrollment_date": lambda: _random_date(7300, 3650),
        "graduation_date": lambda: _random_date(3650, 0),
        "duration": lambda: str(random.choice([3, 4, 5])),
        "study_form": lambda: random.choice(["普通全日制", "成人高等教育", "网络教育", "自学考试"]),
        "education_category": lambda: random.choice(["普通高等教育", "成人高等教育"]),
        "academic_level": lambda: random.choice(["本科", "硕士研究生", "博士研究生"]),
        "graduation_status": lambda: "毕业",
        "query_website": lambda: "中国高等教育学生信息网(学信网)",
        "query_url": lambda: "https://www.chsi.com.cn",
    },
    "professional-cert": {
        "name": lambda: _random_person_name(),
        "gender": lambda: random.choice(["男", "女"]),
        "birth_date": lambda: _random_date(14600, 7300),
        "cert_name": lambda: random.choice(_CERT_STANDARDS["professional-cert"]),
        "cert_number": lambda: _random_cert_number(),
        "management_number": lambda: f"{random.randint(100000000000000,999999999999999)}",
        "cert_level": lambda: random.choice(["高级", "中级", "初级"]),
        "issuing_authority": lambda: random.choice(_CERT_ISSUERS["professional-cert"]),
        "issue_date": lambda: _random_date(1825, 0),
        "valid_from": lambda: _random_dates_valid()[0],
        "valid_to": lambda: _random_dates_valid()[1],
        "major": lambda: random.choice(_MAJORS),
    },
    "contract": {
        "contract_name": lambda: random.choice(["技术服务合同", "软件开发合同", "系统集成合同", "运维服务合同", "采购合同"]),
        "contract_number": lambda: f"HT-{datetime.utcnow().year}{random.randint(1000,9999)}",
        "party_a": lambda: random.choice(["XX市大数据管理局", "XX省信息中心", "XX区人民政府", "XX集团有限公司", "XX省政务服务中心"]),
        "party_a_address": lambda: _random_address(),
        "party_a_contact": lambda: _random_person_name(),
        "party_b": lambda: _random_company_name(),
        "party_b_address": lambda: _random_address(),
        "party_b_contact": lambda: _random_person_name(),
        "contract_amount": lambda: _random_amount(),
        "contract_amount_cn": lambda: random.choice(["伍拾万元整", "壹佰万元整", "贰佰万元整", "伍佰万元整", "捌佰万元整", "壹仟万元整"]),
        "project_name": lambda: random.choice(_PROJECT_TYPES) + random.choice(["平台建设项目", "系统开发项目", "运维服务项目", "升级改造项目"]),
        "project_description": lambda: "本项目旨在建设" + random.choice(_PROJECT_TYPES) + "，实现数据共享、业务协同和智能决策。",
        "sign_date": lambda: _random_date(730, 0),
        "start_date": lambda: _random_date(730, 365),
        "end_date": lambda: _random_date(0, 730),
        "performance_period": lambda: f"{random.choice([90,180,365,540,730])}天",
        "payment_terms": lambda: random.choice(["合同签订后支付30%，验收后支付70%", "按里程碑分期付款", "验收合格后一次性付清"]),
        "signing_location": lambda: random.choice(["北京市", "上海市", "深圳市", "杭州市", "成都市"]),
    },
    "acceptance-report": {
        "project_name": lambda: random.choice(_PROJECT_TYPES) + random.choice(["平台建设项目", "系统升级改造项目", "运维服务项目"]),
        "contract_number": lambda: f"HT-{datetime.utcnow().year}{random.randint(1000,9999)}",
        "company_name": lambda: _random_company_name(),
        "acceptance_date": lambda: _random_date(365, 0),
        "acceptance_result": lambda: random.choice(["验收合格", "验收通过", "终验合格"]),
        "acceptance_opinion": lambda: random.choice(["项目按合同要求完成全部建设内容，系统运行稳定，功能满足需求，同意通过验收。",
                                                    "项目按计划完成，各项指标达到合同约定标准，通过验收。"]),
        "acceptance_team_leader": lambda: _random_person_name(),
        "participants": lambda: "、".join([_random_person_name() for _ in range(random.randint(3, 6))]),
        "delivery_items": lambda: "系统软件、技术文档、培训资料、运维手册",
        "issues_found": lambda: "无",
        "rectification_required": lambda: "否",
    },
    "bid-document": {
        "project_name": lambda: random.choice(_PROJECT_TYPES) + random.choice(["平台建设项目", "系统开发项目", "运维服务项目"]),
        "bid_number": lambda: f"Z{datetime.utcnow().year}{random.randint(10000,99999)}",
        "bidder_name": lambda: _random_company_name(),
        "bid_amount": lambda: _random_amount(),
        "bid_amount_cn": lambda: random.choice(["壹佰万元整", "叁佰万元整", "伍佰万元整", "捌佰万元整", "壹仟贰佰万元整"]),
        "submission_date": lambda: _random_date(180, 0),
        "bid_validity": lambda: f"{random.choice([60, 90, 120])}天",
        "bid_bond": lambda: f"{random.choice([2,5,10,20])}万元",
        "contact_person": lambda: _random_person_name(),
        "contact_phone": lambda: f"1{random.randint(30,99)}{random.randint(10000000,99999999)}",
        "project_location": lambda: random.choice(["北京市朝阳区", "上海市浦东新区", "深圳市南山区", "杭州市西湖区", "成都市高新区"]),
        "construction_period": lambda: f"{random.choice([90, 180, 365, 540])}天",
        "quality_standard": lambda: "合格",
        "result": lambda: random.choice(["中标", "未中标", "评审中"]),
    },
    "authorization": {
        "authorization_type": lambda: random.choice(["法人授权委托书", "投标授权书", "项目授权书", "代理授权书", "法定代表人身份证明书"]),
        "authorizer": lambda: _random_company_name(),
        "authorizer_legal_person": lambda: _random_person_name(),
        "authorized_party": lambda: _random_person_name(),
        "authorized_person_id": lambda: _random_id_number()[0],
        "authorized_person_position": lambda: random.choice(["项目经理", "销售总监", "技术总监", "区域经理", "商务经理"]),
        "scope": lambda: "代表本公司参加" + random.choice(_PROJECT_TYPES) + "项目的投标活动，签署相关文件，处理与投标有关的一切事务。",
        "valid_from": lambda: _random_date(30, 0),
        "valid_to": lambda: _random_date(0, 180),
        "issue_date": lambda: _random_date(30, 0),
    },
    "invoice": {
        "invoice_number": lambda: f"{random.randint(10000000,99999999)}",
        "invoice_code": lambda: f"{random.randint(1000000000,9999999999)}",
        "invoice_type": lambda: random.choice(["增值税专用发票", "增值税普通发票", "电子发票"]),
        "invoice_date": lambda: _random_date(365, 0),
        "buyer": lambda: random.choice(["XX市大数据管理局", "XX省信息中心", "XX区人民政府", "XX集团有限公司"]),
        "buyer_tax_id": lambda: _random_credit_code(),
        "seller": lambda: _random_company_name(),
        "seller_tax_id": lambda: _random_credit_code(),
        "amount": lambda: f"¥{random.randint(1,500)},{random.randint(100,999)}.{random.randint(0,99):02d}",
        "amount_tax": lambda: f"¥{random.randint(10,50)},{random.randint(100,999)}.{random.randint(0,99):02d}",
        "amount_total": lambda: f"¥{random.randint(30,600)},{random.randint(100,999)}.{random.randint(0,99):02d}",
        "amount_cn": lambda: random.choice(["叁拾万元整", "伍拾万元整", "捌拾万元整", "壹佰万元整"]),
        "items": lambda: random.choice(["技术服务费", "软件开发费", "系统集成费", "咨询服务费"]),
        "payment_method": lambda: random.choice(["银行转账", "现金", "承兑汇票"]),
    },
    "product-brochure": {
        "product_name": lambda: random.choice(["智能运维管理平台", "数据中台系统", "AI文档分析引擎",
                                               "知识图谱平台", "智慧城市操作系统", "数字孪生引擎",
                                               "云计算管理平台", "大数据分析系统", "物联网管理平台"]),
        "manufacturer": lambda: _random_company_name(),
        "model": lambda: f"V{random.randint(1,9)}.{random.randint(0,9)}",
        "version": lambda: f"v{random.randint(1,9)}.{random.randint(0,9)}.{random.randint(0,9)}",
        "product_type": lambda: random.choice(["软件产品", "硬件设备", "解决方案", "云服务"]),
        "description": lambda: "本产品是一套完整的" + random.choice(["智能运维", "数据治理", "AI分析", "知识管理", "数字孪生"]) + "解决方案，采用微服务架构设计，支持高可用部署。",
        "features": lambda: "高性能、高可用、易扩展、安全可靠、智能化",
        "application_scenarios": lambda: random.choice(["政府数字化转型", "企业智能化升级", "智慧城市建设", "工业互联网"]),
        "certification": lambda: random.choice(["通过ISO 25051质量认证", "获国家信息安全等级保护三级", "通过CMMI 3级认证"]),
    },
    "company-profile": {
        "company_name": lambda: _random_company_name(),
        "company_name_en": lambda: random.choice(["Huaxin Technology Co., Ltd.", "Zhongke Data Service Co., Ltd.", "Dingxin Software Co., Ltd."]),
        "established_date": lambda: _random_date(7300, -1825),
        "registered_capital": lambda: f"{random.choice([500, 1000, 2000, 5000, 10000])}万元",
        "industry": lambda: random.choice(_INDUSTRIES),
        "company_type": lambda: random.choice(["有限责任公司", "股份有限公司", "其他有限责任公司"]),
        "legal_person": lambda: _random_person_name(),
        "address": lambda: _random_address(),
        "website": lambda: "www." + random.choice(_COMPANY_PREFIXES).lower() + ".com.cn",
        "employee_count": lambda: str(random.choice([50, 100, 200, 300, 500, 800, 1000])),
        "business_scope": lambda: _random_scope(),
        "core_business": lambda: random.choice(["政务信息化系统建设", "企业数字化转型", "人工智能平台研发", "大数据治理与分析"]),
        "certifications": lambda: random.choice(["ISO 9001质量管理体系认证", "ISO 27001信息安全管理体系认证", "CMMI 5级认证", "国家高新技术企业"]),
        "honors": lambda: random.choice(["国家科技进步二等奖", "省级专精特新企业", "中国软件行业百强企业"]),
        "introduction": lambda: "公司成立于2010年，是国内领先的" + random.choice(_INDUSTRIES) + "服务商，服务客户超过500家。",
    },
    "technical-doc": {
        "doc_title": lambda: random.choice(["系统总体设计方案", "技术实施方案", "接口规范说明书", "部署方案", "运维手册", "数据库设计文档"]),
        "project_name": lambda: random.choice(_PROJECT_TYPES) + random.choice(["平台建设项目", "系统开发项目"]),
        "version": lambda: f"V{random.randint(1,5)}.{random.randint(0,9)}",
        "author": lambda: _random_person_name(),
        "reviewer": lambda: _random_person_name(),
        "approver": lambda: _random_person_name(),
        "creation_date": lambda: _random_date(365, 0),
        "doc_type": lambda: random.choice(["技术方案", "设计文档", "用户手册", "测试报告"]),
        "confidentiality_level": lambda: random.choice(["内部", "秘密", "机密", "公开"]),
        "description": lambda: "本文档详细描述了" + random.choice(_PROJECT_TYPES) + "项目的技术方案和实现细节。",
        "tech_stack": lambda: random.choice(["Java/Spring Cloud/MySQL/Redis", "Python/FastAPI/PostgreSQL", "Go/Kubernetes/Docker", "React/Node.js/MongoDB"]),
    },
}


# ── requirement_text-driven content overrides ──────────────────────────
# Deterministic keyword matching: if requirement_text contains a known cert
# name / project domain keyword, use it verbatim instead of the random pool.
# This lets qualification-cert/contract content track what the tender
# actually asked for, instead of always drawing the same random sample.

_QUALIFICATION_CERT_KEYWORDS = [
    "纳税信用A级证书", "纳税信用A级", "CQC节能认证", "CEC环境标志认证", "环境标志认证",
    "发明专利", "实用新型专利", "标准制定证明", "参编标准证明",
    "计算机信息系统集成一级", "计算机信息系统集成二级",
    "电子与智能化工程专业承包一级", "建筑智能化系统设计专项甲级",
    "CMMI 5级", "CMMI 3级", "国家高新技术企业", "高新技术企业",
    "安全生产许可证", "守合同重信用企业",
]

_CONTRACT_PROJECT_KEYWORDS = [
    "教学管理系统", "智慧教育", "智慧医疗", "智慧交通", "智慧园区", "智慧城市",
    "数字政务", "工业互联网", "数据中心", "网络安全", "云平台", "大数据平台",
    "物联网", "人工智能", "电子政务", "OA系统", "ERP系统", "财务管理系统",
    "人事管理系统", "档案管理系统", "客户关系管理系统", "供应链管理系统",
]


def _extract_requirement_overrides(doc_type_code: str, requirement_text: Optional[str]) -> dict:
    """Best-effort deterministic extraction of content hints from requirement_text.

    Returns a dict of field overrides to apply on top of the random template.
    Falls back to no overrides (keep random content) when nothing matches —
    this is a heuristic, not a guarantee, so an empty dict is a valid outcome.
    """
    if not requirement_text:
        return {}

    overrides = {}

    if doc_type_code == "qualification-cert":
        for kw in _QUALIFICATION_CERT_KEYWORDS:
            if kw in requirement_text:
                overrides["cert_name"] = kw
                break

    if doc_type_code == "contract":
        for kw in _CONTRACT_PROJECT_KEYWORDS:
            if kw in requirement_text:
                overrides["project_name"] = kw + random.choice(["销售合同", "服务合同", "建设合同", "采购合同"])
                overrides["project_description"] = f"本合同标的为{kw}项目的建设与实施，实现数据共享、业务协同和智能决策。"
                break

    return overrides


# ── LLM-driven content generation ───────────────────────────────────────
# Keyword matching (_extract_requirement_overrides above) is a brittle fallback:
# every new cert name / project domain needs a new hardcoded entry, and fields
# generated independently (e.g. invoice amount vs amount_total) never get
# cross-checked against each other. For doc types where this has repeatedly
# caused problems, try an LLM call first — it can do semantic matching against
# free-form requirement_text and keep multiple fields internally consistent in
# a single generation. Falls back to the deterministic/random path on any
# failure (timeout, bad JSON, missing provider config) so the endpoint never
# becomes unavailable because of the LLM.

# Fields the LLM is asked to fill per doc type, with a short field-purpose hint
# so the model knows what each key means without us hand-writing a full schema.
_LLM_CONTENT_FIELDS = {
    "qualification-cert": {
        "cert_name": "证书/资质名称，必须精确匹配招标要求原文里提到的证书名称",
        "cert_level": "资质等级（如：一级/二级/甲级/A级，若原文未提及等级则给出该证书常见的等级）",
        "issuing_authority": "该证书的真实发证机关名称（必须与证书类型匹配，如CQC认证的发证机关是中国质量认证中心）",
        "scope": "认证覆盖范围，简要描述",
    },
    "authorization": {
        "authorization_type": "授权文件类型（如：法定代表人授权委托书、投标授权书）",
        "scope": "授权范围，必须明确提到本次招标项目所属的具体业务领域/项目名称，不能是无关领域的套话",
        "authorized_person_position": "被授权人职务",
    },
    "invoice": {
        "items": "发票货物或服务名称，应与招标项目业务领域相关",
        "invoice_type": "发票类型",
    },
    "contract": {
        "project_name": "合同标的项目名称，必须体现招标要求原文中的具体业务领域",
        "project_description": "项目描述，简要说明建设内容，须与 project_name 一致",
        "contract_name": "合同名称类型（如：软件开发合同、销售合同）",
    },
}

_LLM_CONTENT_DOC_TYPES = frozenset(_LLM_CONTENT_FIELDS.keys())


def _llm_generate_content(
    doc_type_code: str,
    requirement_text: Optional[str],
    entity_known_attributes: dict,
) -> dict:
    """Ask the LLM to fill in the semantic content fields for one doc type.

    Returns {} on any failure — callers must treat this as a best-effort
    enhancement layer on top of the existing random/keyword generation,
    never as the sole source of a field.
    """
    fields = _LLM_CONTENT_FIELDS.get(doc_type_code)
    if not fields or not requirement_text:
        return {}

    try:
        from llm_provider import get_llm_provider
        llm = get_llm_provider()
    except Exception as e:
        logger.info("LLM content generation skipped (provider unavailable): %s", e)
        return {}

    field_lines = "\n".join(f'  - "{k}": {desc}' for k, desc in fields.items())
    known_lines = "\n".join(f"  - {k}: {v}" for k, v in entity_known_attributes.items() if v) or "  （无）"

    prompt = f"""你在为一份招标投标场景生成模拟测试文档的内容字段，仅用于系统测试演示。

文档类型：{doc_type_code}
招标要求原文：{requirement_text}

已知的实体真实属性（生成内容时必须与这些保持一致，不能编造矛盾信息）：
{known_lines}

请为以下字段生成合适的中文内容，要求：
1. 内容必须准确匹配"招标要求原文"里提到的具体名称/领域/术语，不能用无关的通用内容替代
2. 字段之间的信息必须互相一致（如果多个字段都涉及同一个项目/证书，必须是同一个）
3. 只返回 JSON，不要任何解释文字，不要用 markdown 代码块包裹

需要生成的字段：
{field_lines}

严格按此 JSON 格式返回：{{{", ".join(f'"{k}": "..."' for k in fields)}}}"""

    try:
        response = llm.chat([{"role": "user", "content": prompt}], temperature=0.3, max_tokens=800)
        json_text = response.strip()
        if "```json" in json_text:
            json_text = json_text.split("```json")[1].split("```")[0].strip()
        elif "```" in json_text:
            json_text = json_text.split("```")[1].split("```")[0].strip()
        result = json.loads(json_text)
        # Only accept the fields we asked for — never let the LLM inject arbitrary keys
        overrides = {k: v for k, v in result.items() if k in fields and v}
        if overrides:
            logger.info("LLM content generation for %s: %s", doc_type_code, list(overrides.keys()))
        return overrides
    except Exception as e:
        logger.warning("LLM content generation failed for %s, falling back: %s", doc_type_code, e)
        return {}


# ── Mock data generation ──────────────────────────────────────────────

def generate_mock_data(doc_type_code: str, entity_name: Optional[str] = None, person_name: Optional[str] = None) -> dict:
    """Generate mock metadata for a given document type code."""
    template = MOCK_TEMPLATES.get(doc_type_code)
    if not template:
        raise ValueError(f"No mock template for doc type: {doc_type_code}")

    data = {}
    for key, generator in template.items():
        data[key] = generator()

    # Override entity-related fields if entity_name is provided
    if entity_name:
        if doc_type_code in ("id-card", "education-cert", "professional-cert"):
            # Personnel doc types: entity_name IS the person's name
            data["name"] = entity_name
        elif "company_name" in template:
            data["company_name"] = entity_name
        elif "party_b" in template:
            data["party_b"] = entity_name
        elif "bidder_name" in template:
            data["bidder_name"] = entity_name
        elif "seller" in template:
            data["seller"] = entity_name
        elif "manufacturer" in template:
            data["manufacturer"] = entity_name
        elif "authorizer" in template:
            data["authorizer"] = entity_name

    # Override person name fields if person_name is provided
    if person_name:
        if doc_type_code == "business-license":
            data["legal_person"] = person_name
        elif doc_type_code == "company-profile":
            data["legal_person"] = person_name
        elif doc_type_code in ("id-card", "education-cert", "professional-cert"):
            data["name"] = person_name
        elif doc_type_code == "authorization":
            data["authorized_party"] = person_name

    # invoice: amount/amount_tax/amount_total are computed together so the
    # arithmetic always holds (previously each was an independent random draw,
    # so amount + amount_tax could land anywhere relative to amount_total).
    if doc_type_code == "invoice":
        data.update(_compute_invoice_amounts())

    return data


def _compute_invoice_amounts(tax_rate: float = 0.13) -> dict:
    """Compute a consistent (amount, amount_tax, amount_total, amount_cn) set.

    amount_total = amount + amount_tax, always — this is the exact
    relationship the GAPS_ROUND2 report flagged as broken. amount_cn (Chinese
    uppercase numerals) is derived from the same amount_total, fixing the
    GAPS_ROUND3 finding that amount_cn was an unrelated random pick.
    """
    base_amounts = [50000, 80000, 100000, 150000, 200000, 280000, 350000,
                     500000, 680000, 800000, 1000000]
    amount = random.choice(base_amounts) + random.randint(0, 9999) / 100
    amount_tax = round(amount * tax_rate, 2)
    amount_total = round(amount + amount_tax, 2)
    return {
        "amount": f"¥{amount:,.2f}",
        "amount_tax": f"¥{amount_tax:,.2f}",
        "amount_total": f"¥{amount_total:,.2f}",
        "amount_cn": _amount_to_chinese(amount_total),
        # Bank transfer is the norm for performance/qualification evidence
        # (proves real fund flow); cash/draft don't serve that purpose.
        "payment_method": "银行转账",
    }


_CN_DIGITS = "零壹贰叁肆伍陆柒捌玖"
_CN_UNITS = ["", "拾", "佰", "仟"]
_CN_BIG_UNITS = ["", "万", "亿"]


def _chinese_group(n: int) -> str:
    """Convert a 0-9999 int to Chinese numerals (no big-unit suffix), e.g. 6482 -> 陆仟肆佰捌拾贰, 31 -> 叁拾壹."""
    digits = [(n // 1000) % 10, (n // 100) % 10, (n // 10) % 10, n % 10]
    units = ["仟", "佰", "拾", ""]
    out = ""
    seen_nonzero = False
    pending_zero = False
    for digit, unit in zip(digits, units):
        if digit == 0:
            if seen_nonzero:
                pending_zero = True
            continue
        if pending_zero:
            out += "零"
            pending_zero = False
        out += _CN_DIGITS[digit] + unit
        seen_nonzero = True
    return out


def _amount_to_chinese(amount: float) -> str:
    """Convert a RMB amount to Chinese uppercase numerals, e.g. 316482.17 -> 叁拾壹万陆仟肆佰捌拾贰元壹角柒分."""
    yuan = int(amount)
    frac = round((amount - yuan) * 100)  # total fen, e.g. 17 -> 1角7分
    jiao, fen = divmod(frac, 10)

    if yuan == 0:
        yuan_cn = "零"
    else:
        groups = []
        n = yuan
        while n > 0:
            groups.append(n % 10000)
            n //= 10000
        parts = []
        emitted = False
        pending_zero = False
        for i in range(len(groups) - 1, -1, -1):
            group = groups[i]
            if group == 0:
                if emitted:
                    pending_zero = True
                continue
            if emitted and (pending_zero or group < 1000):
                parts.append("零")
            parts.append(_chinese_group(group) + _CN_BIG_UNITS[i])
            emitted = True
            pending_zero = False
        yuan_cn = "".join(parts)

    result = yuan_cn + "元"
    if jiao == 0 and fen == 0:
        result += "整"
    else:
        result += (_CN_DIGITS[jiao] + "角") if jiao else "零"
        result += (_CN_DIGITS[fen] + "分") if fen else ""
    return result


def _build_mock_summary(doc_type_code: str, mock_data: dict) -> str:
    """Build a human-readable summary from mock data for KB search indexing."""
    # Key fields that best identify each doc type
    type_keys = {
        "business-license": ["company_name", "unified_social_credit_code", "legal_person",
                             "registered_capital", "address", "business_scope"],
        "qualification-cert": ["cert_name", "cert_number", "company_name", "cert_level",
                               "issuing_authority"],
        "iso-cert": ["cert_name", "cert_number", "company_name", "standard",
                     "issuing_authority", "scope"],
        "honor-award": ["award_name", "company_name", "level", "issuing_authority"],
        "audit-report": ["report_type", "company_name", "period", "issuer", "audit_opinion"],
        "id-card": ["name", "id_number", "gender", "address"],
        "education-cert": ["name", "school_name", "major", "degree", "cert_name"],
        "professional-cert": ["name", "cert_name", "cert_number", "cert_level",
                              "issuing_authority"],
        "contract": ["contract_name", "contract_number", "party_a", "party_b",
                     "contract_amount", "project_name"],
        "acceptance-report": ["project_name", "contract_number", "company_name",
                              "acceptance_date", "acceptance_result"],
        "bid-document": ["project_name", "bid_number", "bidder_name", "bid_amount",
                         "result"],
        "authorization": ["authorization_type", "authorizer", "authorized_party",
                          "scope"],
        "invoice": ["invoice_number", "invoice_type", "buyer", "seller", "amount_total"],
        "product-brochure": ["product_name", "manufacturer", "model", "product_type"],
        "company-profile": ["company_name", "industry", "registered_capital",
                            "core_business", "address"],
        "technical-doc": ["doc_title", "project_name", "author", "tech_stack"],
    }
    keys = type_keys.get(doc_type_code, list(mock_data.keys())[:6])
    parts = []
    for k in keys:
        v = mock_data.get(k)
        if v:
            parts.append(f"{v}")
    return " | ".join(parts) if parts else ""


def _draw_centered_text(draw, text, font, y, width, fill=(0, 0, 0)):
    """Draw text centered horizontally at the given y position."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (width - tw) // 2
    draw.text((x, y), text, fill=fill, font=font)


def _draw_kv_row(draw, key, value, y, width, x_margin=60, key_color=(80, 80, 80), val_color=(20, 20, 20)):
    """Draw a key: value row."""
    font = _FONT_SMALL or _FONT
    if not font:
        return y + 30
    key_x = x_margin
    val_x = x_margin + 180
    draw.text((key_x, y), key + "：", fill=key_color, font=font)
    draw.text((val_x, y), str(value), fill=val_color, font=font)
    return y + 34


def _add_paper_texture(img, intensity=0.03):
    """Add subtle paper-like noise using pure PIL (no numpy dependency)."""
    rng = random.Random()
    getter = getattr(img, "get_flattened_data", img.getdata)
    pixels = list(getter())
    noise_range = int(255 * intensity)
    noisy = []
    for pixel in pixels:
        if isinstance(pixel, int):
            pixel = (pixel,)
        noisy.append(tuple(
            max(0, min(255, c + rng.randint(-noise_range, noise_range)))
            for c in pixel
        ))
    img = Image.new(img.mode, img.size)
    if img.mode == "L":
        noisy = [p[0] for p in noisy]
    img.putdata(noisy)
    return img


def _draw_red_stamp(draw, center_x, center_y, text, size=100):
    """Draw a red circular stamp/seal."""
    # Outer circle
    r = size
    draw.ellipse(
        [center_x - r, center_y - r, center_x + r, center_y + r],
        outline=(180, 30, 30), width=3
    )
    # Inner circle
    draw.ellipse(
        [center_x - r + 8, center_y - r + 8, center_x + r - 8, center_y + r - 8],
        outline=(180, 30, 30), width=1
    )

def generate_mock_image(
    doc_type_name: str,
    doc_type_code: str,
    mock_data: dict,
    entity_name: Optional[str] = None,
    person_name: Optional[str] = None,
) -> bytes:
    """
    Generate a PNG image that looks like a document scan.
    Returns PNG bytes.
    """
    width, height = 800, 1100
    bg_color = (252, 251, 248)  # warm paper white

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # ── Red header banner ──
    header_h = 80
    draw.rectangle([(0, 0), (width, header_h)], fill=(180, 30, 30))

    title_text = doc_type_name
    if entity_name:
        title_text = f"{entity_name} — {doc_type_name}"
    if _FONT_LARGE:
        _draw_centered_text(draw, title_text, _FONT_LARGE, 25, width, fill=(255, 255, 255))
    else:
        draw.text((40, 25), title_text, fill=(255, 255, 255))

    # ── Document number line ──
    doc_no = f"编号: MH-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
    if _FONT_SMALL:
        draw.text((width - 260, header_h + 12), doc_no, fill=(120, 120, 120), font=_FONT_SMALL)
    else:
        draw.text((width - 260, header_h + 12), doc_no, fill=(120, 120, 120))

    # ── Separator line ──
    y = header_h + 40
    draw.line([(40, y), (width - 40, y)], fill=(200, 200, 200), width=1)
    y += 25

    # ── Key-value fields ──
    field_labels = {
        "unified_social_credit_code": "统一社会信用代码",
        "company_name": "公司名称",
        "legal_person": "法定代表人",
        "registered_capital": "注册资本",
        "establishment_date": "成立日期",
        "business_scope": "经营范围",
        "company_type": "企业类型",
        "address": "地址/住址",
        "registration_authority": "登记机关",
        "issue_date": "发证日期",
        "valid_to": "有效期至",
        "valid_from": "有效期起",
        "business_term": "营业期限",
        "cert_number": "证书编号",
        "cert_level": "资质等级/级别",
        "cert_name": "证书名称",
        "issuing_authority": "发证机关/签发机关",
        "standard": "认证标准",
        "scope": "认证范围/经营范围",
        "award_name": "奖项名称",
        "award_date": "获奖日期",
        "award_category": "奖项类别",
        "level": "奖项级别",
        "report_type": "报告类型",
        "period": "报告期间",
        "issuer": "出具机构",
        "report_number": "报告文号",
        "audit_opinion": "审计意见",
        "total_assets": "资产总额",
        "net_profit": "净利润",
        "certified_public_accountant": "签字注册会计师",
        "name": "姓名",
        "id_number": "证件号码",
        "gender": "性别",
        "nationality": "民族",
        "birth_date": "出生日期",
        "school_name": "毕业院校",
        "school": "毕业院校",
        "major": "专业",
        "degree": "学位",
        "education": "学历",
        "graduation_date": "毕业日期",
        "principal_name": "校长/院长",
        "degree_committee_chairman": "学位评定委员会主席",
        "degree_cert_name": "学位证书名称",
        "degree_cert_number": "学位证书编号",
        "enrollment_date": "入学日期",
        "duration": "学制",
        "study_form": "学习形式",
        "education_category": "学历类别",
        "academic_level": "学历层次",
        "graduation_status": "毕业/结业",
        "query_website": "查询网站",
        "query_url": "查询网址",
        "management_number": "管理号",
        "contract_name": "合同名称",
        "contract_number": "合同编号",
        "party_a": "甲方",
        "party_a_address": "甲方地址",
        "party_a_contact": "甲方联系人",
        "party_b": "乙方",
        "party_b_address": "乙方地址",
        "party_b_contact": "乙方联系人",
        "contract_amount": "合同金额",
        "contract_amount_cn": "合同金额(大写)",
        "project_name": "项目名称",
        "project_description": "项目描述",
        "sign_date": "签订日期",
        "start_date": "开始日期",
        "end_date": "结束日期",
        "performance_period": "履约期限",
        "payment_terms": "付款方式",
        "signing_location": "签订地点",
        "acceptance_date": "验收日期",
        "acceptance_result": "验收结论",
        "acceptance_opinion": "验收意见",
        "acceptance_team_leader": "验收组长",
        "participants": "参与人员",
        "delivery_items": "交付物清单",
        "issues_found": "发现问题",
        "rectification_required": "是否需要整改",
        "bid_number": "招标编号",
        "bidder_name": "投标人",
        "bid_amount": "投标报价",
        "bid_amount_cn": "投标报价(大写)",
        "submission_date": "递交日期",
        "bid_validity": "投标有效期",
        "bid_bond": "投标保证金",
        "contact_person": "联系人",
        "contact_phone": "联系电话",
        "project_location": "项目地点",
        "construction_period": "工期",
        "quality_standard": "质量标准",
        "result": "中标结果",
        "authorization_type": "授权类型",
        "authorizer": "授权方",
        "authorizer_legal_person": "授权方法定代表人",
        "authorized_party": "被授权方",
        "authorized_person_id": "被授权人身份证号",
        "authorized_person_position": "被授权人职务",
        "invoice_number": "发票号码",
        "invoice_code": "发票代码",
        "invoice_type": "发票类型",
        "invoice_date": "开票日期",
        "amount": "金额合计",
        "amount_tax": "税额",
        "amount_total": "价税合计",
        "amount_cn": "金额(大写)",
        "buyer": "购方名称",
        "buyer_tax_id": "购方税号",
        "seller": "销方名称",
        "seller_tax_id": "销方税号",
        "items": "货物/服务名称",
        "payment_method": "付款方式",
        "product_name": "产品名称",
        "manufacturer": "生产厂商",
        "model": "型号规格",
        "version": "版本号",
        "product_type": "产品类型",
        "description": "产品描述",
        "features": "产品特性",
        "application_scenarios": "应用场景",
        "certification": "认证情况",
        "company_name_en": "英文名称",
        "industry": "行业领域",
        "established_date": "成立日期",
        "website": "公司网站",
        "employee_count": "员工人数",
        "core_business": "主营业务",
        "certifications": "资质认证",
        "honors": "荣誉奖项",
        "introduction": "公司介绍",
        "accreditation_body": "认可机构",
        "doc_title": "文档标题",
        "author": "编写人",
        "reviewer": "审核人",
        "approver": "批准人",
        "creation_date": "编写日期",
        "doc_type": "文档类型",
        "confidentiality_level": "密级",
        "tech_stack": "技术栈",
    }

    for key, value in mock_data.items():
        label = field_labels.get(key, key)
        y = _draw_kv_row(draw, label, value, y, width)
        if y > height - 200:
            break

    # ── Notes section ──
    y = max(y + 30, height - 200)
    draw.line([(40, y - 10), (width - 40, y - 10)], fill=(200, 200, 200), width=1)
    if _FONT_SMALL:
        draw.text((60, y), "备注：此为系统自动生成的模拟文档，仅供测试和演示使用。", fill=(150, 150, 150), font=_FONT_SMALL)

    # ── Red stamp ──
    _draw_red_stamp(draw, width - 140, height - 160, "模拟印章", size=70)
    draw.text((width - 230, height - 80), "（模拟文档）", fill=(180, 30, 30),
              font=_FONT_SMALL or _FONT if _FONT_SMALL else None)

    # ── Watermark ──
    if _FONT_LARGE:
        wm_text = "MOCK · 模拟文档"
        wm_img = Image.new("RGBA", (600, 100), (0, 0, 0, 0))
        wm_draw = ImageDraw.Draw(wm_img)
        wm_draw.text((10, 10), wm_text, fill=(200, 200, 200, 60), font=_FONT_LARGE)
        wm_rotated = wm_img.rotate(25, expand=True)
        px = (width - wm_rotated.width) // 2
        py = (height - wm_rotated.height) // 2
        img.paste(wm_rotated, (px, py), wm_rotated)

    # ── Texture and slight scan effect ──
    img = _add_paper_texture(img, intensity=0.015)

    # Convert to bytes
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# Canonical entity attribute keys we persist/reuse across calls for the same
# entity_name — mirrors the fields checked in the consistency-override block.
_ENTITY_BASELINE_KEYS = (
    "unified_social_credit_code", "credit_code", "registered_capital",
    "address", "establishment_date", "company_type", "business_scope",
    "legal_person",
)


def _persist_entity_baseline(entity_name: str, mock_data: dict) -> None:
    """Write this call's finalized baseline fields into dms_entities.attributes.

    Best-effort: creates the org Entity if it doesn't exist yet, merges new
    keys into existing attributes (never overwrites a key that's already set,
    so the first generation's values win and stay stable across all later
    calls — including ones made after mock documents were cleaned up).
    """
    from dms_models import get_dms_session, Entity

    new_attrs = {k: mock_data[k] for k in _ENTITY_BASELINE_KEYS if mock_data.get(k)}
    if not new_attrs:
        return
    try:
        with get_dms_session() as session:
            entity = session.query(Entity).filter(
                Entity.entity_type == "org", Entity.name == entity_name,
            ).first()
            if entity:
                try:
                    attrs = json.loads(entity.attributes) if entity.attributes else {}
                except (json.JSONDecodeError, TypeError):
                    attrs = {}
                changed = False
                for k, v in new_attrs.items():
                    if not attrs.get(k):
                        attrs[k] = v
                        changed = True
                if changed:
                    entity.attributes = json.dumps(attrs, ensure_ascii=False)
            else:
                entity = Entity(
                    entity_type="org",
                    name=entity_name,
                    attributes=json.dumps(new_attrs, ensure_ascii=False),
                )
                session.add(entity)
    except Exception as e:
        logger.warning("Failed to persist entity baseline for %s: %s", entity_name, e)


# ── Main entry point ──────────────────────────────────────────────────

def generate_mock(
    doc_type_code: str,
    entity_name: Optional[str] = None,
    person_name: Optional[str] = None,
    create_record: bool = True,
    mock_reason: Optional[str] = None,
    requirement_context: Optional[dict] = None,
    idempotency_key: Optional[str] = None,
    folder_path: Optional[str] = None,
) -> dict:
    """
    Generate a complete mock document: data + PNG + DB record.

    Args:
        mock_reason: e.g. "generated_for_requirement" for on-demand mocks
        requirement_context: tender project info stored in meta_json
        idempotency_key: if set, return existing doc matching (entity, type, key)

    Returns:
        {
            "doc_type_code": str,
            "doc_type_name": str,
            "mock_data": dict,
            "image_path": str,
            "document_id": int | None,
            "image_url": str,
            "requires_user_replacement": bool,
        }
    """
    from dms_models import get_dms_session, DocType, DmsDocument, Folder
    from dms_models import DmsFile, Revision

    if not is_mock_enabled():
        raise RuntimeError("Mock 功能未启用（系统设置 mock_enabled=false）")

    with get_dms_session() as session:
        dt = session.query(DocType).filter(DocType.code == doc_type_code).first()
        if not dt:
            raise ValueError(f"Unknown doc type: {doc_type_code}")
        doc_type_name = dt.name
        dt_id = dt.id
        category = dt.category or "general"
    # Idempotency check — return existing if same (entity, type, key, requirement_text).
    # entity_name and requirement_text must also match: otherwise two different people/certs
    # requested under the same tender_project would incorrectly collapse into one document.
    requirement_text = (requirement_context or {}).get("requirement_text")
    if idempotency_key and entity_name and create_record:
        import json as _json
        with get_dms_session() as session:
            existing = session.query(DmsDocument).filter(
                DmsDocument.status.in_(["active", "draft"]),
            ).all()
            for doc in existing:
                try: meta = _json.loads(doc.meta_json or "{}")
                except: continue
                existing_ctx = meta.get("requirement_context") or {}
                if (meta.get("mock")
                    and meta.get("mock_reason") == "generated_for_requirement"
                    and meta.get("document_type_code") == doc_type_code
                    and entity_name in meta.get("entity_names", [])
                    and existing_ctx.get("tender_project") == idempotency_key
                    and existing_ctx.get("requirement_text") == requirement_text):
                    # Return existing document
                    exp = doc.expiry_date.isoformat() if doc.expiry_date else None
                    return {
                        "doc_type_code": doc_type_code,
                        "doc_type_name": doc_type_name,
                        "mock_data": meta.get("extracted_data", {}),
                        "image_path": "",
                        "image_url": f"/api/v2/mock/files/{meta.get('img_filename', '')}",
                        "document_id": doc.id,
                        "requires_user_replacement": True,
                        "idempotent": True,
                    }
    _existing_overrides = {}
    if entity_name:
        from dms_models import Entity
        with get_dms_session() as session:
            # Persistent baseline: dms_entities.attributes survives independently of
            # mock document cleanup (unlike scanning meta_json on DmsDocument, which
            # loses the baseline the moment old mock docs get deleted — this was the
            # root cause of "entity baseline drifts to a new random person every time
            # old mock docs are cleared" reported in GAPS_ROUND3).
            org_entity = session.query(Entity).filter(
                Entity.entity_type == "org", Entity.name == entity_name,
            ).first()
            if org_entity and org_entity.attributes:
                try:
                    attrs = json.loads(org_entity.attributes)
                except (json.JSONDecodeError, TypeError):
                    attrs = {}
                for k in ("unified_social_credit_code", "credit_code",
                           "registered_capital", "address",
                           "establishment_date", "company_type",
                           "business_scope", "legal_person"):
                    if attrs.get(k):
                        _existing_overrides[k] = attrs[k]
                if attrs.get("legal_person") and not person_name:
                    person_name = attrs["legal_person"]
    # Generate mock data
    mock_data = generate_mock_data(doc_type_code, entity_name, person_name)

    # Semantic content generation: try LLM first (understands free-form
    # requirement_text, keeps related fields internally consistent), then
    # fill any remaining gaps with the deterministic keyword matcher.
    entity_known_attributes = dict(_existing_overrides)
    if entity_name:
        entity_known_attributes.setdefault("company_name", entity_name)
    if person_name:
        entity_known_attributes.setdefault("legal_person", person_name)

    llm_overrides = {}
    if doc_type_code in _LLM_CONTENT_DOC_TYPES:
        llm_overrides = _llm_generate_content(doc_type_code, requirement_text, entity_known_attributes)
    mock_data.update(llm_overrides)

    keyword_overrides = _extract_requirement_overrides(doc_type_code, requirement_text)
    mock_data.update({k: v for k, v in keyword_overrides.items() if k not in llm_overrides})

    # Apply entity consistency overrides from existing documents
    # Map canonical field names to template-specific aliases
    _FIELD_ALIASES = {
        "legal_person": ["authorizer_legal_person", "legal_representative", "contact_person"],
        "unified_social_credit_code": ["credit_code"],
        "address": ["party_b_address"],
    }
    if _existing_overrides:
        for canonical_key, canonical_value in _existing_overrides.items():
            if not canonical_value:
                continue
            # Apply to all matching fields (exact + aliases)
            if canonical_key in mock_data:
                mock_data[canonical_key] = canonical_value
            for alias in _FIELD_ALIASES.get(canonical_key, []):
                if alias in mock_data:
                    mock_data[alias] = canonical_value
            logger.info("Entity consistency: using existing '%s' for entity %s",
                        canonical_key, entity_name)

    # Persist the (possibly newly-generated) baseline attributes back to
    # dms_entities, so subsequent calls for this entity_name stay consistent
    # even after this document — or all mock documents — get cleaned up.
    if entity_name:
        _persist_entity_baseline(entity_name, mock_data)

    # Generate PNG image
    png_bytes = generate_mock_image(doc_type_name, doc_type_code, mock_data, entity_name, person_name)

    # Save to mock directory
    company_name = entity_name or _random_company_name()
    safe_name = company_name.replace("(", "（").replace(")", "）").replace(" ", "_")
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename_base = f"{safe_name}_{doc_type_code}_{ts}"
    img_filename = f"{filename_base}.png"
    img_path = MOCK_DIR / img_filename
    img_path.write_bytes(png_bytes)
    logger.info("Mock image saved: %s", img_path)

    document_id = None
    if create_record:
        try:
            with get_dms_session() as session:
                # Find a matching folder: try explicit path, then by name, then by category path, then root
                folder = None
                if folder_path:
                    folder = session.query(Folder).filter(
                        Folder.path == folder_path
                    ).first()
                if not folder:
                    folder = session.query(Folder).filter(
                        Folder.name == doc_type_name
                    ).first()
                if not folder:
                    folder = session.query(Folder).filter(
                        Folder.path.like(f"/{category}/%")
                    ).first()
                if not folder:
                    folder = session.query(Folder).first()

                title_suffix = "（MOCK-待替换）" if mock_reason == "generated_for_requirement" else "（模拟）"
                doc = DmsDocument(
                    title=f"{entity_name or company_name} - {doc_type_name}{title_suffix}",
                    doc_type_id=dt_id,
                    folder_id=folder.id if folder else None,
                    status="active",
                    meta_json=json.dumps({
                        "mock": True,
                        "mock_reason": mock_reason,
                        "document_type_code": doc_type_code,
                        "extracted_data": mock_data,
                        "entity_names": [entity_name] if entity_name else [],
                        "summary": _build_mock_summary(doc_type_code, mock_data),
                        "requirement_context": requirement_context,
                        "img_filename": img_filename,
                    }, ensure_ascii=False),
                )
                session.add(doc)
                session.flush()

                storage_path = f"dms_files/mock/{img_filename}"
                file_hash = secrets.token_hex(16)

                # Create revision first
                revision = Revision(
                    document_id=doc.id,
                    version_number=1,
                    is_current=True,
                    change_note=f"Mock-generated {doc_type_name}",
                )
                session.add(revision)
                session.flush()

                # Create file record linked to revision
                dms_file = DmsFile(
                    revision_id=revision.id,
                    file_type="original",
                    filename=img_filename,
                    storage_path=storage_path,
                    mime_type="image/png",
                    file_size=len(png_bytes),
                    file_hash=file_hash,
                )
                session.add(dms_file)
                session.flush()

                document_id = doc.id
                session.commit()
                logger.info("Mock document record created: id=%d, title=%s", doc.id, doc.title)

            # Auto-extract entities from mock data (outside inner session)
            try:
                from dms_processor import _link_entities
                _link_entities(document_id, doc_type_code, mock_data)
            except Exception as e:
                logger.warning("Entity linking failed (non-fatal): %s", e)
        except Exception as e:
            logger.warning("Failed to create mock document record: %s", e)
            logger.warning("Traceback:", exc_info=True)
    # Build image URL
    image_url = f"/api/v2/mock/files/{img_filename}"

    return {
        "doc_type_code": doc_type_code,
        "doc_type_name": doc_type_name,
        "mock_data": mock_data,
        "image_path": str(img_path),
        "image_url": image_url,
        "document_id": document_id,
        "requires_user_replacement": mock_reason == "generated_for_requirement",
    }


# ── List available mock types ─────────────────────────────────────────

def list_mock_types() -> list:
    """Return list of doc type codes that have mock templates."""
    return sorted(MOCK_TEMPLATES.keys())
