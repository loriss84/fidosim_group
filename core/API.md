# core API (for the UI builder)

All functions are pure pandas/numpy, no Streamlit, no network (except the balance-sheet lookups). Amounts in
the local currency of the active country (RON for Romania).

## Countries — `core.country`, `core.bs_providers` (v4.0)
- `country.PROFILES[code]` (RO, SK, AT, CZ, DE, HU): currency, VAT prefix, local defaults, balance source.
  `set_active(code)` / `active()`; `Params.for_country(code, **kw)`; `simulate` sets the active country from
  `params.country`; loaders use it for the VAT prefix and the local currency (`loaders.local_currency()`).
  `country.detect(checkfidi)` -> code or None. Texts: "RON" is replaced by the active currency
  (`country.localise`), `texts.COUNTRY_TEXTS[code][key]` overrides a text for one country.
- `bs_providers.for_country(code)` -> provider with `key_from(*vats)`, `cached(key, dir)`, `lookup(key, dir,
  refresh)`, `search_url(key)`; `ManualProvider.save/delete`. Results have the ANAF shape (`values` with
  `balance.FIELDS` keys) and status ok / not_found / no_data / error. `balance.assess(..., period_end_month=12)`.
Codes are returned by the core; sentences live in `core/texts.py`.

## Loading — `core.loaders`
- `load_folder(path, strict=False) -> LoadedData`: loads every .xls/.xlsx in the folder.
- `load_files(sources, strict=False) -> LoadedData`: `sources` = paths, `(name, bytes)` pairs or
  uploaded file objects (`.name` + `.getvalue()`). Each file is recognised by its columns (any sheet).
  Unrecognised/invalid files become `FILE_INVALID` findings; with `strict=True` a `LoaderError`
  (clear message listing the missing columns) is raised instead.
- `LoadedData` fields: `checkfidi`, `cerved`, `ar` (tidy DataFrames or None), `customers`
  (Check fidi + Cerved match), `findings: list[Finding]`, `sources` (kind -> file name),
  `rows_read` (kind -> raw rows), `missing` (kinds not loaded), `ok` (simulation possible),
  `default_reference_date` (latest AR124 invoice date), `cache` (payment days; do not touch).
  Cache it in the UI with `st.cache_resource` (it holds its own cache) or `st.cache_data`.
- `Finding(code, severity, count, examples, details)`: `severity` in error/warning/info;
  text: `texts.DQ_TEXTS[code]` with `count` and `details` as values. `MISSING_*` findings carry
  `details["unavailable"]` = keys of `texts.UNAVAILABLE_TEXTS`. `CV_DUP_CODE.details` has
  `codes_with_different_vat`.
- Finding codes added 20/11/2026: `MATCH_VAT_CONFLICT` (code match rejected for a different VAT;
  details `codes`, `rematched_by_vat`, `not_in_cerved`), `CV_OTHER_CURRENCY` (details `currencies`),
  `CV_NEGATIVE_LIMIT`, `CF_MULTI_COMPANY` (details `kept`, `kept_name`, `companies`, `codes_examples`),
  `COLUMN_MISSING` (optional column missing; details `kind`, `columns`, `unavailable`), `BAD_NUMBERS` /
  `BAD_DATES` (details `kind`, `columns` = {header: n}), `FILE_EMPTY` (details `kind`). `CV_NO_CURRENCY`
  has `details["assumed"] = "RON"`. `MATCH_VAT_DIFFERS` only appears with the legacy matching (see `findings_for`).
- `LoadedData.matched_customers(reject_vat_conflict=True)`: customer base for a matching rule (legacy cached).
- `LoadedData.findings_for(reject_vat_conflict=True)`: findings consistent with the matching rule used (the UI
  passes `params.cerved_reject_vat_conflict`): MATCH_VAT_CONFLICT with the default rule, MATCH_VAT_DIFFERS and
  the matching CV_UNMATCHED with the legacy rule. `findings` itself is the default rule.
- Files are read with `dtype=object` (pandas must not turn the text "12.500" into 12.5); the cleaners parse every
  value. `AMBIGUOUS_NUMBERS` (warning; details `kind`, `columns`): amount columns whose only separators look like
  "12.500" / "120,000" are read as thousands. Numeric dates: Excel serials 1..106.749, or JDE Julian CYYDDD
  (126001 = 01/01/2026) when every number of the column is one and one is >= 100.000; others -> NaT + BAD_DATES,
  never FILE_INVALID.
