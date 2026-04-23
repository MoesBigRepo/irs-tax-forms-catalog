# IRS Tax Forms Catalog

GitHub-ready catalog of official IRS federal tax forms, instructions, publications,
and notices.

The repository tracks metadata and official PDF links from IRS.gov rather than
committing every PDF by default. This keeps git history small while still making
the catalog searchable, refreshable, and easy to mirror when needed.

## Data Sources

The sync script reads the public IRS indexes:

- Current forms, instructions, and publications:
  <https://www.irs.gov/forms-instructions-and-publications>
- Prior-year forms and instructions:
  <https://www.irs.gov/prior-year-forms-and-instructions>

The initial catalog generated on 2026-04-23 contains 3,112 current entries and
24,083 prior-year entries.

## Repository Layout

```text
data/irs/current/forms.json
data/irs/current/forms.csv
data/irs/prior/forms.json
data/irs/prior/forms.csv
data/irs/manifest.json
scripts/sync_irs_forms.py
tests/test_sync_irs_forms.py
```

Each record includes:

- `dataset`: `current` or `prior`
- `product_number`
- `title`
- `revision_date`
- `posted_date` for current products when IRS provides it
- `pdf_url`
- `source_page_url`
- `kind`, inferred from the product number
- `revision_year`, inferred from the revision date when available

## Refresh the Catalog

Requires Python 3.11 or newer and no third-party packages.

```bash
python3 scripts/sync_irs_forms.py --dataset all
```

To download PDFs into a local mirror, use:

```bash
python3 scripts/sync_irs_forms.py --dataset all --download-pdfs
```

PDF downloads are ignored by git by default because the complete IRS archive is
large and changes over time.

## Search Examples

Find all current 1040 products:

```bash
python3 scripts/sync_irs_forms.py --dataset current --find 1040 --stdout
```

Find prior-year W-2 products:

```bash
python3 scripts/sync_irs_forms.py --dataset prior --find W-2 --stdout
```

## Automation

`.github/workflows/update-irs-forms.yml` refreshes the data weekly and commits
changes back to the repository when IRS.gov updates the catalog.

## Disclaimer

This repository is an index of public IRS.gov resources. It is not tax advice,
does not replace IRS instructions, and should not be treated as an authoritative
filing system. Always verify forms, deadlines, and filing requirements directly
with the IRS or a qualified tax professional before filing.
