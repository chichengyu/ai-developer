"""Schema-free page structure analysis, record extraction, and validation.

The extractor does not require CSS selectors or XPath. It discovers records
from HTML tables, repeated list/article blocks, and embedded JSON state,
infers a schema, and validates each record before it enters the pipeline.
A structure fingerprint lets the crawler detect DOM redesigns and reparse
automatically.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from page_data_parser import EmbeddedJson, extract_embedded_json


@dataclass
class FieldSchema:
    name: str
    type: str
    sample: Any = None
    nullable: bool = True
    count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "sample": self.sample,
            "nullable": self.nullable,
            "count": self.count,
        }


@dataclass
class ValidationResult:
    records: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)
    valid_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid_count": self.valid_count,
            "invalid_count": len(self.records) - self.valid_count,
            "warnings": list(self.warnings[:200]),
            "records": self.records,
        }


@dataclass
class ExtractionResult:
    records: list[dict[str, Any]]
    schema: dict[str, FieldSchema]
    signature: str
    sources: dict[str, int] = field(default_factory=dict)
    validation: ValidationResult = field(default_factory=lambda: ValidationResult([]))

    def to_dict(self) -> dict[str, Any]:
        return {
            "signature": self.signature,
            "sources": dict(self.sources),
            "schema": {name: item.to_dict() for name, item in self.schema.items()},
            "records": self.records,
            "validation": self.validation.to_dict(),
        }


class _StructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.counts: Counter[str] = Counter()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.counts[tag.lower()] += 1
        for key, value in attrs:
            if key.lower() == "class" and value:
                for cls in value.split():
                    self.counts[f"class:{cls}"] += 1


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
            self._table.append(self._row)
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
            self._row.append("")
            self._cell = self._row[-1:] and []
            self._row[-1] = ""

    def handle_data(self, data: str) -> None:
        if self._row is not None and self._row:
            self._row[-1] += data

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None
            self._row = None
            self._cell = None
        elif tag == "tr":
            self._row = None
        elif tag in {"td", "th"}:
            self._cell = None


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def _text_links(html: str, base_url: str | None) -> tuple[str, list[str]]:
    text = re.sub(r"\s+", " ", _strip_tags(html)).strip()
    links = re.findall(r'<a[^>]+href=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if base_url:
        links = [__import__("urllib.parse").urljoin(base_url, link) for link in links]
    return text, links


def _table_records(html: str, base_url: str | None) -> list[dict[str, Any]]:
    parser = _TableParser()
    parser.feed(html)
    records: list[dict[str, Any]] = []
    for table in parser.tables:
        if not table:
            continue
        header: list[str] | None = None
        rows = table
        if len(rows) > 1 and all(cell.strip() for cell in rows[0]):
            header = [cell.strip() or f"col{i}" for i, cell in enumerate(rows[0])]
            rows = rows[1:]
        for row_index, row in enumerate(rows):
            record: dict[str, Any] = {"_source": "table", "_row": row_index}
            for col_index, cell in enumerate(row):
                value = _strip_tags(cell).strip()
                key = header[col_index] if header and col_index < len(header) else f"col{col_index}"
                record[key] = value
            records.append(record)
    return records


def _repeated_block_records(html: str, base_url: str | None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for tag in ("li", "article"):
        pattern = re.compile(rf"<{tag}[^>]*>(.*?)</{tag}>", re.IGNORECASE | re.DOTALL)
        blocks = list(pattern.findall(html))
        if len(blocks) < 2:
            continue
        for index, block in enumerate(blocks):
            text, links = _text_links(block, base_url)
            if not text:
                continue
            record: dict[str, Any] = {
                "_source": tag,
                "_index": index,
                "text": text,
            }
            if links:
                record["links"] = links
            records.append(record)
    return records


def _walk_json_records(
    value: Any,
    *,
    source: str,
    depth: int = 0,
    records: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if records is None:
        records = []
    if depth > 20:
        return records
    if isinstance(value, dict):
        for child in value.values():
            _walk_json_records(child, source=source, depth=depth + 1, records=records)
    elif isinstance(value, list):
        dict_items = [item for item in value if isinstance(item, dict)]
        if len(dict_items) >= 2:
            for item in dict_items:
                record = dict(item)
                record.setdefault("_source", source)
                records.append(record)
        for child in value:
            _walk_json_records(child, source=source, depth=depth + 1, records=records)
    return records


def _embedded_records(blocks: list[EmbeddedJson]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for block in blocks:
        if block.parse_error is not None:
            continue
        records.extend(
            _walk_json_records(
                block.data,
                source=block.kind,
                records=records,
            )
        )
    return records


def _type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "null"


def infer_schema(records: list[dict[str, Any]]) -> dict[str, FieldSchema]:
    fields: dict[str, FieldSchema] = {}
    for record in records:
        for key, value in record.items():
            if key.startswith("_"):
                continue
            field = fields.setdefault(
                key,
                FieldSchema(name=key, type=_type_name(value), sample=value),
            )
            field.count += 1
            if field.sample is None and value is not None:
                field.sample = value
    total = len(records)
    for field in fields.values():
        field.nullable = field.count < total
    return fields


def validate_records(
    records: list[dict[str, Any]],
    schema: dict[str, FieldSchema] | None = None,
) -> ValidationResult:
    schema = schema or infer_schema(records)
    warnings: list[str] = []
    cleaned: list[dict[str, Any]] = []
    valid = 0
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            warnings.append(f"row {index}: not a dict")
            continue
        cleaned_record = dict(record)
        record_valid = True
        for name, field_schema in schema.items():
            if name in cleaned_record:
                continue
            if not field_schema.nullable:
                cleaned_record[name] = None
                warnings.append(f"row {index}: missing non-null field {name}")
                record_valid = False
        cleaned.append(cleaned_record)
        if record_valid:
            valid += 1
    return ValidationResult(records=cleaned, warnings=warnings, valid_count=valid)


def structure_signature(html: str) -> str:
    parser = _StructureParser()
    parser.feed(html)
    payload = json.dumps(sorted(parser.counts.items()), ensure_ascii=False)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


class AutoDataExtractor:
    """Reparse a page into validated records without manual selectors."""

    def analyze(self, html: str, base_url: str | None = None) -> ExtractionResult:
        signature = structure_signature(html)
        embedded = extract_embedded_json(html)
        records: list[dict[str, Any]] = []
        sources: dict[str, int] = {}

        def add(batch: list[dict[str, Any]], source: str) -> None:
            sources[source] = len(batch)
            records.extend(batch)

        add(_table_records(html, base_url), "table")
        add(_repeated_block_records(html, base_url), "repeated")
        add(_embedded_records(embedded), "embedded_json")
        schema = infer_schema(records)
        validation = validate_records(records, schema)
        return ExtractionResult(
            records=validation.records,
            schema=schema,
            signature=signature,
            sources=sources,
            validation=validation,
        )

    def is_structure_changed(
        self,
        previous_signature: str | None,
        html: str,
    ) -> bool:
        return previous_signature is not None and previous_signature != structure_signature(html)

    def save_jsonl(self, result: ExtractionResult, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps(record, ensure_ascii=False, default=str)
            for record in result.records
        ]
        out.write_text("\n".join(lines), encoding="utf-8")
        return out


if __name__ == "__main__":
    sample = """
    <table><tr><th>name</th><th>price</th></tr>
    <tr><td>Apple</td><td>10</td></tr>
    <tr><td>Banana</td><td>20</td></tr></table>
    <ul><li>One</li><li>Two</li></ul>
    """
    result = AutoDataExtractor().analyze(sample, "https://example.com/")
    print(result.to_dict())
