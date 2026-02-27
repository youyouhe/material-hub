"""
智能材料导入系统 - 核心流水线
自动识别、分类、归档各类材料文件
"""

import os
import json
import uuid
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime, date
from difflib import SequenceMatcher

from fastapi import UploadFile
from PIL import Image

from database import (
    get_session, Company, Person, Material, Document, PendingReview, MaterialVersion
)
from ocr_client import ocr_image, check_ocr_service
from llm_provider import get_llm_provider

logger = logging.getLogger("materialhub.smart_import")

# 临时文件目录
TEMP_DIR = Path(os.getenv("DATA_DIR", "data")) / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)


class FileProcessor:
    """多格式文件处理器"""

    SUPPORTED_FORMATS = {
        'image': ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.gif'],
        'document': ['.docx', '.doc', '.pdf'],
        'other': ['.txt', '.xlsx']
    }

    def analyze_file(self, file: UploadFile) -> Dict:
        """分析文件类型和特征"""
        filename = file.filename.lower()
        ext = Path(filename).suffix

        # 检测文件类型
        if ext in self.SUPPORTED_FORMATS['image']:
            file_type = 'image'
        elif ext in self.SUPPORTED_FORMATS['document']:
            file_type = 'document'
        else:
            file_type = 'other'

        # 从文件名猜测材料类型
        filename_hints = self.extract_hints_from_filename(filename)

        return {
            "type": file_type,
            "extension": ext,
            "filename": file.filename,
            "hints": filename_hints,
        }

    def extract_hints_from_filename(self, filename: str) -> Dict:
        """从文件名提取提示信息"""
        import re

        hints = {
            "possible_company": None,
            "possible_type": None,
            "possible_date": None
        }

        # 识别公司名（常见模式）
        company_patterns = [
            r'([\u4e00-\u9fa5]+(?:科技|网络|信息|技术|系统|软件|数据|智能)[\u4e00-\u9fa5]*(?:有限公司|公司|集团))',
            r'([\u4e00-\u9fa5]{2,20}有限公司)',
        ]

        for pattern in company_patterns:
            match = re.search(pattern, filename)
            if match:
                hints["possible_company"] = match.group(1)
                break

        # 识别材料类型关键词
        type_keywords = {
            "营业执照": "license",
            "资质": "qualification",
            "ISO": "iso_cert",
            "身份证": "id_card",
            "法人": "legal_person_cert",
            "毕业证": "education_cert",
            "学历": "education_cert",
        }

        for keyword, mat_type in type_keywords.items():
            if keyword in filename:
                hints["possible_type"] = mat_type
                break

        # 提取日期
        date_match = re.search(r'(20\d{2})[年\-_]?(\d{1,2})?[月\-_]?(\d{1,2})?', filename)
        if date_match:
            hints["possible_date"] = date_match.group(0)

        return hints


