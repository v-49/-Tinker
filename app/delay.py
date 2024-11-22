from fastapi import APIRouter, HTTPException
from app.utils import process_countdown
from datetime import datetime
from app.models import Check
from app.database import SessionLocal
import logging
from app.find import task_queue, task_queue_updated
logger = logging.getLogger(__name__)
router = APIRouter()
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
                #Check.status == 0 包括已推送进行延迟
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