- Helpers: `code_to_str` (codes normalised the same way in the three files: spaces stripped, numeric codes by
  integer value), `parse_numbers(series, amounts=False)` / `parse_dates(series)` -> (values, mask of unreadable values);
  `parse_numbers_ex(series, amounts)` adds the mask of ambiguous values.
- Optional columns: Check fidi `VAT`; Cerved `PARTITA_IVA`, `RAGIONE_SOCIALE`, `VALUTA`, `CLASSE_AFFIDABILITA`,
  `FATTURATO_NO_BIL`, `ABITUDINI_PAGAMENTO` (missing -> blank + `COLUMN_MISSING`). An AR124 (or Cerved) with
  headers and no rows is valid.
- Kinds: `checkfidi`, `cerved`, `ar124` (`loaders.KINDS`, the three required ones: `missing` is about these) and the
  optional `md105` (`OPTIONAL_KINDS`; v3.2): JDE customer master, `LoadedData.md105` with columns customer, name,
  status, tax_id, payment_terms (read, not used yet), opened_date. Signature `Cliente` + `Date - Account Opened`
  (+ `Descrizione Cliente`); `read_file` tries header rows 1, 2, 3 (MD105 has a title on row 1). `clean_md105`:
  findings MD_NO_CODE, MD_DUP_CODE (earliest opening date kept), BAD_DATES. Without Cerved everyone is "not in Cerved"; without AR124
  payment days = `fallback_days` and the reference date defaults to today.

## Parameters — `core.params`
- `Params` dataclass, defaults = v3. `validate() -> list[str]`, `check()` (raises), `to_dict()`,
  `to_json()`, `Params.from_dict(d)` / `from_json(s)` (unknown keys ignored), `replace(**kw)`, `diff(other)`.
- `PARAM_META[key]`: `group` (need/risk/caps/controls/populations), `kind` (int/float/bool/choice/date/list),
  `min`, `max`, `step`, `unit` (months/days/pct=fraction/x/coef/RON/EUR/RON/EUR), `primary` (13 suggested
  for the Laboratory), `sensitivity` (offered in sensitivity), `choices` for `rounding_mode`.
- Keys: reference_date, window_months, fallback_days, min_days, cap_extra_days, cap_days_enabled,
  terms_positive_only, m1_days_basis ("contractual" default v3.1 | "measured"), buffer, multiplier, coef_reliable, coef_caution, coef_max_caution, coef_not_in_cerved,
  coef_exempt_not_in_cerved, cerved_reject_vat_conflict, behaviour_enabled (default True),
  behaviour_bonus_max (0.05), behaviour_malus_max (0.10), behaviour_tolerance_days (5), behaviour_full_malus_days (30),
  cerved_cap_enabled, ceiling_is_hard, eur_rate, rounding_step, rounding_mode, min_limit,
  plausibility_threshold, approval_threshold, approval_min_change (default 5000), tier1_eur, tier2_eur,
  intercompany_codes, special_classes,
  exempt_classes. Labels go in `texts.PARAM_TEXTS[key][lang]` (empty, yours).
- `ceiling_is_hard=True` (default, lead decision 20/11/2026): the ceiling is used in whole RON everywhere:
  `ceiling_unit` = floor(round(ceiling, 6)) (4.582,72 -> 4.582; 4.999,9999999 -> 5.000). It caps the limit at
  step 4 (`limit_after_ceiling`, `ceiling_binds` = ceiling_unit < limit_after_coef) and again after rounding and
  minimum (final = min(final, ceiling_unit), not floored to the step). Every proposed limit is whole RON.
  `ceiling_is_hard=False`: step 4 uses the raw ceiling and no final cap.
- Integer parameters (`kind == "int"`: min_limit, rounding_step, approval_min_change, days...) must be whole:
  whole floats become int on construction, `validate()` rejects 5000.5, `from_dict` rounds.
- Approval: `approval_needed` = direction != EQUAL and |diff_pct| > approval_threshold and |diff| >
  approval_min_change.
  `cerved_reject_vat_conflict=True` / `terms_positive_only=True`: the other two decisions of 20/11/2026.
  All three `False` reproduce the original SPEC reference exactly.
- Lists are normalised on construction: classes stripped + upper case; intercompany codes like `code_to_str`.

