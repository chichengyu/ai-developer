"""Show the real public IP (STUN) versus the HTTP/cloud egress IP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from proxy_pool import ProxyPool


def collect() -> dict[str, Any]:
    pool = ProxyPool()
    current_ip = pool.current_ip()
    http_egress_ip = pool._http_egress_ip()
    return {
        "current_ip": current_ip,
        "current_ip_source": pool._current_ip_source,
        "http_egress_ip": http_egress_ip,
        "egress_matches_real": current_ip is not None and current_ip == http_egress_ip,
        "use_current_ip": pool.use_current_ip,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect the real public IP via STUN and compare HTTP egress."
    )
    parser.add_argument("--save", help="write the result to a JSON file")
    args = parser.parse_args(argv)
    result = collect()
    if not result.get("egress_matches_real"):
        print(
            "warning: HTTP egress is proxied; run this script outside Codex "
            "to crawl from the real public IP",
            file=sys.stderr,
        )
    if args.save:
        path = Path(args.save)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
