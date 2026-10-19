"""PostgreSQL-specific database objects (extensions + JSONB/FTRGM indexes).

Everything is guarded by a vendor check so SQLite dev/test environments stay
functional while production Postgres gets the high-performance paths.
"""
from django.db import migrations

SQL_STATEMENTS = [
    ("CREATE EXTENSION IF NOT EXISTS pg_trgm", "DROP EXTENSION IF EXISTS pg_trgm"),
    ("CREATE EXTENSION IF NOT EXISTS btree_gin", "DROP EXTENSION IF EXISTS btree_gin"),
]


def apply_objects(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for forward, _ in SQL_STATEMENTS:
        schema_editor.execute(forward)


def unapply_objects(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for _, reverse in reversed(SQL_STATEMENTS):
        schema_editor.execute(reverse)


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.RunPython(apply_objects, unapply_objects, elidable=False),
    ]