- **v3.2 defaults** (21/11/2026): group `age` in `PARAM_GROUPS` with `age_bands_enabled` (True),
  `new_customer_months` (3), `consolidated_months` (12), `behaviour_min_invoices` (3), all primary (19 primary in
  all) and in sensitivity; validation `new_customer_months <= consolidated_months`. `params.V31 =
  {"age_bands_enabled": False, "behaviour_min_invoices": 0}` = the v3.1 formula exactly; `OLD_V3` includes it.
  Old scenario JSON without these keys loads with the v3.2 defaults.
- **v3.1** (21/11/2026): `m1_days_basis="contractual"` and `behaviour_enabled=True`.
  `params.OLD_V3 = {"m1_days_basis": "measured", "behaviour_enabled": False}`: `Params(**OLD_V3)` is the
  previous v3 formula (its reference numbers are pinned in tests/test_regression.py). Group `behaviour` in
  `PARAM_GROUPS`; `behaviour_enabled` and `m1_days_basis` are primary (15), the four values are shown in the Lab
  when the option is on. Validation: bonus / malus 0–0.5, days >= 0, `behaviour_full_malus_days` >
  `behaviour_tolerance_days`, `m1_days_basis` in `choices`. Old scenario JSON without these keys loads with
  the (v3.1) defaults.

## Simulation — `core.engine`
- `simulate(data, params=None, include_all=False) -> DataFrame`: one row per active customer,
  intercompany excluded (`include_all=True`: all Check fidi rows). ~0.04 s on real data
  (first call ~0.1 s: payment days computed and cached by (reference date, window)).
- `behaviour_pct(delay, params) -> (pct, band)` (vectorised bands; option off -> 0 / NONE). The v3.2 gates are
  applied in `simulate`: band `NEW_CUSTOMER` (age band NEW or NO_HISTORY with the bands on) and `FEW_INVOICES`
  (`behaviour_invoices_n < behaviour_min_invoices`), both 0%, only where a bonus / malus would be computed.
- Customer age (v3.2): `months_between(start, end)` (calendar months + fraction), `age_band(age, params, censored=None)`
  (NEW / YOUNG / CONSOLIDATED / NO_HISTORY = `AGE_BANDS`), `months_active(age, band, params)` (1..12; 12 when not
  annualised), `customer_history(ar, ref, window, md105=None)` (opened_date, first_invoice_date, age_start_date,
  age_source md105 / ar124_earlier (> 31 days before the opening) / ar124, age_months, behaviour_invoices_n;
  cached by `cached_history`), `ar_coverage_months(ar)`, `coverage_finding(data, params)` (AR_SHORT_HISTORY: bands
  on, no MD105, coverage < consolidated_months + 6; details months, needed), `age_findings(result, data, params)`
  (AGE_INVOICE_BEFORE_OPENING, MD_CUSTOMER_MISSING; details codes, scope_n). These findings depend on parameters /
  results and are not in `LoadedData.findings`: `ui.logic.quality_checks` adds them.
- `payment_days(ar, ref_date, window_months, terms_positive_only=True)` (no look-ahead: closing dates after the
  reference date are ignored, invoices dated after it too), `customer_invoices(ar, code, ref, window)`, `reference_date(data, params)`, `weighted_median(v, w)`.

