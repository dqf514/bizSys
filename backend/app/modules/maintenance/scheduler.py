"""每日自动备份调度：APScheduler 常驻线程 + Redis 日锁防多实例重复执行。"""

import logging
from datetime import datetime

from app.core.db import SessionLocal
from app.modules.maintenance import service as svc

logger = logging.getLogger("bizsys.backup")

JOB_ID = "daily_backup"
_LOCK_TTL = 24 * 3600

_scheduler = None


def _run_daily() -> None:
    """到点执行：Redis SET NX 抢日锁，抢到才备份（多实例部署只跑一份）。"""
    try:
        from app.core.redis import get_redis

        lock_key = f"backup:daily:{datetime.now():%Y%m%d}"
        if not get_redis().set(lock_key, "1", nx=True, ex=_LOCK_TTL):
            return
    except Exception:  # noqa: BLE001 Redis 不可用时仍尝试备份（单实例开发态）
        pass
    db = SessionLocal()
    try:
        info = svc.do_backup(db, kind="auto")
        logger.info("每日备份完成：%s (%s bytes)", info["name"], info["size"])
    except Exception:  # noqa: BLE001
        logger.exception("每日备份失败")
    finally:
        db.close()


def _schedule(scheduler, time_str: str) -> None:
    hh, mm = time_str.split(":")
    scheduler.add_job(
        _run_daily,
        trigger="cron",
        hour=int(hh),
        minute=int(mm),
        id=JOB_ID,
        replace_existing=True,
    )


def start() -> None:
    """应用启动时调用（幂等）：启用才挂每日任务。"""
    global _scheduler
    if _scheduler is not None:
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        db = SessionLocal()
        try:
            out = svc.settings_out(db)
        finally:
            db.close()
        _scheduler = BackgroundScheduler(daemon=True)
        if out["backup"]["enabled"]:
            _schedule(_scheduler, out["backup"]["time"])
        _scheduler.start()
        logger.info("备份调度器已启动（enabled=%s）", out["backup"]["enabled"])
    except Exception:  # noqa: BLE001 调度器失败不影响主服务
        logger.exception("备份调度器启动失败")
        _scheduler = None


def reschedule(time_str: str, enabled: bool) -> None:
    """设置变更后重排任务。"""
    if _scheduler is None:
        return
    try:
        if enabled:
            _schedule(_scheduler, time_str)
        else:
            _scheduler.remove_job(JOB_ID)
    except Exception:  # noqa: BLE001
        logger.exception("备份任务重排失败")


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            pass
        _scheduler = None
