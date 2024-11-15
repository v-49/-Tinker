# app/find.py
from app.models import Job, Check
from app.database import SessionLocal
from datetime import datetime, timedelta
import logging
import asyncio
from app.utils import process_countdown
from app.utils import AsyncPriorityQueue

logger = logging.getLogger(__name__)
task_queue = AsyncPriorityQueue()
task_queue_updated = asyncio.Event()

async def discover_tasks():
    try:
        logger.info("开始查找检查项。")
        current_time = datetime.now()
        one_hour_later = current_time + timedelta(hours=3)
        new_tasks_added = False
        with SessionLocal() as db:
            checks = db.query(Check).filter(
                Check.check_time >= current_time,
                Check.check_time <= one_hour_later,
                Check.status == 0
            ).all()
            total_checks_found = len(checks)
            logger.info(f"找到 {total_checks_found} 个检查项将在3小时内推送。")
            for check in checks:
                if not check.check_time or not isinstance(check.check_time, datetime):
                    logger.warning(
                        f"无效的检查项 {check.id}: check_time 无效，跳过该检查项。")
                    continue
                job = db.query(Job).filter(Job.id == check.job_id).first()
                if not job:
                    logger.warning(f"检查项 {check.id} 对应的任务不存在，跳过。")
                    continue
                if job.status == '已办':
                    check.status = 1
                    db.commit()
                    logger.info(f"任务 {job.id} 已完成，检查项 {check.id} 状态更新为已完成。")
                    continue
                countdown_delta = process_countdown(check.countdown)
                push_time = check.check_time - countdown_delta
                if push_time < current_time:
                    logger.info(f"检查项 {check.id} 的推送时间已过，立即推送。")
                    push_time = current_time
                priority = push_time.timestamp()
                if not task_queue.contains(check.id):
                    await task_queue.put((priority, check.id))
                    new_tasks_added = True
                    logger.info(f"检查项 {check.id} 已添加到推送队列，推送时间为: {push_time}")
        logger.info(f"检查项发现完成，共找到 {total_checks_found} 个有效的检查项。")
        if new_tasks_added:
            task_queue_updated.set()
    except Exception as e:
        logger.error(f"发现检查项任务时出错：{e}")
