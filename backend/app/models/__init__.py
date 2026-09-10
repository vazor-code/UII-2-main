"""Модели данных приложения.

Импортируем все модели, чтобы они попали в metadata (Base.metadata)
и были доступны через единую точку входа.
"""

from app.database import Base
from app.models.base import (
    TimestampMixin,
    DocumentStatusMixin,
    DocumentStatusEnum,
    UUID_PK,
)
from app.models.auth import (
    User,
    Role,
    Permission,
    UserRole,
    RolePermission,
    Delegation,
)
from app.models.structure import Building, Room
from app.models.reference import AssetStatus, UnitOfMeasure, Material
from app.models.asset import (
    AssetType,
    AssetAttribute,
    Asset,
    AssetNumberReservation,
)
from app.models.operation import AssetMove, Receipt, ReceiptAsset, WriteOff, Repair, Issuance
from app.models.inventory import Inventory, InventoryItem, InventoryDiscrepancy
from app.models.document import Document, DocumentVersion
from app.models.audit import AuditLog
from app.models.report import ReportJob

__all__ = [
    "Base",
    "TimestampMixin",
    "DocumentStatusMixin",
    "DocumentStatusEnum",
    "UUID_PK",
    # auth
    "User",
    "Role",
    "Permission",
    "UserRole",
    "RolePermission",
    "Delegation",
    # structure
    "Building",
    "Room",
    # reference
    "AssetStatus",
    "UnitOfMeasure",
    "Material",
    # asset
    "AssetType",
    "AssetAttribute",
    "Asset",
    "AssetNumberReservation",
    # operation
    "AssetMove",
    "Receipt",
    "ReceiptAsset",
    "WriteOff",
    "Repair",
    "Issuance",
    # inventory
    "Inventory",
    "InventoryItem",
    "InventoryDiscrepancy",
    # document
    "Document",
    "DocumentVersion",
    # audit
    "AuditLog",
    # report
    "ReportJob",
]
