#!/usr/bin/env python3
"""Build a state tax forms catalog from official state source pages."""

from __future__ import annotations

import argparse
import csv
import json
import re
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


DEFAULT_SOURCE_FILE = Path("data/state_sources.json")
DEFAULT_OUTPUT_DIR = Path("data/states")
USER_AGENT = "irs-tax-forms-catalog/1.0 (+https://github.com/MoesBigRepo/irs-tax-forms-catalog)"
DOCUMENT_EXTENSIONS = (".pdf", ".xlsx", ".xls", ".docx", ".doc", ".csv")
CRAWL_PATTERNS = (
    r"(^|[^a-z])forms?([^a-z]|$)",
    r"(^|[^a-z])returns?([^a-z]|$)",
    r"(^|[^a-z])instructions?([^a-z]|$)",
    r"(^|[^a-z])publications?([^a-z]|$)",
    r"tax-return-forms",
    r"form-search",
    r"forms-and-instructions",
    r"forms-instructions",
    r"forms-publications",
    r"forms-name",
    r"forms-subject",
)


@dataclass(frozen=True)
class StateRecord:
    jurisdiction_type: str
    jurisdiction_code: str
    jurisdiction_name: str
    agency: str
    region: str
    record_type: str
    title: str
    form_number: str
    tax_year: str
    tax_category: str
    file_type: str
    document_url: str
    source_page_url: str
    source_label: str
    notes: str
    retrieved_at: str
    retrieval_status: str
    error: str

    def as_dict(self) -> dict[str, str]:
        return {
            "jurisdiction_type": self.jurisdiction_type,
            "jurisdiction_code": self.jurisdiction_code,
            "jurisdiction_name": self.jurisdiction_name,
            "agency": self.agency,
            "region": self.region,
            "record_type": self.record_type,
            "title": self.title,
            "form_number": self.form_number,
            "tax_year": self.tax_year,
            "tax_category": self.tax_category,
            "file_type": self.file_type,
            "document_url": self.document_url,
            "source_page_url": self.source_page_url,
            "source_label": self.source_label,
            "notes": self.notes,
            "retrieved_at": self.retrieved_at,
            "retrieval_status": self.retrieval_status,
            "error": self.error,
        }


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self.title = ""
        self.h1 = ""
        self._capture: str | None = None
        self._text: list[str] = []
        self._href = ""
        self._link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name: value or "" for name, value in attrs}
        if tag == "title":
            self._capture = "title"
            self._text = []
        elif tag == "h1" and not self.h1:
            self._capture = "h1"
            self._text = []
        elif tag == "a":
            self._href = attr_map.get("href", "")
            self._link_text = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._text.append(data)
        if self._href:
            self._link_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == self._capture:
            text = clean_text("".join(self._text))
            if self._capture == "title":
                self.title = text
            elif self._capture == "h1":
                self.h1 = text
            self._capture = None
            self._text = []
        elif tag == "a" and self._href:
            self.links.append({"href": self._href, "text": clean_text("".join(self._link_text))})
            self._href = ""
            self._link_text = []


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def fetch_html(
    url: str,
    retries: int = 3,
    sleep_seconds: float = 0.5,
    allow_insecure_ssl: bool = False,
) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    context = ssl._create_unverified_context() if allow_insecure_ssl else None
    for attempt in range(1, retries + 1):
        try:
            with urlopen(request, timeout=60, context=context) as response:
                encoding = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(encoding, errors="replace")
        except (HTTPError, URLError, TimeoutError) as exc:
            if attempt == retries:
                raise RuntimeError(f"failed to fetch {url}: {exc}") from exc
            time.sleep(sleep_seconds * attempt)
    raise RuntimeError(f"failed to fetch {url}")


def parse_page(url: str, allow_insecure_ssl: bool = False) -> LinkParser:
    parser = LinkParser()
    parser.feed(fetch_html(url, allow_insecure_ssl=allow_insecure_ssl))
    return parser


def source_catalog(source_file: Path) -> dict[str, object]:
    with source_file.open(encoding="utf-8") as file:
        return json.load(file)


