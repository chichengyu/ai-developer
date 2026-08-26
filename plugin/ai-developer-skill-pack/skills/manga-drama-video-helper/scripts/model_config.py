#!/usr/bin/env python3
"""Read or update the project's current model configuration."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def load_config(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "version": 1,
        "current": {
            "provider": None,
            "model": None,
            "roles": [],
            "selected_at": None,
            "note": None,
        },
        "history": [],
    }


def save_config(path, config):
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cmd_get(args):
    path = Path(args.project_dir).resolve() / "model_config.json"
    print(json.dumps(load_config(path), ensure_ascii=False, indent=2))
    return 0


def cmd_set(args):
    if not args.provider or not args.model:
        print("error: --provider and --model are required", file=sys.stderr)
        return 2
    path = Path(args.project_dir).resolve() / "model_config.json"
    config = load_config(path)
    previous = config.get("current")
    if previous and previous.get("model"):
        config.setdefault("history", []).append(previous)
    config["current"] = {
        "provider": args.provider,
        "model": args.model,
        "roles": [item.strip() for item in (args.roles or "").split(",") if item.strip()],
        "selected_at": datetime.now().isoformat(timespec="seconds"),
        "note": args.note,
    }
    save_config(path, config)
    print(f"wrote: {path}")
    return 0


def cmd_clear(args):
    path = Path(args.project_dir).resolve() / "model_config.json"
    config = load_config(path)
    previous = config.get("current")
    if previous and previous.get("model"):
        config.setdefault("history", []).append(previous)
    config["current"] = {
        "provider": None,
        "model": None,
        "roles": [],
        "selected_at": None,
        "note": None,
    }
    save_config(path, config)
    print(f"wrote: {path}")
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description="Manage the current model for a project without hardcoding it.")
    parser.add_argument("project_dir", help="Project or series root directory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    get_parser = subparsers.add_parser("get", help="Print current model config.")
    get_parser.set_defaults(func=cmd_get)

    set_parser = subparsers.add_parser("set", help="Set or switch the current model.")
    set_parser.add_argument("--provider", required=True)
    set_parser.add_argument("--model", required=True)
    set_parser.add_argument("--roles", default="")
    set_parser.add_argument("--note", default=None)
    set_parser.set_defaults(func=cmd_set)

    switch_parser = subparsers.add_parser("switch", help="Alias for set.")
    switch_parser.add_argument("--provider", required=True)
    switch_parser.add_argument("--model", required=True)
    switch_parser.add_argument("--roles", default="")
    switch_parser.add_argument("--note", default=None)
    switch_parser.set_defaults(func=cmd_set)

    clear_parser = subparsers.add_parser("clear", help="Clear the current model.")
    clear_parser.set_defaults(func=cmd_clear)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
