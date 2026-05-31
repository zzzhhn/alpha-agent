#!/usr/bin/env python3
"""Backfill company_profiles.name_zh (V019).

Mirrors backfill_company_profiles_zh.py: the platform holds no global LLM key,
so names are translated offline via the local `claude` CLI (reuses the Claude
Code OAuth session). Names are short, so we batch many per CLI call and parse a
JSON array back.

Honest by design (no fabricated transliterations): the prompt is told to return
a REAL established Chinese name (Apple Inc.→苹果公司, NVIDIA→英伟达) or the
English name UNCHANGED when none exists. We then store name_zh = that value, so
`name_zh IS NULL` strictly means "not yet considered" (the work queue) and the
UI shows a Chinese name only when name_zh != name.

Run locally with prod DATABASE_URL in .env:

    uv run python scripts/backfill_company_names_zh.py
    uv run python scripts/backfill_company_names_zh.py --limit 100 --batch 40
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from alpha_agent.storage.postgres import get_pool  # noqa: E402
from alpha_agent.storage.queries import (  # noqa: E402
    list_profiles_missing_name_zh,
    set_company_name_zh,
)

_PROMPT_HEAD = (
    "For each US-listed public company name below, give its established, "
    "commonly-used Simplified Chinese name. RULES:\n"
    "- Use a REAL established Chinese name only (e.g. 'Apple Inc.'->'苹果公司', "
    "'NVIDIA Corporation'->'英伟达', 'Tesla, Inc.'->'特斯拉', "
    "'Alphabet Inc.'->'Alphabet（谷歌母公司）').\n"
    "- If the company has NO established/widely-recognized Chinese name, return "
    "the English name UNCHANGED. Do NOT invent a transliteration.\n"
    "- Output ONLY a JSON array of strings, same length and order as the input. "
    "No preamble, no code fence.\n\nINPUT:\n"
)


def _strip_fence(s: str) -> str:
    s = s.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", s)
    return m.group(1).strip() if m else s


def _translate_batch(names: list[str]) -> list[str] | None:
    """Translate one batch of names → list of Chinese-or-unchanged names."""
    numbered = "\n".join(f"{i+1}. {n}" for i, n in enumerate(names))
    try:
        proc = subprocess.run(
            ["claude", "-p", _PROMPT_HEAD + numbered],
            capture_output=True, text=True, timeout=180,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"  claude CLI error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None
    if proc.returncode != 0:
        print(f"  claude exited {proc.returncode}: {proc.stderr[:200]}", file=sys.stderr)
        return None
    try:
        out = json.loads(_strip_fence(proc.stdout))
    except json.JSONDecodeError as exc:
        print(f"  JSON parse failed: {exc}; raw={proc.stdout[:160]!r}", file=sys.stderr)
        return None
    if not isinstance(out, list) or len(out) != len(names):
        print(f"  shape mismatch: got {len(out) if isinstance(out, list) else '?'} "
              f"for {len(names)} names", file=sys.stderr)
        return None
    return [str(x).strip() for x in out]


async def main(limit: int, batch: int) -> None:
    load_dotenv(ROOT / ".env")
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        sys.exit("DATABASE_URL not set.")
    pool = await get_pool(db_url)
    try:
        rows = await list_profiles_missing_name_zh(pool, limit)
        print(f"{len(rows)} row(s) need a Chinese name decision.")
        done = 0
        for i in range(0, len(rows), batch):
            chunk = rows[i : i + batch]
            names = [r["name"] for r in chunk]
            zh = _translate_batch(names)
            if zh is None:
                print(f"  batch {i//batch+1} failed; skipping (re-run picks it up)")
                continue
            for r, name_zh in zip(chunk, zh):
                await set_company_name_zh(pool, r["ticker"], name_zh)
                done += 1
                tag = "→" if name_zh != r["name"] else "= (no zh name)"
                print(f"  {r['ticker']:6s} {r['name'][:34]:34s} {tag} {name_zh}")
        print(f"\nDone. {done}/{len(rows)} written.")
    finally:
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--batch", type=int, default=40)
    asyncio.run(main(**vars(ap.parse_args())))