class ContentExtractor:
    """统一的内容提取器"""

    async def extract(self, file_path: str, file_info: Dict) -> Dict:
        """根据文件类型提取内容"""

        if file_info["type"] == "image":
            return await self.extract_from_image(file_path)

        elif file_info["type"] == "document":
            if file_info["extension"] == ".pdf":
                return await self.extract_from_pdf(file_path)
            elif file_info["extension"] in [".docx", ".doc"]:
                return await self.extract_from_docx(file_path)

        return {"text": "", "images": [], "metadata": {}}

    async def extract_from_image(self, file_path: str) -> Dict:
        """从图片提取文本"""
        if not check_ocr_service():
            logger.warning("OCR服务不可用")
            return {"text": "", "images": [file_path], "metadata": {"source": "no_ocr"}}

        ocr_text = ocr_image(file_path)

        return {
            "text": ocr_text or "",
            "images": [file_path],
            "metadata": {
                "image_count": 1,
                "source": "ocr"
            }
        }

    async def extract_from_pdf(self, file_path: str) -> Dict:
        """从PDF提取文本和图片"""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.error("PyMuPDF未安装，无法处理PDF")
            return {"text": "", "images": [], "metadata": {"error": "PyMuPDF not installed"}}

        doc = fitz.open(file_path)

        # 提取文本
        text_content = []
        images = []

        for page_num in range(len(doc)):
            page = doc[page_num]

            # 提取文本
            text = page.get_text()
            text_content.append(text)

            # 提取图片
            image_list = page.get_images()
            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)

                # 保存图片
                img_path = TEMP_DIR / f"pdf_img_{uuid.uuid4()}.{base_image['ext']}"
                with open(img_path, "wb") as img_file:
                    img_file.write(base_image["image"])

                images.append(str(img_path))

        full_text = "\n".join(text_content)

        # 如果PDF是扫描件（文本很少），对图片OCR
        if len(full_text.strip()) < 100 and images and check_ocr_service():
            ocr_texts = []
            for img_path in images:
                ocr_text = ocr_image(img_path)
                if ocr_text:
                    ocr_texts.append(ocr_text)
            if ocr_texts:
                full_text = "\n".join(ocr_texts)

        return {
            "text": full_text,
            "images": images,
            "metadata": {
                "page_count": len(doc),
                "image_count": len(images),
                "source": "pdf_extract" if len(full_text) > 100 else "ocr"
            }
        }

    async def extract_from_docx(self, file_path: str) -> Dict:
        """从Word文档提取文本和图片"""
        from docx import Document

        doc = Document(file_path)

        # 提取文本
        text_content = []
        for para in doc.paragraphs:
            if para.text.strip():
                text_content.append(para.text)

        # 提取图片
        images = []
        for rel in doc.part.rels.values():
            if "image" in rel.target_ref:
                image_data = rel.target_part.blob
                img_path = TEMP_DIR / f"docx_img_{uuid.uuid4()}.png"
                with open(img_path, "wb") as img_file:
                    img_file.write(image_data)
                images.append(str(img_path))

        return {
            "text": "\n".join(text_content),
            "images": images,
            "metadata": {
                "paragraph_count": len(doc.paragraphs),
                "image_count": len(images),
                "source": "docx_extract"
            }
        }


class IntelligentAnalyzer:
    """LLM智能分析器 - 核心大脑"""

    def __init__(self):
        self.llm = get_llm_provider()

    async def analyze(self, extracted_content: Dict, filename: str) -> Dict:
        """智能分析材料内容"""

        text = extracted_content["text"]

        if not text or len(text.strip()) < 20:
            logger.warning(f"文本内容过少，无法进行智能分析: {filename}")
            return {
                "material_type": "unknown",
                "confidence": 0.0,
                "error": "文本内容不足"
            }

        # 构建分析prompt
        prompt = f"""你是一个专业的材料识别助手。请分析以下材料的内容，提取关键信息。

文件名: {filename}
内容:
{text[:3000]}

请以JSON格式返回以下信息：
{{
    "material_type": "材料类型代码（license/qualification/id_card/education_cert/iso_cert/contract/legal_person_cert等）",
    "material_name": "材料的标准名称",
    "company_info": {{
        "name": "公司全称（必须完整）",
        "legal_person": "法定代表人",
        "credit_code": "统一社会信用代码（18位）",
        "address": "注册地址"
    }},
    "person_info": {{
        "name": "姓名",
        "id_number": "身份证号",
        "education": "学历",
        "position": "职位"
    }},
    "key_dates": {{
        "issue_date": "颁发日期（YYYY-MM-DD）",
        "expiry_date": "有效期至（YYYY-MM-DD）",
        "validity_period": "有效期年限"
    }},
    "certificate_info": {{
        "certificate_number": "证书编号",
        "issuing_authority": "发证机关",
        "certificate_grade": "证书等级"
    }},
    "confidence": 0.95,
    "notes": "其他重要信息"
}}

注意：
1. 如果某个字段无法确定，返回null
2. 公司名称必须是完整的全称
3. 日期格式统一为YYYY-MM-DD
4. 置信度根据信息完整程度评估（0-1之间）
"""

        try:
            # 调用LLM
            response = self.llm.chat(prompt)

            # 解析JSON
            analysis = json.loads(response)

            # 后处理
            analysis = self.post_process_analysis(analysis)
            analysis["_extracted_text"] = text  # 保存原始文本

            return analysis

        except json.JSONDecodeError as e:
            logger.error(f"LLM返回JSON解析失败: {e}\n响应: {response[:200]}")
            return {
                "material_type": "unknown",
                "confidence": 0.0,
                "error": "分析失败"
            }
        except Exception as e:
            logger.error(f"智能分析失败: {e}", exc_info=True)
            return {
                "material_type": "unknown",
                "confidence": 0.0,
                "error": str(e)
            }

    def post_process_analysis(self, analysis: Dict) -> Dict:
        """后处理：清理和标准化"""

        # 清理公司名称
        if analysis.get("company_info", {}).get("name"):
            company_name = analysis["company_info"]["name"]
            company_name = " ".join(company_name.split())  # 去除多余空格
            company_name = company_name.replace('（', '(').replace('）', ')')  # 全角转半角
            analysis["company_info"]["name"] = company_name

        # 标准化日期格式
        if analysis.get("key_dates"):
            for date_key in ["issue_date", "expiry_date"]:
                if analysis["key_dates"].get(date_key):
                    try:
                        analysis["key_dates"][date_key] = self.parse_date(
                            analysis["key_dates"][date_key]
                        )
                    except:
                        analysis["key_dates"][date_key] = None

        # 验证统一社会信用代码格式
        if analysis.get("company_info", {}).get("credit_code"):
            credit_code = analysis["company_info"]["credit_code"]
            if not self.validate_credit_code(credit_code):
                logger.warning(f"信用代码格式可能有误: {credit_code}")
                analysis["confidence"] = max(0, analysis.get("confidence", 0) - 0.1)

        return analysis

    def parse_date(self, date_str: str) -> str:
        """解析各种日期格式为标准格式"""
        from dateutil import parser
        try:
            dt = parser.parse(date_str)
            return dt.strftime("%Y-%m-%d")
        except:
            return date_str

    def validate_credit_code(self, code: str) -> bool:
        """验证统一社会信用代码格式"""
        import re
        pattern = r'^[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}$'
        return bool(re.match(pattern, code))


