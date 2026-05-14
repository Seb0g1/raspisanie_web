#!/usr/bin/env python3
import argparse
import json

from storage import cleanup_technical_data, init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean old technical bot tables.")
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args()

    init_db()
    result = cleanup_technical_data(args.days)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
