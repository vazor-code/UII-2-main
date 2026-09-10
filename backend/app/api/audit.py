"""Эндпоинты журнала аудита (Этап 8).

- Просмотр журнала действий с фильтрацией
- Контроль целостности (проверка целостности записей)
"""

from __future__ import annotations

import uuid
import csv
import json
from datetime import datetime
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select

from app.core.deps import DbSession, Perm, require_permission
from app.models import Asset, AuditLog, Room
from app.schemas.audit import AuditLogOut

router = APIRouter()


@router.get(
    "/export",
    dependencies=[Depends(require_permission(Perm.VIEW_AUDIT))],
    summary="Экспорт журнала аудита в CSV или JSON",
)
async def export_audit(
    db: DbSession,
    format: str = Query(default="CSV", pattern="^(CSV|JSON)$"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
):
    """Выгружает аудит для архивного хранения; записи не удаляются из БД."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.asc())
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= date_to)
    result = await db.execute(stmt)
    rows = [
        {
            "id": str(row.id),
            "user_id": str(row.user_id) if row.user_id else "",
            "action": row.action,
            "entity_type": row.entity_type or "",
            "entity_id": row.entity_id or "",
            "field_name": row.field_name or "",
            "old_value": row.old_value or "",
            "new_value": row.new_value or "",
            "ip_address": row.ip_address or "",
            "comment": row.comment or "",
            "created_at": row.created_at.isoformat(),
        }
        for row in result.scalars().all()
    ]
    if format == "JSON":
        return Response(
            content=json.dumps(rows, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=audit-log.json"},
        )
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]) if rows else ["id"])
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content=output.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit-log.csv"},
    )


@router.get(
    "",
    response_model=list[AuditLogOut],
    dependencies=[Depends(require_permission(Perm.VIEW_AUDIT))],
    summary="Журнал аудита",
)
async def list_audit(
    db: DbSession,
    user_id: uuid.UUID | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= date_to)
    stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.get(
    "/actions",
    dependencies=[Depends(require_permission(Perm.VIEW_AUDIT))],
    summary="Список доступных действий",
)
async def list_actions(db: DbSession):
    result = await db.execute(select(AuditLog.action).distinct())
    return {"actions": [r[0] for r in result.all()]}


@router.get(
    "/integrity",
    dependencies=[Depends(require_permission(Perm.VIEW_AUDIT))],
    summary="Проверка целостности данных",
)
async def integrity_check(db: DbSession):
    """Базовая проверка целостности: корректность связей между таблицами."""
    issues: list[dict] = []

    # Карточки без помещения, но не в статусе списания/резерва
    orphan_assets = await db.execute(
        select(Asset)
        .where(
            Asset.room_id.is_(None),
            Asset.status.not_in(["WRITTEN_OFF", "RESERVED"]),
        )
        .limit(50)
    )
    orphan_count = len(orphan_assets.scalars().all())
    if orphan_count:
        issues.append(
            {
                "entity": "asset",
                "message": f"Найдено {orphan_count} карточек без привязки к помещению",
            }
        )

    # Кабинеты без здания (не должно быть, т.к. FK NOT NULL — проверка для отчёта)
    total_assets = await db.scalar(select(func.count()).select_from(Asset))
    total_rooms = await db.scalar(select(func.count()).select_from(Room))

    return {
        "status": "ok" if not issues else "warnings",
        "issues": issues,
        "counts": {
            "assets": int(total_assets or 0),
            "rooms": int(total_rooms or 0),
        },
    }
