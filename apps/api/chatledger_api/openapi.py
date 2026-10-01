"""Print the API's OpenAPI schema as JSON (used by ``make gen-api-types``)."""

from __future__ import annotations

import json
import sys

from chatledger_api.main import create_app


def main() -> int:
    json.dump(create_app().openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
