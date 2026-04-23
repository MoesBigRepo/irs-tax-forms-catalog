# Tax Forms Catalog

GitHub-ready catalog of official IRS federal tax forms, instructions,
publications, notices, and selected official state tax form sources.

The repository tracks metadata and official document links rather than
committing every PDF by default. This keeps git history small while still making
the catalog searchable, refreshable, and easy to mirror when needed.

## Data Sources

The federal sync script reads the public IRS indexes:

- Current forms, instructions, and publications:
  <https://www.irs.gov/forms-instructions-and-publications>
- Prior-year forms and instructions:
  <https://www.irs.gov/prior-year-forms-and-instructions>

The state sync script reads official source pages listed in
`data/state_sources.json`. The current state set includes Atlantic coastal East
Coast states plus Texas, California, Missouri, Mississippi, and Washington.

The current generated catalog contains:

- 3,112 current IRS entries
- 24,083 prior-year IRS entries
- 3,390 state source and document entries

## Repository Layout

```text
index.html
assets/app.js
assets/styles.css
data/irs/current/forms.json
data/irs/current/forms.csv
data/irs/prior/forms.json
data/irs/prior/forms.csv
data/irs/manifest.json
data/state_sources.json
data/states/forms.json
data/states/forms.csv
data/states/manifest.json
scripts/sync_irs_forms.py
scripts/sync_state_forms.py
tests/test_sync_irs_forms.py
tests/test_sync_state_forms.py
```

IRS records include:

- `dataset`: `current` or `prior`
- `product_number`
- `title`
- `revision_date`
- `posted_date` for current products when IRS provides it
- `pdf_url`
- `source_page_url`
- `kind`, inferred from the product number
- `revision_year`, inferred from the revision date when available

State records include:

- `jurisdiction_code` and `jurisdiction_name`
- `agency`
- `record_type`: `source_page` or `document`
- `title`
- `form_number`, `tax_year`, and `tax_category` when inferred
- `file_type`
- `document_url`
- `source_page_url`
- `retrieval_status` and `error` for source-page fetch issues

## Refresh the Catalog

Requires Python 3.11 or newer and no third-party packages.

```bash
python3 scripts/sync_irs_forms.py --dataset all
python3 scripts/sync_state_forms.py --max-pages-per-state 8
```

To download PDFs into a local mirror, use:

```bash
python3 scripts/sync_irs_forms.py --dataset all --download-pdfs
```

PDF downloads are ignored by git by default because the complete IRS archive is
large and changes over time.

## Search Examples

Open `index.html` through GitHub Pages or a local web server for the searchable
browser catalog.

Find all current 1040 products:

```bash
python3 scripts/sync_irs_forms.py --dataset current --find 1040 --stdout
```

Find prior-year W-2 products:

```bash
python3 scripts/sync_irs_forms.py --dataset prior --find W-2 --stdout
```

Regenerate the selected state catalog:

```bash
python3 scripts/sync_state_forms.py --max-pages-per-state 8
```

## Automation

`.github/workflows/update-irs-forms.yml` refreshes the federal and state data
weekly and commits changes back to the repository when official source pages
change.

Some state portals use JavaScript, blocking, or session-backed search. When a
source page cannot be fetched by the static crawler, the catalog preserves that
source with `retrieval_status=fetch_error` and records the reason in
`data/states/manifest.json`.

## Disclaimer

This repository is an index of public tax agency resources. It is not tax
advice, does not replace official instructions, and should not be treated as an
authoritative filing system. Always verify forms, deadlines, and filing
requirements directly with the IRS, the relevant state agency, or a qualified
tax professional before filing.
