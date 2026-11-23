"""Operator-only importer for genuine dated stock-loan receipts, not a quote generator.

Usage: PYTHONPATH=. .venv/bin/python scripts/research/import_shadow_borrow.py receipt.json
Only writes the isolated shadow borrow table in the explicitly configured DB.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path

import asyncpg

from alpha_agent.paper.shadow_borrow_receipts import import_receipt


async def main(path):
    if path.stat().st_size > 32768:
        raise ValueError("Expected one small, redacted receipt")
    record = json.loads(path.read_text())
    conn = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0, timeout=8)
    try:
        print("Recorded" if await import_receipt(conn, record) else "Already recorded")
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    asyncio.run(main(parser.parse_args().receipt))
