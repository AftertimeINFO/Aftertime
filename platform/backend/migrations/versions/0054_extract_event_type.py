"""Event type "Produce" becomes "Extract", a kind of transfer (as are load and discharge).

Extraction moves matter out of a natural deposit without changing it, so mass-wise it is a
transfer; it keeps its own type because reserves are depleted by it. Events of the old type
move to the new one; the core seed recreates the subclass links.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0054_extract_event_type"
down_revision: str | None = "0053_world_computations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD, NEW = "type:produce", "type:extract"
TRANSFER_KINDS = ("type:extract", "type:load", "type:discharge")


def _rename(old: str, new: str, name: str) -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM entities WHERE id = :id"), {"id": old}).first() is None:
        return
    columns = [
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'entities' "
                "ORDER BY ordinal_position"
            )
        )
    ]
    copied = [c for c in columns if c not in ("id", "name")]
    names = ", ".join(copied)
    bind.execute(
        sa.text(
            f"INSERT INTO entities (id, name, {names}) "
            f"SELECT :new, :name, {names} FROM entities WHERE id = :old "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"old": old, "new": new, "name": name},
    )
    bind.execute(
        sa.text("UPDATE events SET event_type_id = :new WHERE event_type_id = :old"),
        {"old": old, "new": new},
    )
    # Vocabulary links of the old type; the core seed recreates them for the new one.
    bind.execute(
        sa.text("DELETE FROM relations WHERE subject_id = :old OR object_id = :old"),
        {"old": old},
    )
    bind.execute(sa.text("DELETE FROM entities WHERE id = :old"), {"old": old})


def upgrade() -> None:
    _rename(OLD, NEW, "Extract")
    # Extract, load and discharge now sit under transfer: drop their direct link to the
    # event-type root (the seed adds subclass_of transfer).
    op.get_bind().execute(
        sa.text(
            "DELETE FROM relations WHERE predicate = 'subclass_of' "
            "AND object_id = 'type:event-type' AND subject_id = ANY(:ids)"
        ),
        {"ids": list(TRANSFER_KINDS)},
    )


def downgrade() -> None:
    _rename(NEW, OLD, "Produce")
