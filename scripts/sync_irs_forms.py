#!/usr/bin/env python3
"""Sync IRS forms metadata from IRS.gov indexes."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


BASE_URL = "https://www.irs.gov"
DATASETS = {
    "current": {
        "label": "Current IRS forms, instructions, and publications",
        "source_url": "https://www.irs.gov/forms-instructions-and-publications",
        "columns": ("product_number", "title", "revision_date", "posted_date"),
    },
    "prior": {
        "label": "Prior-year IRS forms and instructions",
        "source_url": "https://www.irs.gov/prior-year-forms-and-instructions",
        "columns": ("product_number", "title", "revision_date"),
    },
}
DEFAULT_OUTPUT_DIR = Path("data/irs")
DEFAULT_ITEMS_PER_PAGE = 200
USER_AGENT = "irs-tax-forms-catalog/1.0 (+https://github.com/)"


@dataclass(frozen=True)
class FormRecord:
    dataset: str
    product_number: str
    title: str
    revision_date: str
    posted_date: str
    pdf_url: str
    source_page_url: str
    kind: str
    revision_year: str

    def as_dict(self) -> dict[str, str]:
        return {
            "dataset": self.dataset,
            "product_number": self.product_number,
            "title": self.title,
            "revision_date": self.revision_date,
            "posted_date": self.posted_date,
            "pdf_url": self.pdf_url,
            "source_page_url": self.source_page_url,
            "kind": self.kind,
            "revision_year": self.revision_year,
        }


class IRSFormsTableParser(HTMLParser):
    """Extract rows from the IRS Drupal view table."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, object]] = []
        self._in_tr = False
        self._in_td = False
        self._current_cells: list[str] = []
        self._cell_text: list[str] = []
        self._current_href = ""
        self._current_link_text = ""
        self._link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name: value or "" for name, value in attrs}
        if tag == "tr":
            self._in_tr = True
            self._current_cells = []
            self._current_href = ""
            self._current_link_text = ""
        elif self._in_tr and tag == "td":
            self._in_td = True
            self._cell_text = []
        elif self._in_tr and self._in_td and tag == "a":
            href = attr_map.get("href", "")
            if href.lower().endswith(".pdf"):
                self._current_href = href
                self._link_text = []

    def handle_data(self, data: str) -> None:
        if self._in_td:
            self._cell_text.append(data)
        if self._current_href:
            self._link_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_href and self._link_text:
            self._current_link_text = clean_text("".join(self._link_text))
            self._link_text = []
        elif tag == "td" and self._in_td:
            self._current_cells.append(clean_text("".join(self._cell_text)))
            self._cell_text = []
            self._in_td = False
        elif tag == "tr" and self._in_tr:
            if self._current_href and self._current_cells:
                self.rows.append(
                    {
                        "cells": self._current_cells[:],
                        "href": self._current_href,
                        "link_text": self._current_link_text,
                    }
                )
            self._in_tr = False
            self._in_td = False
            self._current_cells = []
            self._current_href = ""
            self._current_link_text = ""


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def fetch_html(url: str, retries: int = 3, sleep_seconds: float = 0.5) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, retries + 1):
        try:
            with urlopen(request, timeout=60) as response:
                encoding = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(encoding, errors="replace")
        except (HTTPError, URLError, TimeoutError) as exc:
            if attempt == retries:
                raise RuntimeError(f"failed to fetch {url}: {exc}") from exc
            time.sleep(sleep_seconds * attempt)
    raise RuntimeError(f"failed to fetch {url}")


def page_url(source_url: str, page: int, items_per_page: int) -> str:
    return f"{source_url}?{urlencode({'items_per_page': items_per_page, 'page': page})}"


def parse_rows(dataset: str, html: str, source_page_url: str) -> list[FormRecord]:
    parser = IRSFormsTableParser()
    parser.feed(html)
    records: list[FormRecord] = []
    columns = DATASETS[dataset]["columns"]

    for row in parser.rows:
        cells = list(row["cells"])
        if len(cells) < len(columns):
            continue

        values = dict(zip(columns, cells, strict=False))
        product_number = clean_product_number(values.get("product_number", ""))
        title = values.get("title", "")
        revision_date = values.get("revision_date", "")
        posted_date = values.get("posted_date", "")
        pdf_url = urljoin(BASE_URL, str(row["href"]))

        records.append(
            FormRecord(
                dataset=dataset,
                product_number=product_number,
                title=title,
                revision_date=revision_date,
                posted_date=posted_date,
                pdf_url=pdf_url,
                source_page_url=source_page_url,
                kind=infer_kind(product_number),
                revision_year=infer_revision_year(revision_date),
            )
        )

    return records


def clean_product_number(product_number: str) -> str:
    return product_number.replace("Instructions for", "Instructions for").strip()


def infer_kind(product_number: str) -> str:
    lowered = product_number.lower()
    if lowered.startswith("form "):
        return "form"
    if lowered.startswith("publication "):
        return "publication"
    if lowered.startswith("instruction ") or lowered.startswith("instructions "):
        return "instruction"
    if lowered.startswith("notice "):
        return "notice"
    if lowered.startswith("schedule "):
        return "schedule"
    return "other"


