"""Guarded permanent deletion workflow for seven-day image retention.

The module is dependency-injected: callers must provide fresh database state,
Drive metadata, permanent-delete, and database-state callbacks. It has no
network or database access of its own, making safety rules unit-testable.
"""
from datetime import datetime, timezone

from image_retention import plan_image_retention

TEST_FOLDER_MIME = "application/vnd.google-apps.folder"


class RetentionExecutionError(RuntimeError):
    pass


def execute_one_image_deletion(
    asset,
    *,
    now=None,
    test_folder_id,
    load_current_asset,
    load_drive_metadata,
    permanent_delete,
    mark_deleted,
):
    """Permanently delete one eligible image, then mark only its asset row.

    The supplied callbacks must operate on the configured test environment.
    The caller is responsible for authentication and enforcing the test-only
    feature flag. No editorial or LinkedIn records are ever passed to
    mark_deleted.
    """
    if not test_folder_id:
        raise RetentionExecutionError("Test folder is not configured.")

    file_id = asset.get("drive_file_id") if isinstance(asset, dict) else None
    if not isinstance(file_id, str) or not file_id.strip():
        raise RetentionExecutionError("Missing Drive file ID.")

    current = load_current_asset(file_id)
    if not isinstance(current, dict):
        raise RetentionExecutionError("Asset record no longer exists.")
    if current.get("asset_status") != "stored":
        raise RetentionExecutionError("Asset is not in stored state.")
    if current.get("drive_file_id") != file_id:
        raise RetentionExecutionError("Drive file reference changed.")

    plan_input = {
        "drive_file_id": current.get("drive_file_id"),
        "mime_type": current.get("mime_type"),
        "editorial_post_id": current.get("editorial_post_id"),
        "publication_status": current.get("publication_status"),
        "published_at": current.get("published_at"),
    }
    plan = plan_image_retention([plan_input], now=now)
    if plan["eligible_count"] != 1:
        reason = plan["excluded"][0]["reason"] if plan["excluded"] else "not_eligible"
        raise RetentionExecutionError(f"Asset is not eligible: {reason}.")

    metadata = load_drive_metadata(file_id)
    if not isinstance(metadata, dict):
        raise RetentionExecutionError("Drive metadata unavailable.")
    parents = metadata.get("parents") or []
    if (
        metadata.get("id") != file_id
        or metadata.get("trashed") is not False
        or not str(metadata.get("mimeType") or "").lower().startswith("image/")
        or test_folder_id not in parents
    ):
        raise RetentionExecutionError(
            "Drive file identity, image MIME type, or test-folder membership failed."
        )

    # A confirmed 404/already-absent result may be treated as already deleted
    # by the Drive adapter; all other errors must raise and leave DB unchanged.
    delete_result = permanent_delete(file_id)
    if delete_result not in (True, "deleted", "already_deleted"):
        raise RetentionExecutionError("Drive did not confirm permanent deletion.")

    # This callback must update only project_assets, with a guarded WHERE clause.
    deleted_at = datetime.now(timezone.utc)\n    updated = mark_deleted(file_id, deleted_at)
    if updated is not True:
        raise RetentionExecutionError(
            "Drive deletion succeeded but database marking failed; manual reconciliation required."
        )

    return {
        "status": "deleted",
        "drive_file_id": file_id,
        "editorial_post_id": current.get("editorial_post_id"),
        "deleted_at": deleted_at.isoformat(),
        "drive_delete_result": delete_result,
        "preserved": [
            "editorial_posts",
            "LinkedIn identifiers, text, status, timestamps and metrics",
            "publication queue and publication history",
        ],
    }
