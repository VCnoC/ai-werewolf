"""独立数据库初始化脚本，可在 CI 或手动执行"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import init_db


async def main():
    print("正在初始化数据库...")
    await init_db()
    print("数据库初始化完成")


if __name__ == "__main__":
    asyncio.run(main())
