"""One bounded GET per approved public route; receipts stay in /tmp.

Run explicitly. No authentication, redirects, retries, DB or task endpoints.
"""
from datetime import UTC, datetime
import json
from pathlib import Path
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Redirect refused")


def main():
    opener = build_opener(NoRedirect)
    receipts = []
    for route in (
        "/api/l2/evidence?sleeve=tactical",
        "/api/l2/evidence?sleeve=strategic",
        "/api/picks/scoreboard",
        "/api/picks/lean",
    ):
        url = "https://alpha-api.bobbyzhong.com" + route
        receipt = {"url": url, "requested_at": datetime.now(UTC).isoformat()}
        try:
            with opener.open(Request(url, headers={"Accept": "application/json"}), timeout=45) as response:
                body = response.read(2_000_001)
                if len(body) > 2_000_000:
                    raise ValueError("Response limit exceeded")
                receipt.update(status=response.status, payload=json.loads(body))
        except Exception as exc:
            receipt["error_type"] = type(exc).__name__
        receipt["received_at"] = datetime.now(UTC).isoformat()
        receipts.append(receipt)
    path = Path("/tmp/alpha-quant-p0-public-evidence-20261111.json")
    path.write_text(json.dumps(receipts, ensure_ascii=False, indent=2))
    print(path)
    for receipt in receipts:
        payload = receipt.get("payload", {})
        summary = {k: v for k, v in payload.items() if k not in {"series", "cards", "picks", "items"}}
        print(json.dumps({**{k: v for k, v in receipt.items() if k != "payload"}, "summary": summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
