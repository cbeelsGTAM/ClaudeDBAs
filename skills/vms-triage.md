You are guiding an analyst through VMS invoice triage. Each item in the queue is an invoice or attachment that needs attention before it can be processed in VMS.

## Step 1: Fetch the queue

Run:
```bash
PYTHONPATH="c:/dev/scripts/Python" "C:/Program Files/Python311/python.exe" c:/dev/claudedbas/scripts/Python/VMSAI/triage.py --env prod
```

Parse the JSON. Each item has an `_issue` field classifying the problem.

## Step 2: Present items one at a time

For each item show:
- **[N of Total]** Vendor: `VendorName` | Invoice #: `InvoiceNumber` | Date: `InvoiceDate` | Amount: `Amount`
- From: `From` | File: just the filename from `SourceFile`
- **Issue:** [human-readable description — see guide below]

If the item has a `SourceFile` (PDF path), open it automatically before asking the analyst anything:
```powershell
Start-Process "<SourceFile path>"
```

Then present the recommended action and ask the analyst to confirm before running anything.

To run any SQL command:
```bash
PYTHONPATH="c:/dev/scripts/Python" "C:/Program Files/Python311/python.exe" c:/dev/claudedbas/scripts/Python/VMSAI/triage.py --exec "COMMAND" --env prod
```

Always show the exact SQL and wait for confirmation before executing.

---

## Issue Resolution Guide

### vendor-not-found
AI couldn't match the vendor name. `InvNameDesc` contains a search query to find candidates — run it:
```bash
PYTHONPATH="c:/dev/scripts/Python" "C:/Program Files/Python311/python.exe" c:/dev/claudedbas/scripts/Python/VMSAI/triage.py --exec "<InvNameDesc value>" --env prod
```
Show results. Ask analyst which vendor matches. Replace `TBD` in `RunCmd` with the chosen VendorID, then run:
1. The alias INSERT (modified RunCmd)
2. `Retry` to re-queue the invoice

### no-contract
`Contract` column is blank — vendor exists but has no active contract.
Tell the analyst: "No contract on file for [VendorName] — send the invoice to the originator/Emily asking for a contract to be set up. Once it's done, run Retry."
Show the `Retry` command for when they're ready.

### no-workflow
Workflow is missing. First look up available workflows:
```bash
PYTHONPATH="c:/dev/scripts/Python" "C:/Program Files/Python311/python.exe" c:/dev/claudedbas/scripts/Python/VMSAI/triage.py --exec "EXEC vms_UTILITY.[HELPER].[GetWFCreationIDs] 'research'" --env prod
```
Show results and ask analyst which workflow applies.

- **Vendor-level default**: replace `XXX` in `SetWorkflow` with the workflow name and run it.
- **Contract-level override**: build and run:
```sql
INSERT INTO [VMSAI].[VMS].[ContractWorkflowOverrides] (ContractID, WorkflowID, WorkflowStepID)
VALUES (<ContractID>, <WorkflowID>, <WorkflowStepID>)
```

### no-invoice-number
AI couldn't extract an invoice number. Tell analyst to open `SourceFile` and check.
- If the number is genuinely missing: ask the originator, then run `Retry` once it's added.
- If AI keeps missing it: flag for Chris B to update the prompt.

### duplicate-number
Same invoice number found under `SameNumberVendor` at `SameNumberLink`.
Tell analyst: "Invoice [InvoiceNumber] already exists under [SameNumberVendor]. If someone entered it manually, run IgnoreCMD to remove it from the queue."
Show `IgnoreCMD` for confirmation before running.

### non-invoice
AI flagged as non-invoice. The PDF will already be open. Ask the analyst to confirm:
- **Confirmed non-invoice**: run `RunCmd` (marks it as confirmed, clears it from the queue).
- **Actually is an invoice** (AI wrong): run `Retry` to re-queue. If it keeps failing, flag for Chris B.

### no-invoice-number
AI couldn't extract an invoice number. The PDF will already be open. Ask the analyst to check:
- If the number is genuinely missing: ask the originator, then run `Retry` once it's added.
- If AI keeps missing it: flag for Chris B to update the prompt.

### ready
All fields present. The queue may return multiple rows for the same invoice (same InvoiceID), one per candidate contract match. **Group all rows with the same InvoiceID together as a single item.**

**Auto-select contract if memo matches:** Before asking the analyst, check whether any candidate contract's name contains a word or account number that also appears in `InvNameDesc`. If exactly one contract matches, auto-select it — state which contract was chosen and why, then proceed without asking. If zero contracts match, show the candidate list and ask the analyst to pick (or choose none). If multiple contracts match (ambiguous), create the invoice **without a contract** — tell the analyst why and proceed.

Show the analyst the list of candidate contracts (with 2026 budget and extrapolated monthly×12 / quarterly×4 annualized amounts) and ask which ONE to use (or none, if the invoice shouldn't be tied to a contract).

`CreateVMSInvoices` takes `(InvoiceID, ContractID)` and must be run **exactly once** per invoice. Use the `RunCmd` from the row matching the chosen contract, or build `EXEC [VMS].[CreateVMSInvoices] <InvoiceID>` (no second argument) if no contract applies.

- If vendor or contract looks wrong: try `Retry` first.
- Persistent wrong-vendor mismatches: flag for Chris B to update the prompt.

---

## After each item
Confirm it's resolved, then move to the next. At the end, summarize: how many resolved, how many need follow-up (and with whom).
