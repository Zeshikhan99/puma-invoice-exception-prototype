"""Meaningful routing and permission checks for the synthetic demo."""

import json
import unittest
from pathlib import Path

from puma_invoice_demo import ReadOnlyTools, run_case, simulate_case_b_resolution


CASES = json.loads(Path(__file__).with_name("cases.json").read_text(encoding="utf-8"))
ACTIONS = json.loads(Path(__file__).with_name("case_b_human_actions.json").read_text(encoding="utf-8"))


class WorkflowTests(unittest.TestCase):
    def test_four_cases_and_read_only_boundary(self):
        results = [run_case(case) for case in CASES]
        self.assertEqual([r["tier"] for r in results], [1, 2, 2, 3])
        self.assertEqual(results[0]["status"], "would_release_clean_match")
        self.assertTrue(all(r["status"] == "pending_human_resolution_no_release"
                            for r in results[1:]))
        self.assertTrue(results[2]["due_alert_to_ap_lead"])
        self.assertFalse(any(r["payment_executed"] or r["master_data_changed"]
                             for r in results))
        self.assertEqual([len(r["investigation_evidence"]) for r in results], [0, 1, 1, 2])
        self.assertIn("No approved price amendment", results[1]["draft_advice"])
        self.assertIn("no approved bank-change request", results[3]["draft_advice"])

    def test_only_bounded_read_tools(self):
        with self.assertRaises(PermissionError):
            ReadOnlyTools([]).read("A3", "write_supplier_bank", "SUP-1")

    def test_pilot_release_is_only_simulated_and_only_tier_one(self):
        results = [run_case(case, "simulated_pilot") for case in CASES]
        self.assertEqual(results[0]["status"], "released_to_simulated_payment_queue")
        self.assertTrue(all(r["status"] == "pending_human_resolution_no_release"
                            for r in results[1:]))
        self.assertFalse(any(r["payment_executed"] for r in results))

    def test_price_correction_requires_human_steps_and_rematch(self):
        resolution = simulate_case_b_resolution(CASES[1], ACTIONS)
        self.assertEqual(resolution["before"]["tier"], 2)
        self.assertEqual(resolution["after"]["tier"], 1)
        self.assertFalse(resolution["after"]["payment_executed"])
        self.assertIn("simulated approval", [e["action"] for e in resolution["events"]])
        self.assertEqual(resolution["events"][-2]["result"], "clean match")

    def test_price_correction_does_not_release_without_ap_approval(self):
        actions = json.loads(json.dumps(ACTIONS))
        actions["ap_approval"]["approved"] = False
        with self.assertRaises(PermissionError):
            simulate_case_b_resolution(CASES[1], actions)


if __name__ == "__main__":
    unittest.main()
