from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sync_irs_forms import infer_kind, infer_revision_year, parse_rows


CURRENT_HTML = """
<table>
  <tr>
    <td><a href="/pub/irs-pdf/f1040.pdf">Form 1040</a></td>
    <td>U.S. Individual Income Tax Return</td>
    <td>2025</td>
    <td>12/31/2025</td>
  </tr>
</table>
"""


PRIOR_HTML = """
<table>
  <tr>
    <td><a href="/pub/irs-prior/f1040--2024.pdf">Form 1040</a></td>
    <td>U.S. Individual Income Tax Return</td>
    <td>2024</td>
  </tr>
</table>
"""


class SyncIRSFormsTests(unittest.TestCase):
    def test_parse_current_row(self) -> None:
        records = parse_rows("current", CURRENT_HTML, "https://example.test/current?page=0")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].product_number, "Form 1040")
        self.assertEqual(records[0].posted_date, "12/31/2025")
        self.assertEqual(records[0].pdf_url, "https://www.irs.gov/pub/irs-pdf/f1040.pdf")

    def test_parse_prior_row(self) -> None:
        records = parse_rows("prior", PRIOR_HTML, "https://example.test/prior?page=0")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].revision_year, "2024")
        self.assertEqual(records[0].pdf_url, "https://www.irs.gov/pub/irs-prior/f1040--2024.pdf")

    def test_infer_kind(self) -> None:
        self.assertEqual(infer_kind("Form W-9"), "form")
        self.assertEqual(infer_kind("Publication 1"), "publication")
        self.assertEqual(infer_kind("Instruction 709"), "instruction")
        self.assertEqual(infer_kind("Instructions for Form 1040"), "instruction")

    def test_infer_revision_year(self) -> None:
        self.assertEqual(infer_revision_year("Sep 2017"), "2017")
        self.assertEqual(infer_revision_year("2025"), "2025")
        self.assertEqual(infer_revision_year(""), "")


if __name__ == "__main__":
    unittest.main()