Columns:
| group | columns |
|---|---|
| identity | code, name, risk_class, vat, block_description |
| Cerved | in_cerved, match_method (code/vat/NaN), vat_differs, vat_conflict, cerved_name, score, score_bucket (AFFIDABILE/CAUTELA/MASSIMA CAUTELA/NONE), reliability_class, cerved_limit_orig, cerved_currency, cerved_limit_usable (False: other currency / negative), cerved_limit_ron (NaN for other currencies), cerved_turnover |
| amounts | balance, overdue, ordered, delivered, exposure (=balance+ordered+delivered), current_limit, turnover_12m |
| populations | is_active, is_intercompany, is_special, is_exempt, in_scope (order-check perimeter) |
| age (v3.2) | opened_date (MD105), first_invoice_date (AR124, whole file, amount > 0), age_start_date, age_source (md105/ar124_earlier/ar124/NaN), age_months, age_band (NEW/YOUNG/CONSOLIDATED/NO_HISTORY; computed also with the bands off), months_active (1..12; 12 when off), monthly_revenue_used (= max(T12, 0) / months_active), behaviour_invoices_n, revenue_check_flag (NEW with the bands on), age_censored (age from a first AR124 invoice within 31 days of the file start -> CONSOLIDATED, age is a minimum), ar_start_date |
| days | days_measured, days_terms, n_invoices, days_source (measured/terms/fallback; contractual basis: contractual/fallback), days_raw, days_min_applied, days_max (terms+extra), days_capped, days_used |
| behaviour | delay_days (measured − terms, raw; NaN without measured days), behaviour_pct (fraction, signed), behaviour_band (BONUS/TOLERANCE/MALUS/NEW_CUSTOMER/FEW_INVOICES/NONE; NONE for all when off), limit_after_behaviour (= limit_after_coef × (1 + pct)), proposed_limit_no_behaviour (same chain without the bonus/malus), behaviour_effect (proposed − without) |
| formula | m1 (= monthly_revenue_used × days / 30 × (1 + buffer)), base_limit, coefficient, limit_after_coef, ceiling (NaN = none), ceiling_binds, limit_after_ceiling, zero_special, zero_no_turnover, limit_before_rounding, limit_rounded, limit_after_minimum, ceiling_unit, hard_cap_applied, min_applied, proposed_limit |
| controls | over_new, over_current (only in_scope), excess_new, excess_current, diff, diff_pct (inf if current 0), direction (HIGHER/LOWER/EQUAL, tolerance 0.5 RON), plausibility_ratio, plausibility_flag, approval_needed (% and materiality), proposed_limit_eur, tier (1/2/3 on proposed limit in EUR) |
| explanation | reason_base_code (reason without the behaviour overlay), reason_code, change_code (reason `R_FULL_NEED_NEUTRAL`: full need without a reliable score) |

## Explanations — `core.explain`
- `REASON_CODES` (priority order), `CHANGE_CODES`; sentences in `texts.REASON_TEXTS` (short, tables/Excel),
  `texts.REASON_LONG_TEXTS` (Customer page; plus `R_COEF_NOT_IN_CERVED_EXEMPT` chosen by the UI for exempt
  classes) and `texts.CHANGE_TEXTS`. Reasons use the whole-RON ceiling (`R_CERVED_ZERO` when ceiling_unit is 0 and
  the limit is 0). Change codes are always true for the row: C_HIGHER_CERVED_CAP / C_LOWER_CERVED_CAP (formula
  above the Cerved limit), C_*_MINIMUM_CAPPED / C_*_ROUNDED_CAPPED (the minimum / rounding would go above it),
  C_HIGHER_MINIMUM / C_LOWER_MINIMUM, C_HIGHER_ROUNDED (formula below today, rounding up above it),
  C_HIGHER_NO_CURRENT, C_HIGHER_NEED, C_LOWER_* by reason.
  Customer age (v3.2): overlay `age_reasons(r, reason, params)` after the behaviour one -> R_NEW_CUSTOMER /
  R_YOUNG_CUSTOMER where the reason is still a formula reason and months_active < 12 (one decimal); change codes
  C_HIGHER_AGE / C_LOWER_AGE; placeholders `age`, `months`, `monthly`, `monthly12`, `turnover`, `inv_due`,
  `min_invoices`, `age_source_code` (-> `age_src` in the sentence language); steps S_AGE_NEW / YOUNG / CONSOLIDATED /
  NO_HISTORY after S_TURNOVER (bands on), S_BEHAVIOUR_NEW / S_BEHAVIOUR_FEW; S_M1 shows `/ {months}`.
  Payment behaviour: overlay `behaviour_reasons` -> R_BEHAVIOUR_BONUS / R_BEHAVIOUR_MALUS where the base reason is a
  formula reason (`FORMULA_REASONS`) and `|behaviour_effect| >= 0.5`; C_HIGHER_BONUS / C_LOWER_MALUS when decisive
  (without the bonus not higher than today / without the malus not lower). `{after_coef}` = limit after the
  bonus/malus; `{risk_limit}` = after the risk factor; also `delay`, `behaviour_pct`, `behaviour_pct_abs`,
  `no_behaviour`, `days_terms`. Steps: S_BEHAVIOUR_BONUS/TOLERANCE/MALUS/NONE after S_COEF when the option is on;
  S_DAYS_CONTRACTUAL for the contractual basis. Format specs `{x:dd}` (days, 1 decimal), `{x:sdd}` (signed), `{x:spct}`.
- `text_values(row, params) -> dict` placeholders for those sentences: current, proposed, need (= M1), base,
  after_coef (the formula, step 6), formula (the formula as rounded when below the minimum), before_round,
  cerved_limit (whole RON), bucket (-> `score_lbl` in the sentence language), coefficient, min_limit, mult...
