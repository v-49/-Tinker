# app/active.py

from fastapi import APIRouter, HTTPException
from app.models import Check, Job
from app.database import SessionLocal
from datetime import datetime
import logging
from app.utils import process_countdown
from app.ws_routes import manager
import asyncio
import traceback
from app.find import task_queue, task_queue_updated

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
        await push_checks([check])
        check.status = 1
        db.commit()
        logger.info(f" {check.id} pushed。")

# 推送检查项的消息
async def push_checks(checks):
    try:
        message = build_message_for_checks(checks)
        await manager.broadcast(message)
        logger.info(f"pushing：{[check.id for check in checks]}。")
    except Exception as e:
        logger.error(f"推送检查项时出错：{e}")
# 构建推送消息
def build_message_for_checks(checks):
    checks_data = [
        {
            "check_number": check.number,
            "check_name": check.name,
            "check_time": check.check_time.strftime("%Y-%m-%d %H:%M:%S") if check.check_time else None,
            "countdown": check.countdown,
            "check_group": check.check_group
        }
        for check in checks
    ]
    return {
        "summary": {
            "total_active_checks": len(checks)
        },
        "details": {
            "active_reminder": {
                "checks": checks_data
            }
        }
    }

# 延迟检查项接口
@router.post("/api/v1/checks/{check_id}/delay")
async def delay_check(check_id: int, pushtime: str):
    """
    延迟检查项，根据传入的 pushtime 计算 delay_minutes 和 delay_seconds。
    """
    try:
        pushtime = datetime.strptime(pushtime, "%Y-%m-%d %H:%M:%S")
        with SessionLocal() as db:
            check = db.query(Check).filter(Check.id == check_id).first()
            if not check:
                raise HTTPException(status_code=404, detail="检查项不存在")
            original_time = check.check_time
            delay_duration = pushtime - original_time
            if delay_duration.total_seconds() <= 0:
                raise HTTPException(status_code=400, detail="传入的 pushtime 必须晚于原始时间")
            total_seconds = delay_duration.total_seconds() #已算出具体延迟，下面做展示
            delay_minutes = int(total_seconds // 60)
            delay_seconds = int(total_seconds % 60)
            #查找后续的同一任务下的检查项
            job_id = check.job_id
            subsequent_checks = db.query(Check).filter(
                Check.job_id == job_id,
                Check.check_time >= check.check_time,
                Check.status == 0
            ).all()
            if not subsequent_checks:
                raise HTTPException(status_code=400, detail="没有找到后续未推送的检查项")
            # 应用延迟到后续检查项
            for subsequent_check in subsequent_checks:
                new_check_time = subsequent_check.check_time + delay_duration
                subsequent_check.check_time = new_check_time
                subsequent_check.status = 0
            db.commit()
            logger.info(
                f"延迟任务ID {job_id} 的检查项 {', '.join([str(c.id) for c in subsequent_checks])} "
                f"{delay_minutes} 分钟 {delay_seconds} 秒"
            )
            # 更新队列中的检查项
            for subsequent_check in subsequent_checks:
                # 计算新的推送时间
                countdown_delta = process_countdown(subsequent_check.countdown)
                push_time = subsequent_check.check_time - countdown_delta

                priority = push_time.timestamp()
                await task_queue.put((priority, subsequent_check.id))
                task_queue_updated.set()

            return {
                "message": "检查项延迟成功",
                "延迟时间": {
                    "minutes": delay_minutes,
                    "seconds": delay_seconds
                },
                "delayed_checks": [check.id for check in subsequent_checks]
            }

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"延迟检查项失败: {e}")
        raise HTTPException(status_code=500, detail="延迟检查项失败")