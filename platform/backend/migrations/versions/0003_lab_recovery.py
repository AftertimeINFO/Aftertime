"""Model Lab recovery pools and work orders."""
from collections.abc import Sequence
from alembic import op
from app.db import Base
from app import models  # noqa: F401
revision: str = "0003_lab_recovery"
down_revision: str | None = "0002_model_lab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
def upgrade() -> None: Base.metadata.create_all(bind=op.get_bind())
def downgrade() -> None:
    op.drop_table("lab_work_orders"); op.drop_table("lab_resource_pools")
