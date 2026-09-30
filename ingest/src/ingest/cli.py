import argparse

from ingest.build_db import build_db
from ingest.build_index import build_index
from ingest.fetch import fetch


def main() -> None:
    parser = argparse.ArgumentParser(prog="ingest", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    fetch_cmd = sub.add_parser("fetch", help="download PokeAPI CSV tables")
    fetch_cmd.add_argument("--ref", default="master", help="git ref of PokeAPI/pokeapi to pin to")
    fetch_cmd.add_argument("--force", action="store_true", help="refetch even if up to date")

    sub.add_parser("build-db", help="build the SQLite DB for structured tools")
    sub.add_parser("build-index", help="build the vector + BM25 index")
    sub.add_parser("all", help="fetch, build-db, build-index")

    args = parser.parse_args()
    if args.command == "fetch":
        fetch(ref=args.ref, force=args.force)
    elif args.command == "build-db":
        build_db()
    elif args.command == "build-index":
        build_index()
    elif args.command == "all":
        fetch()
        build_db()
        build_index()


if __name__ == "__main__":
    main()
