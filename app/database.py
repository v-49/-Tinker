import logging
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from urllib.parse import urlparse
from app.cfg import DATABASE_URL

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

try:
    parsed_url = urlparse(DATABASE_URL)
    safe_url = f"{parsed_url.scheme}://{parsed_url.hostname}:{parsed_url.port}/[REDACTED]"
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True
    )
    logger.info(f"数据库连接建立成功，连接地址: {safe_url}")
except OperationalError as e:
    logger.error(f"数据库连接失败，可能是连接配置问题，错误信息: {e}")
    raise
except Exception as e:
    logger.error(f"未知错误导致数据库连接失败，错误信息: {e}")
    raise
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
