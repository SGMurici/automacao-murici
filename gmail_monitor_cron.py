"""Render Cron entrypoint for the isolated Gmail monitor.

Only sends a POST to the dedicated Gmail endpoint. It does not invoke
/scheduler/run and cannot publish LinkedIn posts.
"""
import json
import os
import sys
import urllib.error
import urllib.request


def main():
    base_url = os.environ["GMAIL_MONITOR_BASE_URL"].rstrip("/")
    secret = os.environ["GMAIL_MONITOR_SECRET"]
    url = base_url + "/internal/gmail/monitor/run"
    request = urllib.request.Request(
        url,
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "X-Gmail-Monitor-Secret": secret,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
            status_code = response.status
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {}
        status_code = error.code
    except Exception as error:
        print(json.dumps({
            "status": "erro",
            "tipo": type(error).__name__,
        }))
        return 1

    accounts = payload.get("accounts", {})
    summary = {
        "http_status": status_code,
        "status": payload.get("status", "erro"),
        "mode": payload.get("mode", "somente_leitura"),
        "accounts": {},
    }
    for name, result in accounts.items():
        summary["accounts"][name] = {
            "status": result.get("status", "desconhecido"),
            "count": result.get("count", len(result.get("messages", []))),
        }

    print(json.dumps(summary, ensure_ascii=False))
    return 0 if status_code in (200, 207) else 1


if __name__ == "__main__":
    sys.exit(main())
