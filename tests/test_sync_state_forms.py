from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sync_state_forms import infer_form_number, infer_tax_category, infer_tax_year


class SyncStateFormsTests(unittest.TestCase):
    def test_infer_form_number(self) -> None:
        self.assertEqual(infer_form_number("Form 502 Maryland Resident Income Tax Return", ""), "502")
        self.assertEqual(infer_form_number("D-400 Individual Income Tax Return", ""), "D-400")
        self.assertEqual(infer_form_number("Schedule A Itemized Deductions", ""), "A")

    def test_infer_tax_year(self) -> None:
        self.assertEqual(infer_tax_year("2025 Individual Income Tax Return", ""), "2025")
        self.assertEqual(infer_tax_year("Resident return", "/forms/2024/d-400.pdf"), "2024")
        self.assertEqual(infer_tax_year("Power of Attorney", ""), "")

    def test_infer_tax_category(self) -> None:
        self.assertEqual(infer_tax_category("Individual Income Tax Return", ""), "individual")
        self.assertEqual(infer_tax_category("Sales and Use Tax Return", ""), "sales_use")
        self.assertEqual(infer_tax_category("Corporate Franchise Tax", ""), "business")


if __name__ == "__main__":
    unittest.main()
