"""Guarded, dependency-injected permanent deletion workflow."""
from datetime import datetime, timezone
from image_retention import plan_image_retention


class RetentionExecutionError(RuntimeError):
    pass


def execute_one_image_deletion(
    asset, *, test_folder_id, asset_lock, load_current_asset,
    load_drive_metadata, permanent_delete, mark_deleted, record_audit,
    now=None,
):
    """Run under an exclusive per-asset lock; callbacks must use test resources."""
    if not test_folder_id:
        raise RetentionExecutionError("Test folder is not configured.")
    file_id = asset.get("drive_file_id") if isinstance(asset, dict) else None
    if not isinstance(file_id, str) or not file_id.strip():
        raise RetentionExecutionError("Missing Drive file ID.")

    with asset_lock(file_id):
        current = load_current_asset(file_id)
        if not isinstance(current, dict):
            raise RetentionExecutionError("Asset record no longer exists.")
        if current.get("asset_status") != "stored" or current.get("drive_file_id") != file_id:
            raise RetentionExecutionError("Asset state or Drive reference changed.")

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
        parents = (metadata.get("parents") or []) if isinstance(metadata, dict) else []
        if (
            not isinstance(metadata, dict)
            or metadata.get("id") != file_id
            or metadata.get("trashed") is not False
            or not str(metadata.get("mimeType") or "").lower().startswith("image/")
            or test_folder_id not in parents
        ):
            raise RetentionExecutionError("Drive identity, MIME type, trashed state, or test-folder membership failed.")

        # The adapter may return already_deleted only after an authoritative 404.
        delete_result = permanent_delete(file_id)
        if delete_result not in (True, "deleted", "already_deleted"):
            raise RetentionExecutionError("Drive did not confirm permanent deletion.")

        deleted_at = datetime.now(timezone.utc)
        if mark_deleted(file_id, deleted_at) is not True:
            record_audit({
                "event": "drive_deleted_database_reconciliation_required",
                "drive_file_id": file_id,
                "editorial_post_id": current.get("editorial_post_id"),
                "occurred_at": deleted_at.isoformat(),
            })
            raise RetentionExecutionError(
                "Drive deletion succeeded but database marking failed; reconciliation audit recorded."
            )

        record_audit({
            "event": "image_permanently_deleted",
            "drive_file_id": file_id,
            "editorial_post_id": current.get("editorial_post_id"),
            "drive_result": delete_result,
            "occurred_at": deleted_at.isoformat(),
        })
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