class EntityMatcher:
    """智能实体匹配器"""

    async def match(self, analysis: Dict) -> Dict:
        """匹配实体"""
        result = {
            "company_id": None,
            "company_name": None,
            "company_match_type": None,
            "person_id": None,
            "person_name": None,
            "person_match_type": None,
            "confidence": 1.0,
            "alternatives": []
        }

        # 匹配公司
        if analysis.get("company_info", {}).get("name"):
            company_match = await self.match_company(analysis["company_info"])
            result.update(company_match)

        # 匹配人员
        if analysis.get("person_info", {}).get("name"):
            person_match = await self.match_person(
                analysis["person_info"],
                result.get("company_id")
            )
            result.update(person_match)

        return result

    async def match_company(self, company_info: Dict) -> Dict:
        """匹配公司"""
        company_name = company_info.get("name")
        credit_code = company_info.get("credit_code")

        if not company_name:
            return {
                "company_id": None,
                "company_match_type": None,
                "confidence": 0.0
            }

        with get_session() as session:
            # 1. 精确匹配：统一社会信用代码
            if credit_code:
                company = session.query(Company).filter(
                    Company.credit_code == credit_code
                ).first()

                if company:
                    logger.info(f"✅ 公司精确匹配（信用代码）: {company.name}")
                    return {
                        "company_id": company.id,
                        "company_name": company.name,
                        "company_match_type": "exact_credit_code",
                        "confidence": 1.0
                    }

            # 2. 精确匹配：公司名称
            company = session.query(Company).filter(
                Company.name == company_name
            ).first()

            if company:
                logger.info(f"✅ 公司精确匹配（名称）: {company.name}")
                return {
                    "company_id": company.id,
                    "company_name": company.name,
                    "company_match_type": "exact_name",
                    "confidence": 1.0
                }

            # 3. 模糊匹配
            all_companies = session.query(Company).all()
            fuzzy_matches = []

            for comp in all_companies:
                similarity = self.calculate_company_name_similarity(
                    company_name,
                    comp.name
                )
                if similarity > 0.8:
                    fuzzy_matches.append({
                        "company_id": comp.id,
                        "company_name": comp.name,
                        "similarity": similarity
                    })

            if fuzzy_matches:
                fuzzy_matches.sort(key=lambda x: x["similarity"], reverse=True)
                best_match = fuzzy_matches[0]

                if best_match["similarity"] > 0.95:
                    logger.info(f"✅ 公司高度相似匹配: {best_match['company_name']} (相似度: {best_match['similarity']:.2f})")
                    return {
                        "company_id": best_match["company_id"],
                        "company_name": best_match["company_name"],
                        "company_match_type": "fuzzy_high",
                        "confidence": best_match["similarity"],
                        "alternatives": fuzzy_matches[1:3]
                    }
                else:
                    logger.info(f"⚠️ 公司低相似度匹配，需人工确认: {company_name}")
                    return {
                        "company_id": None,
                        "company_name": company_name,
                        "company_match_type": "fuzzy_low",
                        "confidence": 0.5,
                        "alternatives": fuzzy_matches[:3],
                        "new_company_info": company_info
                    }

            # 4. 无匹配：新公司
            logger.info(f"🆕 新公司: {company_name}")
            return {
                "company_id": None,
                "company_name": company_name,
                "company_match_type": "new",
                "confidence": 0.7,
                "new_company_info": company_info
            }

    def calculate_company_name_similarity(self, name1: str, name2: str) -> float:
        """计算公司名称相似度"""
        base_similarity = SequenceMatcher(None, name1, name2).ratio()

        # 去除公司类型后缀后的相似度
        def remove_suffix(name):
            suffixes = ["有限公司", "有限责任公司", "股份有限公司", "集团", "公司"]
            for suffix in suffixes:
                if name.endswith(suffix):
                    return name[:-len(suffix)]
            return name

        core1 = remove_suffix(name1)
        core2 = remove_suffix(name2)
        core_similarity = SequenceMatcher(None, core1, core2).ratio()

        return max(base_similarity, core_similarity)

    async def match_person(self, person_info: Dict, company_id: Optional[int]) -> Dict:
        """匹配人员"""
        person_name = person_info.get("name")
        id_number = person_info.get("id_number")

        if not person_name:
            return {"person_id": None}

        with get_session() as session:
            # 1. 身份证号精确匹配
            if id_number:
                person = session.query(Person).filter(
                    Person.id_number == id_number
                ).first()

                if person:
                    return {
                        "person_id": person.id,
                        "person_name": person.name,
                        "person_match_type": "exact_id",
                        "confidence": 1.0
                    }

            # 2. 姓名+公司匹配
            if company_id:
                person = session.query(Person).filter(
                    Person.name == person_name,
                    Person.company_id == company_id
                ).first()

                if person:
                    return {
                        "person_id": person.id,
                        "person_name": person.name,
                        "person_match_type": "name_company",
                        "confidence": 0.9
                    }

            # 3. 新人员
            return {
                "person_id": None,
                "person_name": person_name,
                "person_match_type": "new",
                "confidence": 0.6,
                "new_person_info": person_info
            }