def sync_states(
    source_file: Path = DEFAULT_SOURCE_FILE,
    max_depth: int = 1,
    max_pages_per_state: int = 25,
    sleep_seconds: float = 0.1,
) -> tuple[list[StateRecord], list[dict[str, str]]]:
    catalog = source_catalog(source_file)
    records: list[StateRecord] = []
    errors: list[dict[str, str]] = []
    retrieved_at = now_iso()

    for jurisdiction in catalog["jurisdictions"]:
        queue: list[tuple[str, str, int]] = [
            (source["url"], source["label"], 0) for source in jurisdiction["source_urls"]
        ]
        source_ssl_options = {
            normalize_url(source["url"]): bool(source.get("allow_insecure_ssl", False))
            for source in jurisdiction["source_urls"]
        }
        jurisdiction_allow_insecure_ssl = any(source_ssl_options.values())
        visited: set[str] = set()
        pages_seen = 0

        while queue and pages_seen < max_pages_per_state:
            url, source_label, depth = queue.pop(0)
            normalized_url = normalize_url(url)
            if normalized_url in visited:
                continue
            visited.add(normalized_url)

            try:
                parser = parse_page(
                    normalized_url,
                    allow_insecure_ssl=source_ssl_options.get(
                        normalized_url, jurisdiction_allow_insecure_ssl
                    ),
                )
            except RuntimeError as exc:
                errors.append(
                    {
                        "jurisdiction_code": jurisdiction["code"],
                        "source_label": source_label,
                        "url": normalized_url,
                        "error": str(exc),
                    }
                )
                records.append(
                    build_record(
                        jurisdiction,
                        record_type="source_page",
                        title=source_label,
                        document_url=normalized_url,
                        source_page_url=normalized_url,
                        source_label=source_label,
                        retrieved_at=retrieved_at,
                        retrieval_status="fetch_error",
                        error=str(exc),
                    )
                )
                continue

            pages_seen += 1
            page_title = parser.h1 or parser.title or source_label
            records.append(
                build_record(
                    jurisdiction,
                    record_type="source_page",
                    title=page_title,
                    document_url=normalized_url,
                    source_page_url=normalized_url,
                    source_label=source_label,
                    retrieved_at=retrieved_at,
                    retrieval_status="ok",
                    error="",
                )
            )

            for link in parser.links:
                absolute_url = normalize_url(urljoin(normalized_url, link["href"]))
                if not should_keep_url(absolute_url):
                    continue

                link_text = link["text"] or Path(urlparse(absolute_url).path).name
                if is_document_url(absolute_url):
                    records.append(
                        build_record(
                            jurisdiction,
                            record_type="document",
                            title=link_text,
                            document_url=absolute_url,
                            source_page_url=normalized_url,
                            source_label=source_label,
                            retrieved_at=retrieved_at,
                            retrieval_status="ok",
                            error="",
                        )
                    )
                elif depth < max_depth and should_crawl_link(jurisdiction, absolute_url, link_text):
                    queue.append((absolute_url, link_text or source_label, depth + 1))

            if sleep_seconds:
                time.sleep(sleep_seconds)

    return dedupe_records(records), errors


def build_record(
    jurisdiction: dict[str, object],
    record_type: str,
    title: str,
    document_url: str,
    source_page_url: str,
    source_label: str,
    retrieved_at: str,
    retrieval_status: str,
    error: str,
) -> StateRecord:
    return StateRecord(
        jurisdiction_type="state",
        jurisdiction_code=str(jurisdiction["code"]),
        jurisdiction_name=str(jurisdiction["name"]),
        agency=str(jurisdiction["agency"]),
        region=str(jurisdiction["region"]),
        record_type=record_type,
        title=clean_text(title),
        form_number=infer_form_number(title, document_url),
        tax_year=infer_tax_year(title, document_url),
        tax_category=infer_tax_category(title, source_page_url),
        file_type=file_type(document_url),
        document_url=document_url,
        source_page_url=source_page_url,
        source_label=source_label,
        notes=str(jurisdiction.get("notes", "")),
        retrieved_at=retrieved_at,
        retrieval_status=retrieval_status,
        error=error,
    )


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return url
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme}://{parsed.netloc}{path}{query}"


def should_keep_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.casefold()
    return parsed.scheme in {"http", "https"} and not parsed.fragment and "uat" not in host


def is_document_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith(DOCUMENT_EXTENSIONS)


def should_crawl_link(jurisdiction: dict[str, object], url: str, link_text: str) -> bool:
    if is_document_url(url):
        return False
    if not is_allowed_host(jurisdiction, url):
        return False
    haystack = f"{urlparse(url).path} {link_text}".casefold()
    return any(re.search(pattern, haystack) for pattern in CRAWL_PATTERNS)


