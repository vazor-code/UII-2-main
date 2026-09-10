"""add receipts and document relations

Revision ID: 0004_receipts_and_document_links
Revises: 0003_document_versions
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_receipts_and_document_links"
down_revision: Union[str, None] = "0003_document_versions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "receipts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("receipt_type", sa.String(32), nullable=False),
        sa.Column("received_at", sa.Date(), nullable=False),
        sa.Column("counterparty", sa.String(255), nullable=True),
        sa.Column("basis_number", sa.String(128), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("status_changed_by_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["status_changed_by_id"], ["users.id"]),
    )
    op.create_table(
        "receipt_assets",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("receipt_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.UniqueConstraint("receipt_id", "asset_id", name="uq_receipt_asset"),
    )
    op.create_index("ix_receipt_assets_receipt_id", "receipt_assets", ["receipt_id"])
    op.create_index("ix_receipt_assets_asset_id", "receipt_assets", ["asset_id"])
    op.add_column("documents", sa.Column("receipt_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("documents", sa.Column("discrepancy_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_documents_receipt", "documents", "receipts", ["receipt_id"], ["id"])
    op.create_foreign_key("fk_documents_discrepancy", "documents", "inventory_discrepancies", ["discrepancy_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_documents_discrepancy", "documents", type_="foreignkey")
    op.drop_constraint("fk_documents_receipt", "documents", type_="foreignkey")
    op.drop_column("documents", "discrepancy_id")
    op.drop_column("documents", "receipt_id")
    op.drop_index("ix_receipt_assets_asset_id", table_name="receipt_assets")
    op.drop_index("ix_receipt_assets_receipt_id", table_name="receipt_assets")
    op.drop_table("receipt_assets")
    op.drop_table("receipts")
