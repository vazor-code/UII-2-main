"""Эндпоинты инвентаризации (Этап 6).

- Управление инвентаризациями (создание, статусы, утверждение)
- Позиции описи (фактические данные, фото, отметка проверки) — мобильный сценарий
- Расхождения (недостача/излишек)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, DbSession, Perm, require_permission
from app.models import Asset, Inventory, InventoryDiscrepancy, InventoryItem
from app.schemas.inventory import (
    DiscrepancyOut,
    DiscrepancyUpdate,
    InventoryApproveRequest,
    InventoryCreate,
    InventoryItemOut,
    InventoryItemUpdate,
    InventoryScanRequest,
    InventoryOut,
    InventoryUpdate,
)
from app.services.audit import write_audit
from app.services.storage import IMAGE_EXTENSIONS, delete_file, save_upload

router = APIRouter()


def _get_client_ip(request: Request) -> str | None:
    if request.client:
        return request.client.host
    return None


async def _get_inventory_or_404(db: AsyncSession, inventory_id: uuid.UUID) -> Inventory:
    inv = await db.get(Inventory, inventory_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Инвентаризация не найдена")
    return inv


async def _get_item_or_404(db: AsyncSession, item_id: uuid.UUID) -> InventoryItem:
    item = await db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Позиция описи не найдена")
    return item


def _item_out(item: InventoryItem, asset: Asset) -> dict:
    data = InventoryItemOut.model_validate(item).model_dump()
    data.update(asset_inventory_number=asset.inventory_number, asset_name=asset.name)
    return data


async def _require_editable(inv: Inventory) -> None:
    if inv.status == "APPROVED":
        raise HTTPException(status_code=400, detail="Утверждённую инвентаризацию нельзя изменять")


# --- Инвентаризации ---
@router.get(
    "",
    response_model=list[InventoryOut],
    dependencies=[Depends(require_permission(Perm.RUN_INVENTORY))],
    summary="Список инвентаризаций",
)
async def list_inventories(
    db: DbSession,
    status_filter: str | None = Query(default=None, alias="status"),
):
    stmt = select(Inventory).order_by(Inventory.created_at.desc())
    if status_filter:
        stmt = stmt.where(Inventory.status == status_filter)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post(
    "",
    response_model=InventoryOut,
    dependencies=[Depends(require_permission(Perm.RUN_INVENTORY))],
    summary="Создание инвентаризации",
)
async def create_inventory(
    payload: InventoryCreate,
    db: DbSession,
    user: CurrentUser,
    request: Request,
):
    inv = Inventory(
        name=payload.name,
        inv_type=payload.inv_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        coverage=payload.coverage,
        commission=payload.commission,
        building_id=payload.building_id,
        room_id=payload.room_id,
        department=payload.department,
        created_by_id=user.id,
    )
    db.add(inv)
    await write_audit(
        db,
        user_id=user.id,
        action="CREATE",
        entity_type="inventory",
        entity_id=str(inv.id),
        new_value=payload.name,
        ip_address=_get_client_ip(request),
    )
    await db.commit()
    await db.refresh(inv)
    return inv


@router.get(
    "/{inventory_id}",
    response_model=InventoryOut,
    dependencies=[Depends(require_permission(Perm.RUN_INVENTORY))],
    summary="Инвентаризация по id",
)
async def get_inventory(inventory_id: uuid.UUID, db: DbSession):
    return await _get_inventory_or_404(db, inventory_id)


@router.patch(
    "/{inventory_id}",
    response_model=InventoryOut,
    dependencies=[Depends(require_permission(Perm.RUN_INVENTORY))],
    summary="Обновление инвентаризации",
)
async def update_inventory(
    inventory_id: uuid.UUID,
    payload: InventoryUpdate,
    db: DbSession,
    user: CurrentUser,
    request: Request,
):
    inv = await _get_inventory_or_404(db, inventory_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(inv, field, value)
    await write_audit(
        db,
        user_id=user.id,
        action="UPDATE",
        entity_type="inventory",
        entity_id=str(inv.id),
        ip_address=_get_client_ip(request),
    )
    await db.commit()
    await db.refresh(inv)
    return inv


@router.post(
    "/{inventory_id}/start",
    response_model=InventoryOut,
    dependencies=[Depends(require_permission(Perm.RUN_INVENTORY))],
    summary="Начало инвентаризации",
)
async def start_inventory(
    inventory_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
):
    inv = await _get_inventory_or_404(db, inventory_id)
    inv.status = "IN_PROGRESS"
    inv.start_date = inv.start_date or datetime.now().date()

    # Формируем позиции описи по всем карточкам
    existing = await db.execute(
        select(InventoryItem).where(InventoryItem.inventory_id == inv.id)
    )
    if existing.scalar_one_or_none() is None:
        assets = await db.execute(select(Asset).where(Asset.status != "WRITTEN_OFF"))
        for asset in assets.scalars().all():
            item = InventoryItem(
                inventory_id=inv.id,
                asset_id=asset.id,
                accounting_quantity=asset.quantity,
                accounting_status=asset.status,
            )
            db.add(item)

    await write_audit(
        db,
        user_id=user.id,
        action="INVENTORY_START",
        entity_type="inventory",
        entity_id=str(inv.id),
        ip_address=None,
    )
    await db.commit()
    await db.refresh(inv)
    return inv


@router.post(
    "/{inventory_id}/complete",
    response_model=InventoryOut,
    dependencies=[Depends(require_permission(Perm.RUN_INVENTORY))],
    summary="Завершение инвентаризации",
)
async def complete_inventory(
    inventory_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
):
    inv = await _get_inventory_or_404(db, inventory_id)
    inv.status = "COMPLETED"
    inv.end_date = inv.end_date or datetime.now().date()

    # Автоматически формируем расхождения по несовпадающим позициям
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.inventory_id == inv.id)
    )
    for item in result.scalars().all():
        if item.accounting_quantity is None or item.actual_quantity is None:
            continue
        diff = item.actual_quantity - item.accounting_quantity
        if diff != 0:
            discrepancy_type = "SURPLUS" if diff > 0 else "SHORTAGE"
            exists = await db.execute(
                select(InventoryDiscrepancy).where(
                    InventoryDiscrepancy.inventory_id == inv.id,
                    InventoryDiscrepancy.inventory_item_id == item.id,
                )
            )
            if exists.scalar_one_or_none() is None:
                db.add(
                    InventoryDiscrepancy(
                        inventory_id=inv.id,
                        inventory_item_id=item.id,
                        asset_id=item.asset_id,
                        discrepancy_type=discrepancy_type,
                        accounting_quantity=item.accounting_quantity,
                        actual_quantity=item.actual_quantity,
                        difference=abs(diff),
                    )
                )

    await write_audit(
        db,
        user_id=user.id,
        action="INVENTORY_COMPLETE",
        entity_type="inventory",
        entity_id=str(inv.id),
        ip_address=None,
    )
    await db.commit()
    await db.refresh(inv)
    return inv


@router.post(
    "/{inventory_id}/approve",
    response_model=InventoryOut,
    dependencies=[Depends(require_permission(Perm.APPROVE_INVENTORY))],
    summary="Утверждение инвентаризации",
)
async def approve_inventory(
    inventory_id: uuid.UUID,
    payload: InventoryApproveRequest,
    db: DbSession,
    user: CurrentUser,
    request: Request,
):
    inv = await _get_inventory_or_404(db, inventory_id)
    inv.status = "APPROVED"
    inv.approved_by_id = user.id
    inv.approved_at = datetime.now(timezone.utc)

    await write_audit(
        db,
        user_id=user.id,
        action="INVENTORY_APPROVE",
        entity_type="inventory",
        entity_id=str(inv.id),
        comment=payload.comment,
        ip_address=_get_client_ip(request),
    )
    await db.commit()
    await db.refresh(inv)
    return inv


# --- Позиции описи ---
@router.get(
    "/{inventory_id}/items",
    response_model=list[InventoryItemOut],
    dependencies=[Depends(require_permission(Perm.RUN_INVENTORY))],
    summary="Позиции описи",
)
async def list_items(
    inventory_id: uuid.UUID,
    db: DbSession,
    only_checked: bool | None = Query(default=None, alias="checked"),
):
    await _get_inventory_or_404(db, inventory_id)
    stmt = select(InventoryItem).where(
        InventoryItem.inventory_id == inventory_id
    )
    if only_checked is not None:
        stmt = stmt.where(InventoryItem.is_checked.is_(only_checked))
    result = await db.execute(stmt)
    items = result.scalars().all()
    assets = {
        asset.id: asset
        for asset in (await db.execute(select(Asset).where(Asset.id.in_([item.asset_id for item in items])))).scalars().all()
    }
    return [_item_out(item, assets[item.asset_id]) for item in items]


@router.post(
    "/{inventory_id}/scan",
    response_model=InventoryItemOut,
    dependencies=[Depends(require_permission(Perm.RUN_INVENTORY))],
    summary="Отметка позиции по QR/штрих-коду или инвентарному номеру",
)
async def scan_item(
    inventory_id: uuid.UUID,
    payload: InventoryScanRequest,
    db: DbSession,
    user: CurrentUser,
):
    """Находит позицию описи по инвентарному номеру и фиксирует её наличие."""
    inv = await _get_inventory_or_404(db, inventory_id)
    await _require_editable(inv)
    result = await db.execute(
        select(InventoryItem)
        .join(Asset, InventoryItem.asset_id == Asset.id)
        .where(
            InventoryItem.inventory_id == inventory_id,
            Asset.inventory_number == payload.code.strip(),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Имущество с таким номером не входит в опись")
    item.actual_quantity = payload.actual_quantity if payload.actual_quantity is not None else item.accounting_quantity
    item.is_checked = True
    item.checked_by_id = user.id
    item.checked_at = datetime.now(timezone.utc)
    await write_audit(
        db,
        user_id=user.id,
        action="INVENTORY_SCAN",
        entity_type="inventory_item",
        entity_id=str(item.id),
        new_value=payload.code.strip(),
    )
    await db.commit()
    await db.refresh(item)
    return _item_out(item, await db.get(Asset, item.asset_id))


@router.patch(
    "/{inventory_id}/items/{item_id}",
    response_model=InventoryItemOut,
    dependencies=[Depends(require_permission(Perm.RUN_INVENTORY))],
    summary="Фиксация фактических данных позиции (мобильный сценарий)",
)
async def update_item(
    inventory_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: InventoryItemUpdate,
    db: DbSession,
    user: CurrentUser,
):
    inv = await _get_inventory_or_404(db, inventory_id)
    await _require_editable(inv)
    item = await _get_item_or_404(db, item_id)
    if item.inventory_id != inventory_id:
        raise HTTPException(status_code=400, detail="Позиция не относится к этой инвентаризации")

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(item, field, value)
    # фиксируем проверку
    if "actual_quantity" in data or "actual_status" in data:
        item.is_checked = True
        item.checked_by_id = user.id
        item.checked_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(item)
    return _item_out(item, await db.get(Asset, item.asset_id))


@router.post(
    "/{inventory_id}/items/{item_id}/photo", response_model=InventoryItemOut,
    dependencies=[Depends(require_permission(Perm.RUN_INVENTORY))], summary="Фотофиксация позиции описи",
)
async def upload_item_photo(inventory_id: uuid.UUID, item_id: uuid.UUID, db: DbSession, user: CurrentUser, file: UploadFile = File(...)):
    inv = await _get_inventory_or_404(db, inventory_id)
    await _require_editable(inv)
    item = await _get_item_or_404(db, item_id)
    if item.inventory_id != inventory_id:
        raise HTTPException(status_code=400, detail="Позиция не относится к этой инвентаризации")
    path, _, _ = await save_upload(file, subdir=f"inventory/{inventory_id}/{item_id}", allowed_extensions=IMAGE_EXTENSIONS)
    if item.photo_path:
        delete_file(item.photo_path)
    item.photo_path = path
    item.is_checked = True
    item.checked_by_id = user.id
    item.checked_at = datetime.now(timezone.utc)
    await write_audit(
        db,
        user_id=user.id,
        action="INVENTORY_PHOTO_UPLOAD",
        entity_type="inventory_item",
        entity_id=str(item.id),
        new_value=path,
    )
    await db.commit()
    await db.refresh(item)
    return _item_out(item, await db.get(Asset, item.asset_id))


# --- Расхождения ---
@router.get(
    "/{inventory_id}/discrepancies",
    response_model=list[DiscrepancyOut],
    dependencies=[Depends(require_permission(Perm.RUN_INVENTORY))],
    summary="Расхождения по инвентаризации",
)
async def list_discrepancies(inventory_id: uuid.UUID, db: DbSession):
    await _get_inventory_or_404(db, inventory_id)
    result = await db.execute(
        select(InventoryDiscrepancy).where(
            InventoryDiscrepancy.inventory_id == inventory_id
        )
    )
    return result.scalars().all()


@router.patch(
    "/{inventory_id}/discrepancies/{discrepancy_id}",
    response_model=DiscrepancyOut,
    dependencies=[Depends(require_permission(Perm.APPROVE_INVENTORY))],
    summary="Расследование/закрытие расхождения",
)
async def update_discrepancy(
    inventory_id: uuid.UUID,
    discrepancy_id: uuid.UUID,
    payload: DiscrepancyUpdate,
    db: DbSession,
    user: CurrentUser,
):
    inv = await _get_inventory_or_404(db, inventory_id)
    disc = await db.get(InventoryDiscrepancy, discrepancy_id)
    if disc is None:
        raise HTTPException(status_code=404, detail="Расхождение не найдено")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(disc, field, value)
    await write_audit(
        db,
        user_id=user.id,
        action="DISCREPANCY_UPDATE",
        entity_type="inventory_discrepancy",
        entity_id=str(disc.id),
        new_value=str(data),
    )
    await db.commit()
    await db.refresh(disc)
    return disc