def is_allowed_host(jurisdiction: dict[str, object], url: str) -> bool:
    host = urlparse(url).netloc.casefold()
    if not host:
        return False
    allowed_bases = {
        base_domain(urlparse(source["url"]).netloc)
        for source in jurisdiction["source_urls"]
        if urlparse(source["url"]).netloc
    }
    return any(host == base or host.endswith(f".{base}") for base in allowed_bases)


def base_domain(host: str) -> str:
    parts = host.casefold().split(".")
    if len(parts) <= 2:
        return host.casefold()
    return ".".join(parts[-2:])


def file_type(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower().lstrip(".")
    return suffix or "html"


def infer_tax_year(title: str, url: str) -> str:
    matches = re.findall(r"\b(20\d{2}|19\d{2})\b", f"{title} {url}")
    return matches[-1] if matches else ""


def infer_form_number(title: str, url: str) -> str:
    text = clean_text(title)
    patterns = [
        r"\bSchedule\s+([A-Z][A-Z0-9-]*)\b",
        r"\b(?:Form|Schedule)\s+([A-Z]{0,4}[- ]?\d{1,5}[A-Z0-9-]*)\b",
        r"\b([A-Z]{1,5}[- ]?\d{1,5}[A-Z0-9-]*)\b",
        r"\b(\d{2,4}[- ]\d{2,4}[A-Z]?)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper().replace(" ", "-")

    filename = Path(urlparse(url).path).stem
    match = re.search(r"([A-Za-z]{1,5}[-_]?\d{1,5}[A-Za-z0-9-]*)", filename)
    return match.group(1).upper().replace("_", "-") if match else ""


def infer_tax_category(title: str, source_page_url: str) -> str:
    text = f"{title} {source_page_url}".casefold()
    categories = {
        "individual": ("individual", "personal income", "resident", "nonresident", "1040"),
        "business": ("business", "corporate", "corporation", "franchise", "partnership", "pass-through"),
        "sales_use": ("sales", "use tax", "surtax", "resale"),
        "withholding": ("withholding", "payroll", "employer"),
        "property": ("property", "real estate", "assessment"),
        "estate_fiduciary": ("estate", "fiduciary", "trust"),
        "excise": ("excise", "fuel", "tobacco", "cigarette", "alcohol", "motor"),
    }
    for category, needles in categories.items():
        if any(needle in text for needle in needles):
            return category
    return ""


def dedupe_records(records: Iterable[StateRecord]) -> list[StateRecord]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[StateRecord] = []
    for record in records:
        key = (record.jurisdiction_code, record.record_type, record.document_url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def write_outputs(output_dir: Path, records: list[StateRecord], errors: list[dict[str, str]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [record.as_dict() for record in records]
    generated_at = now_iso()
    by_state: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for record in records:
        by_state[record.jurisdiction_code] = by_state.get(record.jurisdiction_code, 0) + 1
        by_type[record.record_type] = by_type.get(record.record_type, 0) + 1

    payload = {
        "dataset": "states",
        "generated_at": generated_at,
        "record_count": len(rows),
        "records": rows,
    }
    with (output_dir / "forms.json").open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)
        file.write("\n")

    fieldnames = list(
        StateRecord("", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "").as_dict()
    )
    with (output_dir / "forms.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    manifest = {
        "dataset": "states",
        "generated_at": generated_at,
        "record_count": len(rows),
        "record_count_by_state": dict(sorted(by_state.items())),
        "record_count_by_type": dict(sorted(by_type.items())),
        "errors": errors,
    }
    with (output_dir / "manifest.json").open("w", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2, sort_keys=True)
        file.write("\n")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-file", type=Path, default=DEFAULT_SOURCE_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-depth", type=int, default=1)
    parser.add_argument("--max-pages-per-state", type=int, default=25)
    parser.add_argument("--sleep", type=float, default=0.1)
    parser.add_argument("--stdout", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    records, errors = sync_states(
        source_file=args.source_file,
        max_depth=args.max_depth,
        max_pages_per_state=args.max_pages_per_state,
        sleep_seconds=args.sleep,
    )
    if args.stdout:
        for record in records:
            print(json.dumps(record.as_dict(), sort_keys=True))
        for error in errors:
            print(json.dumps({"error": error}, sort_keys=True), file=sys.stderr)
    else:
        write_outputs(args.output_dir, records, errors)
        print(f"states: {len(records)} records")
        if errors:
            print(f"state source errors: {len(errors)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
