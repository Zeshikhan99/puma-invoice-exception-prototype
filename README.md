# PUMA invoice-exception prototype

This package uses fictional invoices and fixture records. It connects to no PUMA system, supplier, email service, bank or payment service.

## Files

- `PUMA_Invoice_Exception_Agent.langflow.json` — importable Langflow 1.8 flow: Chat Input → Agent → Chat Output, with four read-only tools and a five-iteration limit.
- `cases.json` — four synthetic invoice inputs (clean, price variance, duplicate and bank change).
- `case_b_human_actions.json` — explicit fictional buyer review, corrected supplier invoice and AP approval for the price case.
- `puma_invoice_demo.py` — offline fixed-rule routing and safety replay. It is separate from the LLM Agent node.
- `test_demo.py` — permission, escalation and correction-loop checks.
- `run_results.json` — observed output from the offline shadow replay.
- `simulated_pilot_results.json` — observed output from the offline simulated-pilot replay; no real invoice is released.
- `case_b_resolution.json` — fictional correction and approval loop.
- `langflow_validation.json` — import and tool-component checks performed with Langflow 1.8.0.
- `PUMA_Langflow_Flow_Screenshot.png` — actual Langflow editor capture of the connected flow. It does not show a model run.

## Langflow setup

1. Install and start Langflow 1.8.x. Import `PUMA_Invoice_Exception_Agent.langflow.json` from the flow menu.
2. In the Agent node, select a supported tool-calling model and provide the provider credential. The file contains no key. The export stores `gpt-5-mini` as a proposed option, but the imported editor displayed “Select a model”.
3. Paste one object from `cases.json` into Chat Input and run it. The Agent prompt asks the model to choose relevant read-only lookups and return `classification`, `short_reason`, `evidence`, `recommended_human_owner`, and `draft_supplier_email` as JSON.
4. Review the tool trace and response. The Agent has no write, email-send, release, bank-update or payment tool. Fixed policy and AP staff retain those decisions in the proposed process.

The flow imported into Langflow 1.8.0 and each custom read-only lookup returned the expected fixture record. A provider credential was unavailable in this workspace, so the package contains no live LLM tool-call trace. The four-case results and Case B loop below are outputs of the offline fixed-rule replay.

## Reproduce the offline replay

Python 3.10+; no third-party packages are needed:

```bash
python3 -m unittest discover -s . -p 'test_demo.py' -v
python3 puma_invoice_demo.py --output run_results.json
```

The five tests cover four routes, read-only permissions, no real payment, explicit AP approval and corrected-invoice re-match. Case B remains pending until the fictional human-action fixture supplies buyer confirmation, a linked €10,000 correction and AP approval. Only then does the fixed policy re-match and place it in a fictitious payment queue. Nothing is paid or sent.

## Citation and AI use

Halstrick, L. (2026). *PUMA invoice-exception prototype* [Computer software and data]. https://github.com/Zeshikhan99/puma-invoice-exception-prototype

The PowerPoint Appendix D documents the prototype, tests, results and AI use. The author used Claude for source research, drafting and critique. ChatGPT assisted with slide and note editing, process and financial checks, source and APA checks, Langflow configuration, and offline Python code and tests. All AI-generated content was reviewed and verified by the author. The presentation identifies the Python replay separately from an unrun Langflow model.
