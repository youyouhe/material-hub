#!/usr/bin/env python3
"""
Change user password for MaterialHub.
Usage: python change_password.py <username>
"""

import sys
import getpass
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent))

from database import get_session, User
from auth import hash_password


def change_password(username: str, new_password: str):
    """Change password for a user."""
    with get_session() as db:
        user = db.query(User).filter(User.username == username).first()

        if not user:
            print(f"错误: 用户 '{username}' 不存在")
            return False

        # Hash new password
        password_hash = hash_password(new_password)

        # Update user
        user.password_hash = password_hash
        db.commit()

        print(f"✓ 成功修改用户 '{username}' 的密码")
        return True


def list_users():
    """List all users."""
    with get_session() as db:
        users = db.query(User).all()

        if not users:
            print("数据库中没有用户")
            return

        print("\n当前用户列表:")
        print("-" * 40)
        for user in users:
            print(f"ID: {user.id}")
            print(f"用户名: {user.username}")
            print(f"创建时间: {user.created_at}")
            print(f"最后登录: {user.last_login or '从未登录'}")
            print("-" * 40)


def main():
    if len(sys.argv) < 2:
        print("用法: python change_password.py <username>")
        print("\n或者使用 --list 查看所有用户:")
        print("python change_password.py --list")
        sys.exit(1)

    if sys.argv[1] == "--list":
        list_users()
        sys.exit(0)

    username = sys.argv[1]

    print(f"修改用户 '{username}' 的密码")
    print("-" * 40)

    # Get new password (with confirmation)
    while True:
        password1 = getpass.getpass("新密码: ")
        if len(password1) < 6:
            print("错误: 密码至少需要6个字符")
            continue

        password2 = getpass.getpass("确认密码: ")

        if password1 != password2:
            print("错误: 两次输入的密码不一致，请重试")
            continue

        break

    # Change password
    if change_password(username, password1):
        print("\n密码修改成功! 请使用新密码登录。")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