def infer_revision_year(revision_date: str) -> str:
    matches = re.findall(r"\b(18\d{2}|19\d{2}|20\d{2})\b", revision_date)
    return matches[-1] if matches else ""


def sync_dataset(
    dataset: str,
    items_per_page: int = DEFAULT_ITEMS_PER_PAGE,
    max_pages: int | None = None,
    sleep_seconds: float = 0.1,
) -> list[FormRecord]:
    source_url = DATASETS[dataset]["source_url"]
    all_records: list[FormRecord] = []
    page = 0

    while True:
        if max_pages is not None and page >= max_pages:
            break

        url = page_url(source_url, page, items_per_page)
        html = fetch_html(url)
        records = parse_rows(dataset, html, url)
        if not records:
            break

        all_records.extend(records)
        if len(records) < items_per_page:
            break

        page += 1
        if sleep_seconds:
            time.sleep(sleep_seconds)

    return dedupe_records(all_records)


def dedupe_records(records: Iterable[FormRecord]) -> list[FormRecord]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[FormRecord] = []
    for record in records:
        key = (record.dataset, record.product_number, record.revision_date, record.pdf_url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def write_dataset(output_dir: Path, dataset: str, records: list[FormRecord]) -> dict[str, object]:
    dataset_dir = output_dir / dataset
    dataset_dir.mkdir(parents=True, exist_ok=True)
    rows = [record.as_dict() for record in records]
    generated_at = now_iso()

    json_payload = {
        "dataset": dataset,
        "label": DATASETS[dataset]["label"],
        "source_url": DATASETS[dataset]["source_url"],
        "generated_at": generated_at,
        "record_count": len(rows),
        "records": rows,
    }

    json_path = dataset_dir / "forms.json"
    csv_path = dataset_dir / "forms.csv"

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(json_payload, file, indent=2, sort_keys=True)
        file.write("\n")

    fieldnames = list(FormRecord("", "", "", "", "", "", "", "", "").as_dict().keys())
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return {
        "dataset": dataset,
        "label": DATASETS[dataset]["label"],
        "source_url": DATASETS[dataset]["source_url"],
        "generated_at": generated_at,
        "record_count": len(rows),
        "json_path": str(json_path),
        "csv_path": str(csv_path),
    }


def write_manifest(output_dir: Path, summaries: list[dict[str, object]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at": now_iso(),
        "source": "IRS.gov",
        "datasets": summaries,
    }
    with (output_dir / "manifest.json").open("w", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2, sort_keys=True)
        file.write("\n")


def download_pdfs(output_dir: Path, records: Iterable[FormRecord], sleep_seconds: float = 0.1) -> None:
    pdf_dir = output_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    for record in records:
        parsed = urlparse(record.pdf_url)
        filename = Path(parsed.path).name
        target = pdf_dir / record.dataset / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.stat().st_size > 0:
            continue
        request = Request(record.pdf_url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=120) as response:
            target.write_bytes(response.read())
        if sleep_seconds:
            time.sleep(sleep_seconds)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def filter_records(records: Iterable[FormRecord], find_text: str) -> list[FormRecord]:
    needle = find_text.casefold()
    return [
        record
        for record in records
        if needle in record.product_number.casefold()
        or needle in record.title.casefold()
        or needle in record.revision_date.casefold()
    ]


def selected_datasets(value: str) -> list[str]:
    return ["current", "prior"] if value == "all" else [value]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        choices=("current", "prior", "all"),
        default="all",
        help="IRS dataset to sync.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated JSON and CSV files.",
    )
    parser.add_argument(
        "--items-per-page",
        type=int,
        default=DEFAULT_ITEMS_PER_PAGE,
        choices=(25, 50, 100, 200),
        help="IRS page size.",
    )
    parser.add_argument("--max-pages", type=int, help="Limit pages per dataset.")
    parser.add_argument("--sleep", type=float, default=0.1, help="Seconds between page fetches.")
    parser.add_argument("--download-pdfs", action="store_true", help="Mirror PDFs under data/irs/pdfs.")
    parser.add_argument("--find", help="Filter fetched records by product number, title, or revision date.")
    parser.add_argument("--stdout", action="store_true", help="Print records as JSON lines instead of writing files.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summaries: list[dict[str, object]] = []
    all_records: list[FormRecord] = []

    for dataset in selected_datasets(args.dataset):
        records = sync_dataset(
            dataset,
            items_per_page=args.items_per_page,
            max_pages=args.max_pages,
            sleep_seconds=args.sleep,
        )
        if args.find:
            records = filter_records(records, args.find)

        if args.stdout:
            for record in records:
                print(json.dumps(record.as_dict(), sort_keys=True))
        else:
            summaries.append(write_dataset(args.output_dir, dataset, records))

        all_records.extend(records)

    if args.download_pdfs:
        download_pdfs(args.output_dir, all_records, sleep_seconds=args.sleep)

    if not args.stdout:
        write_manifest(args.output_dir, summaries)
        for summary in summaries:
            print(f"{summary['dataset']}: {summary['record_count']} records")

    return 0


if __name__ == "__main__":
    sys.exit(main())
