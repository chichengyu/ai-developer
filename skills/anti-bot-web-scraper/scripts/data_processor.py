"""Declarative data processing for collected page/API records.

The pipeline is a JSON list of ordered steps: select, rename, filter,
sort, dedupe, flatten, limit, aggregate, drop, default, convert, map,
replace, and join. It is standard-library only and accepts JSON, JSONL,
and CSV input; output uses the same formats.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

_MISSING = object()


def get_path(item: Any, path: str, default: Any = None) -> Any:
    """Read a dotted path such as ``user.name`` or ``items.0.id``."""
    current = item
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part, _MISSING)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else _MISSING
        else:
            return default
        if current is _MISSING:
            return default
    return current


def _compare(actual: Any, op: str, expected: Any, case_sensitive: bool = False) -> bool:
    if actual is _MISSING or actual is None:
        return op in {"not_exists", "falsy"}
    if op == "exists":
        return True
    if op == "not_exists":
        return False
    if op == "truthy":
        return bool(actual)
    if op == "falsy":
        return not bool(actual)

    def norm(value: Any) -> Any:
        if isinstance(value, str) and not case_sensitive:
            return value.casefold()
        return value

    left = norm(actual)
    right = norm(expected)
    if op in {"eq", "ne"}:
        return left == right if op == "eq" else left != right
    if op == "contains":
        return str(right) in str(left)
    if op == "not_contains":
        return str(right) not in str(left)
    if op == "in":
        return left in right if isinstance(right, list | tuple | set) else False
    if op == "not_in":
        return left not in right if isinstance(right, list | tuple | set) else True
    if op == "regex":
        return re.search(str(right), str(actual)) is not None
    if op in {"gt", "gte", "lt", "lte"}:
        try:
            left_num = float(left)
            right_num = float(right)
            left, right = left_num, right_num
        except (TypeError, ValueError):
            pass
        if op == "gt":
            return left > right
        if op == "gte":
            return left >= right
        if op == "lt":
            return left < right
        return left <= right
    raise ValueError(f"unsupported filter op: {op}")


def _select_record(record: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    return {
        field: get_path(record, field, None)
        for field in fields
        if get_path(record, field, _MISSING) is not _MISSING
    }


def _apply_rename(records: list[dict[str, Any]], mapping: dict[str, str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for record in records:
        renamed: dict[str, Any] = {}
        for key, value in record.items():
            renamed[mapping.get(key, key)] = value
        result.append(renamed)
    return result


def _set_path(record: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current: Any = record
    for part in parts[:-1]:
        if not isinstance(current, dict):
            return
        current = current.setdefault(part, {})
    if isinstance(current, dict):
        current[parts[-1]] = value


def _delete_path(record: dict[str, Any], path: str) -> None:
    parts = path.split(".")
    current: Any = record
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return
        current = current[part]
    if isinstance(current, dict):
        current.pop(parts[-1], None)


def _apply_drop(records: list[dict[str, Any]], fields: list[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for record in records:
        copied = deepcopy(record)
        for field in fields:
            _delete_path(copied, field)
        result.append(copied)
    return result


def _apply_default(
    records: list[dict[str, Any]],
    mapping: dict[str, Any],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for record in records:
        copied = deepcopy(record)
        for field, value in mapping.items():
            if get_path(copied, field, _MISSING) is _MISSING or get_path(copied, field) is None:
                _set_path(copied, field, value)
        result.append(copied)
    return result


def _convert_value(value: Any, target: str) -> Any:
    target = target.lower()
    if target == "int":
        if isinstance(value, bool):
            return int(value)
        return int(float(str(value).strip()))
    if target == "float":
        return float(str(value).strip())
    if target == "str":
        return str(value)
    if target == "bool":
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    raise ValueError(f"unsupported convert type: {target}")


def _apply_convert(
    records: list[dict[str, Any]],
    fields: Any,
) -> list[dict[str, Any]]:
    specs: list[tuple[str, str]] = []
    if isinstance(fields, dict):
        specs = [(str(field), str(target)) for field, target in fields.items()]
    else:
        for item in fields or []:
            if isinstance(item, dict):
                specs.append((str(item.get("field", "")), str(item.get("type", "str"))))
    result: list[dict[str, Any]] = []
    for record in records:
        copied = deepcopy(record)
        for field, target in specs:
            if get_path(copied, field, _MISSING) is _MISSING:
                continue
            value = get_path(copied, field)
            _set_path(copied, field, _convert_value(value, target))
        result.append(copied)
    return result


def _apply_map(records: list[dict[str, Any]], fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for record in records:
        copied = deepcopy(record)
        for item in fields:
            output = str(item.get("output", ""))
            if not output:
                continue
            if "template" in item:
                template = str(item["template"])
                template_value = template
                for key in re.findall(r"\{([^{}]+)\}", template):
                    template_value = template_value.replace(
                        "{" + key + "}", str(get_path(copied, key, ""))
                    )
                _set_path(copied, output, template_value)
                continue
            field = str(item.get("field", ""))
            if get_path(copied, field, _MISSING) is _MISSING:
                continue
            mapped_value = get_path(copied, field)
            transform = str(item.get("transform", "") or "").lower()
            if transform == "lower":
                mapped_value = str(mapped_value).lower()
            elif transform == "upper":
                mapped_value = str(mapped_value).upper()
            elif transform in {"strip", "trim"}:
                mapped_value = str(mapped_value).strip()
            elif transform == "title":
                mapped_value = str(mapped_value).title()
            elif transform == "length":
                mapped_value = len(mapped_value)
            elif transform == "str":
                mapped_value = str(mapped_value)
            elif transform == "int":
                mapped_value = int(float(str(mapped_value).strip()))
            elif transform == "float":
                mapped_value = float(str(mapped_value).strip())
            elif transform == "bool":
                mapped_value = bool(mapped_value)
            elif transform == "json":
                mapped_value = json.dumps(mapped_value, ensure_ascii=False, default=str)
            elif transform not in {"", "none"}:
                raise ValueError(f"unsupported map transform: {transform}")
            _set_path(copied, output, mapped_value)
        result.append(copied)
    return result


def _apply_replace(
    records: list[dict[str, Any]],
    fields: Any,
) -> list[dict[str, Any]]:
    specs: list[tuple[str, str, str, bool]] = []
    if isinstance(fields, dict):
        for field, rule in fields.items():
            if isinstance(rule, dict):
                specs.append(
                    (
                        str(field),
                        str(rule.get("pattern", "")),
                        str(rule.get("replacement", "")),
                        bool(rule.get("regex", False)),
                    )
                )
            elif isinstance(rule, list) and len(rule) == 2:
                specs.append((str(field), str(rule[0]), str(rule[1]), False))
    else:
        for item in fields or []:
            if not isinstance(item, dict):
                continue
            specs.append(
                (
                    str(item.get("field", "")),
                    str(item.get("pattern", "")),
                    str(item.get("replacement", "")),
                    bool(item.get("regex", False)),
                )
            )
    result: list[dict[str, Any]] = []
    for record in records:
        copied = deepcopy(record)
        for field, pattern, replacement, regex in specs:
            if get_path(copied, field, _MISSING) is _MISSING:
                continue
            value = get_path(copied, field)
            if not isinstance(value, str):
                value = str(value)
            value = (
                re.sub(pattern, replacement, value)
                if regex
                else value.replace(pattern, replacement)
            )
            _set_path(copied, field, value)
        result.append(copied)
    return result


def _apply_join(records: list[dict[str, Any]], params: dict[str, Any]) -> list[dict[str, Any]]:
    path = params.get("path")
    if not path:
        raise ValueError("join requires path")
    on_fields = [str(field) for field in params.get("on", [])]
    if not on_fields:
        raise ValueError("join requires on fields")
    join_type = str(params.get("type", "left")).lower()
    prefix = str(params.get("prefix", "") or "")
    selected_fields = (
        [str(field) for field in params.get("fields", [])] if params.get("fields") else None
    )
    lookup: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in load_records(str(path)):
        key = tuple(get_path(row, field, None) for field in on_fields)
        lookup.setdefault(key, row)
    result: list[dict[str, Any]] = []
    for record in records:
        copied = deepcopy(record)
        key = tuple(get_path(copied, field, None) for field in on_fields)
        matched = lookup.get(key)
        if matched is None:
            if join_type != "inner":
                result.append(copied)
            continue
        if selected_fields:
            for field in selected_fields:
                value = get_path(matched, field, _MISSING)
                if value is not _MISSING:
                    _set_path(copied, f"{prefix}{field}", value)
        else:
            for field, value in matched.items():
                _set_path(copied, f"{prefix}{field}", value)
        result.append(copied)
    return result


def _apply_filter(records: list[dict[str, Any]], params: dict[str, Any]) -> list[dict[str, Any]]:
    conditions = params.get("conditions") or params.get("rules") or []
    operator = str(params.get("operator", "and")).lower()
    result: list[dict[str, Any]] = []
    for record in records:
        outcomes = [
            _compare(
                get_path(record, str(condition.get("field", "")), _MISSING),
                str(condition.get("op", "eq")),
                condition.get("value"),
                bool(condition.get("case_sensitive", False)),
            )
            for condition in conditions
        ]
        keep = all(outcomes) if operator != "or" else any(outcomes)
        if keep:
            result.append(record)
    return result


def _sort_value(value: Any) -> tuple[bool, Any]:
    if value is None or value is _MISSING:
        return (True, "")
    try:
        return (False, float(value))
    except (TypeError, ValueError):
        return (False, str(value))


def _apply_sort(records: list[dict[str, Any]], params: dict[str, Any]) -> list[dict[str, Any]]:
    keys = params.get("keys") or params.get("fields") or []
    if isinstance(keys, str):
        keys = [{"field": keys}]
    ordered = list(records)
    for key_spec in reversed(keys):
        field = str(key_spec.get("field", "") if isinstance(key_spec, dict) else key_spec)
        desc = bool(key_spec.get("desc", False)) if isinstance(key_spec, dict) else False
        ordered.sort(
            key=lambda record: _sort_value(get_path(record, field, _MISSING)),
            reverse=desc,
        )
    return ordered


def _record_signature(record: dict[str, Any], fields: list[str]) -> tuple[Any, ...]:
    if fields:
        return tuple(get_path(record, field, None) for field in fields)
    return (json.dumps(record, sort_keys=True, ensure_ascii=False, default=str),)


def _apply_dedupe(records: list[dict[str, Any]], params: dict[str, Any]) -> list[dict[str, Any]]:
    fields = [str(field) for field in params.get("fields", [])]
    keep = str(params.get("keep", "first")).lower()
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    ordered = records if keep == "first" else list(reversed(records))
    for record in ordered:
        signature = _record_signature(record, fields)
        if signature in seen:
            continue
        seen.add(signature)
        result.append(record)
    return result if keep == "first" else list(reversed(result))


def _flatten_item(
    value: Any,
    prefix: str = "",
    separator: str = ".",
    depth: int = 0,
) -> dict[str, Any]:
    if depth > 40:
        return {prefix or "value": value}
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            child_prefix = f"{prefix}{separator}{key}" if prefix else str(key)
            child_flat = _flatten_item(child, child_prefix, separator, depth + 1)
            if isinstance(child_flat, dict):
                result.update(child_flat)
            else:
                result[child_prefix] = child_flat
        return result
    if isinstance(value, list):
        result = {}
        for index, child in enumerate(value):
            child_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            child_flat = _flatten_item(child, child_prefix, separator, depth + 1)
            if isinstance(child_flat, dict):
                result.update(child_flat)
            else:
                result[child_prefix] = child_flat
        return result
    return {prefix: value} if prefix else {}


def _apply_flatten(records: list[dict[str, Any]], params: dict[str, Any]) -> list[dict[str, Any]]:
    separator = str(params.get("separator", "."))
    return [_flatten_item(record, separator=separator) for record in records]


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _aggregate_group(
    group_records: list[dict[str, Any]],
    by_fields: list[str],
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    row: dict[str, Any] = {}
    if group_records:
        sample = group_records[0]
        for field in by_fields:
            row[field] = get_path(sample, field, None)
    for op in operations:
        field = str(op.get("field", ""))
        method = str(op.get("method", "count")).lower()
        output = str(op.get("output", "") or f"{field}_{method}" if field else method)
        values = [get_path(record, field, None) for record in group_records]
        present = [value for value in values if value is not None and value is not _MISSING]
        if method == "count":
            row[output] = len(group_records)
        elif method == "count_distinct":
            row[output] = len({json.dumps(value, sort_keys=True, default=str) for value in present})
        elif method == "first":
            row[output] = present[0] if present else None
        elif method == "last":
            row[output] = present[-1] if present else None
        elif method in {"sum", "avg", "min", "max"}:
            numbers = [number for value in present if (number := _numeric(value)) is not None]
            if not numbers:
                row[output] = None
            elif method == "sum":
                total = sum(numbers)
                row[output] = (
                    int(total)
                    if all(
                        isinstance(value, int) and not isinstance(value, bool) for value in present
                    )
                    else total
                )
            elif method == "avg":
                row[output] = sum(numbers) / len(numbers)
            elif method == "min":
                row[output] = min(numbers)
            else:
                row[output] = max(numbers)
        else:
            raise ValueError(f"unsupported aggregate method: {method}")
    return row


def _apply_aggregate(records: list[dict[str, Any]], params: dict[str, Any]) -> list[dict[str, Any]]:
    groups = params.get("groups") or [params]
    result: list[dict[str, Any]] = []
    for group in groups:
        by_fields = [str(field) for field in group.get("by", [])]
        operations = group.get("ops") or group.get("operations") or []
        buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for record in records:
            key = tuple(get_path(record, field, None) for field in by_fields)
            buckets.setdefault(key, []).append(record)
        for bucket_records in buckets.values():
            result.append(_aggregate_group(bucket_records, by_fields, operations))
    return result


def process_records(
    records: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Apply an ordered list of processing steps to records."""
    result = list(records)
    steps = config.get("steps") or config.get("operations") or []
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError(f"invalid step: {step!r}")
        op = step.get("op")
        params = step.get("params") or {}
        if op is None:
            for candidate in (
                "select",
                "rename",
                "filter",
                "sort",
                "dedupe",
                "flatten",
                "limit",
                "aggregate",
                "drop",
                "default",
                "convert",
                "map",
                "replace",
                "join",
            ):
                if candidate in step:
                    op = candidate
                    params = step[candidate]
                    if not isinstance(params, dict):
                        params = (
                            {"fields": params}
                            if candidate in {"select", "sort"}
                            else {"value": params}
                        )
                    break
        if op is None:
            raise ValueError(f"step has no operation: {step!r}")
        if op == "select":
            fields = params.get("fields") or params.get("paths") or []
            result = [_select_record(record, [str(field) for field in fields]) for record in result]
        elif op == "rename":
            result = _apply_rename(
                result, {str(k): str(v) for k, v in (params.get("mapping") or {}).items()}
            )
        elif op == "filter":
            result = _apply_filter(result, params)
        elif op == "sort":
            result = _apply_sort(result, params)
        elif op == "dedupe":
            result = _apply_dedupe(result, params)
        elif op == "flatten":
            result = _apply_flatten(result, params)
        elif op == "limit":
            limit = max(0, int(params.get("value", params.get("count", 0))))
            result = result[:limit]
        elif op == "aggregate":
            result = _apply_aggregate(result, params)
        elif op == "drop":
            result = _apply_drop(result, [str(field) for field in params.get("fields", [])])
        elif op == "default":
            result = _apply_default(
                result, {str(k): v for k, v in (params.get("mapping") or {}).items()}
            )
        elif op == "convert":
            result = _apply_convert(result, params.get("fields") or params.get("mapping") or [])
        elif op == "map":
            result = _apply_map(result, params.get("fields") or [])
        elif op == "replace":
            result = _apply_replace(result, params.get("fields") or params.get("mapping") or [])
        elif op == "join":
            result = _apply_join(result, params)
        else:
            raise ValueError(f"unsupported processing step: {op}")
    return result


