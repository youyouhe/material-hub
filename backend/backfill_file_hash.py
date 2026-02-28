"""
回填历史数据的file_hash
为所有file_hash为NULL的Material记录计算并更新hash
"""
import os
import sys
from pathlib import Path
from database import get_session, Material
from ocr_cache import get_file_hash
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def backfill_material_file_hash():
    """回填Material表的file_hash"""

    with get_session() as session:
        # 查询所有file_hash为NULL的记录
        materials = session.query(Material).filter(
            Material.file_hash == None
        ).all()

        total = len(materials)
        logger.info(f"📊 找到 {total} 条需要回填hash的记录")

        if total == 0:
            logger.info("✅ 所有记录都已有hash，无需回填")
            return

        success_count = 0
        fail_count = 0

        for i, material in enumerate(materials, 1):
            file_path = material.image_path

            # 检查文件是否存在
            if not os.path.exists(file_path):
                logger.warning(f"⚠️ [{i}/{total}] 文件不存在: {file_path} (Material ID={material.id})")
                fail_count += 1
                continue

            try:
                # 计算hash
                file_hash = get_file_hash(file_path)

                if file_hash:
                    # 更新到数据库
                    material.file_hash = file_hash
                    logger.info(f"✅ [{i}/{total}] Material ID={material.id}, hash={file_hash[:16]}..., {material.title}")
                    success_count += 1
                else:
                    logger.error(f"❌ [{i}/{total}] hash计算失败: {file_path} (Material ID={material.id})")
                    fail_count += 1

            except Exception as e:
                logger.error(f"❌ [{i}/{total}] 处理失败: {file_path} (Material ID={material.id}), 错误: {e}")
                fail_count += 1

        # 提交事务
        try:
            session.commit()
            logger.info(f"🎉 回填完成！成功: {success_count}, 失败: {fail_count}, 总计: {total}")
        except Exception as e:
            session.rollback()
            logger.error(f"❌ 数据库提交失败: {e}")


def check_duplicates():
    """检查是否有重复的hash（用于验证）"""

    with get_session() as session:
        # 查询所有有hash的记录
        materials = session.query(Material).filter(
            Material.file_hash != None
        ).all()

        hash_map = {}
        duplicates = []

        for material in materials:
            file_hash = material.file_hash
            if file_hash in hash_map:
                # 发现重复
                duplicates.append({
                    "hash": file_hash,
                    "materials": [
                        {"id": hash_map[file_hash].id, "title": hash_map[file_hash].title},
                        {"id": material.id, "title": material.title}
                    ]
                })
            else:
                hash_map[file_hash] = material

        if duplicates:
            logger.warning(f"⚠️ 发现 {len(duplicates)} 组重复文件:")
            for dup in duplicates:
                logger.warning(f"  Hash: {dup['hash'][:16]}...")
                for mat in dup['materials']:
                    logger.warning(f"    - Material ID={mat['id']}: {mat['title']}")
        else:
            logger.info("✅ 未发现重复文件")


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("开始回填历史数据的file_hash")
    logger.info("=" * 60)

    # 执行回填
    backfill_material_file_hash()

    # 检查重复
    logger.info("")
    logger.info("=" * 60)
    logger.info("检查重复文件")
    logger.info("=" * 60)
    check_duplicates()
