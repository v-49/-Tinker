#cfg.py
import os
#exp:"mysql+pymysql://user:password@host:port/database"
DATABASE_URL = os.getenv(
    "DATABASE_URL",
"mysql+pymysql://root:mysql_THhGnA@119.254.155.171:23306/airport"
)
if not DATABASE_URL:
    raise ValueError("环境变量 DATABASE_URL 未设置，请配置数据库连接字符串。")