def load_records(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".json":
        data = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("records", "data", "items"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [data]
        raise ValueError("JSON input must be an object or a list of objects")
    if suffix == ".jsonl":
        records: list[dict[str, Any]] = []
        for line in source.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                records.append(item)
        return records
    if suffix == ".csv":
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    raise ValueError(f"unsupported input format: {suffix}")


def _csv_fieldnames(records: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for record in records:
        for key in record:
            if key not in names:
                names.append(str(key))
    return names


def save_records(records: list[dict[str, Any]], path: str | Path) -> Path:
    out = Path(path)
    suffix = out.suffix.lower()
    if suffix == ".json":
        out.write_text(
            json.dumps(records, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    elif suffix == ".jsonl":
        out.write_text(
            "\n".join(json.dumps(record, ensure_ascii=False, default=str) for record in records),
            encoding="utf-8",
        )
    elif suffix == ".csv":
        fieldnames = _csv_fieldnames(records)
        with out.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for record in records:
                writer.writerow(
                    {
                        key: (
                            json.dumps(value, ensure_ascii=False, default=str)
                            if isinstance(value, dict | list)
                            else value
                        )
                        for key, value in record.items()
                    }
                )
    else:
        raise ValueError(f"unsupported output format: {suffix}")
    return out


def _self_test() -> None:
    records = [
        {"id": 1, "name": "Alpha", "price": 10, "tags": ["a"], "meta": {"ok": True}},
        {"id": 2, "name": "Beta", "price": 20, "tags": ["b"], "meta": {"ok": False}},
        {"id": 3, "name": "Alpha", "price": 30, "tags": ["a"], "meta": {"ok": True}},
    ]
    config = {
        "steps": [
            {
                "op": "filter",
                "params": {"conditions": [{"field": "meta.ok", "op": "eq", "value": True}]},
            },
            {
                "op": "aggregate",
                "params": {
                    "by": ["name"],
                    "ops": [{"field": "price", "method": "sum", "output": "total"}],
                },
            },
            {"op": "dedupe", "params": {"fields": ["name"]}},
            {"op": "sort", "params": {"keys": [{"field": "total", "desc": True}]}},
        ]
    }
    processed = process_records(records, config)
    assert processed == [{"name": "Alpha", "total": 40}], processed
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "in.json"
        source.write_text(json.dumps(records), encoding="utf-8")
        loaded = load_records(source)
        assert len(loaded) == 3
        out = Path(tmp) / "out.csv"
        save_records(loaded[:2], out)
        assert out.exists()
    print("data_processor self-test OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Process collected data with a declarative pipeline"
    )
    parser.add_argument("--config", help="JSON pipeline config")
    parser.add_argument("--input", help="input JSON/JSONL/CSV")
    parser.add_argument("--output", help="output JSON/JSONL/CSV")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        _self_test()
        return 0
    if not args.config or not args.input or not args.output:
        parser.error("--config, --input, and --output are required")
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    records = load_records(args.input)
    result = process_records(records, config)
    save_records(result, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
