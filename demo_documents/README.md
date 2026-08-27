# Demo documents

Realistic `.pdf` files to upload through the dashboard's **Submit an
artifact → Upload document** form (`POST /vendors/artifacts/upload`),
instead of typing text into the paste box. One file per vendor per
**doc type** -- every option in the dashboard's Doc type dropdown has a
matching file here, for all three seeded vendors. Each one exercises the
real server-side extraction path (`api/document_extraction.py`) exactly
the way a judge's own PDF would.

Content is deliberately consistent with `scripts/seed_demo_data.py`'s
existing narrative -- same vendors, same control facts (MFA posture, log
retention, breach-notification window, liability terms), same shared
subprocessor -- so uploading one of these *adds* to the seeded story
instead of contradicting it.

| Doc type (dropdown value) | Routes to | File |
|---|---|---|
| `SOC2` | Intake | `SOC2_Type_II_Report.pdf` |
| `ISO` | Intake | `ISO_27001_Certification_Summary.pdf` |
| `pen-test` | Intake | `Penetration_Test_Summary.pdf` |
| `DPA` | Contract Intelligence | `Data_Processing_Agreement.pdf` |
| `MSA` | Contract Intelligence | `Master_Service_Agreement.pdf` |
| `contract` | Contract Intelligence | `Vendor_Contract.pdf` |
| `SLA` | Contract Intelligence | `Service_Level_Agreement.pdf` |
| `order form` | Contract Intelligence | `Order_Form.pdf` |

Each file lives under `<vendor-slug>/`:

- `cloudy-saas-inc/` -- **Cloudy SaaS Inc** (critical tier). Its base
  seed already has a SOC 2 finding (MFA satisfied, CC6.8 log-retention
  gap) and one subprocessor; it has **no contract on file** until you
  upload one of its DPA/MSA/contract/SLA/order-form PDFs here.
- `umbrella-corp/` -- **Umbrella Corp** (moderate tier). The base seed
  only ever submits a *poisoned* SOC 2 for this vendor (Model Armor
  blocks it, on purpose, as the injection demo), so its SOC2 PDF here is
  the first real one. Its contract-type PDFs disclose the same
  subprocessor (AWS us-east-1) Cloudy SaaS Inc and Sibling Analytics Inc
  already use -- upload one to grow the Concentration Risk cluster from
  2 vendors to 3.
- `sibling-analytics-inc/` -- **Sibling Analytics Inc** (moderate tier).
  Already has a DPA and subprocessor from the base seed; these PDFs are
  here for completeness and to demo the other doc types against a
  vendor that already has other data on file.

## How to use these

1. Open the dashboard, seed the base demo data if you haven't
   (`BULWARK_SEED_DEMO_DATA=true` on boot, or `./scripts/seed_live_demo_data.sh`
   against a deployed instance).
2. **Vendors → Submit artifact**, pick the vendor from the dropdown
   (or "+ New vendor…" if trying against a fresh instance with no seed
   data), pick the matching doc type, switch to the **Upload document**
   tab, and pick the file from the table above.
3. Needs Gemini credentials configured (same requirement as the paste-text
   path) -- Intake / Contract Intelligence still run the real
   extraction and cross-referencing agents on whatever text comes out
   of the file.

These are generated, not hand-typed -- a small pure-Python PDF writer
(no new runtime dependency; the same raw PDF object/xref technique
already proven against `pypdf` in `tests/test_document_extraction.py`)
lays out the text above into real, multi-page-capable PDF files. Ask
for the generator script if you need to add a vendor or change the
content; it isn't part of the shipped app so it isn't committed here.
