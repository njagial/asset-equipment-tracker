"""Server-side fuzzy search helpers.

On PostgreSQL, rows are ranked with pg_trgm *trigram similarity* across tags,
serial numbers, locations and names. On SQLite (local dev/tests) the same
query falls back to case-insensitive OR matching so behaviour is testable
without Postgres.
"""
from django.contrib.postgres.search import TrigramSimilarity
from django.db import connection, models

SEARCH_FIELDS = ("asset_tag", "serial_number", "location", "name", "barcode_qr_data")


def fuzzy_search_queryset(queryset, term, fields="asset_search"):
    if not term or not term.strip():
        return queryset
    term = term.strip()
    if fields == "asset_search":
        targets = SEARCH_FIELDS
    else:
        targets = tuple(fields)

    if connection.vendor == "postgresql":
        annotations = {}
        for i, f in enumerate(targets):
            annotations[f"sim_{i}"] = TrigramSimilarity(f, term)
        queryset = queryset.annotate(**annotations).annotate(
            _sim=models.Greatest(*annotations.keys())
        ).filter(_sim__gte=0.05).order_by("-_sim")
        return queryset

    q = models.Q()
    for f in targets:
        kw = {f"{f}__icontains": term}
        q |= models.Q(**kw)
    return queryset.filter(q).distinct()
