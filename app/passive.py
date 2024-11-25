# passive.py
from fastapi import APIRouter
from app.models import Job, Check
from app.database import SessionLocal
from datetime import datetime, timedelta
import logging
from collections import defaultdict
from app.utils import process_countdown, calculate_pushtime
from sqlalchemy.sql import func
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/v1/jobs/active")
async def get_jobs_with_checks():
    db = SessionLocal()
    ignored_jobs = []  # 存储那些被忽略的任务ID
    try:
        logger.info("开始查询任务...")

        current_time = datetime.now()

        # 1. 获取符合条件的检查项（Check）
        valid_checks = get_valid_checks(db, current_time)

        # 2. 获取符合条件的任务（Job）
        jobs = get_jobs_by_checks(db, valid_checks)

        # 3. 按级别分类并统计任务数量
        response = classify_and_count_jobs_by_level(db, jobs, current_time, ignored_jobs)

        # 返回最终结果
        return {
            "level_counts": response["level_counts"],
            "jobs": response["jobs"],
            "ignored_jobs": ignored_jobs
        }

    except Exception as e:
        logger.error(f"API任务查询错误：{e}")
        return {
            "error": f"无法获取任务: {str(e)}",
            "ignored_jobs": ignored_jobs,
        }
    finally:
        db.close()
        logger.info("查询完成。")


def get_valid_checks(db, current_time):
    """
    获取符合条件的检查项（前期倒排和流程节点管控）
    """
    checks_early = db.query(Check).filter(
        func.coalesce(Check.new_check_time, Check.check_time) <= current_time + timedelta(hours=73),
        func.coalesce(Check.new_check_time, Check.check_time) >= current_time,
        Check.check_group == "前期倒排"
    ).all()

    checks_flow_control = db.query(Check).filter(
        func.coalesce(Check.new_check_time, Check.check_time) >= current_time,
        Check.check_group == "流程节点管控"
    ).all()

    return checks_early + checks_flow_control


def get_jobs_by_checks(db, valid_checks):
    """
    根据检查项的job_id获取任务
    """
    if not valid_checks:
        return []

    valid_job_ids = [check.job_id for check in valid_checks]
    jobs = db.query(Job).filter(
        Job.id.in_(valid_job_ids),
        Job.status != "已办"
    ).all()

    return jobs


def classify_and_count_jobs_by_level(db, jobs, current_time, ignored_jobs):
    """
    按照任务级别分类，并统计每个级别的任务数量
    """
    level_count = defaultdict(int)  # 用于统计每个级别的任务数量
    level_jobs = defaultdict(list)  # 用于存储每个级别的任务数据
    jobs_data = []  # 存储最终所有任务的详细信息

    for job in jobs:
        if job.time is None:
            ignored_jobs.append(job.id)
            continue

        # 获取该任务的检查项
        checks = db.query(Check).filter(Check.job_id == job.id).order_by(Check.check_time).all()
        has_active_checks = any(
            (check.new_check_time or check.check_time) > current_time for check in checks
        )

        if job.time >= current_time or has_active_checks:
            job_data = build_job_with_checks(db, job, checks, current_time)
            job_level = job.level if job.level else "其他"  # 默认分类为 "其他"（无法归类的任务）

            # 分类统计任务数量
            level_count[job_level] += 1
            level_jobs[job_level].append(job_data)

    # 将任务按级别分类，放入返回的响应中
    for level in level_count:
        # 对每个级别下的任务按检查项的分组排序
        for job_data in level_jobs[level]:
            jobs_data.append(job_data)

    # 返回统计信息和任务详细信息
    return {
        "level_counts": level_count,  # 各级别任务数量统计
        "jobs": jobs_data  # 所有任务的详细信息
    }


def build_job_with_checks(db, job, checks, current_time):
    """
    构建任务及其对应的检查项信息，并增加倒计时字段
    """
    # 对检查项进行分组，先按 check_group 再按 check_time 排序
    grouped_checks = defaultdict(list)

    # 遍历检查项并进行分组
    for check_obj in checks:  # 使用 `check_obj` 作为内部变量名
        grouped_checks[check_obj.check_group].append(check_obj)

    # 对每个组内的检查项按时间排序
    for group in grouped_checks:
        grouped_checks[group] = sorted(
            grouped_checks[group],
            key=lambda check: check.new_check_time or check.check_time
        )
    checks_data = []
    # 遍历每个分组及其对应的检查项
    for group, group_checks in grouped_checks.items():
        for check_obj in group_checks:  # 使用 `check_obj` 作为变量名
            effective_check_time = check_obj.new_check_time or check_obj.check_time
            if check_obj.new_pushtime:
                push_time = check_obj.new_pushtime
                logger.info(f"检查项 {check_obj.id} 使用 new_pushtime 作为推送时间：{push_time}")

            else:
                # 计算并初始化 pushtime
                push_time = calculate_pushtime(check_obj)
                db.commit()

                logger.info(f"检查项 {check_obj.id} 计算 pushtime：{push_time}")

            if push_time <= current_time:
                # 计算倒计时
                countdown = int((check_obj.check_time - current_time).total_seconds())
                if countdown < 0:
                    countdown = -1
            else:
                # 推送时间还没到，倒计时不变
                countdown = process_countdown(check_obj.countdown).total_seconds()
            checks_data.append({
                "check_id": check_obj.id,
                "check_name": check_obj.name,
                "check_number": check_obj.number,
                "check_time": effective_check_time.strftime("%Y-%m-%d %H:%M:%S") if effective_check_time else None,
                "countdown": countdown,  # 计算倒计时（秒）
                "pushtime": push_time.strftime("%Y-%m-%d %H:%M:%S") if push_time else None,
                "check_group": group,
                "new_check_time": check_obj.new_check_time.strftime(
                    "%Y-%m-%d %H:%M:%S") if check_obj.new_check_time else None,
                "new_pushtime": check_obj.new_pushtime.strftime(
                    "%Y-%m-%d %H:%M:%S") if check_obj.new_pushtime else None,
                "status": check_obj.status,
            })

    return {
        "job_id": job.id,
        "job_name": job.name,
        "job_number": job.number,
        "job_level": job.level,
        "time": job.time.strftime("%Y-%m-%d %H:%M:%S") if job.time else None,
        "checks": checks_data
    }
