# Source Registry

The single production source registry is `config/source_registry.json`.

Required source IDs:

| Source ID | Display name | Workbook | Grain |
|---|---|---|---|
| `machine_downtime` | Machine Downtime | `Machine_Downtime_20260203_100753.xlsx` | downtime event |
| `loss_assignment` | Loss Assignment | `Loss_Assignment_20260203_100840.xlsx` | loss event |
| `apqoee_cumulative` | APQOEE Cumulative | `Cup3.xlsx` | cumulative snapshot |

Runtime registry loading is implemented in `src/sources/registry.py`. It computes checksum, schema fingerprint, readiness, business timezone, supported metrics, and approved relationships.

No production module should choose a business source from arbitrary uploaded filename keywords. Upload is disabled by default with `CUSTOMER_UPLOAD_ENABLED=false`.