class SmartImportPipeline:
    """智能导入流水线"""

    def __init__(self):
        self.file_processor = FileProcessor()
        self.content_extractor = ContentExtractor()
        self.intelligent_analyzer = IntelligentAnalyzer()
        self.entity_matcher = EntityMatcher()
        self.auto_archiver = AutoArchiver()

    async def process_single_file(self, file: UploadFile) -> Dict:
        """处理单个文件的完整流程"""

        logger.info(f"=" * 60)
        logger.info(f"📄 开始处理文件: {file.filename}")

        try:
            # 1. 保存临时文件
            temp_path = TEMP_DIR / f"{uuid.uuid4()}{Path(file.filename).suffix}"
            with open(temp_path, "wb") as f:
                content = await file.read()
                f.write(content)

            logger.info(f"💾 临时文件保存: {temp_path}")

            # 2. 格式识别
            file_info = self.file_processor.analyze_file(file)
            logger.info(f"📋 文件类型: {file_info['type']}, 提示: {file_info['hints']}")

            # 3. 内容提取
            extracted_content = await self.content_extractor.extract(str(temp_path), file_info)
            logger.info(f"📝 提取内容: {len(extracted_content['text'])} 字符, {len(extracted_content.get('images', []))} 张图片")

            # 4. 智能分析
            analysis = await self.intelligent_analyzer.analyze(extracted_content, file.filename)
            logger.info(f"🤖 智能分析: 类型={analysis.get('material_type')}, 置信度={analysis.get('confidence', 0):.2f}")

            # 5. 实体匹配
            entities = await self.entity_matcher.match(analysis)
            logger.info(f"🔗 实体匹配: 公司={entities.get('company_name')}, 匹配类型={entities.get('company_match_type')}")

            # 6. 计算总体置信度
            overall_confidence = self.calculate_confidence(analysis, entities)
            logger.info(f"📊 总体置信度: {overall_confidence:.2f}")

            # 7. 决策：自动归档 or 人工审核
            if overall_confidence >= 0.85:
                # 自动归档
                logger.info(f"✅ 置信度高，执行自动归档")
                material = await self.auto_archiver.archive(
                    temp_path=str(temp_path),
                    filename=file.filename,
                    file_info=file_info,
                    analysis=analysis,
                    entities=entities
                )
                return {
                    "status": "auto_archived",
                    "material_id": material.id,
                    "filename": file.filename,
                    "confidence": overall_confidence,
                    "message": f"已自动归档: {material.title}"
                }
            else:
                # 创建待审核项
                pending_id = await self.create_pending_review(
                    temp_path=str(temp_path),
                    filename=file.filename,
                    file_info=file_info,
                    analysis=analysis,
                    entities=entities,
                    confidence=overall_confidence
                )
                logger.info(f"⚠️ 置信度不足，已加入待审核队列 (ID: {pending_id})")
                return {
                    "status": "pending_review",
                    "pending_id": pending_id,
                    "filename": file.filename,
                    "confidence": overall_confidence,
                    "message": "置信度不足，需人工审核"
                }

        except Exception as e:
            logger.error(f"❌ 处理失败: {file.filename} - {e}", exc_info=True)
            return {
                "status": "failed",
                "filename": file.filename,
                "error": str(e)
            }

    def calculate_confidence(self, analysis: Dict, entities: Dict) -> float:
        """计算总体置信度"""
        analysis_conf = analysis.get("confidence", 0)
        entity_conf = entities.get("confidence", 0)

        # 综合评分
        overall = (analysis_conf * 0.6 + entity_conf * 0.4)

        # 调整因子
        if entities.get("company_match_type") == "exact_credit_code":
            overall += 0.1
        elif entities.get("company_match_type") == "new":
            overall -= 0.15

        return min(1.0, max(0.0, overall))

    async def create_pending_review(
        self,
        temp_path: str,
        filename: str,
        file_info: Dict,
        analysis: Dict,
        entities: Dict,
        confidence: float
    ) -> int:
        """创建待审核项"""
        with get_session() as session:
            pending = PendingReview(
                file_path=temp_path,
                filename=filename,
                file_type=file_info["type"],
                analysis_json=json.dumps(analysis, ensure_ascii=False),
                entities_json=json.dumps(entities, ensure_ascii=False),
                version_info_json=json.dumps({"is_update": False}, ensure_ascii=False),
                confidence=int(confidence * 100),
                status="pending"
            )
            session.add(pending)
            session.commit()
            return pending.id


