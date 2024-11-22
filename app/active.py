from fastapi import APIRouter
from app.models import Check, Job
from app.database import SessionLocal
import logging
from app.ws_routes import manager
import asyncio
from app.find import task_queue, task_queue_updated
from datetime import datetime
from app.utils import mark_check_as_pushed, process_countdown

router = APIRouter()
logger = logging.getLogger(__name__)

# 推送任务的核心逻辑
async def push_tasks():
    task_progress = {}  # 记录每个任务的已推送检查项

    while True:
        try:
            if task_queue.empty():
                await task_queue_updated.wait()  # 等待队列更新
                task_queue_updated.clear()

            # 获取队列中的所有任务，处理所有需要推送的检查项
            priority, check_id = await task_queue.get()

            # 获取当前检查项的信息
            with SessionLocal() as db:
                check = db.query(Check).filter(Check.id == check_id).first()
                if not check:
                    logger.warning(f"检查项 {check_id} 不存在，跳过。")
                    continue

                job = db.query(Job).filter(Job.id == check.job_id).first()
                if not job:
                    logger.warning(f"检查项 {check.id} 对应的任务不存在，跳过。")
                    continue

                # 计算推送时间（check_time - countdown）
                push_time = calculate_push_time(check.check_time, check.countdown)

                # 判断当前时间是否到达推送时间
                if datetime.now() < push_time:
                    logger.info(f"检查项 {check.id} 尚未到推送时间，跳过。")
                    continue

                # 更新任务的推送进度
                if job.id not in task_progress:
                    task_progress[job.id] = {'checks': [], 'total_checks': 0}

                # 将当前检查项添加到已推送列表，避免重复
                if check not in task_progress[job.id]['checks']:
                    task_progress[job.id]['checks'].append(check)

                # 标记检查项为已推送
                mark_check_as_pushed(check)

                # 更新任务的总检查项数
                if task_progress[job.id]['total_checks'] == 0:
                    task_progress[job.id]['total_checks'] = db.query(Check).filter(Check.job_id == job.id).count()

                # 检查任务是否完成
                pushed_checks = len(task_progress[job.id]['checks'])
                if pushed_checks >= task_progress[job.id]['total_checks']:
                    # 任务完成，更新任务状态并从进度中移除
                    job.status = '已办'
                    db.commit()
                    logger.info(f"任务 {job.id} 所有检查项已推送完，任务已标记为已完成。")
                    del task_progress[job.id]

                # 构建推送消息，包含所有未完成任务的已推送检查项
                await push_checks(task_progress)

        except asyncio.CancelledError:
            logger.info("等待任务被取消，重新调度。")
            break
        except Exception as e:
            logger.error(f"推送任务时出错: {e}")
            await asyncio.sleep(5)

# 推送检查项的消息
async def push_checks(task_progress):
    try:
        message = build_message_for_tasks(task_progress)
        await manager.broadcast(message)  # 使用 WebSocket 广播消息
        logger.info(f"推送了任务更新：{list(task_progress.keys())}")
    except Exception as e:
        logger.error(f"推送检查项时出错：{e}")

# 构建推送消息
def build_message_for_tasks(task_progress):
    tasks_data = []
    total_active_checks = 0

    with SessionLocal() as db:
        for job_id, progress in task_progress.items():
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                continue

            checks_info = []
            for check in progress['checks']:
                checks_info.append({
                    "check_id": check.id,
                    "check_number": check.number,
                    "check_name": check.name,
                    "check_time": check.check_time.strftime("%Y-%m-%d %H:%M:%S") if check.check_time else None,
                    "countdown": check.countdown,
                    "check_group": check.check_group
                })
            total_active_checks += len(checks_info)

            tasks_data.append({
                "task_id": job.id,
                "task_status": job.status,  # 任务状态：已办 或 待办
                "checks": checks_info
            })

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total_active_checks": total_active_checks
        },
        "details": {
            "active_reminder": {
                "tasks": tasks_data
            }
        }
    }


def calculate_push_time(check_time, countdown_str):
    countdown_delta = process_countdown(countdown_str)
    push_time = check_time - countdown_delta
    return push_time
