"""Планировщик повторяющихся отчётов на базе APScheduler."""

from __future__ import annotations

import uuid

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.database import async_session_maker
from app.models import ReportJob
from app.services.reporting import execute_report_job

scheduler = AsyncIOScheduler(timezone="UTC")


def _trigger(cron: str) -> CronTrigger:
    return CronTrigger.from_crontab(cron, timezone="UTC")


def validate_cron(cron: str) -> None:
    """Проверяет стандартное пяти-польное cron-выражение до сохранения."""
    _trigger(cron)


async def run_scheduled_report(template_id: uuid.UUID) -> None:
    """Создаёт отдельную задачу по шаблону и передаёт её в очередь."""
    async with async_session_maker() as db:
        template = await db.get(ReportJob, template_id)
        if template is None:
            return
        job = ReportJob(
            report_type=template.report_type,
            format=template.format,
            params=template.params,
            created_by_id=template.created_by_id,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
    await execute_report_job(job.id)


def add_report_schedule(job: ReportJob) -> None:
    if not job.schedule_cron:
        return
    scheduler.add_job(
        run_scheduled_report,
        _trigger(job.schedule_cron),
        args=[job.id],
        id=f"report-{job.id}",
        replace_existing=True,
        misfire_grace_time=3600,
    )


async def start_scheduler() -> None:
    """Восстанавливает расписания после перезапуска приложения."""
    if not scheduler.running:
        scheduler.start()
    async with async_session_maker() as db:
        result = await db.execute(
            select(ReportJob).where(ReportJob.schedule_cron.is_not(None))
        )
        for job in result.scalars().all():
            try:
                add_report_schedule(job)
            except ValueError:
                # Невалидные исторические расписания не должны ронять API.
                continue


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
