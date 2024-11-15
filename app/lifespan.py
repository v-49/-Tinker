from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.find import discover_tasks
from app.active import push_tasks
from datetime import datetime
import logging
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建调度器
scheduler = AsyncIOScheduler()
@asynccontextmanager
async def lifespan(_app):
    push_task = None
    try:
        scheduler.start()
        logger.info("Scheduler started.")
        scheduler.add_job(
            discover_tasks,
            'interval',
            seconds=30,
            next_run_time=datetime.now()
        )
        logger.info("发现任务已经添加 周期：30s.")
        push_task = asyncio.create_task(push_tasks())
        logger.info("push_tasks 已作为后台推送任务启动。")
        yield
    finally:
        scheduler.shutdown()
        if push_task:
            push_task.cancel()
            try:
                await push_task
            except asyncio.CancelledError:
                logger.info("push_tasks 已取消。")
        logger.info("调度器已结束.")