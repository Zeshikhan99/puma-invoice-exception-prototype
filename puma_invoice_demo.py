"""Small, offline demonstration of the invoice-exception workflow in the deck.

All records are synthetic. No PUMA systems, model API, payment service, or vendor
master are connected. The A3 investigator chooses among read-only tools; the
fixed A4 policy owns release and escalation. Python 3.10+; no dependencies.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DATA = {
    "purchase_orders": {
        "PO-101": {"supplier": "SUP-1", "amount_eur": 9800},
        "PO-102": {"supplier": "SUP-1", "amount_eur": 10000},
        "PO-103": {"supplier": "SUP-1", "amount_eur": 9600},
        "PO-104": {"supplier": "SUP-2", "amount_eur": 12000},
    },
    "goods_receipts": {
        "PO-101": {"received": True},
        "PO-102": {"received": True},
        "PO-103": {"received": True},
        "PO-104": {"received": True},
    },
    "suppliers": {
        "SUP-1": {"approved": True, "bank_token": "BANK-1"},
        "SUP-2": {"approved": True, "bank_token": "BANK-2"},
    },
    "prior_invoices": {"INV-103": {"supplier": "SUP-1", "amount_eur": 9600}},
    "contract_prices": {"PO-102": {"approved_amendment": False}},
    "bank_change_requests": {"SUP-2": {"approved": False}},
}

ALLOWED_TOOLS = {
    "purchase_orders", "goods_receipts", "suppliers", "prior_invoices",
    "contract_prices", "bank_change_requests",
}


class ReadOnlyTools:
    def __init__(self, audit):
        self.audit = audit

    def read(self, component, collection, key):
        if collection not in ALLOWED_TOOLS:
            raise PermissionError(f"Tool not allowed: {collection}")
        result = DATA[collection].get(key)
        self.audit.append({"component": component, "action": "read_tool",
                           "tool": collection, "key": key, "found": result is not None})
        return result


def route(flags):
    """Fixed A4 policy: highest risk tier wins; A3 cannot override this."""
    tier3 = {"new_supplier", "bank_change", "over_limit", "low_confidence", "tax_or_legal"}
    tier2 = {"price_variance", "missing_receipt", "duplicate"}
    if tier3 & flags:
        return 3
    if tier2 & flags:
        return 2
    return 1


def investigate(invoice, flags, tools, audit):
    """A3 chooses investigation tools from observed exceptions, then drafts advice.

    This is an explicit local policy, not an LLM. Its autonomy is bounded to
    selecting read-only lookups and preparing an explanation for human review.
    """
    selected = []
    if "price_variance" in flags:
        selected.append(("contract_prices", invoice["po_id"]))
    if "duplicate" in flags:
        selected.append(("prior_invoices", invoice["invoice_id"]))
    if "bank_change" in flags:
        selected.extend([("suppliers", invoice["supplier_id"]),
                         ("bank_change_requests", invoice["supplier_id"])])
    if "missing_receipt" in flags:
        selected.append(("goods_receipts", invoice["po_id"]))
    evidence = []
    for collection, key in selected:
        value = tools.read("A3", collection, key)
        evidence.append({"tool": collection, "key": key, "result": value})
    observed = {item["tool"]: item["result"] for item in evidence}
    if "bank_change" in flags:
        if (observed.get("bank_change_requests") or {}).get("approved"):
            advice = "Hold; AP lead independently verifies the approved bank-change request."
        else:
            advice = "Hold; no approved bank-change request; AP lead verifies independently."
    elif "duplicate" in flags:
        advice = "Hold; AP checks the prior invoice and any payment record."
    elif "price_variance" in flags:
        if (observed.get("contract_prices") or {}).get("approved_amendment"):
            advice = "Ask buyer to verify the amendment; AP re-matches only after approval."
        else:
            advice = "No approved price amendment; ask buyer to verify and AP to re-match."
    elif "missing_receipt" in flags:
        advice = "Ask goods-receipt owner to confirm delivery; keep unresolved."
    else:
        advice = "Escalate to AP for investigation."
    audit.append({"component": "A3", "action": "draft_advice",
                  "selected_tools": [x[0] for x in selected], "advice": advice})
    return evidence, advice


def run_case(invoice, phase="shadow"):
    if phase not in {"shadow", "simulated_pilot"}:
        raise ValueError("Only shadow or simulated_pilot mode is supported")
    audit = [{"component": "A1", "action": "receive_structured_fixture",
              "invoice_id": invoice["invoice_id"]}]
    tools = ReadOnlyTools(audit)
    po = tools.read("A2", "purchase_orders", invoice["po_id"])
    receipt = tools.read("A2", "goods_receipts", invoice["po_id"])
    supplier = tools.read("A4", "suppliers", invoice["supplier_id"])
    prior = tools.read("A4", "prior_invoices", invoice["invoice_id"])

    flags = set()
    if not po or po["supplier"] != invoice["supplier_id"]:
        flags.add("new_supplier")
    elif abs(invoice["amount_eur"] - po["amount_eur"]) / po["amount_eur"] > .02:
        flags.add("price_variance")
    if not receipt or not receipt["received"]:
        flags.add("missing_receipt")
    if not supplier or not supplier["approved"]:
        flags.add("new_supplier")
    elif invoice["bank_token"] != supplier["bank_token"]:
        flags.add("bank_change")
    if prior:
        flags.add("duplicate")
    if invoice["amount_eur"] > 50000:
        flags.add("over_limit")
    if invoice["extraction_confidence"] < .95:
        flags.add("low_confidence")
    if invoice.get("tax_or_legal_question", False):
        flags.add("tax_or_legal")

    tier = route(flags)
    evidence, advice = investigate(invoice, flags, tools, audit) if tier > 1 else ([], None)
    if tier == 1:
        status = ("would_release_clean_match" if phase == "shadow"
                  else "released_to_simulated_payment_queue")
        owner = "A4 fixed rules"
    else:
        status = "pending_human_resolution_no_release"
        owner = "AP specialist" if tier == 2 else "AP lead"
    due_alert = bool(tier > 1 and invoice["days_to_due"] <= 5)
    audit.append({"component": "A4", "action": "route_and_log", "tier": tier,
                  "status": status, "owner": owner, "due_alert_to_ap_lead": due_alert})
    return {"case": invoice["case"], "invoice_id": invoice["invoice_id"],
            "synthetic": True, "phase": phase, "flags": sorted(flags), "tier": tier,
            "status": status, "owner": owner, "due_alert_to_ap_lead": due_alert,
            "investigation_evidence": evidence, "draft_advice": advice,
            "payment_executed": False, "master_data_changed": False, "audit": audit}


def simulate_case_b_resolution(original_invoice, actions):
    """Replay the correction loop only when explicit fictional approvals are supplied."""
    first = run_case(original_invoice, "shadow")
    assert first["tier"] == 2 and "price_variance" in first["flags"]
    if not actions.get("buyer_review", {}).get("po_price_confirmed"):
        raise PermissionError("Buyer review is required before correction")
    correction = actions.get("supplier_correction", {})
    if correction.get("original_invoice_id") != original_invoice["invoice_id"]:
        raise PermissionError("Supplier correction must link to the original invoice")
    if not actions.get("ap_approval", {}).get("approved"):
        raise PermissionError("AP approval is required before re-match")
    corrected = dict(original_invoice)
    corrected.update(invoice_id=correction["invoice_id"], amount_eur=correction["amount_eur"],
                     case="B corrected")
    after = run_case(corrected, "simulated_pilot")
    assert after["tier"] == 1 and not after["flags"]
    return {
        "case": "B correction loop", "synthetic": True,
        "events": [
            {"actor": "A2", "action": "mismatch", "result": "price 6% above PO"},
            {"actor": "A3", "action": "read-only investigation", "result": first["draft_advice"]},
            {"actor": "Buyer", "action": "simulated human review", "result": "PO price confirmed"},
            {"actor": "Supplier", "action": "simulated correction", "result": f"replacement invoice for EUR {correction['amount_eur']:,}"},
            {"actor": "AP specialist", "action": "simulated approval", "result": "correction accepted"},
            {"actor": "A2", "action": "re-match", "result": "clean match"},
            {"actor": "A4", "action": "release", "result": "fictitious payment queue only"},
        ],
        "before": {"tier": first["tier"], "status": first["status"]},
        "after": {"tier": after["tier"], "status": after["status"],
                  "payment_executed": after["payment_executed"]},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("cases.json"))
    parser.add_argument("--phase", choices=["shadow", "simulated_pilot"], default="shadow")
    parser.add_argument("--output", type=Path, default=Path("run_results.json"))
    parser.add_argument("--human-actions", type=Path,
                        default=Path(__file__).with_name("case_b_human_actions.json"))
    args = parser.parse_args()
    fixtures = json.loads(args.cases.read_text(encoding="utf-8"))
    results = [run_case(case, args.phase) for case in fixtures]
    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    case_b = next(case for case in fixtures if case["case"] == "price_6_percent_high")
    actions = json.loads(args.human_actions.read_text(encoding="utf-8"))
    resolution = simulate_case_b_resolution(case_b, actions)
    args.output.with_name("case_b_resolution.json").write_text(
        json.dumps(resolution, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for result in results:
        print(f"{result['case']}: Tier {result['tier']}, {result['status']}, "
              f"A3 lookups={len(result['investigation_evidence'])}")
    print(f"Wrote {args.output}")
    print("Wrote case_b_resolution.json (fictional human actions and queue release)")


if __name__ == "__main__":
    main()
