# Demo documents

Realistic `.docx` files to upload through the dashboard's **Submit an
artifact → Upload document** form (`POST /vendors/artifacts/upload`),
instead of typing text into the paste box. Each one exercises the real
server-side extraction path (`api/document_extraction.py`) exactly the
way a judge's own PDF/DOCX would.

Content is deliberately consistent with `scripts/seed_demo_data.py`'s
existing narrative -- same vendors, same control gaps, same shared
subprocessor -- so uploading one of these *adds* to the seeded story
instead of contradicting it.

| File | Upload against | Doc type | What it fills in |
|---|---|---|---|
| `cloudy-saas-inc/SOC2_Type_II_Report.docx` | Cloudy SaaS Inc | `SOC2` | Re-affirms the seeded MFA finding and the CC6.8 log-retention gap |
| `cloudy-saas-inc/Data_Processing_Agreement.docx` | Cloudy SaaS Inc | `DPA` | This vendor has **no contract on file** in the base seed -- upload this to populate its Contract Terms tab |
| `umbrella-corp/SOC2_Type_II_Report.docx` | Umbrella Corp | `SOC2` | The base seed only ever submits a *poisoned* SOC 2 for this vendor (Model Armor blocks it, on purpose, as the injection demo) -- this is a real, clean one |
| `umbrella-corp/Data_Processing_Agreement.docx` | Umbrella Corp | `DPA` | Fills this vendor's empty Contract Terms **and** Subprocessors tabs. It discloses the same subprocessor (AWS us-east-1) Cloudy SaaS Inc and Sibling Analytics Inc already use -- upload it to grow the Concentration Risk cluster from 2 vendors to 3 |
| `sibling-analytics-inc/SOC2_Type_II_Report.docx` | Sibling Analytics Inc | `SOC2` | This vendor already has a DPA from the base seed; this SOC 2 is here for completeness / to demo the SOC2 doc type against a vendor that already has other data |
| `sibling-analytics-inc/Data_Processing_Agreement.docx` | Sibling Analytics Inc | `DPA` | Same content as the base seed's inline DPA text -- re-uploading it is harmless (idempotent-ish demo) |

## How to use these

1. Open the dashboard, seed the base demo data if you haven't
   (`BULWARK_SEED_DEMO_DATA=true` on boot, or `./scripts/seed_live_demo_data.sh`
   against a deployed instance).
2. **Vendors → Submit artifact**, pick the vendor from the dropdown
   (or "+ New vendor…" if trying against a fresh instance with no seed
   data), pick the matching doc type, switch to the **Upload document**
   tab, and pick the file from the table above.
3. Needs Gemini credentials configured (same requirement as the paste-text
   path) -- Contract Intelligence/Intake still run the real extraction
   and cross-referencing agents on whatever text comes out of the file.

Regenerate these from scratch (they're static committed files, not
built at deploy time) with the one-off script that produced them --
ask for it if you need to add a vendor or change the content; it isn't
part of the shipped app so it isn't committed here.
