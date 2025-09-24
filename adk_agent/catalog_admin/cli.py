import argparse
import os
import sys
from typing import Any

from libs.tools_firebase import FirebaseFunctionsClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Catalog Admin CLI smoke tests")
    parser.add_argument("--base-url", default=os.getenv("MYON_FUNCTIONS_BASE_URL", "https://us-central1-myon-53d85.cloudfunctions.net"))
    parser.add_argument("--api-key", default=os.getenv("FIREBASE_API_KEY"))
    parser.add_argument("--bearer", default=os.getenv("FIREBASE_ID_TOKEN"))
    parser.add_argument("--action", choices=["health","list-families","search-aliases"], default="health")
    parser.add_argument("--q", help="query for search-aliases")
    args = parser.parse_args(argv)

    client = FirebaseFunctionsClient(base_url=args.base_url, api_key=args.api_key, bearer_token=args.bearer)

    if args.action == "health":
        data = client.health()
        print(data)
        return 0
    if args.action == "list-families":
        data = client.list_families(minSize=1, limit=20)
        print(data)
        return 0
    if args.action == "search-aliases":
        q = args.q or "ohp"
        data = client.search_aliases(q)
        print(data)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


