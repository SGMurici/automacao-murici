"""Coordinator for Gmail monitoring and LinkedIn publishing.

Safe by default: LinkedIn publishing is skipped unless
ENABLE_LINKEDIN_PUBLISH=true is explicitly configured.
The Gmail response body is reduced to account status/counts before logging.
"""
import json
import os
import sys
import urllib.error
import urllib.request


def post_json(url, headers, timeout=120):
    request = urllib.request.Request(
        url,
        data=b"{}",
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            code = response.status
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        code = error.code
    except Exception as error:
        return {
            "http_status": None,
            "status": "erro",
            "error_type": type(error).__name__,
        }

    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    return {"http_status": code, "payload": payload}


def gmail_summary(result):
    payload = result.get("payload", {})
    accounts = payload.get("accounts", {})
    return {
        "http_status": result.get("http_status"),
        "status": payload.get("status", "erro"),
        "mode": payload.get("mode", "somente_leitura"),
        "accounts": {
            name: {
                "status": item.get("status", "desconhecido"),
                "count": item.get("count", len(item.get("messages", []))),
            }
            for name, item in accounts.items()
        },
        **({"error_type": result["error_type"]} if "error_type" in result else {}),
    }


def main():
    base_url = os.environ["GMAIL_MONITOR_BASE_URL"].rstrip("/")
    gmail_secret = os.environ["GMAIL_MONITOR_SECRET"]

    gmail_result = post_json(
        base_url + "/internal/gmail/monitor/run",
        {"X-Gmail-Monitor-Secret": gmail_secret},
    )
    gmail = gmail_summary(gmail_result)

    publish_enabled = os.getenv("ENABLE_LINKEDIN_PUBLISH", "false").strip().lower() == "true"
    if publish_enabled:
        publish_base = os.environ["PUBLISH_BASE_URL"].rstrip("/")
        publish_secret = os.environ["PUBLISH_SECRET"]
        publish_result = post_json(
            publish_base + "/scheduler/run",
            {"X-Publish-Secret": publish_secret},
        )
        publish_payload = publish_result.get("payload", {})
        publishing = {
            "executed": True,
            "http_status": publish_result.get("http_status"),
            "status": publish_payload.get("status", "erro"),
        }
        if "error_type" in publish_result:
            publishing["error_type"] = publish_result["error_type"]
        publish_ok = publish_result.get("http_status") in (200, 409)
    else:
        publishing = {
            "executed": False,
            "status": "skipped_safe_mode",
        }
        publish_ok = True

    output = {
        "gmail": gmail,
        "linkedin_publishing": publishing,
        "mode": "combined" if publish_enabled else "validation_safe_mode",
    }
    print(json.dumps(output, ensure_ascii=False))

    gmail_ok = gmail.get("http_status") in (200, 207)
    return 0 if gmail_ok and publish_ok else 1


if __name__ == "__main__":
    sys.exit(main())
