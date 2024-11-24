# cfg.py
import os

# exp:"mysql+pymysql://user:password@host:port/database"
DATABASE_URL = os.getenv(
    "DATABASE_URL"
)
if not DATABASE_URL:
    raise ValueError("环境变量 DATABASE_URL 未设置，请配置数据库连接字符串。")