- `explain_customer(result, code, params) -> dict`: reason_code, change_code, values, steps, controls, cerved.
- `steps(row, params) -> list[{step, values, amount, unit}]`; `steps_text(steps, lang)` -> rows
  `{step, label, calc, amount, unit}` ready for the "passo / calcolo / RON" table.
- `add_texts(result, params, lang)` -> copy with `reason` and `why_change` columns.

## KPIs — `core.kpi`
- `kpis(result) -> dict` with stable keys `KPI_KEYS` (labels `texts.KPI_TEXTS`). Perimeter unless suffix
  `_active`. Over-limit split: `over_new_positive_n` / `over_new_zero_n` (proposed limit > 0 / = 0 by rule),
  `over_current_positive_n` / `over_current_zero_n` (today's limit > 0 / <= 0).
  Payment behaviour (scope): `behaviour_bonus_n`, `behaviour_tolerance_n`, `behaviour_malus_n`,
  `behaviour_no_history_n` (no delay), and net effect `behaviour_effect_active` / `behaviour_effect_scope` (RON). Score split: `n_/over_new_n_/over_current_n_` + reliable/caution/max_caution/not_in_cerved.
- `score_breakdown(result) -> DataFrame` per score bucket.
- v3.2 KPI keys: `behaviour_new_n`, `behaviour_few_n`, `age_new_n`, `age_young_n`, `age_consolidated_n`,
  `age_no_history_n` (scope). `age_breakdown(result, scope=True) -> DataFrame[age_band, n, exposure,
  limits_current, limits_proposed, over_new_n, over_new_positive_n, over_current_n]` in `AGE_BANDS` order.
- `compare(kpis_base, kpis_scenario) -> DataFrame[key, base, scenario, delta, delta_pct]`.
- `changed_customers(result_base, result_scenario) -> DataFrame` (change = LIMIT / OVER_STATUS / BOTH);
  name, score_bucket, exposure, current_limit from whichever result has the customer.
- `data_summary(data, params) -> dict` for the Data page (rows read, active, intercompany excluded,
  match_code_n / match_vat_n / match_none_n, reference date, missing).

## Sensitivity — `core.sensitivity`
- `sensitivity(data, params, key, values, kpi_keys=None) -> DataFrame[value, <kpis>]`
  (default KPIs `DEFAULT_KPIS`; `[]` = all). ~0.05 s per point.
- `value_range(key, start, stop, n=10)` values snapped to the parameter step.

## Export — `core.export`
- `to_excel(result, params, lang="it", path=None) -> bytes`: sheets Clienti/Customers (friendly names
  from `texts.COLUMN_TEXTS`), KPI, Parametri/Parameters. Amounts `#,##0`; `diff_pct` and `plausibility_ratio` as
  percentages (`0.0%`); Cerved suggested limit and ceiling in whole RON (as the proposed limit uses them); Cerved
  match translated (`texts.MATCH_TEXTS`); with the bonus/malus on, `BEHAVIOUR_COLUMNS` after the risk factor
  (band translated with `texts.BAND_TEXTS`, % as `0.0%`), and with the age bands or the minimum-invoices gate on `AGE_COLUMNS` before M1 (dates dd/mm/yyyy, band and
  source translated with `texts.AGE_BAND_TEXTS` / `AGE_SOURCE_TEXTS`), see `export_columns(params)`; KPI sheet: shares (`SHARE_KPIS`) as `0.0%`, the others `#,##0`.

## Texts — `core.texts`
- `t(TABLE, code, lang, **values)`, `render(template, lang, **values)`, `fmt_amount(x, lang)`.
  Placeholders `{x:amt}` `{x:pct}` `{x:days}` `{x:num}`. Tables: SCORE_TEXTS, DIRECTION_TEXTS,
  `{x:x}` compact multiplier (2 -> "2", 2.5 -> "2,5"); `t()` adds `score_lbl` from `bucket`.
  REASON_TEXTS, REASON_LONG_TEXTS, CHANGE_TEXTS, STEP_TEXTS (`{"label", "calc"}`), DQ_TEXTS, UNAVAILABLE_TEXTS, KPI_TEXTS, MATCH_TEXTS,
  COLUMN_TEXTS (`(it, en)` tuples), EXPORT_TEXTS, PARAM_TEXTS (empty, for the UI agent).