class AutoArchiver:
    """自动归档器 - 创建材料记录和实体"""

    def __init__(self):
        self.data_dir = Path(os.getenv("DATA_DIR", "data"))
        self.files_dir = self.data_dir / "files"
        self.images_dir = self.data_dir / "images"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    async def archive(
        self,
        temp_path: str,
        filename: str,
        file_info: Dict,
        analysis: Dict,
        entities: Dict
    ) -> Material:
        """执行自动归档"""
        logger.info(f"🗄️ 开始自动归档: {filename}")

        with get_session() as session:
            # 1. 创建或获取公司
            company_id = await self._get_or_create_company(session, entities, analysis)

            # 2. 创建或获取人员
            person_id = await self._get_or_create_person(session, entities, analysis, company_id)

            # 3. 保存文件到永久位置
            saved_file_path = self._save_file_permanent(temp_path, filename, file_info)

            # 4. 创建Document记录（如果需要）
            document = self._get_or_create_document(session, filename, company_id)

            # 5. 创建Material记录
            material = self._create_material(
                session,
                document_id=document.id,
                company_id=company_id,
                person_id=person_id,
                saved_file_path=saved_file_path,
                filename=filename,
                analysis=analysis
            )

            session.commit()
            logger.info(f"✅ 归档完成: Material ID={material.id}, {material.title}")

            # 6. 清理临时文件
            try:
                Path(temp_path).unlink()
            except:
                pass

            return material

    async def _get_or_create_company(
        self,
        session,
        entities: Dict,
        analysis: Dict
    ) -> Optional[int]:
        """获取或创建公司"""
        company_id = entities.get("company_id")

        # 如果已匹配到公司，直接返回
        if company_id:
            logger.info(f"  ✓ 使用已匹配公司 ID={company_id}")
            return company_id

        # 如果需要创建新公司
        if entities.get("new_company_info"):
            company_info = entities["new_company_info"]
            company = Company(
                name=company_info.get("name"),
                legal_person=company_info.get("legal_person"),
                credit_code=company_info.get("credit_code"),
                address=company_info.get("address")
            )
            session.add(company)
            session.flush()
            logger.info(f"  ✓ 创建新公司: {company.name} (ID={company.id})")
            return company.id

        return None

    async def _get_or_create_person(
        self,
        session,
        entities: Dict,
        analysis: Dict,
        company_id: Optional[int]
    ) -> Optional[int]:
        """获取或创建人员"""
        person_id = entities.get("person_id")

        # 如果已匹配到人员，直接返回
        if person_id:
            logger.info(f"  ✓ 使用已匹配人员 ID={person_id}")
            return person_id

        # 如果需要创建新人员
        if entities.get("new_person_info"):
            person_info = entities["new_person_info"]
            person = Person(
                name=person_info.get("name"),
                id_number=person_info.get("id_number"),
                education=person_info.get("education"),
                position=person_info.get("position"),
                company_id=company_id
            )
            session.add(person)
            session.flush()
            logger.info(f"  ✓ 创建新人员: {person.name} (ID={person.id})")
            return person.id

        return None

    def _save_file_permanent(
        self,
        temp_path: str,
        filename: str,
        file_info: Dict
    ) -> str:
        """保存文件到永久位置"""
        # 生成唯一文件名
        ext = Path(filename).suffix
        unique_filename = f"{uuid.uuid4()}{ext}"

        # 根据文件类型选择目录
        if file_info["type"] == "image":
            target_dir = self.images_dir
        else:
            target_dir = self.files_dir

        target_path = target_dir / unique_filename

        # 移动文件
        import shutil
        shutil.move(temp_path, target_path)

        logger.info(f"  ✓ 文件已保存: {target_path}")
        return str(target_path)

    def _get_or_create_document(
        self,
        session,
        filename: str,
        company_id: Optional[int]
    ) -> Document:
        """获取或创建Document记录"""
        # 对于智能导入，每个文件创建一个独立的Document
        document = Document(
            filename=filename,
            company_id=company_id,
            section_count=0,
            image_count=1
        )
        session.add(document)
        session.flush()
        logger.info(f"  ✓ 创建Document记录 ID={document.id}")
        return document

    def _create_material(
        self,
        session,
        document_id: int,
        company_id: Optional[int],
        person_id: Optional[int],
        saved_file_path: str,
        filename: str,
        analysis: Dict
    ) -> Material:
        """创建Material记录"""
        # 解析有效期
        expiry_date = None
        if analysis.get("key_dates", {}).get("expiry_date"):
            try:
                from datetime import datetime
                expiry_date = datetime.strptime(
                    analysis["key_dates"]["expiry_date"],
                    "%Y-%m-%d"
                ).date()
            except:
                pass

        # 确定section
        section = self._determine_section(analysis.get("material_type"))

        # 创建材料
        material = Material(
            document_id=document_id,
            company_id=company_id,
            person_id=person_id,
            title=analysis.get("material_name") or filename,
            section=section,
            image_filename=Path(saved_file_path).name,
            image_path=saved_file_path,
            file_size=Path(saved_file_path).stat().st_size,
            material_type=analysis.get("material_type"),
            ocr_text=analysis.get("_extracted_text"),
            extracted_json=json.dumps({
                k: v for k, v in analysis.items()
                if k != "_extracted_text"
            }, ensure_ascii=False),
            expiry_date=expiry_date,
            ocr_status="completed",
            ocr_processed_at=datetime.utcnow()
        )

        session.add(material)
        session.flush()

        logger.info(f"  ✓ 创建Material记录: {material.title} (ID={material.id})")
        return material

    def _determine_section(self, material_type: Optional[str]) -> str:
        """根据材料类型确定section"""
        type_to_section = {
            "license": "营业执照",
            "qualification": "资质证书",
            "iso_cert": "ISO认证",
            "id_card": "身份证",
            "education_cert": "学历证书",
            "legal_person_cert": "法人证明",
            "contract": "合同",
        }
        return type_to_section.get(material_type, "其他材料")
