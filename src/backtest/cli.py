"""Unified backtest CLI entry point.

Usage examples:
    # Full pipeline (all phases)
    python -m src.backtest.cli --config full_2025.json

    # Single phase
    python -m src.backtest.cli --config full_2025.json --phase 2

    # Only FNO flat validation
    python -m src.backtest.cli --config full_2025.json --phase 3a

    # Only Grade A+B capital sim
    python -m src.backtest.cli --config full_2025.json --phase 3b

    # Single date quick test
    python -m src.backtest.cli --config full_2025.json --date 2025-02-28

    # Resume from existing Phase 1/2 output
    python -m src.backtest.cli --config full_2025.json --phase 3a --results-dir path/to/run
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from src.backtest.config.schema import load_config
from src.backtest.pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("BacktestCLI")


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(
        description="Backtest Pipeline — unified entry point",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--config", required=True,
        help="Config preset filename (e.g. full_2025.json) or absolute path to JSON",
    )
    parser.add_argument(
        "--phase", default="all",
        help="Phase(s) to run: all | 1 | 2 | 3a | 3b | comma-separated (default: all)",
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="Override trading_dates with a single date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--results-dir", type=str, default=None,
        help="Existing results directory to resume from (for phases 2/3)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    config = load_config(args.config)

    if args.date:
        config.name = f"single_day_{args.date}"
        config.description = f"Single-date test run for {args.date}"
        config.trading_dates = [args.date]
        logger.info(f"*** SINGLE-DATE MODE: {args.date} ***")

    results_dir = Path(args.results_dir) if args.results_dir else None

    logger.info(f"Config: {config.name}")
    logger.info(f"Phases: {args.phase}")
    logger.info(f"Dates: {len(config.trading_dates)} trading days")

    asyncio.run(run_pipeline(config, phases=args.phase, results_dir=results_dir))


if __name__ == "__main__":
    main()
