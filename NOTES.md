# FAERS Data Exploration Notes

**Dataset:** FDA Adverse Event Reporting System (FAERS), Quarterly Data Extract  
**Quarter analysed:** 2026 Q1  
**Source:** https://fis.fda.gov/extensions/FPD-QDE-FAERS/FPD-QDE-FAERS.html  
**File explored first:** `DEMO26Q1.txt` (demographics, one row per case version)  
**Rows:** 397,224  
**Columns:** 25  
**Encoding:** latin-1 (not UTF-8)  
**Delimiter:** `$`

---

## Data quality issues found

Each issue: what it is, where I saw it, example, and what I plan to do about it.

### 1. Mixed types in `to_mfr` column
- **Observed:** pandas raised DtypeWarning on read. `to_mfr` is documented as Y/N but contains other values.
- **Example values:** `Y` (208,431 rows), `N` (188,001 rows), blank (783 rows), `<some unexpected value if you found one>` (N rows)
- **Decision:** read all columns as strings on ingest; validate `to_mfr` as enum {Y, N, null} in Pydantic; reject anything else to the rejected_rows table.

### 2. Partial dates in date fields
- **Observed:** `event_dt`, `init_fda_dt`, `fda_dt`, `mfr_dt`, `rept_dt` are stored as integer-shaped strings of length 4, 6, or 8.
- **Example values:** `20240315` (full), `202403` (year-month only), `2024` (year only).
- **Source confirms this is intentional:** README section C — FDA preserves the granularity submitted in each case rather than fabricating missing day/month.
- **Decision:** model as a custom `PartialDate` type in Pydantic; store as string in DB plus a separate `event_dt_precision` column (`day` / `month` / `year`) so downstream queries can filter on precision.

### 3. Age values with unit-dependent magnitudes
- **Observed:** `age` ranges from 0 to <max you saw>. `age_cod` indicates unit.
- **Example:** row X has `age=10950, age_cod=DY` which is 30 years in days; row Y has `age=85, age_cod=YR`.
- **Decision:** normalise to years on ingest; store both raw `(age, age_cod)` and a derived `age_years` float. Flag `age_years > 120` as suspicious but not rejected (FDA may genuinely have implausible values).