# FAERS Data Exploration Notes

**Dataset:** FDA Adverse Event Reporting System (FAERS), Quarterly Data Extract  
**Quarter analysed:** 2026 Q1  
**Source:** https://fis.fda.gov/extensions/FPD-QDE-FAERS/FPD-QDE-FAERS.html  
**File explored:** `DEMO26Q1.txt` — demographics, one row per case version  
**Shape:** 397,224 rows × 25 columns  
**Encoding:** latin-1 (not UTF-8)  
**Delimiter:** `$`  
**Read strategy:** all columns as strings (`dtype=str`); type coercion is the validator's job, not pandas'.

---

## Confirmed from spec

- Delimiter `$`, encoding latin-1
- `primaryid` is unique per row (every value count = 1)
- `caseid` is unique per row *within this quarter*, but the spec states a `caseid` can have multiple `caseversion` values across quarters. Distribution of `caseversion` confirms follow-ups arriving alongside initial reports: 67% v1, 20% v2, 6% v3, dropping to a long tail past v10.
- Partial dates exist (see issue #3)
- Age unit varies by `age_cod` (see issue #5)
- `sex` is a coded value (M/F/null). Note: the spec mentions "UNK" and "NS" codes — these do not appear in 2026 Q1; FAERS modernisation appears to have collapsed them into null.

---

## Data quality issues

### 1. `to_mfr` is 97% null
- **Counts:** NaN 384,965 (96.9%) · N 10,891 (2.7%) · Y 1,368 (0.3%)
- **Spec says:** Y/N flag for whether the case was forwarded to the manufacturer.
- **Ambiguity:** NaN could mean "no, not forwarded" or "unknown / not captured." The data alone can't distinguish.
- **Pandas dtype warning explained:** chunked type inference — early chunks were all NaN (inferred float), later chunks contained "Y"/"N" strings, forcing a widen. A chunking artifact, not a real data issue.
- **Decision:** validate as `Optional[Literal["Y","N"]]`; preserve null as null. Do not coerce missing → "N".

### 2. `i_f_code` cleanly splits initial vs follow-up
- **Counts:** I 267,307 (67.3%) · F 129,917 (32.7%) · no nulls, no surprises
- **Decision:** validate as `Literal["I","F"]`, required.

### 3. Partial dates are real and pervasive
- **Observed:** date fields stored as integer-shaped strings of length 4, 6, or 8.
- **Example values:** `20260112` (day), `202602` (month), `2026` (year). Top values in `event_dt` include many `YYYY0101` and `YYYYMM01` patterns.
- **Spec confirms** (README section C): FDA preserves submitted granularity; partial dates are intentional.
- **Decision:** model dates as a `PartialDate` type — original string plus a `precision` enum (`day`/`month`/`year`). Do not coerce to `datetime.date` on ingest; downstream analytics can decide how to handle precision.

### 4. `event_dt` is 58% null
- **Counts:** 229,258 of 397,224 rows (57.7%) have no event date.
- **Spec says:** "Case Event Date, when available" — null is allowed.
- **Decision:** nullable; not a rejection condition. Worth surfacing in any per-quarter completeness report.

### 5. Age requires unit normalisation
- **`age_cod` counts:** YR 240,261 · NaN 151,605 · DEC 3,850 · MON 1,102 · DY 265 · WK 126 · HR 15
- **Spec confirms:** "a 30-year (YR) old will be displayed as a 10,950-day (DY) old" — manufacturers may submit any unit.
- **Inconsistency found:** `age` has 151,608 nulls, `age_cod` has 151,605 nulls — **3 rows have `age_cod` populated but `age` missing.** A unit without a value.
- **Decision:** normalise to `age_years` (float) using `{YR:1, MON:1/12, WK:1/52, DY:1/365.25, HR:1/8766, DEC:10}`. Store raw `(age, age_cod)` alongside derived `age_years` for traceability. Validation rule: if either is non-null, both must be non-null.

### 6. Weight is 83% null and unit-coded
- **`wt_cod` counts:** NaN 328,133 · KG 69,039 · LBS 52
- **Pattern:** weights in pounds are vanishingly rare (~0.08% of populated weights).
- **Decision:** normalise to `weight_kg` using `{KG:1, LBS:0.453592}`. Same both-or-neither rule as age.

### 7. `sex` is 19% null and has no UNK/NS values
- **Counts:** F 198,072 (49.9%) · M 123,719 (31.2%) · NaN 75,433 (19%) — no UNK, no NS
- **Spec discrepancy:** spec lists UNK and NS as valid values. The 2026 Q1 data uses null instead.
- **Decision:** `Optional[Literal["F","M"]]`. Reject any other non-null value to `rejected_rows` with reason `unexpected_sex_code`.

### 8. `reporter_country` contains a non-ISO sentinel
- **Observed:** "COUNTRY NOT SPECIFIED" appears 4,012 times alongside 2-letter ISO codes (US, EU, CA, GB, JP…).
- **Side note:** "EU" isn't a country either — it's used as an aggregate code (40,633 rows).
- **Decision:** validate against the set of ISO 3166 2-letter codes ∪ `{EU}`. Coerce on ingest, log the count for the run report.

### 9. `occr_country` has true nulls but `reporter_country` does not
- **Observation:** `reporter_country` has 0 nulls; `occr_country` has 32,166 nulls (8.1%).
- **Implication:** the submitter's country is always known (likely a required submission field), but the country where the event *occurred* often isn't.
- **Decision:** `reporter_country` required, `occr_country` nullable. Useful asymmetry to document — it reveals something about the data-generating process.

### 10. Heavy heaping on first-of-month/year in event dates
- **Top values in `event_dt`:** `20250101` (15,599), `20260101` (10,176), `20251201` (5,933), `20240101` (4,851), `20260201` (4,205) …
- **Suspicious pattern:** dates ending in `0101` and `MM01` are over-represented for what should be a roughly uniform distribution of real-world events.
- **Spec contradiction:** the README states FDA *no longer* imputes — partial dates should be preserved as partial. So why are full 8-digit dates clustering on `01` days? Possibilities: (a) submitters self-impute before transmitting; (b) legacy migration imputed missing components; (c) FDA documentation lags actual processing.
- **Decision:** flag rows where `event_dt` matches `YYYY0101` or `YYYYMM01` with a boolean `event_dt_suspect_imputed`. Do not reject — annotate. Downstream analyses involving event timing should be aware.

---

## Sparse columns

Mostly null by design rather than by error. Listed for schema clarity:

| Column | Null % | Treatment |
|---|---|---|
| `to_mfr` | 96.9% | nullable enum |
| `lit_ref` | 93.8% | nullable, free text (see issue #11) |
| `auth_num` | 90.3% | nullable, free text |
| `wt`, `wt_cod` | 82.6% | nullable, both-or-neither |
| `age_grp` | 66.8% | nullable enum |
| `occp_cod` | 35.1% | nullable enum |
| `mfr_num` | 3.4% | nullable, free text |

### 11. `lit_ref` is uncontrolled free text with massive within-citation duplication
- **Observed:** 24,819 non-null rows. The top 10 most common values are all variants of *the same citation* (the 2024 NPDS annual report). One paper, ten different spellings differing in punctuation, "America^s" vs "America?s", "42nd Annual report" vs "42nd annual report", with and without DOI.
- **Significance:** textbook example of why uncontrolled free-text reference fields fail. Persistent identifiers (DOIs) and controlled vocabularies would collapse these to a single record. This is the kind of data-quality problem FAIR principles directly address.
- **Treatment:** ingest as raw string; do not attempt deduplication at ingest. Document as a candidate for downstream enrichment via CrossRef DOI matching.

---

## Things expected from the spec but not observed

- No `UNK` / `NS` codes in `sex` — only null
- No `GNDR_COD` column — confirmed renamed to `sex`
- No `age_cod` values outside the documented enum
- No `i_f_code` or `rept_cod` values outside the documented enums
- No malformed rows reported by `on_bad_lines="warn"` — all 397,224 rows parsed structurally clean

## Open questions

- Schema drift across quarterly files — load an older quarter (e.g. 2014 Q3) and diff columns
- The 3 rows with `age_cod` populated but `age` missing — pull them, examine
- Is `EU` used consistently in `reporter_country` (EMA submissions)?
- The four date fields `mfr_dt`, `init_fda_dt`, `fda_dt`, `rept_dt` — spec is hazy on their distinctions; which (if any) should the validator treat as required?

---

## Read settings used

```python
demo = pd.read_csv(
    DATA / "DEMO26Q1.txt",
    sep="$",
    encoding="latin-1",
    dtype=str,
    keep_default_na=False,
    na_values=[""],
    on_bad_lines="warn",
)
```

### 12. Numeric outliers in `age` and `wt` reveal upstream coding errors, not random noise

Both columns parse without error (no unparseable strings) but contain biologically implausible values. The pattern of the outliers is more interesting than the count.

**Age — 4 implausible rows out of 245,616 populated (0.0016%).**

| primaryid | age | age_cod | age_grp | normalised years |
|---|---|---|---|---|
| 262740041 | 23 | DEC | A (Adult) | 230 |
| 244150… | 126 | YR | — | 126 |
| 265065331 | 40 | DEC | (null) | 400 |
| 265083411 | 70 | DEC | (null) | 700 |

Three of four implausibles use `age_cod = DEC` with values that would be perfectly normal as `YR`. Row `262740041` is internally contradictory: `age=23, age_cod=DEC` normalises to 230 years, yet `age_grp=A` (Adult, ~18–64). Within a single row, the submitter has told us they intended a 23-year-old adult and coded the unit as decades. This confirms the `DEC↔YR` miscoding hypothesis for at least this row; the two other DEC outliers have null `age_grp` so the hypothesis is consistent but not directly confirmed.

The fourth row (`126 YR`) is more likely a digit-transposition error (intended 26 or 76).

This is also a worked example of why **cross-field validation matters**: each field individually passes a single-column check (`age` is a valid integer, `age_cod` is a valid enum, `age_grp` is a valid enum), but the combination is impossible. Single-column validators cannot detect this class of error.

**Weight — 5 rows over 500 kg, plus a tail of suspiciously small values.**

| primaryid | wt | wt_cod | plausible intended value |
|---|---|---|---|
| 248762252 | 551.15 | KG | possibly real |
| 263128201 | 4,105 | KG | probably 41.05 (lost decimal) |
| 263822571 | 80,505 | KG | probably 80.505 kg, or 80,505 g coded as KG |
| 263827301 | 26,775 | KG | probably 26.775 or 267.75 |
| 265001761 | 849 | KG | borderline; could be real |

Two distinct patterns visible: dropped decimal separators, and possible gram-vs-kilogram confusion. Without round-tripping to the source we can't recover the intended values reliably.

Sub-1kg weights: 64 rows. Likely "unknown coded as 0", but some could legitimately be neonatal — worth cross-checking against `age_grp = N` before assuming.

**Lesson:** parseability is not validity. A column can be 100% numeric and still contain semantic garbage. More importantly, outliers often cluster around a specific upstream error mode (here: unit miscoding, lost decimals) rather than being random noise. Examining outliers *qualitatively* yields more information than counting them.


**Decision:** graded severity for age validation.

- `age_years` single-field check:
  - Reject if >150 (reason: `age_implausible`)
- `(age_years, age_grp)` cross-field check, with two thresholds:
  - **Strict band** (per spec definition): N <1mo, I 1mo–2yr, C 2–12, T 13–17, A 18–64, E ≥65
  - **Implausible band** (wider tolerance for typo/interpretation): N <1yr, I <5yr, C <18yr, T 5–25, A 10–80, E ≥40
  - Outside implausible band → reject (`age_group_inconsistent`). Catches DEC↔YR miscoding.
  - Outside strict but inside implausible → annotate `age_group_boundary_mismatch = True`. Preserves the row for downstream consumers who care.
- Rationale: a 12-year-old declared "Adolescent" is a definition disagreement, not a data error. A 230-year-old declared "Adult" is a data error. The two-tier design treats them differently.

`weight_kg`:
- Reject if >1000 or <0 (reason: `weight_implausible`)

Soft warnings preserve the record with an annotation; hard rejections only catch the unsalvageable.

**Process lesson:** the first pass of the validator over the real data found 654 rejections, 100% from this rule, which surfaced the boundary-vs-miscoding distinction. The model is calibrated against the data, not against the spec alone.

**End-to-end validation against 2026 Q1 (397,224 rows):**

- 45 rows rejected (0.011%)
- Rejection categories:
  - `weight_kg == 0` sentinel — most of the 45
  - `age_grp` Adult overflow (age 81–99 with age_grp=A): 5 rows
  - `age_grp` Elderly underflow (age <65 with age_grp=E): 2 rows
  - `age` populated without `age_cod` (or vice versa): the inconsistency originally flagged at exploration
- Soft annotations on valid rows:
  - `age_group_boundary_mismatch`: <FILL IN from your annotation counter>
  - `event_dt_suspect_imputed`: <FILL IN>

**Tuning decision:** the 7 Adult/Elderly boundary rejections were considered for relaxation (widening the implausible bands). Rejected: 7 rows in 397k is below the noise floor, and loosening the band would weaken the catastrophic-mismatch catch that motivates the rule (the DEC↔YR miscoding produces values orders of magnitude outside the band, not 5 years outside). The bounds remain spec-aligned with a generous tolerance; rare submitter convention disagreements are correctly routed to the rejection table for review rather than silently passed.

These numbers calibrate the validator against the actual data-generating process, not just the spec. A future quarterly ingest producing 10× this rejection rate would indicate either a schema change or an upstream system issue worth investigating.


---

## Production ingest results — 2026 Q1

First run: 397,224 rows in 2m 54s (~2,280 rows/sec).

| Outcome | Count |
|---|---|
| Clean | 397,179 |
| `weight_implausible` | 30 |
| `age_group_inconsistent` | 7 |
| `age_unit_mismatch` | 5 |
| `age_implausible` | 3 |
| **Total rejected** | **45** (0.0113%) |

Reconciliation note: one `age=126, age_cod=YR` row from exploration passed validation because `age_grp` was null (no cross-field check fires) and 126 < 150 (hard reject threshold). It is now in `demo_clean` and would only be detectable by a softer "implausible-but-not-catastrophic" annotation. Documented as a known limitation; not addressed in this iteration.