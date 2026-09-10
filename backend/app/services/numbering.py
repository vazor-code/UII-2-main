"""Сервис генерации инвентарных номеров и резервирования.

Шаблон: {Год}-{Тип}-{№} — настраивается в asset_types.number_template.
Поддерживаются плейсхолдеры:
  {Год}   — текущий год
  {Тип}   — код типа объекта (asset_type.code)
  {№}     — порядковый номер (автоинкремент)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset, AssetNumberReservation, AssetType

# Плейсхолдеры шаблона
DEFAULT_TEMPLATE = "{Год}-{Тип}-{№}"


def _safe_filename_template(template: str) -> str:
    return template or DEFAULT_TEMPLATE


async def _next_sequence(db: AsyncSession, asset_type_id) -> int:
    """Возвращает следующий номер для типа независимо от шаблона записи."""
    count = await db.scalar(
        select(func.count())
        .select_from(Asset)
        .where(Asset.asset_type_id == asset_type_id)
    )
    used_res = await db.scalar(
        select(func.count())
        .select_from(AssetNumberReservation)
        .where(AssetNumberReservation.asset_type_id == asset_type_id)
    )
    return int(count or 0) + int(used_res or 0) + 1


def _render(template: str, year: int, type_code: str, seq: int) -> str:
    """Подставляет значения в шаблон."""
    return (
        template
        .replace("{Год}", str(year))
        .replace("{Тип}", type_code)
        .replace("{№}", str(seq))
        # English aliases are accepted too, so older manually-created
        # templates continue to produce usable inventory numbers.
        .replace("{YYYY}", str(year))
        .replace("{TYPE}", type_code)
        .replace("{SEQ}", str(seq))
    )


async def generate_number(
    db: AsyncSession,
    *,
    asset_type: AssetType,
    reserved_by_id,
) -> str:
    """Генерирует инвентарный номер и сразу резервирует его."""
    template = _safe_filename_template(asset_type.number_template)
    year = datetime.now().year
    seq = await _next_sequence(db, asset_type.id)
    number = _render(template, year, asset_type.code, seq)

    # Создаём резервацию
    reservation = AssetNumberReservation(
        inventory_number=number,
        asset_type_id=asset_type.id,
        reserved_by_id=reserved_by_id,
        is_used=False,
    )
    db.add(reservation)
    await db.flush()
    return number
