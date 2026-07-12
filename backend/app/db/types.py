"""Portable column types.

The production target is Supabase Postgres, but the test suite runs against
SQLite so models can be exercised without a live database. These helpers pick
the best native type per dialect: ``JSONB`` / native ``UUID`` on Postgres and
portable equivalents elsewhere.
"""

from sqlalchemy import JSON, Uuid
from sqlalchemy.dialects.postgresql import JSONB

# JSONB on Postgres, generic JSON everywhere else.
JSONType = JSON().with_variant(JSONB(), "postgresql")

# Native UUID on Postgres, CHAR(32) elsewhere. ``as_uuid=True`` keeps Python
# ``uuid.UUID`` values on both sides of the boundary.
GUID = Uuid(as_uuid=True)
