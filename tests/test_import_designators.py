import unittest
from unittest.mock import patch

from inserter_platform import importer


class ImportDesignatorTests(unittest.TestCase):
    def test_customer_identifiers_in_bom_and_placement(self):
        names = ["X-AL", "X-AN1", "X-AN2", "X-CANB", "X-CANA", "X-TMP_NTC",
                 "X-DIAG1'", "Z_K5K6", "Z_RPA5A7", "ZEN", "ZUX", "RP.A2.1", "R1"]
        self.assertEqual(importer.split_designators(",".join(names)), names)
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(importer.split_placement_designators(name), [name])

    def test_normalization_and_existing_notes(self):
        self.assertEqual(importer.split_designators("x-diag1’; rp·a2·1; zen;zux"),
                         ["X-DIAG1'", "RP.A2.1", "ZEN", "ZUX"])
        self.assertEqual(importer.parse_designator_cell("R1 R2 nie montowac; X-AL DNP"),
                         (["R1", "R2", "X-AL"], "nie montowac | DNP"))
        self.assertEqual(importer.split_designators("TP20+TP21+TP22 / J1"),
                         ["TP20", "TP21", "TP22", "J1"])
        self.assertEqual(importer.split_designators("R1, nie montowac, R2"), ["R1", "R2"])

    def test_invalid_identifier_segments(self):
        for name in ("X--AL", "X__AL", "_X1", "1X", "X-", "X_", "X@AL", "R..1"):
            with self.subTest(name=name):
                self.assertEqual(importer.split_designators(name), [])
                self.assertEqual(importer.split_placement_designators(name), [])

    def test_bom_and_pp_pipeline_keeps_missing_points_explicit(self):
        bom_rows = [
            {"designators": "X-CANA,X-CANB", "value": "RJ45", "medcom_index": "M-RJ45", "source_row": 2},
            {"designators": "ZEN,ZUX", "value": "wire", "medcom_index": "M-WIRE", "source_row": 3},
            {"designators": "X-DIAG1’", "value": "screw", "medcom_index": "M-SCREW", "source_row": 4},
        ]
        pp_rows = [{"designator": name, "x": 1.5, "y": 2, "rotation": 90, "source_row": i}
                   for i, name in enumerate(["X-CANA", "X-CANB", "ZEN", "ZUX", "X-EXTRA"], 2)]
        with patch.object(importer, "read_xlsx_table", side_effect=[bom_rows, pp_rows]):
            steps, points, summary = importer.prepare_prepared_import(bom_bytes=b"bom", pp_bytes=b"pp")
        self.assertEqual(summary["bomDesignators"], 5)
        self.assertEqual(summary["bomRowsWithoutDesignators"], [])
        self.assertEqual(summary["ppInvalidRows"], [])
        self.assertEqual(summary["missingInPp"], ["X-DIAG1'"])
        self.assertEqual(summary["extraInPp"], ["X-EXTRA"])
        self.assertEqual(len(points), 4)
        self.assertEqual(steps[-1]["notes"], "Brak punktu P&P: X-DIAG1'")


if __name__ == "__main__":
    unittest.main()
