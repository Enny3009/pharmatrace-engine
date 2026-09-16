# migrations/versions/005_transfers_approvals_and_idempotency.py
"""005_transfers_approvals_and_idempotency

Revision ID: 005_complete_specs
Revises: 29bef24bce15
Create Date: 2026-09-16 13:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '005_complete_specs'
down_revision: Union[str, None] = '29bef24bce15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Idempotency Keys
    op.create_table(
        'idempotency_keys',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('request_path', sa.String(length=255), nullable=False),
        sa.Column('request_hash', sa.String(length=64), nullable=False),
        sa.Column('response_status', sa.Integer(), nullable=False),
        sa.Column('response_body', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'idempotency_key', name='uq_idempotency_org_key')
    )
    op.create_index(op.f('ix_idempotency_keys_expires_at'), 'idempotency_keys', ['expires_at'], unique=False)
    op.create_index(op.f('ix_idempotency_keys_organization_id'), 'idempotency_keys', ['organization_id'], unique=False)

    # 2. Inventory Adjustments
    op.create_table(
        'inventory_adjustments',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('requested_quantity', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('actual_quantity', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('difference', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('inventory_id', sa.Uuid(), nullable=False),
        sa.Column('requested_by', sa.Uuid(), nullable=False),
        sa.Column('approved_by', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['inventory_id'], ['inventory.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_inventory_adjustments_inventory_id'), 'inventory_adjustments', ['inventory_id'], unique=False)
    op.create_index(op.f('ix_inventory_adjustments_organization_id'), 'inventory_adjustments', ['organization_id'], unique=False)

    # 3. Stock Transfers
    op.create_table(
        'stock_transfers',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('batch_id', sa.Uuid(), nullable=False),
        sa.Column('source_location_id', sa.Uuid(), nullable=False),
        sa.Column('destination_location_id', sa.Uuid(), nullable=False),
        sa.Column('requested_by', sa.Uuid(), nullable=False),
        sa.Column('approved_by', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['destination_location_id'], ['storage_locations.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['source_location_id'], ['storage_locations.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_stock_transfers_organization_id'), 'stock_transfers', ['organization_id'], unique=False)

    # 4. Approval Requests
    op.create_table(
        'approval_requests',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('request_type', sa.String(length=64), nullable=False),
        sa.Column('reference_type', sa.String(length=64), nullable=False),
        sa.Column('reference_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('requested_by', sa.Uuid(), nullable=False),
        sa.Column('assigned_to', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_approval_requests_organization_id'), 'approval_requests', ['organization_id'], unique=False)
    op.create_index(op.f('ix_approval_requests_reference_id'), 'approval_requests', ['reference_id'], unique=False)

    # 5. Notifications & Deliveries
    op.create_table(
        'notifications',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('type', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notifications_created_at'), 'notifications', ['created_at'], unique=False)
    op.create_index(op.f('ix_notifications_organization_id'), 'notifications', ['organization_id'], unique=False)
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)

    op.create_table(
        'notification_deliveries',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('notification_id', sa.Uuid(), nullable=False),
        sa.Column('channel', sa.String(length=32), nullable=False),
        sa.Column('recipient', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notification_deliveries_notification_id'), 'notification_deliveries', ['notification_id'], unique=False)


def downgrade() -> None:
    op.drop_table('notification_deliveries')
    op.drop_table('notifications')
    op.drop_table('approval_requests')
    op.drop_table('stock_transfers')
    op.drop_table('inventory_adjustments')
    op.drop_table('idempotency_keys')