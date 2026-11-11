"""Read bundled Parquet metadata and fingerprints locally; no provider calls."""
from datetime import UTC, datetime
from hashlib import file_digest
import json
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq


def main():
    root = Path(__file__).resolve().parents[2]
    files = []
    for path in sorted((root / "alpha_agent/data").glob("*.parquet")):
        table = pq.read_table(path)
        with path.open("rb") as stream:
            fingerprint = file_digest(stream, "sha256").hexdigest()
        result = {"file": str(path.relative_to(root)), "sha256": fingerprint,
                  "rows": table.num_rows, "columns": table.column_names}
        for field in ("date", "filing_date"):
            if field in table.column_names:
                result[field] = pc.min_max(table[field]).as_py()
        if "ticker" in table.column_names:
            result["symbols"] = len(pc.unique(table["ticker"]))
            if "date" in table.column_names:
                result["benchmark_dates"] = {
                    symbol: pc.min_max(table["date"].filter(pc.equal(table["ticker"], symbol))).as_py()
                    for symbol in ("SPY", "RSP")
                }
        files.append(result)
    print(json.dumps({"observed_at": datetime.now(UTC).isoformat(), "files": files}, indent=2))


if __name__ == "__main__":
    main()
