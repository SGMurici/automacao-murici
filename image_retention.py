"""Seven-day image-retention planner.

This module is intentionally non-destructive. It only identifies image assets
that are explicitly linked to a published editorial record and whose
publication timestamp is at least seven full days old. It never mutates Drive
or LinkedIn records.
"""
from datetime import datetime, timedelta, timezone

RETENTION_DAYS = 7
IMAGE_MIME_PREFIX = "image/"


def _parse_timestamp(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        parsed = datetime.fromisoformat(normalized)
    else:
        return None

    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def plan_image_retention(assets, now=None, retention_days=RETENTION_DAYS):
    """Return a deterministic dry-run plan; no file or database writes occur.

    Required asset fields:
      drive_file_id, mime_type, editorial_post_id, publication_status,
      published_at.
    Unlinked, unpublished, non-image, or timezone-naive records are excluded.
    Duplicate Drive IDs are reported once and treated as ambiguous (excluded).
    """
    if retention_days != RETENTION_DAYS:
        raise ValueError("The approved retention period is fixed at seven days.")

    current = _parse_timestamp(now or datetime.now(timezone.utc))
    if current is None:
        raise ValueError("now must be a timezone-aware timestamp.")

    rows = list(assets or [])
    id_counts = {}
    for row in rows:
        if isinstance(row, dict):
            file_id = row.get("drive_file_id")
            if isinstance(file_id, str) and file_id.strip():
                id_counts[file_id] = id_counts.get(file_id, 0) + 1

    eligible, excluded = [], []
    cutoff_delta = timedelta(days=RETENTION_DAYS)

    for row in rows:
        reason = None
        if not isinstance(row, dict):
            excluded.append({"reason": "invalid_manifest_record"})
            continue

        file_id = row.get("drive_file_id")
        if not isinstance(file_id, str) or not file_id.strip():
            reason = "missing_drive_file_id"
        elif id_counts.get(file_id) != 1:
            reason = "duplicate_drive_file_reference"
        elif not str(row.get("mime_type") or "").lower().startswith(IMAGE_MIME_PREFIX):
            reason = "not_an_image"
        elif not row.get("editorial_post_id"):
            reason = "not_linked_to_editorial_post"
        elif str(row.get("publication_status") or "").lower() != "publicado":
            reason = "post_not_confirmed_published"
        else:
            published_at = _parse_timestamp(row.get("published_at"))
            if published_at is None:
                reason = "missing_or_timezone_naive_published_at"
            elif current < published_at + cutoff_delta:
                reason = "retention_period_not_completed"

        if reason:
            excluded.append({
                "drive_file_id": file_id if isinstance(file_id, str) else None,
                "reason": reason,
            })
            continue

        eligible.append({
            "drive_file_id": file_id,
            "editorial_post_id": row["editorial_post_id"],
            "published_at": published_at.isoformat(),
            "eligible_after": (published_at + cutoff_delta).isoformat(),
            "retention_days": RETENTION_DAYS,
        })

    return {
        "mode": "dry_run",
        "destructive": False,
        "retention_days": RETENTION_DAYS,
        "evaluated_at": current.isoformat(),
        "eligible_count": len(eligible),
        "excluded_count": len(excluded),
        "eligible": eligible,
        "excluded": excluded,
        "preserved_data": [
            "LinkedIn post text and identifiers",
            "publication timestamps and status",
            "metrics and publication history",
            "editorial and queue records",
        ],
    }
