"""Reclaim one merged PR's Vercel-created Neon preview. Dry-run by default."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

REPOSITORY = "zzzhhn/alpha-agent"
PROJECT_ID = "gentle-king-25994955"
PRODUCTION_BRANCH = "br-blue-salad-anselaqv"


def select_preview(branches, pr, open_prs, current_head):
    """Return an exact eligible ID, never a wildcard or production target."""
    head = pr.get("head") or {}
    if (pr.get("state") != "closed" or not pr.get("merged_at")
            or (head.get("repo") or {}).get("full_name") != REPOSITORY
            or not head.get("sha") or not head.get("ref") or open_prs
            or (current_head is not None and current_head != head["sha"])):
        return None
    matches = [b for b in branches if b.get("name") == f"preview/{head['ref']}"]
    if len(matches) != 1:
        return None
    branch = matches[0]
    if (not branch.get("id") or branch["id"] == PRODUCTION_BRANCH
            or branch.get("project_id") != PROJECT_ID
            or branch.get("parent_id") != PRODUCTION_BRANCH
            or branch.get("creation_source") != "vercel"
            or any(branch.get(k) is not False for k in ("primary", "default", "protected"))
            or branch.get("restricted_actions")
            or any(b.get("parent_id") == branch["id"] for b in branches)):
        return None
    return branch["id"]


class API:
    def __init__(self, base, token):
        self.base, self.token = base, token

    def request(self, path, method="GET", allow_missing=False):
        request = Request(self.base + path, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/json",
            "User-Agent": "alpha-agent-preview-cleanup",
        })
        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except HTTPError as exc:
            if allow_missing and exc.code == 404:
                return None
            # Do not emit bodies, headers, connection URLs or credential material.
            raise RuntimeError(f"{method} request failed with HTTP {exc.code}") from None


def branch_list(neon):
    result = neon.request(f"/projects/{PROJECT_ID}/branches?limit=100")
    if (result.get("pagination") or {}).get("cursor"):
        raise RuntimeError("Branch inventory incomplete; no cleanup performed")
    return result["branches"]


def cleanup_pr(github, neon, number, apply=False):
    path = f"/repos/{REPOSITORY}"
    pr = github.request(f"{path}/pulls/{number}")
    head = pr.get("head") or {}
    if not head.get("ref"):
        return {"pr": number, "status": "preserved", "reason": "missing_head"}

    def eligibility():
        # A merged branch may be reused. Check current work immediately before deletion.
        current = github.request(f"{path}/git/ref/heads/{quote(head['ref'], safe='')}",
                                 allow_missing=True)
        opened = github.request(f"{path}/pulls?" + urlencode({
            "state": "open", "head": f"zzzhhn:{head['ref']}", "per_page": 1,
        }))
        branches = branch_list(neon)
        current_head = current["object"]["sha"] if current else None
        return select_preview(branches, pr, opened, current_head)

    branch_id = eligibility()
    receipt = {"pr": number, "branch": f"preview/{head['ref']}", "branch_id": branch_id}
    if not branch_id:
        return {**receipt, "status": "preserved_or_absent"}
    if not apply:
        return {**receipt, "status": "would_delete"}
    if eligibility() != branch_id:
        return {**receipt, "status": "preserved", "reason": "state_changed"}
    neon.request(f"/projects/{PROJECT_ID}/branches/{quote(branch_id, safe='')}",
                 method="DELETE", allow_missing=True)
    if any(b["id"] == branch_id for b in branch_list(neon)):
        raise RuntimeError("Deletion was requested but branch is still present")
    return {**receipt, "status": "deleted"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.pr <= 0:
        parser.error("PR number must be positive")
    github = API("https://api.github.com", os.environ["GH_TOKEN"])
    neon = API("https://console.neon.tech/api/v2", os.environ["NEON_PREVIEW_CLEANUP_KEY"])
    receipt = cleanup_pr(github, neon, args.pr, apply=args.apply)
    result = json.dumps(receipt, ensure_ascii=False)
    print(result)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a") as stream:
            stream.write("## Neon preview cleanup\n\n```json\n" + result + "\n```\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, KeyError) as exc:
        print(f"Preview cleanup stopped: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
