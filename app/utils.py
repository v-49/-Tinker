# utils.py
import logging
from datetime import timedelta
from app.database import SessionLocal
from app.models import Check
import asyncio
import heapq
logger = logging.getLogger(__name__)


def process_countdown(countdown_str):
    try:
        parts = countdown_str.split(':')
        if len(parts) == 3:
            h = int(parts[0])
            m = int(parts[1])
            s = int(parts[2])
        else:
            raise ValueError("countdown 格式不正确")
        return timedelta(hours=h, minutes=m, seconds=s)
    except ValueError as e:
        logger.error(f"处理countdown出错：{e}")
        return timedelta()


def calculate_pushtime(check):
    countdown_delta = process_countdown(check.countdown)
    effective_check_time = check.new_check_time or check.check_time
    pushtime = effective_check_time - countdown_delta
    check.pushtime = pushtime
    return pushtime


def mark_check_as_pushed(check: Check):
    db = SessionLocal()
    try:
        check.status = 1
        db.commit()
        logger.info(f"Check {check.id} pushed.")
    except Exception as e:
        db.rollback()
        logger.error(f"标记检查项为已推送失败：{e}")
    finally:
        db.close()


class AsyncPriorityQueue:
            def __init__(self):
                self._queue = []
                self._event = asyncio.Event()
                self._lock = asyncio.Lock()

            async def put(self, item):
                async with self._lock:
                    heapq.heappush(self._queue, item)
                    self._event.set()

            async def get(self):
                while True:
                    async with self._lock:
                        if self._queue:
                            return heapq.heappop(self._queue)
                        else:
                            self._event.clear()
                    await self._event.wait()

            def peek(self):
                if self._queue:
                    return self._queue[0]
                else:
                    return None

            def empty(self):
                return len(self._queue) == 0

            def contains(self, check_id):
                return any(item[1] == check_id for item in self._queue)
