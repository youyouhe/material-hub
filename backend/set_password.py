#!/usr/bin/env python3
"""
Set user password for MaterialHub.
Usage: python set_password.py <username> <new_password>
"""

import sys
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent))

from database import get_session, User
from auth import hash_password


def main():
    if len(sys.argv) < 3:
        print("用法: python set_password.py <username> <new_password>")
        print("\n示例:")
        print("  python set_password.py admin mynewpassword")
        print("\n或者查看所有用户:")
        print("  python set_password.py --list")
        sys.exit(1)

    if sys.argv[1] == "--list":
        with get_session() as db:
            users = db.query(User).all()
            if not users:
                print("数据库中没有用户")
                return

            print("\n当前用户列表:")
            print("-" * 50)
            for user in users:
                print(f"用户名: {user.username:<15} ID: {user.id}")
                print(f"创建时间: {user.created_at}")
                print(f"最后登录: {user.last_login or '从未登录'}")
                print("-" * 50)
        return

    username = sys.argv[1]
    new_password = sys.argv[2]

    if len(new_password) < 6:
        print("错误: 密码至少需要6个字符")
        sys.exit(1)

    with get_session() as db:
        user = db.query(User).filter(User.username == username).first()

        if not user:
            print(f"错误: 用户 '{username}' 不存在")
            print("\n提示: 使用 --list 查看所有用户")
            sys.exit(1)

        # Hash and update password
        user.password_hash = hash_password(new_password)
        db.commit()

        print(f"✓ 成功修改用户 '{username}' 的密码")
        print(f"  新密码: {new_password}")


if __name__ == "__main__":
    main()
