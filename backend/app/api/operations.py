"""Эндпоинты операций с имуществом (Этап 5).

- Перемещение (asset_moves)
- Списание (write_offs) с согласованием
- Ремонт/обслуживание (repairs)
- Выдача/возврат (issuances)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, DbSession, Perm, require_permission
from app.models import (
    Asset,
    AssetMove,
    Document,
    Issuance,
    Receipt,
    ReceiptAsset,
    Repair,
    WriteOff,
)
from app.models.base import DocumentStatusEnum
from app.schemas.operation import (
    AssetMoveCreate,
    AssetMoveOut,
    IssuanceCreate,
    IssuanceOut,
    IssuanceReturnRequest,
    RepairCreate,
    RepairOut,
    RepairUpdate,
    ReceiptCreate,
    ReceiptOut,
    StatusChangeRequest,
    WriteOffCreate,
    WriteOffOut,
    WriteOffUpdate,
)
from app.services.audit import write_audit

router = APIRouter()


def _get_client_ip(request: Request) -> str | None:
    if request.client:
        return request.client.host
    return None


async def _get_asset(db: AsyncSession, asset_id: uuid.UUID) -> Asset:
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Имущество не найдено")
    return asset


async def _receipt_out(db: AsyncSession, receipt: Receipt) -> dict:
    result = await db.execute(select(ReceiptAsset.asset_id).where(ReceiptAsset.receipt_id == receipt.id))
    return {
        "id": receipt.id, "receipt_type": receipt.receipt_type, "received_at": receipt.received_at,
        "counterparty": receipt.counterparty, "basis_number": receipt.basis_number,
        "comment": receipt.comment, "status": receipt.status, "created_by_id": receipt.created_by_id,
        "created_at": receipt.created_at, "asset_ids": [row[0] for row in result.all()],
    }


# --- Поступления ---
@router.get(
    "/receipts", response_model=list[ReceiptOut],
    dependencies=[Depends(require_permission(Perm.VIEW_CARDS))], summary="Список поступлений",
)
async def list_receipts(db: DbSession, asset_id: uuid.UUID | None = None):
    stmt = select(Receipt).order_by(Receipt.created_at.desc())
    if asset_id:
        stmt = stmt.join(ReceiptAsset, ReceiptAsset.receipt_id == Receipt.id).where(ReceiptAsset.asset_id == asset_id)
    result = await db.execute(stmt)
    return [await _receipt_out(db, receipt) for receipt in result.scalars().all()]


@router.post(
    "/receipts", response_model=ReceiptOut,
    dependencies=[Depends(require_permission(Perm.CREATE_CARD))], summary="Создание поступления",
)
async def create_receipt(payload: ReceiptCreate, db: DbSession, user: CurrentUser, request: Request):
    receipt = Receipt(
        receipt_type=payload.receipt_type, received_at=payload.received_at,
        counterparty=payload.counterparty, basis_number=payload.basis_number,
        comment=payload.comment, created_by_id=user.id,
    )
    db.add(receipt)
    await db.flush()
    for asset_id in set(payload.asset_ids):
        await _get_asset(db, asset_id)
        db.add(ReceiptAsset(receipt_id=receipt.id, asset_id=asset_id))
    await write_audit(db, user_id=user.id, action="CREATE", entity_type="receipt", entity_id=str(receipt.id), new_value=receipt.receipt_type, ip_address=_get_client_ip(request))
    await db.commit()
    await db.refresh(receipt)
    return await _receipt_out(db, receipt)


@router.get(
    "/receipts/{receipt_id}", response_model=ReceiptOut,
    dependencies=[Depends(require_permission(Perm.VIEW_CARDS))], summary="Поступление по id",
)
async def get_receipt(receipt_id: uuid.UUID, db: DbSession):
    receipt = await db.get(Receipt, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Поступление не найдено")
    return await _receipt_out(db, receipt)


@router.post(
    "/receipts/{receipt_id}/complete", response_model=ReceiptOut,
    dependencies=[Depends(require_permission(Perm.CREATE_CARD))], summary="Завершение поступления",
)
async def complete_receipt(receipt_id: uuid.UUID, db: DbSession, user: CurrentUser, request: Request):
    receipt = await db.get(Receipt, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Поступление не найдено")
    if receipt.status == DocumentStatusEnum.APPROVED.value:
        raise HTTPException(status_code=400, detail="Поступление уже завершено")
    basis = await db.scalar(select(Document.id).where(Document.receipt_id == receipt.id).limit(1))
    if basis is None:
        raise HTTPException(status_code=400, detail="Для завершения прикрепите документ-основание")
    receipt.status = DocumentStatusEnum.APPROVED.value
    receipt.status_changed_by_id = user.id
    receipt.status_changed_at = datetime.now(timezone.utc)
    await write_audit(db, user_id=user.id, action="RECEIPT_COMPLETE", entity_type="receipt", entity_id=str(receipt.id), ip_address=_get_client_ip(request))
    await db.commit()
    await db.refresh(receipt)
    return await _receipt_out(db, receipt)


# --- Перемещения ---
@router.get(
    "/moves",
    response_model=list[AssetMoveOut],
    dependencies=[Depends(require_permission(Perm.VIEW_CARDS))],
    summary="История перемещений",
)
async def list_moves(db: DbSession, asset_id: uuid.UUID | None = None):
    stmt = select(AssetMove).order_by(AssetMove.moved_at.desc())
    if asset_id:
        stmt = stmt.where(AssetMove.asset_id == asset_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post(
    "/moves",
    response_model=AssetMoveOut,
    dependencies=[Depends(require_permission(Perm.MOVE_ASSET))],
    summary="Перемещение имущества",
)
async def create_move(
    payload: AssetMoveCreate,
    db: DbSession,
    user: CurrentUser,
    request: Request,
):
    asset = await _get_asset(db, payload.asset_id)
    move = AssetMove(
        asset_id=payload.asset_id,
        from_room_id=asset.room_id,
        to_room_id=payload.to_room_id,
        reason=payload.reason,
        moved_by_id=user.id,
    )
    # обновляем расположение карточки
    if payload.to_room_id is not None:
        asset.room_id = payload.to_room_id
    asset.status = "MOVED"

    db.add(move)
    await write_audit(
        db,
        user_id=user.id,
        action="MOVE",
        entity_type="asset",
        entity_id=str(asset.id),
        new_value=f"из {move.from_room_id} в {move.to_room_id}",
        ip_address=_get_client_ip(request),
    )
    await db.commit()
    await db.refresh(move)
    return move


# --- Списание ---
@router.get(
    "/write-offs",
    response_model=list[WriteOffOut],
    dependencies=[Depends(require_permission(Perm.VIEW_CARDS))],
    summary="Список списаний",
)
async def list_write_offs(db: DbSession):
    result = await db.execute(select(WriteOff).order_by(WriteOff.created_at.desc()))
    return result.scalars().all()


@router.post(
    "/write-offs",
    response_model=WriteOffOut,
    dependencies=[Depends(require_permission(Perm.CREATE_CARD))],
    summary="Создание акта списания",
)
async def create_write_off(
    payload: WriteOffCreate,
    db: DbSession,
    user: CurrentUser,
    request: Request,
):
    await _get_asset(db, payload.asset_id)
    write_off = WriteOff(
        asset_id=payload.asset_id,
        reason=payload.reason,
        commission_members=payload.commission_members,
        write_off_date=payload.write_off_date,
        created_by_id=user.id,
    )
    db.add(write_off)
    await write_audit(
        db,
        user_id=user.id,
        action="CREATE",
        entity_type="write_off",
        entity_id=str(write_off.id),
        ip_address=_get_client_ip(request),
    )
    await db.commit()
    await db.refresh(write_off)
    return write_off


@router.post(
    "/write-offs/{write_off_id}/status",
    response_model=WriteOffOut,
    dependencies=[Depends(require_permission(Perm.APPROVE_WRITEOFF))],
    summary="Смена статуса акта списания",
)
async def change_write_off_status(
    write_off_id: uuid.UUID,
    payload: StatusChangeRequest,
    db: DbSession,
    user: CurrentUser,
    request: Request,
):
    write_off = await db.get(WriteOff, write_off_id)
    if write_off is None:
        raise HTTPException(status_code=404, detail="Акт списания не найден")
    write_off.status = payload.status
    write_off.status_changed_by_id = user.id
    write_off.status_changed_at = datetime.now(timezone.utc)

    # при утверждении — списываем имущество
    if payload.status == DocumentStatusEnum.APPROVED.value:
        asset = await _get_asset(db, write_off.asset_id)
        asset.status = "WRITTEN_OFF"
        asset.write_off_date = write_off.write_off_date or datetime.now().date()

    await write_audit(
        db,
        user_id=user.id,
        action="STATUS_CHANGE",
        entity_type="write_off",
        entity_id=str(write_off.id),
        new_value=payload.status,
        comment=payload.comment,
        ip_address=_get_client_ip(request),
    )
    await db.commit()
    await db.refresh(write_off)
    return write_off


@router.patch(
    "/write-offs/{write_off_id}",
    response_model=WriteOffOut,
    dependencies=[Depends(require_permission(Perm.EDIT_CARD))],
    summary="Обновление акта списания",
)
async def update_write_off(
    write_off_id: uuid.UUID,
    payload: WriteOffUpdate,
    db: DbSession,
):
    write_off = await db.get(WriteOff, write_off_id)
    if write_off is None:
        raise HTTPException(status_code=404, detail="Акт списания не найден")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(write_off, field, value)
    await db.commit()
    await db.refresh(write_off)
    return write_off


# --- Ремонт ---
@router.get(
    "/repairs",
    response_model=list[RepairOut],
    dependencies=[Depends(require_permission(Perm.VIEW_CARDS))],
    summary="Список ремонтов",
)
async def list_repairs(db: DbSession, asset_id: uuid.UUID | None = None):
    stmt = select(Repair).order_by(Repair.created_at.desc())
    if asset_id:
        stmt = stmt.where(Repair.asset_id == asset_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post(
    "/repairs",
    response_model=RepairOut,
    dependencies=[Depends(require_permission(Perm.EDIT_CARD))],
    summary="Направление в ремонт",
)
async def create_repair(
    payload: RepairCreate,
    db: DbSession,
    user: CurrentUser,
    request: Request,
):
    asset = await _get_asset(db, payload.asset_id)
    asset.status = "ON_REPAIR"
    repair = Repair(
        asset_id=payload.asset_id,
        contractor=payload.contractor,
        description=payload.description,
        start_date=payload.start_date,
        end_date=payload.end_date,
        cost=payload.cost,
        warranty_until=payload.warranty_until,
        is_guarantee=payload.is_guarantee,
        act_number=payload.act_number,
        created_by_id=user.id,
    )
    db.add(repair)
    await write_audit(
        db,
        user_id=user.id,
        action="REPAIR",
        entity_type="asset",
        entity_id=str(asset.id),
        ip_address=_get_client_ip(request),
    )
    await db.commit()
    await db.refresh(repair)
    return repair


@router.patch(
    "/repairs/{repair_id}",
    response_model=RepairOut,
    dependencies=[Depends(require_permission(Perm.EDIT_CARD))],
    summary="Завершение/обновление ремонта",
)
async def update_repair(
    repair_id: uuid.UUID,
    payload: RepairUpdate,
    db: DbSession,
):
    repair = await db.get(Repair, repair_id)
    if repair is None:
        raise HTTPException(status_code=404, detail="Ремонт не найден")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(repair, field, value)
    # если указана дата окончания — имущество снова в обороте
    if payload.end_date is not None:
        asset = await _get_asset(db, repair.asset_id)
        if asset.status == "ON_REPAIR":
            asset.status = "IN_STOCK"
    await db.commit()
    await db.refresh(repair)
    return repair


# --- Выдача / возврат ---
@router.get(
    "/issuances",
    response_model=list[IssuanceOut],
    dependencies=[Depends(require_permission(Perm.VIEW_CARDS))],
    summary="Список выдач",
)
async def list_issuances(db: DbSession, asset_id: uuid.UUID | None = None):
    stmt = select(Issuance).order_by(Issuance.created_at.desc())
    if asset_id:
        stmt = stmt.where(Issuance.asset_id == asset_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post(
    "/issuances",
    response_model=IssuanceOut,
    dependencies=[Depends(require_permission(Perm.MOVE_ASSET))],
    summary="Выдача имущества",
)
async def create_issuance(
    payload: IssuanceCreate,
    db: DbSession,
    user: CurrentUser,
    request: Request,
):
    asset = await _get_asset(db, payload.asset_id)
    asset.status = "ISSUED"
    issuance = Issuance(
        asset_id=payload.asset_id,
        issued_to_id=payload.issued_to_id,
        issued_by_id=user.id,
        issued_at=datetime.now(timezone.utc),
        expected_return=payload.expected_return,
        reason=payload.reason,
        created_by_id=user.id,
    )
    db.add(issuance)
    await write_audit(
        db,
        user_id=user.id,
        action="ISSUE",
        entity_type="asset",
        entity_id=str(asset.id),
        new_value=f"выдано {payload.issued_to_id}",
        ip_address=_get_client_ip(request),
    )
    await db.commit()
    await db.refresh(issuance)
    return issuance


@router.post(
    "/issuances/{issuance_id}/return",
    response_model=IssuanceOut,
    dependencies=[Depends(require_permission(Perm.MOVE_ASSET))],
    summary="Возврат имущества",
)
async def return_issuance(
    issuance_id: uuid.UUID,
    payload: IssuanceReturnRequest,
    db: DbSession,
    user: CurrentUser,
    request: Request,
):
    issuance = await db.get(Issuance, issuance_id)
    if issuance is None:
        raise HTTPException(status_code=404, detail="Выдача не найдена")
    if issuance.is_returned:
        raise HTTPException(status_code=400, detail="Имущество уже возвращено")

    issuance.is_returned = True
    issuance.return_at = datetime.now(timezone.utc)
    issuance.returned_condition = payload.returned_condition

    asset = await _get_asset(db, issuance.asset_id)
    if asset.status == "ISSUED":
        asset.status = "IN_STOCK"

    await write_audit(
        db,
        user_id=user.id,
        action="RETURN",
        entity_type="asset",
        entity_id=str(asset.id),
        ip_address=_get_client_ip(request),
    )
    await db.commit()
    await db.refresh(issuance)
    return issuance
