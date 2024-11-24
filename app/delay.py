# delay.py
from fastapi import APIRouter, HTTPException
from app.utils import process_countdown
from datetime import datetime
from app.models import Check
from app.database import SessionLocal
import logging
from app.find import task_queue, task_queue_updated
from sqlalchemy.sql import func
logger = logging.getLogger(__name__)
router = APIRouter()


# 延迟检查项接口
@router.post("/api/v1/checks/{check_id}/delay")
async def delay_check(check_id: int, pushtime: str):
    try:
        pushtime = datetime.strptime(pushtime, "%Y-%m-%d %H:%M:%S")
        with SessionLocal() as db:
            check = db.query(Check).filter(Check.id == check_id).first()
            if not check:
                raise HTTPException(status_code=404, detail="检查项不存在")

            # 使用 new_check_time（如果存在）或 check_time 作为基准时间
            base_time = check.new_check_time or check.check_time
            delay_duration = pushtime - base_time
            if delay_duration.total_seconds() <= 0:
                raise HTTPException(status_code=400, detail="传入的 pushtime 必须晚于当前的检查项时间")

            total_seconds = delay_duration.total_seconds()
            delay_minutes = int(total_seconds // 60)
            delay_seconds = int(total_seconds % 60)
            # 查找后续的同一任务下的检查项
            job_id = check.job_id
            subsequent_checks = db.query(Check).filter(
                Check.job_id == job_id,
                func.coalesce(Check.new_check_time, Check.check_time) >= base_time,
                Check.check_group == "流程节点管控"
            ).all()
            if not subsequent_checks:
                raise HTTPException(status_code=400, detail="没有找到后续未推送的检查项")

            def get_check_time(cc):
                return cc.new_check_time or cc.check_time or datetime.min
            subsequent_checks.sort(key=get_check_time)
            current_index = None
            for idx, c in enumerate(subsequent_checks):
                if c.id == check.id:
                    current_index = idx
                    break
            if current_index is None:
                raise HTTPException(status_code=400, detail="未能找到当前的检查项")
            subsequent_checks = subsequent_checks[current_index:]

            # 应用延迟到后续检查项
            for subsequent_check in subsequent_checks:
                base_time = subsequent_check.new_check_time or subsequent_check.check_time
                new_check_time = base_time + delay_duration
                subsequent_check.new_check_time = new_check_time
                subsequent_check.status = 0

                # 计算新的 new_pushtime
                countdown_delta = process_countdown(subsequent_check.countdown)
                new_pushtime = new_check_time - countdown_delta
                subsequent_check.new_pushtime = new_pushtime
            db.commit()
            logger.info(
                f"延迟任务ID {job_id} 的“流程节点管控”检查项 {', '.join([str(c.id) for c in subsequent_checks])} "
                f"{delay_minutes} 分钟 {delay_seconds} 秒"
            )
            # 更新队列中的检查项
            for subsequent_check in subsequent_checks:
                if subsequent_check.new_pushtime:
                    push_time = subsequent_check.new_pushtime
                elif subsequent_check.pushtime:
                    push_time = subsequent_check.pushtime
                else:
                    # 计算并初始化 pushtime
                    countdown_delta = process_countdown(subsequent_check.countdown)
                    pushtime = (subsequent_check.new_check_time or subsequent_check.check_time) - countdown_delta
                    subsequent_check.pushtime = pushtime
                    db.commit()
                    push_time = pushtime
                    logger.info(f"3检查项 {subsequent_check.id} 计算并初始化 pushtime：{push_time}")

                priority = push_time.timestamp()
                await task_queue.put((priority, subsequent_check.id))
                task_queue_updated.set()

            return {
                "message": "检查项延迟成功",
                "延迟时间": {
                    "minutes": delay_minutes,
                    "seconds": delay_seconds
                },
                "delayed_checks": [cc.id for cc in subsequent_checks]
            }

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.exception("延迟检查项失败")  # 使用 logger.exception 会记录完整的堆栈信息
        raise HTTPException(status_code=500, detail=f"延迟检查项失败: {str(e)}")
