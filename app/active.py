# app/active.py
from fastapi import APIRouter
from app.models import Check, Job
from app.database import SessionLocal
from datetime import datetime
import logging
from app.utils import process_countdown
from app.ws_routes import manager
import asyncio
import traceback
from app.find import task_queue, task_queue_updated
from app.passive import build_job_with_checks
logger = logging.getLogger(__name__)
router = APIRouter()
async def push_tasks():
    current_task = None
    while True:
        try:
            if current_task is None:
                if task_queue.empty():
                    await task_queue_updated.wait()
                    task_queue_updated.clear()
                    continue
                else:
                    priority, check_id = await task_queue.get()
                    current_task = (priority, check_id)
                    logger.info(f"获取到新的检查项 {check_id}，推送时间为 {datetime.fromtimestamp(priority)}")
            current_time = datetime.now().timestamp()
            total_delay = current_task[0] - current_time
            if total_delay <= 0:
                await process_check(current_task[1])
                current_task = None
            else:
                wait_task = asyncio.create_task(asyncio.sleep(total_delay))
                done, pending = await asyncio.wait(
                    [wait_task, task_queue_updated.wait()],
                    return_when=asyncio.FIRST_COMPLETED
                )
                if task_queue_updated.is_set():
                    task_queue_updated.clear()
                    next_task = task_queue.peek()
                    if next_task and next_task[0] < current_task[0]:
                        logger.info(f"发现更高优先级的检查项 {next_task[1]}，推送时间为 {datetime.fromtimestamp(next_task[0])}")
                        wait_task.cancel()
                        await task_queue.put(current_task)
                        priority, check_id = await task_queue.get()
                        current_task = (priority, check_id)
                        logger.info(f"切换到新的检查项 {check_id}，推送时间为 {datetime.fromtimestamp(priority)}")
                        continue
                if wait_task in done:
                    await process_check(current_task[1])
                    current_task = None
        except asyncio.CancelledError:
            logger.info("等待任务被取消，重新调度。")
            break
        except Exception as e:
            logger.error(f"推送任务时出错: {e}")
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            await asyncio.sleep(5)
# 处理单个检查项的逻辑，判断是否满足推送条件然后推送后状态置1
async def process_check(check_id):
    with SessionLocal() as db:
        check = db.query(Check).filter(Check.id == check_id).first()
        if not check:
            logger.warning(f"检查项 {check_id} 不存在，跳过。")
            return
        current_time = datetime.now()
        job = db.query(Job).filter(Job.id == check.job_id).first()
        if not job:
            logger.warning(f"检查项 {check.id} 对应的任务不存在，跳过。")
            return
        if job.status == '已办':
            check.status = 1
            db.commit()
            logger.info(f"任务 {job.id} 已完成，检查项 {check.id} 状态更新为已完成。")
            return
        countdown_delta = process_countdown(check.countdown)
        push_time = check.check_time - countdown_delta
        if push_time > current_time:

            logger.warning(f"检查项 {check.id} 的推送时间未到，当前时间：{current_time}，推送时间：{push_time}")
            return
        if check.status != 0:
            logger.info(f"检查项 {check.id} 状态已更新为 {check.status}，不再推送")
            return
        logger.info(f"gonna push {check.id} ")
        pushed_checks = db.query(Check).filter(Check.job_id == job.id, Check.status == 1).all()

        # 将当前检查项添加到已推送的列表中
        pushed_checks.append(check)
        await push_checks_with_job(job, pushed_checks, current_time)
        check.status = 1
        db.commit()
        logger.info(f" {check.id} pushed。")

# 推送检查项的消息
async def push_checks_with_job(job, checks, current_time):
    try:
        message = build_job_with_checks(job, checks, current_time)
        await manager.broadcast(message)
        logger.info(f"推送任务 {job.id} 和检查项 {', '.join(str(check.id) for check in checks)}。")
    except Exception as e:
        logger.error(f"推送任务和检查项时出错：{e}")
# 构建推送消息
