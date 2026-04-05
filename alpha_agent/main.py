"""CLI entry point for the alpha-agent factor research system.

Usage:
    python -m alpha_agent "find short-term reversal factors"
    python -m alpha_agent --expr "Rank(-Delta($close, 5))" --backtest
"""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="alpha-agent",
        description="LLM-powered alpha factor research agent for A-share markets",
    )
    subparsers = parser.add_subparsers(dest="command")

    # Backtest a single expression
    bt_parser = subparsers.add_parser("backtest", help="Backtest a factor expression")
    bt_parser.add_argument("expression", help='Factor expression (e.g., "Rank(-Delta($close, 5))")')
    bt_parser.add_argument("--start", default="20220101", help="Start date (YYYYMMDD)")
    bt_parser.add_argument("--end", default="20241231", help="End date (YYYYMMDD)")
    bt_parser.add_argument("--top-n", type=int, default=50, help="Number of stocks to use")

    # Parse a factor expression (dry run)
    parse_parser = subparsers.add_parser("parse", help="Parse and display AST of an expression")
    parse_parser.add_argument("expression", help="Factor expression to parse")

    args = parser.parse_args()

    if args.command == "parse":
        _run_parse(args.expression)
    elif args.command == "backtest":
        _run_backtest(args.expression, args.start, args.end, args.top_n)
    else:
        parser.print_help()
        sys.exit(1)


def _run_parse(expression: str) -> None:
    from alpha_agent.factor_engine.parser import ExprParser, ParseError

    try:
        ast = ExprParser().parse(expression)
        print(f"Expression: {expression}")
        print(f"AST: {ast}")
    except ParseError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _run_backtest(expression: str, start: str, end: str, top_n: int) -> None:
    import pandas as pd

    from alpha_agent.backtest.engine import BacktestEngine
    from alpha_agent.data.cache import ParquetCache
    from alpha_agent.data.provider import AKShareProvider
    from alpha_agent.data.universe import CSI300Universe
    from alpha_agent.factor_engine.evaluator import ExprEvaluator
    from alpha_agent.factor_engine.parser import ExprParser, ParseError

    # Parse
    try:
        ast = ExprParser().parse(expression)
    except ParseError as e:
        print(f"Parse error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Factor: {expression}")
    print(f"Period: {start} - {end}")

    # Fetch data
    universe = CSI300Universe()
    codes = universe.stock_codes[:top_n]
    print(f"Universe: {len(codes)} stocks")

    cache = ParquetCache()
    provider = AKShareProvider(cache=cache)
    print("Fetching data (cached if available)...")
    data = provider.fetch(stock_codes=codes, start_date=start, end_date=end)

    if data.empty:
        print("Error: No data fetched. Check network or AKShare availability.", file=sys.stderr)
        sys.exit(1)

    print(f"Data: {len(data)} rows, {data.index.get_level_values('stock_code').nunique()} stocks")

    # Evaluate factor
    print("Evaluating factor...")
    evaluator = ExprEvaluator()
    factor_values = evaluator.evaluate(ast, data)

    # Backtest
    print("Running backtest...")
    engine = BacktestEngine()
    result = engine.run(factor_values=factor_values, price_data=data)

    print("\n" + str(result))


if __name__ == "__main__":
    main()
