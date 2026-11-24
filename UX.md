# Simulatore Fido SIAD v3: UX design and copy deck

> Final review (20/11/2026): sections 3.1, 3.3, 5.1-5.3, 6.5 and 7 describe the final behaviour; the copy-deck
> tables of section 6 are the original design, `core/texts.py` is the authoritative text.

Audience: the developer who builds `app.py` (Streamlit 1.4x+) on top of `core/`.
Read together with `SPEC.md`. Where this file and SPEC disagree on *calculation*, SPEC wins;
on *interface and wording*, this file wins. Proposed SPEC changes are listed in section 9.

---

## 0. What we are fixing compared with the old `fidosim`

The old simulator had seven sections, a seven-tab rules form, an "Apply rules" button, a rule
library, workspace management, backtests, currencies and setup checks. Every one of those was
reasonable on its own; together they made it impossible to answer one question on a projector.
Rules for v3:

1. **One question per page.** The page title *is* the question.
2. **Live.** No "Apply" button anywhere. Every control recalculates at once (core < 1 s).
3. **The active scenario is always visible** (sidebar). Results and Customer pages always show the
   active scenario; when it is not the v3.2 default, every page says so in one line.
4. **Fixed vocabulary.** "Fido attuale / Current limit", "Fido proposto / Proposed limit",
   "Esposizione / Exposure", "Oltre fido / Over limit". Never "AS IS", "TO BE", "GTP", "M2",
   "applicable limit", "FullRisk", "prop", "CL" in the UI.
5. **No colour-only meaning, no red unless it is really bad** (section 7).
6. **Fewer options.** No column pickers, no chart-type pickers, no themes, no per-user settings.

---

## 1. Global shell

### 1.1 Page config and navigation

```python
st.set_page_config(page_title=T("app_title"), layout="wide", initial_sidebar_state="expanded")
pages = [st.Page(page_data, title=T("nav_data"), icon=":material/folder_open:", url_path="data"),
         st.Page(page_results, title=T("nav_results"), icon=":material/insights:", url_path="results", default=True),
         st.Page(page_customer, title=T("nav_customer"), icon=":material/person_search:", url_path="customer"),
         st.Page(page_lab, title=T("nav_lab"), icon=":material/tune:", url_path="lab"),
         st.Page(page_rules, title=T("nav_rules"), icon=":material/menu_book:", url_path="rules")]
st.navigation(pages, position="sidebar").run()
```

Default page: **Results** when the three files load from `data/`; **Data** when Check fidi is missing
(redirect with `st.switch_page` once per session).

### 1.2 Sidebar, top to bottom (nothing else goes in the sidebar)

1. `st.markdown("### " + T("app_title"))` and `st.caption(T("app_subtitle"))`
   ("SIAD Romania · società 42 · RON").
2. Language: `st.segmented_control(T("lang_label"), ["IT", "EN"], default=<session>, key="lang")`.
   Default **EN** (the meeting language); stored in `st.session_state.lang`. Switching never changes a number.
3. Navigation (rendered by `st.navigation`).
4. `st.divider()`
5. **Data status badge** (one line each, Markdown badges):
   - all three files: `:green-badge[:material/check: {T("badge_data_ok")}]` + caption `T("badge_ref_date")`
   - some missing: `:orange-badge[:material/warning: {T("badge_data_partial", n=k)}]`
   - Check fidi missing: `:gray-badge[{T("badge_data_none")}]`
6. **Scenario badge**:
   - defaults: `:blue-badge[{T("badge_scn_default")}]`
   - modified: `:violet-badge[{T("badge_scn_modified", n=changed_params)}]` + the scenario name if saved,
     and a small `st.button(T("btn_reset_defaults"), key="sb_reset")` under it.

### 1.3 Every page starts the same way

```
st.title(T("<page>_title"))        # the question
st.caption(T("<page>_subtitle"))   # one sentence: what the page is for
[scenario banner]                  # only if active scenario != default:
                                   #   st.info(T("banner_scenario", name=..., changes=...), icon=":material/tune:")
[missing-data banner]              # only if a file is missing (texts in 6.3)
```

### 1.4 Number formatting (one helper, used everywhere including tables and Excel)

| Kind | IT | EN | Rule |
|---|---|---|---|
| amount | `1.234.567 RON` | `1,234,567 RON` | integer, thousands separator; RON always shown in tiles, headers and sentences. In table cells the unit is in the column header ("Esposizione (RON)") not in each cell. |
| large amount in KPI tiles | `39,75 mln RON` | `39.75 M RON` | values ≥ 1,000,000 → 2 decimals in millions; full value in the tile's help text |
| count | `1.598` | `1,598` | |
| percent | `10%`, `-12,5%` | `10%`, `-12.5%` | 0 decimals for parameters, 1 decimal for changes |
| coefficient | `0,70` | `0.70` | always 2 decimals |
| days | `70 gg` | `70 days` | |
| date | `20/11/2026` | `20/11/2026` | dd/mm/yyyy in both languages (no US dates in front of a Romanian team) |
| sign | `+12` / `-1.234` | `+12` / `-1,234` | always show the sign on deltas. Use ASCII hyphen-minus: `st.metric` reads the leading `-` to pick the arrow direction. |

Tables: keep the numeric dtype so sorting works, and format the display with a pandas `Styler`
(`.format(thousands=".", decimal=",", precision=0)` for IT, `thousands=","` for EN) passed to
`st.dataframe`. Do **not** use `NumberColumn(format="localized")`: it follows the browser locale,
not the IT/EN switch. `column_config` is still used for labels, widths and help.

---

## 2. Page "Dati / Data"

**Purpose:** show that the three files are loaded and trustworthy, and say plainly what cannot be
calculated if one is missing.

Layout, top to bottom (fits one screen when everything is fine):

1. Title/subtitle.
2. **Three file cards**: `st.columns(3)`, each `st.container(border=True)`:
   - `st.markdown("**" + T("file_checkfidi") + "**")` (resp. `file_cerved`, `file_ar124`)
   - state line: `:green-badge[T("file_loaded")]` / `:orange-badge[T("file_missing")]`
   - `st.caption(filename · T("file_rows", n=...))`, e.g. "checkfidi_20-11-2026.xlsx · 12.527 righe"
   - one line of what the file gives: `T("file_checkfidi_role")` etc.
3. **Upload area** in `st.expander(T("upload_title"), expanded=<any file missing>)`:
   `st.file_uploader(T("upload_label"), type=["xlsx","xls"], accept_multiple_files=True)` +
   `st.caption(T("upload_help"))`. Files are recognised by columns; an unrecognised file gives
   `st.error(T("err_unrecognised", name=...))`. An uploaded file replaces the one from `data/` of the same kind.
4. `st.subheader(T("data_population"))` + one `st.columns(5)` row of `st.metric` (no deltas):
   Check fidi rows (12.527) · Active customers (2.116) · Intercompany excluded (3) ·
   Order-check scope (1.598) · Reference date (20/11/2026). Help texts: `help_*` keys.
5. `st.subheader(T("data_matching"))` + `st.columns(4)` metrics, all on active customers:
   Matched by code · Matched by VAT · Not in Cerved · Cerved rows not matched.
   Under it `st.caption(T("data_cerved_share", n=1177, pct=71))`.
6. `st.subheader(T("data_quality"))`: **one table, not a wall of warning boxes.**
   `st.dataframe` with columns `Controllo/Check | Quanti/Count | Cosa significa/What it means`,
   rows from codes in 6.4 (only rows with count > 0). If none: `st.success(T("dq_all_ok"))`.
   Under it, one `st.expander(T("dq_details"))` with a selectbox of the check and the affected rows
   (code, name, VAT, Cerved name).
7. `st.expander(T("data_settings"))` (collapsed): reference date `st.date_input` and the window in
   months. These are data choices, not formula choices (moved here from the Lab, see 9).

**Empty / loading states**
- First load: `with st.spinner(T("loading_files")):` around the cached loaders.
- No files at all: cards show "Manca/Missing", the upload expander is open, metrics sections are
  replaced by `st.info(T("empty_data"))`.
- Missing file: the card is orange and shows `T("missing_<kind>_impact")` under it (section 6.3).

---

## 3. Page "Risultati / Results"

**Purpose:** answer at a glance "what changes with the new formula?" for the active scenario.

Population rule, shown once under the tiles as caption: over-limit KPIs are on the **order-check
scope** (1.598 customers: active, no intercompany, no special, no exempt classes); totals of limits
and exposure are on **all active customers** (2.116). The help text of each tile repeats its population.

### 3.1 KPI tiles

Three rows of four `st.metric(..., border=True)` (values 1.75rem: the CSS forces the size on every element inside
`stMetricValue`, which renders the value in a markdown container). Delta always "vs current limits".
Reference numbers = v3 defaults on the files in `data/`.

| # | key | Label EN (IT) | Value | Delta | delta_color |
|---|---|---|---|---|---|
| 1 | `kpi_over_pos` | Over a positive limit (Oltre un fido positivo) — **headline** | **130** | `-72 vs current (202)` | `inverse` |
| 2 | `kpi_over_n` | Over limit, total (Oltre fido, totale) | **290** | `+23 vs current (267)` | `off`; caption `kpi_over_split`: "160 at limit 0 by rule + 130 over a positive limit (today 65 + 202)" |
| 3 | `kpi_over_amt` | Exposure over limit | **6.98 M RON** | `-2.88 M RON vs current` | `inverse` |
| 4 | `kpi_orders_over` | Open orders over limit | **38** | `+3 vs current (35)` | `inverse` |
| 5 | `kpi_limits_scope` | Total limits · order-check scope (1,598 customers) | **33.16 M RON** | `+1.06 M RON vs current` | `off` |
| 6 | `kpi_limits` | Total limits · all active (2,116 customers) | **39.71 M RON** | `-0.29 M RON vs current` | `off` |
| 7 | `kpi_exposure` | Exposure · all active | **36.12 M RON** | none | |
| 8 | `kpi_moves` | Higher / lower / same | **796 / 614 / 188** | none | |
| 9 | `kpi_zero` | Zero limit with turnover | **166** | `+76 vs current (90)` | `off` (today's 0 may mean "not checked") |
| 10 | `kpi_approval` | Need approval | **421** (Tier 1/2/3 in the help: 401/19/1) | none | |
| 11 | `kpi_review` | To review | **22**, caption "2.00 M RON of exposure" | none | |

Why: the Romanian limits were inflated on purpose, so the headline must not read "the new formula puts 23 more
customers over limit". 160 of the 290 are at limit 0 by rule (maximum caution, Cerved 0, no turnover); over a
positive limit the count goes from 202 to 130. Both populations of the totals are labelled on the tile so
"-0.29 M" (all active) and "+1.06 M" (scope) cannot be confused. Caption under the tiles: `kpi_scope_caption` +
`kpi_cerved_mix`.

### 3.2 Charts (two side by side, one optional)

`col_a, col_b = st.columns(2)`. Altair, height 320, font sizes in section 7. Colours: **current = grey
#9AA5B1, new = SIAD blue #1F4E79**; increase = blue #2E75B6, decrease = orange #D9822B, unchanged = grey.
No red/green pairs. Every bar carries its number as a text label.

1. **Over limit by Cerved score** (`chart_over_by_score`), left. Horizontal grouped bars.
   y = score in fixed order: Affidabile / Reliable, Cautela / Caution, Massima cautela / Maximum caution,
   Non in Cerved / Not in Cerved. x = customers over limit. Two bars per score: Current, New.
   Why: shows *who* ends over limit. With v3 the bulk moves to maximum caution (97) and caution (80),
   only 38 reliable: the formula blocks the risky customers, not the good ones.
2. **How limits change** (`chart_change_buckets`), right. Vertical bars, x = ordered buckets, y = customers
   (order-check scope). Buckets (code → label in copy deck):
   `TO_ZERO` To zero · `DOWN_50` -50% or more · `DOWN_20_50` -20% to -50% · `WITHIN_20` Within ±20% ·
   `UP_20_50` +20% to +50% · `UP_50` +50% or more · `FROM_ZERO` New limit (current was 0).
   Why: in one image the team sees how many customers move a lot (these need approval) and in which direction.
   Clicking is not needed; the table below has the same filter.
3. `st.expander(T("chart_more"))` (collapsed): **Limits and exposure by score** (`chart_amounts_by_score`):
   grouped bars per score, in M RON: Current limits, Proposed limits, Exposure. Why: where credit moves.

### 3.3 Customer table

Filters: search, Cerved score (multiselect, placeholder "All"), change (All / Higher / Lower / Same), pills
(over limit new, becomes over, no longer over, to review, need approval). One row: toggle `flt_scope_all`
("All active customers"; help: exempt and special too), toggle `flt_more_cols` ("More columns"), Excel button.

Main columns, sized to fit **1366 px without horizontal scrolling** (`ui/logic.TABLE_MAIN`, pixel widths in
`results.py`): Code · Customer · Current (RON) · Proposed (RON, bold) · Difference (RON, signed, blue/orange) ·
Over limit (`No → Yes`) · Why this limit (short reason, ≤ ~32 characters: e.g. "Cerved suggested limit",
"Caution score (0.70)", "Minimum 5,000 RON"). "More columns" adds Cerved score, Exposure, Overdue, Why it changes,
Notes (`TABLE_MORE`). The full reason and "why it changes" are on the Customer page (row click).
Default sort: exposure descending.

### 3.4 Empty / loading / missing

- No Check fidi: only title, then `st.info(T("empty_results"))` + `st.page_link(data page, label=T("go_data"))`.
- Calculation: `st.spinner(T("calculating"))` (normally invisible, < 1 s).
- Cerved missing: banner `missing_cerved_impact`; chart 1 shows only "Not in Cerved"; replace it by
  `st.caption(T("chart_needs_cerved"))`. Tile 8 shows "-" with help `T("help_review_needs_cerved")`.
- Check fidi without current limits (all 0): tiles show values without deltas.

---

## 4. Page "Cliente / Customer"

**Purpose:** explain one customer's proposed limit step by step, so anybody in the room can redo it on paper.

Layout:

1. Title/subtitle.
2. `st.selectbox(T("cust_pick"), options=codes, format_func=lambda c: f"{c} · {name}", index=<session or largest exposure>)`.
   Searchable by typing code or name. Options: all active customers including exempt, special and
   intercompany (intercompany shows only the INTERCOMPANY sentence and stops).
3. Header line: `st.markdown(f"## {name}")` + caption `code · VAT · risk class AMF · score label`.
4. **Four tiles** `st.columns(4)`, `border=True`:
   Current limit · Proposed limit (delta vs current, `off`) · Exposure today · Over limit
   (value `T("yes")`/`T("no")` for new, delta-free; caption with current status). Exempt and special classes are
   not in the order check: value "Not checked", caption "Exempt: above / within the monitoring limit" or "Special
   class: already blocked in CreditBoard". Cerved box: suggested limit in whole RON (as used by the limit); if the
   Cerved row with this code was rejected for another VAT number, a caption says so (`cv_vat_conflict`). Checks
   box: change "none (0 in both)" when both limits are 0; tier "does not apply (limit 0)" for a zero limit;
   approval shows both thresholds (±20% and 5,000 RON). Step 7 shows the ceiling in whole RON (26,790, not 26,791).
5. **The answer in two sentences**: `st.info(reason_long + "\n\n" + why_change)`, icon `:material/lightbulb:`.
   Use `st.warning` only for MAX_CAUTION / CERVED_ZERO / SPECIAL / NO_TURNOVER (the customer gets 0).
6. `left, right = st.columns([3, 2])`
   - **left**: `st.subheader(T("steps_title"))` + the step table (4.1) rendered with `st.table`
     (static, large, no scrollbars: best on a projector). Under it the exposure sentence (`expo_sentence`).
   - **right**: three bordered containers, each a 2-column mini table (`st.table`, label | value):
     - *Cerved*: score, Cerved suggested limit (RON, and EUR if original was EUR), reliability class,
       Cerved total turnover, matched by (code / VAT / not found).
     - *Payment days*: measured, contractual terms, used, invoices counted, `T("days_capped")` line if capped.
     - *Checks*: plausibility % with verdict, change vs current %, approval needed (yes/no), approval tier.
7. `st.expander(T("cust_invoices"))` (collapsed): the customer's AR124 invoices in the window, with
   columns invoice date, due date, closed date, amount, days counted. For checking, not for the meeting.

### 4.1 Step table (always the same 10 rows for every customer)

Columns: `#` · `Step / Passo` · `Calculation / Calcolo` · `RON`. Rows that do not apply keep their place
and say "does not apply" in the Calculation column with the RON column carrying the previous value,
so the table shape never changes between customers. The final row is bold.

When a rule sets the limit to 0 (special class, no turnover, max caution), the row that triggers it
writes 0 and the following rows say "-".

### 4.2 Worked example (realistic numbers; also a test case for `explain.py`)

Customer 30012345 · ALFA GAZ SRL · score CAUTELA · risk class B2 · turnover 12 months 600,000 RON
(50,000 RON/month) · contractual terms 60 days · measured days 70 (amount-weighted median of 46 invoices)
· Cerved suggested limit 150,000 RON · Cerved total turnover 9,800,000 RON · current limit 300,000 RON
· Balance 118,400 · Ordered 24,000 · Delivered 20,000.

**EN**

| # | Step | Calculation | RON |
|---|---|---|---|
| 1 | Turnover, last 12 months | from Check fidi | 600,000 |
| 2 | Monthly turnover | 600,000 / 12 | 50,000 |
| 3 | Payment days used | measured 70 days; minimum 15, maximum 60 + 15 = 75 → 70 days | |
| 4 | Need M1 | 50,000 × 70 / 30 × (1 + 10%) | 128,333 |
| 5 | Base limit | 2 × 128,333 | 256,667 |
| 6 | Cerved risk: Caution | 256,667 × 0.70 | 179,667 |
| 7 | Cerved ceiling | Cerved suggests 150,000 → the lower one applies | 150,000 |
| 8 | Special class / no turnover | does not apply | 150,000 |
| 9 | Rounding | up to the next 1,000 | 150,000 |
| 10 | Minimum limit | 5,000: does not apply | 150,000 |
| | **Proposed limit** | | **150,000** |

Box (st.info): "Limited by the Cerved suggested limit (150,000 RON). / Lower: the Cerved ceiling
(150,000 RON) is below the current limit (300,000 RON)."

Exposure sentence: "Exposure today 162,400 RON = balance 118,400 + ordered 24,000 + delivered 20,000.
With the proposed limit the customer is **over limit by 12,400 RON**; with the current limit (300,000 RON) it is not."

Right panel, Checks: Plausibility 6.1% of Cerved turnover → OK (threshold 10%) · Change vs current -50.0%
→ needs approval (threshold ±20%) · Approval tier: Tier 1 (150,000 RON = 30,151 EUR at 4.975).

**IT** (same table)

| # | Passo | Calcolo | RON |
|---|---|---|---|
| 1 | Fatturato ultimi 12 mesi | da Check fidi | 600.000 |
| 2 | Fatturato mensile | 600.000 / 12 | 50.000 |
| 3 | Giorni di pagamento usati | misurati 70 gg; minimo 15, massimo 60 + 15 = 75 → 70 gg | |
| 4 | Bisogno M1 | 50.000 × 70 / 30 × (1 + 10%) | 128.333 |
| 5 | Fido base | 2 × 128.333 | 256.667 |
| 6 | Rischio Cerved: Cautela | 256.667 × 0,70 | 179.667 |
| 7 | Tetto Cerved | Cerved suggerisce 150.000 → vale il minore | 150.000 |
| 8 | Classe speciale / nessun fatturato | non si applica | 150.000 |
| 9 | Arrotondamento | per eccesso al 1.000 successivo | 150.000 |
| 10 | Fido minimo | 5.000: non si applica | 150.000 |
| | **Fido proposto** | | **150.000** |

Variants to show in tests and, if asked, in the meeting:
- Same customer with Cerved suggesting 200,000: step 7 "does not apply", step 9 rounds 179,667 → 180,000.
  Reason COEF_CAUTION: "Caution score: need × 0.70." Why: "Lower: Caution score (× 0.70), the current
  limit (300,000 RON) is above the need."
- Same customer paying at 90 days: step 3 "measured 90 days; maximum 60 + 15 = 75 → **75 days**",
  flag "Slow payer: days limited to 75", M1 = 137,500.

---

## 5. Page "Laboratorio / Lab"

**Purpose:** change the formula live and see in a few seconds what it does compared with the v3.2 default.

**v3.1 (21/11/2026).** The default formula is v3.1: Need (M1) on **contractual terms** and the payment
**bonus/malus** on. Lab additions:
- Group *Bisogno (M1) / Need (M1)*: first control is the segmented control **"Giorni per il Bisogno (M1) / Days
  for the Need (M1)"** = *Termini contrattuali / Contractual terms* (default) | *Misurati / Measured*. Help, one
  line: with "measured" a late payer gets a larger M1, which the malus may not offset; with "contractual terms"
  behaviour acts only through the bonus/malus. On contractual terms the "Cap slow payers" toggle and "Days over
  terms" slider are disabled (they only apply to measured days).
- New group **"Comportamento di pagamento / Payment behaviour"** after Risk: toggle "Bonus / malus sul
  comportamento di pagamento"; when on, sliders *Bonus* (0–20%, default 5%) and *Maximum malus* (0–30%,
  default 10%), number inputs *Tolerance (days late)* (default 5) and *Full malus from (days late)* (default 30,
  always kept above the tolerance). When off, the four values are hidden (kept in the scenario).
- KPI row shown when the option is on: *Customers with bonus*, *Customers with malus* (order-check scope), *Net
  bonus/malus effect · all active* (RON, delta vs v3.2), caption with customers within the tolerance, without
  measured days and the net effect on the scope.
- Sensitivity offers bonus, malus, tolerance and full-malus days when the option is on.
- Customer page: with the option on the step table has **11 rows + total**: step 7 "Payment behaviour: bonus /
  tolerance / malus / no data" with "delay +17 days (measured 47 − terms 30), beyond 5 days (full malus from 30)
  → 220,000 × (1 − 5%)", amount = limit after the bonus/malus; the later steps move by one. The Payment days box
  adds *Delay vs terms* and *Bonus / malus* (band and %), and a caption "The Need (M1) uses the contractual terms
  (30 days), not the measured days." The measured days stay visible as the basis of the bonus/malus.
- Rules page: the formula line gets "× (1 + payment bonus/malus)"; one sentence for the bonus/malus rule generated
  from the parameters (or "no bonus and no malus" when off); the days sentence says M1 uses contractual terms.
- Results/Excel: flags "Payment bonus" / "Payment malus"; Excel adds Delay vs terms, Payment behaviour, Bonus/malus %,
  After bonus/malus, Limit without bonus/malus, Bonus/malus effect when the option is on.

### 5.1 Layout

```
left, right = st.columns([1, 2.3], gap="large")
left:  [Reset to v3.2 defaults button]  [changed-parameters caption]
       four bordered groups (5.2), no fixed-height container (a nested scroll at 768 px is unusable)
       st.expander("Other settings") (5.2, last block), collapsed
right: KPI tiles scenario vs base (5.3)   ← always visible, top of the right column
       st.tabs([Effect, Sensitivity, Scenarios])
         Effect      → changed customers (5.4)
         Sensitivity → (5.5)
         Scenarios   → (5.6)
```

Every control writes into the active parameter set in `st.session_state.params`; the whole app
(Results, Customer, Rules) follows it. Under the reset button:
`st.caption(T("lab_changed", list="Multiplier 2.00 → 2.50 · Caution 0.70 → 0.80"))` or `T("lab_unchanged")`.
Each changed control's label gets a suffix ` •` (bullet) so changes are visible in the panel without colour.

Reset: `st.button(T("btn_reset_defaults"), icon=":material/restart_alt:", use_container_width=True)`:
immediate, no confirmation (the previous state can be saved as a scenario first; the button help says so).

### 5.2 Parameters (15 in the four groups + 6 in "Other settings")

Sliders show the value with unit via `format`. Streamlit formats slider and number-input values with
sprintf ("1.25", "5000"): in Italian the slider's own numbers are hidden (CSS `CSS_IT_SLIDERS`) and the label carries
the formatted value ("Cautela: **0,70**"); amount inputs (minimum limit, approval RON threshold, tiers) show the
formatted value in the label in both languages. Sensitivity axes use a Vega `labelExpr` that swaps separators in
Italian; the legend is a plain sentence (`sens_legend`), not a bulleted dash line.
Scenario table: numbers first (total limits all active, over a positive limit, over limit total, excess, zero,
approvals), the long "what differs from v3" text last; Load / Delete / Export in a row of three under the picker. Help is the one-liner below (IT/EN in the copy deck,
keys `p_<name>` and `p_<name>_help`).

**Group A: Need / Bisogno**

| key | Control | Range | Step | Default | Unit | Help EN | Help IT |
|---|---|---|---|---|---|---|---|
| buffer_pct | slider | 0-50 | 5 | 10 | % | Extra margin on the monthly need. | Margine in più sul bisogno mensile. |
| multiplier | slider | 1.00-4.00 | 0.25 | 2.00 | × M1 | How many months of need the limit covers. | Quanti mesi di bisogno copre il fido. |
| days_min | number_input | 0-60 | 5 | 15 | days | Customers who pay faster still count at least this many days. | Chi paga prima conta comunque almeno questi giorni. |
| days_cap_on | toggle | on/off | | on | | Slow payers do not get a higher limit. | Chi paga tardi non ottiene un fido più alto. |
| days_over_terms | slider (disabled if toggle off) | 0-90 | 5 | 15 | days | Maximum days = contractual terms + this. | Giorni massimi = termini contrattuali + questi. |
| days_default | number_input | 15-120 | 5 | 30 | days | Used when a customer has no invoices and no terms. | Usati se il cliente non ha fatture né termini. |

**Group B: Risk / Rischio** (four sliders 0.00-1.50, step 0.05; the 0.00-1.00 range covers almost all
discussions but 1.50 allows a premium for reliable customers)

| key | Default | Help EN | Help IT |
|---|---|---|---|
| coef_reliable | 1.00 | Multiplier for Cerved "Reliable". | Moltiplicatore per Cerved "Affidabile". |
| coef_caution | 0.70 | Multiplier for Cerved "Caution". | Moltiplicatore per Cerved "Cautela". |
| coef_max_caution | 0.00 | Multiplier for "Maximum caution". 0 = no credit. | Moltiplicatore per "Massima cautela". 0 = niente credito. |
| coef_not_in_cerved | 0.50 | Multiplier for customers Cerved does not know. | Moltiplicatore per i clienti che Cerved non conosce. |

**Group C: Ceilings and rounding / Tetti e arrotondamenti**

| key | Control | Range | Step | Default | Help EN | Help IT |
|---|---|---|---|---|---|---|
| cerved_cap_on | toggle | | | on | The limit never exceeds the Cerved suggested limit. | Il fido non supera mai il fido suggerito da Cerved. |
| round_step | segmented_control | 100 / 500 / 1,000 / 5,000 | | 1,000 | Limits are rounded to this amount (RON). | I fidi sono arrotondati a questo importo (RON). |
| min_limit | number_input | 0-50,000 | 1,000 | 5,000 | RON. Smallest limit for a customer who gets credit. | RON. Fido più piccolo per chi riceve credito. |

**Group D: Checks / Controlli** (they never change a limit; they only change flags and counts)

| key | Control | Range | Step | Default | Help EN | Help IT |
|---|---|---|---|---|---|---|
| plaus_pct | slider | 1-50 | 1 | 10 | % | Review if our turnover is above this share of the customer's total turnover (Cerved). | Da rivedere se il nostro fatturato supera questa quota del fatturato totale del cliente (Cerved). |
| approval_pct | slider | 0-100 | 5 | 20 | % | Approval needed if the limit changes more than this vs the current one. | Serve approvazione se il fido cambia più di così rispetto all'attuale. |

**Other settings / Altre impostazioni** (collapsed expander; not offered in sensitivity):
approval_min_change (number_input, step 1,000, default 5,000 RON: approval only if the change is above
±20% **and** above this amount) · round_direction (segmented Up/Down, default Up) · coef_exempt_not_in_cerved (slider 0-1.5, 0.50) ·
eur_rate (number_input 4.000-6.000, step 0.001, 4.975, "RON per 1 EUR") · tier1_eur / tier2_eur
(number_input, step 10,000, 50,000 / 200,000) · intercompany codes, special classes, exempt classes
(`st.multiselect` with `accept_new_options=True`, defaults from SPEC 4).
Reference date and invoice window live on the Data page.

### 5.3 Scenario vs base: tiles

Two rows in the right column (values 1.6rem, labels wrap): counts first — Over a positive limit (headline,
`inverse`), Over limit total (`off`, caption "of which 160 at limit 0 by rule"), Zero limit with turnover (`off`),
Need approval (`off`); then amounts — Exposure over limit (`inverse`), Total limits · scope (`off`), Total limits ·
all active (`off`). Delta vs v3, hidden when the scenario is v3. Caption `lab_current_ref`: "202 customers over a
positive limit, 267 over limit in total, 9.86 M RON over limit" with today's limits.

### 5.4 Tab "Effect / Effetto": customers that change vs base

- `st.caption(T("chg_summary", n=312, up=290, down=22, into=15, out=4))`:
  "312 customers change: 290 higher, 22 lower; 15 become over limit, 4 no longer."
- `st.segmented_control` All / Limit changes / Over-limit status changes (default All).
- `st.dataframe` height 420, sorted by absolute change desc:
  Code · Customer · Score · Exposure (RON) · Limit v3 (RON) · Limit scenario (RON) · Change (RON) ·
  Over limit (v3 → scenario, e.g. `No → Yes`) · Why (reason in the scenario, short).
- Row click opens Customer as on Results.
- No changes: `st.info(T("chg_none"))` ("Same as v3: change a parameter on the left.").

### 5.5 Tab "Sensitivity / Sensibilità"

One row: `st.selectbox(T("sens_param"), the 15 parameters of groups A-D except toggles and checks)`,
`st.number_input(T("sens_from"))`, `st.number_input(T("sens_to"))` (pre-filled with the slider range around
the current value, e.g. multiplier 1.00 to 3.00), points fixed at **9**, `st.button(T("btn_run_sens"), type="primary")`.
Runs only on click (`st.spinner(T("sens_running"))`); result kept until parameters change, then
`st.caption(T("sens_stale"))`.

Output: two Altair line charts side by side, x = parameter value (with unit), points marked and labelled:
left "Total limits (M RON)", right "Customers over limit". A vertical dashed rule at the **current scenario
value** and a grey dashed horizontal rule at the **current-limits** reference (40.00 M / 267). No dual axes.
Below: `st.dataframe` value | total limits (RON) | customers over limit | exposure over limit (RON) |
zero limit with turnover; current value row in bold.
For checks (plausibility, approval) the sensitivity is not offered: they do not change limits.

### 5.6 Tab "Scenarios / Scenari"

- Save: `st.text_input(T("scn_name"), placeholder="e.g. Multiplier 2.5")` + `st.button(T("btn_save"))`.
  Writes `workspace/<slug>.json` (params + name + date) and confirms with `st.toast(T("scn_saved", name=...))`.
  Same name: overwrite after `T("scn_overwrite")` checkbox.
- Comparison table (`st.dataframe`), first row always **v3 default** (not deletable), second row
  **Current limits** (reference, no parameters), then saved scenarios sorted by name.
  Columns: Scenario · What differs from v3 (text, e.g. "Multiplier 2.50; Caution 0.80") · Total limits ·
  Customers over limit · Exposure over limit · Zero limit with turnover · Need approval. Active scenario
  row marked "(active)" in the name.
- Actions in one row: `st.selectbox` of saved scenarios + `Load` + `Delete` buttons;
  `st.download_button(T("btn_export_json"))` of the selected one;
  `st.file_uploader(T("scn_import"), type=["json"])` imports into `workspace/`. Invalid file:
  `st.error(T("scn_import_err"))`; unknown keys are ignored and listed in `st.caption`.
- Empty: `st.info(T("scn_empty"))`.

---

## 6. Copy deck

All strings live in `core/texts.py` as `TEXTS = {key: {"it": ..., "en": ...}}`. `T(key, **kw)` formats with
`str.format`; numbers are passed already formatted (section 1.4). Missing key → show the key (so a hole is
visible in tests, not hidden). Placeholders: `{n}` counts, `{amt}` amounts with RON, `{pct}` percent,
`{coef}` coefficients, `{days}` days.

### 6.1 Shell, navigation, common

| key | IT | EN |
|---|---|---|
| app_title | Simulatore Fido | Credit Limit Simulator |
| app_subtitle | SIAD Romania · società 42 · RON | SIAD Romania · company 42 · RON |
| lang_label | Lingua | Language |
| nav_data | Dati | Data |
| nav_results | Risultati | Results |
| nav_customer | Cliente | Customer |
| nav_lab | Laboratorio | Lab |
| nav_rules | Regole | Rules |
| badge_data_ok | Dati: 3 file su 3 | Data: 3 of 3 files |
| badge_data_partial | Dati: mancano {n} file | Data: {n} file(s) missing |
| badge_data_none | Nessun dato caricato | No data loaded |
| badge_ref_date | Data di riferimento {date} | Reference date {date} |
| badge_scn_default | Formula: default v3.2 | Formula: v3.2 default |
| badge_scn_modified | Formula modificata ({n} parametri) | Formula changed ({n} parameters) |
| banner_scenario | Stai guardando lo scenario «{name}»: {changes}. | You are looking at scenario "{name}": {changes}. |
| scn_unsaved | non salvato | unsaved |
| btn_reset_defaults | Ripristina default v3.2 | Reset to v3.2 defaults |
| btn_reset_help | Riporta tutti i parametri alle regole v3. Salva prima lo scenario se vuoi tenerlo. | Puts every parameter back to the v3.2 rules. Save the scenario first if you want to keep it. |
| go_data | Vai alla pagina Dati | Go to the Data page |
| calculating | Calcolo in corso... | Calculating... |
| loading_files | Lettura dei file... | Reading the files... |
| yes | Sì | Yes |
| no | No | No |
| ron | RON | RON |
| days_unit | gg | days |
| mln | mln RON | M RON |
| vs_current | rispetto all'attuale | vs current |
| vs_v3 | rispetto a v3.2 | vs v3.2 |
| not_applicable | non si applica | does not apply |
| dash | - | - |

### 6.2 Data page

| key | IT | EN |
|---|---|---|
| data_title | I dati sono completi e affidabili? | Is the data complete and reliable? |
| data_subtitle | I tre file di partenza, cosa contengono e cosa abbiamo controllato. | The three input files, what they contain and what we checked. |
| file_checkfidi | Check fidi (CreditBoard) | Check fidi (CreditBoard) |
| file_cerved | Cerved Slim Report | Cerved Slim Report |
| file_ar124 | Fatture AR124 (JDE) | AR124 invoices (JDE) |
| file_checkfidi_role | Clienti, esposizione, fido attuale, fatturato 12 mesi. | Customers, exposure, current limit, 12-month turnover. |
| file_cerved_role | Score, fido suggerito e fatturato totale del cliente. | Score, suggested limit and the customer's total turnover. |
| file_ar124_role | Fatture: da qui i giorni di pagamento reali. | Invoices: the real payment days come from here. |
| file_loaded | Caricato | Loaded |
| file_missing | Manca | Missing |
| file_rows | {n} righe | {n} rows |
| upload_title | Carica o sostituisci i file | Upload or replace files |
| upload_label | Trascina qui i file (anche tutti e tre insieme) | Drop the files here (all three together is fine) |
| upload_help | Il tipo di file si riconosce dalle colonne, il nome non conta. Senza caricare nulla l'app usa la cartella data/. | The file type is recognised from its columns; the name does not matter. Without uploads the app uses the data/ folder. |
| err_unrecognised | «{name}» non sembra né Check fidi, né Cerved, né AR124: mancano le colonne attese. | "{name}" does not look like Check fidi, Cerved or AR124: the expected columns are missing. |
| data_population | Clienti | Customers |
| m_rows_checkfidi | Righe Check fidi | Check fidi rows |
| m_active | Clienti attivi | Active customers |
| m_intercompany | Intercompany esclusi | Intercompany excluded |
| m_scope | Perimetro controllo ordini | Order-check scope |
| m_ref_date | Data di riferimento | Reference date |
| help_active | Saldo diverso da zero oppure fatturato negli ultimi 12 mesi. Intercompany esclusi. | Balance not zero or turnover in the last 12 months. Intercompany excluded. |
| help_intercompany | Società del gruppo SIAD: fuori dalla simulazione. | SIAD group companies: left out of the simulation. |
| help_scope | Clienti che JDE fermerebbe davvero: attivi, senza classi speciali né esenti. | Customers JDE would really stop: active, no special or exempt classes. |
| help_ref_date | La data a cui si misurano giorni di pagamento e scaduto. Di default l'ultima fattura AR124. | The date payment days and overdue are measured at. By default the latest AR124 invoice. |
| data_matching | Abbinamento con Cerved | Matching with Cerved |
| m_match_code | Abbinati per codice | Matched by code |
| m_match_vat | Abbinati per partita IVA | Matched by VAT number |
| m_match_none | Non in Cerved | Not in Cerved |
| m_cerved_orphans | Righe Cerved senza cliente | Cerved rows with no customer |
| help_match_code | Codice cliente uguale al riferimento Cerved. | Customer code equals the Cerved reference. |
| help_match_vat | Codice non trovato, ma stessa partita IVA. | Code not found, but same VAT number. |
| help_match_none | Clienti attivi senza dati Cerved: ricevono il coefficiente "non in Cerved". | Active customers without Cerved data: they get the "not in Cerved" multiplier. |
| help_cerved_orphans | Righe Cerved che non corrispondono a nessun cliente attivo. | Cerved rows that match no active customer. |
| data_cerved_share | In Cerved: {n} clienti attivi, {pct} dell'esposizione. | In Cerved: {n} active customers, {pct} of exposure. |
| data_quality | Controlli di qualità | Data quality checks |
| dq_col_check | Controllo | Check |
| dq_col_count | Quanti | Count |
| dq_col_meaning | Cosa significa | What it means |
| dq_details | Vedi le righe interessate | See the rows concerned |
| dq_all_ok | Nessun problema trovato nei dati. | No problems found in the data. |
| data_settings | Impostazioni dei dati | Data settings |
| p_ref_date | Data di riferimento | Reference date |
| p_window_months | Finestra fatture (mesi) | Invoice window (months) |
| p_window_months_help | Quanti mesi di fatture usare per i giorni di pagamento. | How many months of invoices to use for payment days. |
| empty_data | Carica i tre file per iniziare. Basta Check fidi per un primo calcolo. | Upload the three files to start. Check fidi alone is enough for a first calculation. |

### 6.3 Missing-file impact (Data cards and page banners)

| key | IT | EN |
|---|---|---|
| missing_checkfidi_impact | Senza Check fidi non si può calcolare nulla: mancano clienti, esposizione e fatturato. | Without Check fidi nothing can be calculated: customers, exposure and turnover are missing. |
| missing_cerved_impact | Cerved manca: tutti i clienti sono trattati come "non in Cerved" (× {coef}), nessun tetto Cerved, nessun controllo di plausibilità. | Cerved is missing: every customer is treated as "not in Cerved" (× {coef}), no Cerved ceiling, no plausibility check. |
| missing_ar124_impact | AR124 manca: i giorni di pagamento sono {days} giorni per tutti. | AR124 is missing: payment days are {days} days for everyone. |
| empty_results | Nessun risultato: serve almeno il file Check fidi. | No results yet: at least the Check fidi file is needed. |
| chart_needs_cerved | Questo grafico richiede il file Cerved. | This chart needs the Cerved file. |
| help_review_needs_cerved | Il controllo di plausibilità usa il fatturato totale Cerved. | The plausibility check uses the Cerved total turnover. |

### 6.4 Data-quality checks (rows of the quality table)

| key | IT | EN |
|---|---|---|
| dq_total_rows | Righe di totale scartate (AR124) | Total rows skipped (AR124) |
| dq_total_rows_m | Righe "Total ..." di JDE: non sono fatture, non contano. | JDE "Total ..." rows: not invoices, not counted. |
| dq_dup_codes | Codici Cerved duplicati | Duplicate Cerved codes |
| dq_dup_codes_m | Stesso codice due volte in Cerved: usiamo la riga con la stessa partita IVA, altrimenti la prima. | Same code twice in Cerved: we use the row with the same VAT number, otherwise the first. |
| dq_dup_diff_company | Codice Cerved su due aziende diverse | Cerved code on two different companies |
| dq_dup_diff_company_m | Es. 30006208 (AVI-TOP / AVICOD): da correggere in Cerved. | E.g. 30006208 (AVI-TOP / AVICOD): to be fixed in Cerved. |
| dq_vat_mismatch | Codice uguale ma partita IVA diversa | Same code but different VAT number |
| dq_vat_mismatch_m | Abbinati per codice, ma la partita IVA non coincide: controllare. | Matched by code, but the VAT number differs: please check. |
| dq_vat_conflict | Codice Cerved con partita IVA diversa | Cerved code with a different VAT number |
| dq_vat_conflict_m | Stesso codice ma partita IVA diversa: la riga Cerved non si usa; si cerca per IVA, altrimenti "non in Cerved". | Same code but different VAT number: the Cerved row is not used; the VAT number is tried instead, otherwise "not in Cerved". |
| dq_no_ref | Righe Cerved senza riferimento | Cerved rows with no reference |
| dq_no_ref_m | Abbinabili solo per partita IVA. | Can be matched only by VAT number. |
| dq_cerved_eur | Fido Cerved in EUR | Cerved limit in EUR |
| dq_cerved_eur_m | Convertito in RON al cambio {rate}. | Converted to RON at {rate}. |
| dq_neg_turnover | Fatturato 12 mesi negativo | Negative 12-month turnover |
| dq_neg_turnover_m | Trattato come zero: fido 0. | Treated as zero: limit 0. |
| dq_no_invoices | Clienti attivi senza fatture nella finestra | Active customers with no invoices in the window |
| dq_no_invoices_m | Giorni = termini contrattuali, o {days} giorni se mancano anche quelli. | Days = contractual terms, or {days} days if those are missing too. |
| dq_no_current_limit | Clienti attivi con fido attuale zero | Active customers with current limit zero |
| dq_no_current_limit_m | Il confronto con l'attuale per loro è "nuovo fido". | For them the comparison reads "new limit". |

Other data-quality rows added on 20/11/2026 (texts in `core/texts.py`): dq_other_currency, dq_negative_limit, dq_multi_company, dq_column_missing, dq_bad_numbers, dq_bad_dates, dq_file_empty. Since the default matching rule rejects code matches with a different VAT, dq_vat_mismatch only appears with the legacy parameter `cerved_reject_vat_conflict = False`.

### 6.5 Reason codes and 6.6 "why it changes" (final wording 20/11/2026)

The authoritative text is `core/texts.py` (REASON_TEXTS short, REASON_LONG_TEXTS long, CHANGE_TEXTS). Rules:
- Every sentence is factually true for the customer it is shown for; it quotes "the formula gives X RON" (step 6)
  and never "real need". "Need (M1)" / "Bisogno (M1)" only for M1; "multiplier" / "moltiplicatore" only for ×2;
  "risk factor" / "coefficiente di rischio" for the score coefficient; "Cerved suggested limit" / "fido suggerito
  Cerved" for VALORE_FIDO, "Cerved ceiling" / "tetto Cerved" for the rule.
- When the Cerved ceiling decides, the why-change sentence says so: C_HIGHER_CERVED_CAP ("Higher than today
  (1,000,000 RON), but held at the Cerved suggested limit (5,041,500 RON); the formula alone would give
  12,937,901 RON"), C_HIGHER/LOWER_MINIMUM_CAPPED ("the 5,000 RON minimum would be above the Cerved suggested
  limit, so the limit is the Cerved value (3,433 RON)"), C_HIGHER/LOWER_ROUNDED_CAPPED, C_LOWER_CERVED_CAP.
- Maximum caution (long): "Cerved rates this company Maximum caution. Our rule: no unsecured credit for this score
  (risk factor 0.00), so the limit is 0 RON; orders need prepayment, a guarantee or an approved exception."
- Exempt not in Cerved (long, `R_COEF_NOT_IN_CERVED_EXEMPT`): "Exempt class EKM, not rated by Cerved: monitoring
  limit with risk factor 0.50."
- Late payer suffix: "Measured payment days 119; the formula counts at most 75 (terms + 15)." Flag "Days capped".
- Short reasons fit the Results table (≤ ~32 characters); the amount of a Cerved-capped limit is the proposed
  limit itself, so the short form is just "Cerved suggested limit".

### 6.7 Results page

| key | IT | EN |
|---|---|---|
| res_title | Cosa cambia con la nuova formula? | What changes with the new formula? |
| res_subtitle | Fidi proposti a confronto con quelli attuali. Il metro di giudizio è l'esposizione reale. | Proposed limits compared with the current ones. The yardstick is real exposure. |
| kpi_over_n | Clienti oltre fido | Customers over limit |
| help_over_n | Clienti del perimetro controllo con esposizione sopra il fido proposto. Con i fidi attuali: {cur}. | Customers in the order-check scope with exposure above the proposed limit. With current limits: {cur}. |
| kpi_over_amt | Esposizione oltre fido | Exposure over limit |
| help_over_amt | Somma degli sforamenti (esposizione meno fido) dei clienti oltre fido. Valore esatto: {amt}. | Sum of the excess (exposure minus limit) of customers over limit. Exact value: {amt}. |
| kpi_limits | Totale fidi | Total limits |
| help_limits | Somma dei fidi proposti, tutti i clienti attivi. Attuali: {cur}. | Sum of proposed limits, all active customers. Current: {cur}. |
| kpi_exposure | Esposizione totale | Total exposure |
| help_exposure | Saldo + ordinato + consegnato, tutti i clienti attivi. Non dipende dalla formula. Valore esatto: {amt}. | Balance + ordered + delivered, all active customers. It does not depend on the formula. Exact value: {amt}. |
| kpi_moves | Più alto / più basso / uguale | Higher / lower / same |
| help_moves | Clienti del perimetro controllo il cui fido proposto è più alto, più basso o uguale all'attuale. | Customers in the order-check scope whose proposed limit is higher, lower or the same as the current one. |
| kpi_zero | Fido zero con fatturato | Zero limit with turnover |
| help_zero | Clienti che fatturano ma ricevono fido 0 (classi speciali escluse). | Customers with turnover who get limit 0 (special classes excluded). |
| kpi_orders_over | Ordini aperti oltre fido | Open orders over limit |
| help_orders_over | Clienti oltre fido con ordini aperti: quelli che JDE fermerebbe subito. | Customers over limit with open orders: those JDE would stop straight away. |
| kpi_review | Da rivedere | To review |
| help_review | Nostro fatturato sopra il {pct} del fatturato totale Cerved: il dato va controllato a mano. | Our turnover above {pct} of the Cerved total turnover: the data needs a manual check. |
| kpi_review_caption | {amt} di esposizione | {amt} of exposure |
| kpi_cerved_mix | In Cerved: {n} clienti attivi, {pct} dell'esposizione. | In Cerved: {n} active customers, {pct} of exposure. |
| kpi_scope_caption | Oltre fido: perimetro controllo ({n} clienti). Totali: tutti gli attivi ({m} clienti). | Over limit: order-check scope ({n} customers). Totals: all active customers ({m}). |
| delta_vs_current | {d} rispetto all'attuale ({cur}) | {d} vs current ({cur}) |
| chart_over_by_score | Oltre fido per score Cerved | Over limit by Cerved score |
| chart_over_by_score_x | Clienti oltre fido | Customers over limit |
| chart_change_buckets | Come cambiano i fidi | How limits change |
| chart_change_y | Clienti | Customers |
| chart_amounts_by_score | Fidi ed esposizione per score (mln RON) | Limits and exposure by score (M RON) |
| chart_more | Altri grafici | More charts |
| series_current | Attuale | Current |
| series_new | Nuovo | New |
| series_exposure | Esposizione | Exposure |
| score_AFFIDABILE | Affidabile | Reliable |
| score_CAUTELA | Cautela | Caution |
| score_MASSIMA_CAUTELA | Massima cautela | Maximum caution |
| score_NONE | Non in Cerved | Not in Cerved |
| b_TO_ZERO | A zero | To zero |
| b_DOWN_50 | -50% e oltre | -50% or more |
| b_DOWN_20_50 | da -20% a -50% | -20% to -50% |
| b_WITHIN_20 | entro ±20% | within ±20% |
| b_UP_20_50 | da +20% a +50% | +20% to +50% |
| b_UP_50 | +50% e oltre | +50% or more |
| b_FROM_ZERO | Nuovo fido (attuale 0) | New limit (current 0) |
| tbl_title | Clienti | Customers |
| flt_search | Cerca | Search |
| flt_search_ph | codice o nome | code or name |
| flt_score | Score Cerved | Cerved score |
| flt_change | Variazione | Change |
| flt_all | Tutti | All |
| flt_higher | Più alto | Higher |
| flt_lower | Più basso | Lower |
| flt_same | Uguale | Same |
| flt_only | Mostra solo | Show only |
| flt_over_new | Oltre fido (nuovo) | Over limit (new) |
| flt_becomes_over | Diventano oltre fido | Become over limit |
| flt_leaves_over | Non più oltre fido | No longer over limit |
| flt_review | Da rivedere | To review |
| flt_approval | Serve approvazione | Need approval |
| flt_scope_all | Mostra tutti gli attivi (anche esenti e classi speciali) | Show all active customers (exempt and special classes too) |
| tbl_count | {shown} clienti su {total} | {shown} of {total} customers |
| tbl_empty | Nessun cliente con questi filtri. | No customer matches these filters. |
| col_code | Codice | Code |
| col_name | Cliente | Customer |
| col_score | Score Cerved | Cerved score |
| col_exposure | Esposizione (RON) | Exposure (RON) |
| col_overdue | Scaduto (RON) | Overdue (RON) |
| col_cur | Attuale (RON) | Current (RON) |
| col_new | Proposto (RON) | Proposed (RON) |
| col_diff | Differenza (RON) | Difference (RON) |
| col_over | Oltre fido | Over limit |
| col_over_help | Attuale → nuovo. Una sola parola se non cambia. | Current → new. One word if it does not change. |
| col_reason | Perché questo fido | Why this limit |
| col_why | Perché cambia | Why it changes |
| col_flags | Note | Notes |
| flag_review | Da rivedere | To review |
| flag_approval | Approvazione Tier {t} | Approval Tier {t} |
| flag_late | Giorni limitati | Days capped |
| flag_exempt | Esente | Exempt |
| btn_excel | Scarica Excel | Download Excel |
| btn_open_customer | Apri il dettaglio di {name} | Open details for {name} |
| excel_filename | fidi_RO_{date}.xlsx | credit_limits_RO_{date}.xlsx |

### 6.8 Customer page

| key | IT | EN |
|---|---|---|
| cust_title | Come si arriva a questo fido? | How do we get to this limit? |
| cust_subtitle | Il calcolo passo per passo per un cliente, con i numeri. | The step-by-step calculation for one customer, with the numbers. |
| cust_pick | Cliente | Customer |
| cust_header | Codice {code} · P. IVA {vat} · classe {cls} · score {score} | Code {code} · VAT {vat} · class {cls} · score {score} |
| cust_t_cur | Fido attuale | Current limit |
| cust_t_new | Fido proposto | Proposed limit |
| cust_t_expo | Esposizione oggi | Exposure today |
| cust_t_over | Oltre fido | Over limit |
| cust_t_over_caption | Con il fido attuale: {v} | With the current limit: {v} |
| steps_title | Calcolo passo per passo | Step-by-step calculation |
| st_col_n | # | # |
| st_col_step | Passo | Step |
| st_col_calc | Calcolo | Calculation |
| st_col_ron | RON | RON |
| st_1 | Fatturato ultimi 12 mesi | Turnover, last 12 months |
| st_1_calc | da Check fidi | from Check fidi |
| st_2 | Fatturato mensile | Monthly turnover |
| st_2_calc | {t12} / 12 | {t12} / 12 |
| st_3 | Giorni di pagamento usati | Payment days used |
| st_3_calc | {src} {meas} gg; minimo {min}, massimo {terms} + {over} = {max} → {used} gg | {src} {meas} days; minimum {min}, maximum {terms} + {over} = {max} → {used} days |
| st_3_src_measured | misurati | measured |
| st_3_src_terms | termini contrattuali (nessuna fattura) | contractual terms (no invoices) |
| st_3_src_default | default (né fatture né termini) | default (no invoices, no terms) |
| st_4 | Bisogno M1 | Need M1 |
| st_4_calc | {m} × {used} / 30 × (1 + {buf}) | {m} × {used} / 30 × (1 + {buf}) |
| st_5 | Fido base | Base limit |
| st_5_calc | {mult} × {m1} | {mult} × {m1} |
| st_6 | Rischio Cerved: {score} | Cerved risk: {score} |
| st_6_calc | {base} × {coef} | {base} × {coef} |
| st_7 | Tetto Cerved | Cerved ceiling |
| st_7_calc_applies | Cerved suggerisce {amt} → vale il minore | Cerved suggests {amt} → the lower one applies |
| st_7_calc_no | Cerved suggerisce {amt}: non serve | Cerved suggests {amt}: not needed |
| st_7_calc_none | nessun fido suggerito Cerved | no Cerved suggested limit |
| st_7_calc_off | tetto Cerved disattivato | Cerved ceiling switched off |
| st_8 | Classe speciale / nessun fatturato | Special class / no turnover |
| st_8_calc_special | classe {cls} → 0 | class {cls} → 0 |
| st_8_calc_noturn | nessun fatturato → 0 | no turnover → 0 |
| st_9 | Arrotondamento | Rounding |
| st_9_calc_up | per eccesso al {step} successivo | up to the next {step} |
| st_9_calc_down | per difetto al {step} precedente | down to the previous {step} |
| st_10 | Fido minimo | Minimum limit |
| st_10_calc_applies | sotto {min} → {min} | below {min} → {min} |
| st_10_calc_no | {min}: non si applica | {min}: does not apply |
| st_total | Fido proposto | Proposed limit |
| expo_sentence | Esposizione oggi {expo} = saldo {bal} + ordinato {ord} + consegnato {del}. | Exposure today {expo} = balance {bal} + ordered {ord} + delivered {del}. |
| expo_over_new | Con il fido proposto è **oltre fido di {amt}**. | With the proposed limit it is **over limit by {amt}**. |
| expo_ok_new | Con il fido proposto resta {amt} di margine. | With the proposed limit {amt} of headroom remains. |
| expo_cur_over | Con il fido attuale ({cur}) è oltre fido di {amt}. | With the current limit ({cur}) it is over limit by {amt}. |
| expo_cur_ok | Con il fido attuale ({cur}) non lo è. | With the current limit ({cur}) it is not. |
| expo_exempt | Classe esente: non viene mai bloccato, l'oltre fido è solo informativo. | Exempt class: never blocked; over limit is for information only. |
| box_cerved | Cerved | Cerved |
| cv_score | Score | Score |
| cv_limit | Fido suggerito | Suggested limit |
| cv_limit_eur | {eur} EUR = {ron} al cambio {rate} | {eur} EUR = {ron} at {rate} |
| cv_class | Classe di affidabilità | Reliability class |
| cv_turnover | Fatturato totale del cliente | Customer's total turnover |
| cv_match | Abbinato per | Matched by |
| cv_match_code | codice | code |
| cv_match_vat | partita IVA | VAT number |
| cv_not_found | Cliente non presente in Cerved. | Customer not in Cerved. |
| box_days | Giorni di pagamento | Payment days |
| pd_measured | Misurati (mediana ponderata) | Measured (weighted median) |
| pd_terms | Termini contrattuali | Contractual terms |
| pd_used | Usati nel calcolo | Used in the calculation |
| pd_invoices | Fatture considerate | Invoices counted |
| days_capped | Paga tardi: contati {days} giorni invece di {meas}. | Slow payer: {days} days counted instead of {meas}. |
| days_floored | Paga presto: contati almeno {days} giorni. | Fast payer: at least {days} days counted. |
| box_checks | Controlli | Checks |
| ck_plaus | Plausibilità | Plausibility |
| ck_plaus_ok | {pct} del fatturato Cerved: OK (soglia {thr}) | {pct} of Cerved turnover: OK (threshold {thr}) |
| ck_plaus_review | {pct} del fatturato Cerved: da rivedere (soglia {thr}) | {pct} of Cerved turnover: to review (threshold {thr}) |
| ck_plaus_na | non calcolabile (manca il fatturato Cerved) | cannot be calculated (no Cerved turnover) |
| ck_change | Variazione rispetto all'attuale | Change vs current |
| ck_approval | Serve approvazione | Approval needed |
| ck_approval_yes | Sì, variazione oltre ±{thr} | Yes, change above ±{thr} |
| ck_approval_no | No, entro ±{thr} | No, within ±{thr} |
| ck_tier | Livello di approvazione | Approval tier |
| ck_tier_val | Tier {t} ({ron} = {eur} EUR) | Tier {t} ({ron} = {eur} EUR) |
| cust_invoices | Fatture del cliente (AR124) | Customer invoices (AR124) |
| inv_date | Data fattura | Invoice date |
| inv_due | Scadenza | Due date |
| inv_closed | Chiusa il | Closed on |
| inv_amount | Importo (RON) | Amount (RON) |
| inv_days | Giorni contati | Days counted |
| inv_open | aperta | open |

### 6.9 Lab page

| key | IT | EN |
|---|---|---|
| lab_title | Quale formula funziona meglio? | Which formula works best? |
| lab_subtitle | Cambia i parametri a sinistra: tutto si ricalcola subito ed è confrontato con la formula v3. | Change the parameters on the left: everything recalculates at once and is compared with the v3.2 formula. |
| lab_changed | Modificati: {list} | Changed: {list} |
| lab_unchanged | Nessuna modifica: è la formula v3. | No changes: this is the v3.2 formula. |
| grp_need | Bisogno | Need |
| grp_risk | Rischio | Risk |
| grp_caps | Tetti e arrotondamenti | Ceilings and rounding |
| grp_checks | Controlli (non cambiano i fidi) | Checks (do not change limits) |
| grp_other | Altre impostazioni | Other settings |
| p_buffer_pct | Margine sul bisogno | Buffer on need |
| p_buffer_pct_help | Margine in più sul bisogno mensile. | Extra margin on the monthly need. |
| p_multiplier | Moltiplicatore | Multiplier |
| p_multiplier_help | Quanti mesi di bisogno copre il fido. | How many months of need the limit covers. |
| p_days_min | Giorni minimi | Minimum days |
| p_days_min_help | Chi paga prima conta comunque almeno questi giorni. | Customers who pay faster still count at least this many days. |
| p_days_cap_on | Limita chi paga tardi | Cap slow payers |
| p_days_cap_on_help | Chi paga tardi non ottiene un fido più alto. | Slow payers do not get a higher limit. |
| p_days_over_terms | Giorni oltre i termini | Days over terms |
| p_days_over_terms_help | Giorni massimi = termini contrattuali + questi. | Maximum days = contractual terms + this. |
| p_days_default | Giorni se mancano i dati | Days when data is missing |
| p_days_default_help | Usati se il cliente non ha fatture né termini. | Used when a customer has no invoices and no terms. |
| p_coef_reliable | Affidabile | Reliable |
| p_coef_reliable_help | Moltiplicatore per Cerved "Affidabile". | Multiplier for Cerved "Reliable". |
| p_coef_caution | Cautela | Caution |
| p_coef_caution_help | Moltiplicatore per Cerved "Cautela". | Multiplier for Cerved "Caution". |
| p_coef_max_caution | Massima cautela | Maximum caution |
| p_coef_max_caution_help | Moltiplicatore per "Massima cautela". 0 = niente credito. | Multiplier for "Maximum caution". 0 = no credit. |
| p_coef_not_in_cerved | Non in Cerved | Not in Cerved |
| p_coef_not_in_cerved_help | Moltiplicatore per i clienti che Cerved non conosce. | Multiplier for customers Cerved does not know. |
| p_coef_exempt_nf | Esenti non in Cerved | Exempt, not in Cerved |
| p_coef_exempt_nf_help | Moltiplicatore per i clienti esenti (es. ospedali) che Cerved non conosce. | Multiplier for exempt customers (e.g. hospitals) Cerved does not know. |
| p_cerved_cap_on | Tetto Cerved | Cerved ceiling |
| p_cerved_cap_on_help | Il fido non supera mai il fido suggerito da Cerved. | The limit never exceeds the Cerved suggested limit. |
| p_round_step | Arrotondamento (RON) | Rounding (RON) |
| p_round_step_help | I fidi sono arrotondati a questo importo. | Limits are rounded to this amount. |
| p_round_dir | Direzione arrotondamento | Rounding direction |
| p_round_up | Per eccesso | Up |
| p_round_down | Per difetto | Down |
| p_min_limit | Fido minimo (RON) | Minimum limit (RON) |
| p_min_limit_help | Fido più piccolo per chi riceve credito. | Smallest limit for a customer who gets credit. |
| p_plaus_pct | Soglia plausibilità | Plausibility threshold |
| p_plaus_pct_help | Da rivedere se il nostro fatturato supera questa quota del fatturato totale del cliente (Cerved). | Review if our turnover is above this share of the customer's total turnover (Cerved). |
| p_approval_pct | Soglia approvazione | Approval threshold |
| p_approval_pct_help | Serve approvazione se il fido cambia più di così rispetto all'attuale. | Approval needed if the limit changes more than this vs the current one. |
| p_eur_rate | Cambio (RON per 1 EUR) | Exchange rate (RON per 1 EUR) |
| p_eur_rate_help | Per i fidi Cerved in EUR e per i livelli di approvazione. | For Cerved limits in EUR and for approval tiers. |
| p_tier1 | Tier 1 fino a (EUR) | Tier 1 up to (EUR) |
| p_tier2 | Tier 2 fino a (EUR) | Tier 2 up to (EUR) |
| p_tier_help | Soglie provvisorie. Oltre Tier 2 è Tier 3. | Provisional thresholds. Above Tier 2 is Tier 3. |
| p_intercompany | Codici intercompany | Intercompany codes |
| p_special | Classi speciali (fido 0) | Special classes (limit 0) |
| p_exempt | Classi esenti (mai bloccate) | Exempt classes (never blocked) |
| lab_kpi_over_n | Clienti oltre fido | Customers over limit |
| lab_kpi_over_amt | Esposizione oltre fido | Exposure over limit |
| lab_kpi_limits | Totale fidi | Total limits |
| lab_kpi_zero | Fido zero con fatturato | Zero limit with turnover |
| lab_kpi_approval | Da approvare | Need approval |
| lab_delta | {d} rispetto a v3.2 | {d} vs v3.2 |
| lab_current_ref | Per riferimento, con i fidi attuali: {over} clienti oltre fido, {amt} oltre fido. | For reference, with the current limits: {over} customers over limit, {amt} over limit. |
| tab_effect | Effetto | Effect |
| tab_sens | Sensibilità | Sensitivity |
| tab_scn | Scenari | Scenarios |
| chg_summary | {n} clienti cambiano: {up} più alto, {down} più basso; {into} diventano oltre fido, {out} non lo sono più. | {n} customers change: {up} higher, {down} lower; {into} become over limit, {out} no longer are. |
| chg_filter_all | Tutti | All |
| chg_filter_limit | Cambia il fido | Limit changes |
| chg_filter_status | Cambia l'oltre fido | Over-limit status changes |
| chg_col_v3 | Fido v3.2 (RON) | Limit v3.2 (RON) |
| chg_col_scn | Fido scenario (RON) | Limit scenario (RON) |
| chg_col_over | Oltre fido (v3.2 → scenario) | Over limit (v3.2 → scenario) |
| chg_none | Uguale a v3.2: cambia un parametro a sinistra. | Same as v3.2: change a parameter on the left. |
| sens_param | Parametro | Parameter |
| sens_from | Da | From |
| sens_to | A | To |
| btn_run_sens | Calcola | Run |
| sens_running | Calcolo di 9 scenari... | Calculating 9 scenarios... |
| sens_stale | I parametri sono cambiati: premi Calcola per aggiornare. | Parameters changed: press Run to update. |
| sens_chart_limits | Totale fidi (mln RON) | Total limits (M RON) |
| sens_chart_over | Clienti oltre fido | Customers over limit |
| sens_now | valore attuale | current value |
| sens_cur_limits | fidi attuali | current limits |
| sens_col_value | Valore | Value |
| sens_empty | Scegli un parametro e un intervallo, poi premi Calcola. | Pick a parameter and a range, then press Run. |
| sens_range_err | «Da» deve essere minore di «A». | "From" must be lower than "To". |
| scn_name | Nome dello scenario | Scenario name |
| scn_name_ph | es. Moltiplicatore 2,5 | e.g. Multiplier 2.5 |
| btn_save | Salva | Save |
| scn_saved | Scenario «{name}» salvato. | Scenario "{name}" saved. |
| scn_overwrite | Esiste già: sovrascrivi | It already exists: overwrite |
| scn_name_empty | Dai un nome allo scenario. | Give the scenario a name. |
| scn_col_name | Scenario | Scenario |
| scn_col_diff | Cosa cambia rispetto a v3.2 | What differs from v3.2 |
| scn_v3 | Default v3.2 | v3.2 default |
| scn_current_limits | Fidi attuali | Current limits |
| scn_active | (attivo) | (active) |
| btn_load | Carica | Load |
| btn_delete | Elimina | Delete |
| btn_export_json | Esporta JSON | Export JSON |
| scn_import | Importa uno scenario (JSON) | Import a scenario (JSON) |
| scn_import_ok | Scenario «{name}» importato. | Scenario "{name}" imported. |
| scn_import_err | Il file non è uno scenario valido. | The file is not a valid scenario. |
| scn_import_ignored | Parametri sconosciuti ignorati: {list} | Unknown parameters ignored: {list} |
| scn_loaded | Scenario «{name}» caricato. | Scenario "{name}" loaded. |
| scn_deleted | Scenario «{name}» eliminato. | Scenario "{name}" deleted. |
| scn_empty | Nessuno scenario salvato. Dai un nome alle impostazioni attuali e premi Salva. | No saved scenarios. Name the current settings and press Save. |

### 6.10 Rules page and glossary

| key | IT | EN |
|---|---|---|
| rules_title | Quali regole sono attive? | Which rules are active? |
| rules_subtitle | Le regole dello scenario attivo, scritte dai parametri. Se non suonano come la nostra politica del credito, i parametri non lo sono. | The rules of the active scenario, written from the parameters. If they do not read like our credit policy, the parameters are not our policy. |
| rules_h_who | Chi è nel calcolo | Who is in the calculation |
| rules_h_limit | Come si calcola il fido | How the limit is calculated |
| rules_h_checks | Controlli | Checks |
| rules_changed_tag | (modificato) | (changed) |
| gloss_title | Glossario | Glossary |

---

## 7. Rules page

**Purpose:** the active rules in plain language, plus a short glossary. One screen, printable.

Layout: `left, right = st.columns([3, 2])`. Left: three `st.subheader` sections with numbered Markdown
lists built from the templates below. Every sentence whose parameter differs from v3 gets
` *(modificato / changed)*` at the end and the changed value in bold. Right: glossary as a `st.table`
(term | meaning), or `st.markdown` definition list. A `st.download_button` "Scarica le regole (txt) /
Download the rules (txt)" under the list (same text, plain; handy to paste into minutes).

### 7.1 Rule templates (values formatted per 1.4)

| key | IT | EN |
|---|---|---|
| rl_active | Un cliente è **attivo** se ha un saldo diverso da zero o fatturato negli ultimi 12 mesi. | A customer is **active** if it has a balance other than zero or turnover in the last 12 months. |
| rl_intercompany | Le società del gruppo ({list}) sono escluse dalla simulazione. | Group companies ({list}) are left out of the simulation. |
| rl_special | Le classi {list} sono **speciali**: fido 0, il cliente è già bloccato in CreditBoard. | Classes {list} are **special**: limit 0, the customer is already blocked in CreditBoard. |
| rl_exempt | Le classi {list} sono **esenti**: non vengono mai bloccate; il fido è calcolato solo per monitoraggio. | Classes {list} are **exempt**: never blocked; the limit is calculated for monitoring only. |
| rl_scope | Il **controllo ordini** riguarda gli attivi senza classi speciali né esenti ({n} clienti). | The **order check** covers active customers without special or exempt classes ({n} customers). |
| rl_exposure | **Esposizione** = saldo + ordinato + consegnato. | **Exposure** = balance + ordered + delivered. |
| rl_days | I **giorni di pagamento** sono la mediana, ponderata per importo, dei giorni con cui il cliente ha pagato le fatture degli ultimi {months} mesi. | **Payment days** are the amount-weighted median of the days the customer took to pay its invoices of the last {months} months. |
| rl_days_min | Si contano almeno {min} giorni. | At least {min} days are counted. |
| rl_days_cap | Si contano al massimo i termini contrattuali + {over} giorni: chi paga tardi non ottiene un fido più alto. | At most the contractual terms + {over} days are counted: slow payers do not get a higher limit. |
| rl_days_nocap | Non c'è un massimo: chi paga tardi ottiene un fido più alto. | There is no maximum: slow payers get a higher limit. |
| rl_days_default | Senza fatture si usano i termini contrattuali; senza nemmeno quelli, {days} giorni. | Without invoices the contractual terms are used; without those either, {days} days. |
| rl_need | Il **bisogno M1** è il fatturato mensile × giorni di pagamento / 30, più il {buf} di margine. | The **need M1** is monthly turnover × payment days / 30, plus a {buf} buffer. |
| rl_mult | Il **fido base** è {mult} volte il bisogno M1. | The **base limit** is {mult} times the need M1. |
| rl_coef | Il fido base si moltiplica per lo score Cerved: affidabile {r}, cautela {c}, massima cautela {mc}, non in Cerved {nf} (esenti non in Cerved {enf}). | The base limit is multiplied by the Cerved score: reliable {r}, caution {c}, maximum caution {mc}, not in Cerved {nf} (exempt not in Cerved {enf}). |
| rl_cap_on | Il fido non supera mai il **fido suggerito da Cerved**; se Cerved suggerisce 0, il fido è 0. I fidi Cerved in EUR si convertono a {rate} RON per EUR. | The limit never exceeds the **Cerved suggested limit**; if Cerved suggests 0, the limit is 0. Cerved limits in EUR are converted at {rate} RON per EUR. |
| rl_cap_off | Il fido suggerito da Cerved **non** è usato come tetto. | The Cerved suggested limit is **not** used as a ceiling. |
| rl_zero | Fido 0 per le classi speciali e per chi non ha fatturato negli ultimi 12 mesi. | Limit 0 for special classes and for customers with no turnover in the last 12 months. |
| rl_round | Il fido si arrotonda per {dir} a multipli di {step} RON. | The limit is rounded {dir} to multiples of {step} RON. |
| rl_round_up_word | eccesso | up |
| rl_round_down_word | difetto | down |
| rl_min | Chi riceve credito ha almeno {min} RON. | A customer who gets credit has at least {min} RON. |
| rl_over | Un cliente è **oltre fido** se l'esposizione supera il fido (solo nel perimetro del controllo ordini). | A customer is **over limit** if exposure is above the limit (order-check scope only). |
| rl_plaus | **Da rivedere** se il nostro fatturato supera il {pct} del fatturato totale del cliente secondo Cerved. | **To review** if our turnover is above {pct} of the customer's total turnover according to Cerved. |
| rl_approval | Serve **approvazione** se il fido proposto cambia più del {pct} rispetto all'attuale. | **Approval** is needed if the proposed limit changes more than {pct} vs the current one. |
| rl_tiers | Livello di approvazione: Tier 1 fino a {t1} EUR, Tier 2 fino a {t2} EUR, Tier 3 oltre (soglie provvisorie). | Approval tier: Tier 1 up to {t1} EUR, Tier 2 up to {t2} EUR, Tier 3 above (provisional thresholds). |

The Rules page has four sections: who is in the calculation (active, intercompany, special, exempt with what
the **monitoring limit** is for, what "**in scope of the order check**" means, exposure, Cerved matching), **the
formula in one line** (`rl_formula`: limit = min( max( round up to 1,000 of ( 2 × Need (M1) × risk factor ),
5,000 ), Cerved suggested limit in whole RON ), with Need (M1) = T12 / 12 × days / 30 × (1 + 10%)), **how the
limit is calculated** as ordered steps a controller can redo by hand (T12 from CreditBoard "Turnover 12 months";
payment days from AR124 incl. how open overdue and open not-due invoices count; terms + 15 cap with terms at
least 15; Need (M1); ×2 and why — a customer paying as usual uses about half (45%) of the limit, the rest covers
new orders and deliveries not yet invoiced; risk factor and why maximum caution gets 0; the Cerved suggested limit
(VALORE_FIDO) in whole RON; zero rules; rounding; minimum 5,000 unless the Cerved limit is lower), and checks
(over limit = next order stopped, limit 0 by rule counted separately; plausibility; approval with materiality;
tiers on the proposed limit). It never states that 1,000,000 EUR is Cerved's maximum (not confirmed). The
formula section is one paragraph; the others are numbered.

### 7.2 Glossary

| key | Term IT / EN | IT | EN |
|---|---|---|---|
| g_exposure | Esposizione / Exposure | Quanto il cliente ci deve o ci dovrà a breve: saldo + ordinato + consegnato non fatturato. È il metro con cui giudichiamo il fido. | What the customer owes us or soon will: balance + ordered + delivered not yet invoiced. It is the yardstick for the limit. |
| g_m1 | Bisogno M1 / Need M1 | Il credito che il cliente usa normalmente: fatturato di un mese × i giorni con cui paga / 30, più un margine. | The credit the customer normally uses: one month of turnover × the days it takes to pay / 30, plus a buffer. |
| g_mult | Moltiplicatore / Multiplier | Quante volte il bisogno M1 copre il fido. 2 = spazio per due "cicli" di fatturazione. | How many times the need M1 the limit covers. 2 = room for two billing cycles. |
| g_coef | Coefficiente di rischio / Risk factor | Riduce il fido secondo lo score Cerved: 1 = pieno, 0 = niente credito. | Reduces the limit according to the Cerved score: 1 = full, 0 = no credit. |
| g_cap | Tetto Cerved / Cerved ceiling | Il fido suggerito da Cerved: il nostro fido non lo supera mai. | The limit suggested by Cerved: our limit never goes above it. |
| g_scope | Perimetro controllo ordini / Order-check scope | I clienti che JDE fermerebbe davvero se oltre fido: attivi, non intercompany, non speciali, non esenti. | The customers JDE would really stop when over limit: active, not intercompany, not special, not exempt. |
| g_over | Oltre fido / Over limit | Esposizione più alta del fido. Nel perimetro, significa ordine bloccato. | Exposure higher than the limit. In the scope, it means an order is stopped. |
| g_plaus | Plausibilità / Plausibility | Se il nostro fatturato con il cliente è una quota troppo alta del suo fatturato totale (Cerved), uno dei due dati è probabilmente sbagliato: va controllato a mano. | If our turnover with the customer is too high a share of its total turnover (Cerved), one of the two figures is probably wrong: check it by hand. |
| g_approval | Livello di approvazione / Approval tier | Chi deve approvare un fido che cambia molto: dipende dall'importo in EUR (Tier 1, 2, 3). | Who must approve a limit that changes a lot: it depends on the amount in EUR (Tier 1, 2, 3). |
| g_ic | Intercompany | Società del gruppo SIAD: fuori dalla simulazione. | SIAD group companies: left out of the simulation. |
| g_exempt | Classi esenti / Exempt classes | Clienti che non si bloccano mai (es. enti pubblici, ospedali): il fido è solo un riferimento. | Customers who are never blocked (e.g. public bodies, hospitals): the limit is only a reference. |
| g_special | Classi speciali / Special classes | Clienti già bloccati in CreditBoard (contenzioso, procedure): fido 0. | Customers already blocked in CreditBoard (litigation, insolvency): limit 0. |
| g_days | Giorni di pagamento / Payment days | Quanti giorni il cliente impiega davvero a pagare, misurati sulle fatture. | How many days the customer really takes to pay, measured on its invoices. |

(The developer should confirm with Loris the examples in g_exempt and g_special; they are the usual
meaning of those classes in the SIAD blocking rules, not taken from data.)

---

## 8. Projector accessibility

- **Layout:** `layout="wide"`; design target 1366×768 at browser zoom 100% and 1920×1080 at 125%.
  Every page's first screen must contain the answer (tiles + charts on Results, tiles + steps on Customer,
  parameters + tiles on Lab).
- **Theme** in `.streamlit/config.toml`:
  ```toml
  [theme]
  base = "light"
  primaryColor = "#1F4E79"
  backgroundColor = "#FFFFFF"
  secondaryBackgroundColor = "#EEF2F6"
  textColor = "#111827"
  font = "sans serif"
  baseFontSize = 17          # Streamlit >= 1.46; otherwise use the CSS below
  ```
  Light theme only (dark themes wash out on projectors). Do not offer a theme switch.
- **Font sizes** (one small CSS block via `st.markdown("<style>...</style>", unsafe_allow_html=True)`):
  body 17px; `st.metric` label 16px, value 1.75rem ≈ 30px, forced on `[data-testid="stMetricValue"] *` because
  the value is a markdown `<p>` that the generic 17px rule would otherwise shrink; values may wrap,
  delta 15px; table cells 15-16px (`st.table` inherits body size; for `st.dataframe` the grid font is fixed,
  so on the projector use browser zoom 125%); chart axis labels 14px, titles 16px, bar labels 14px
  (Altair `configure_axis(labelFontSize=14, titleFontSize=15)`, `configure_title(fontSize=16)`).
- **Contrast:** text #111827 on white (≥ 15:1). Grey only for secondary series and captions, never
  lighter than #6B7280 for text. Bars: blue #1F4E79 vs grey #9AA5B1 (distinguishable also in greyscale).
- **No colour-only meaning:** deltas carry sign and arrow; the Over limit column is words (`No → Yes`);
  scores are written labels; badges carry text; changed parameters get a bullet and are listed in words;
  charts have legends and number labels on every bar.
- **Red is rare:** only `st.metric` inverse deltas that get worse, `st.error` for unreadable files, and
  nothing else. Decreases of limits are orange, not red. Zero-limit customers use `st.warning`, not error.
- **Motion:** no auto-refresh, no animations; `st.toast` only for save/load confirmations.
- **Help texts** are hover-only, so everything needed to understand a tile in the meeting is in its label
  and delta; the help adds the exact figure and population.

---

## 9. Suggested SPEC changes

1. **Rounding up after the Cerved ceiling exceeds the ceiling.** SPEC orders: ceiling (step 4) → round up
   (6). Cerved 27,500 becomes 28,000, above what Cerved suggests; the reference code (`variants.finish`)
   does the same. Proposal: when the ceiling binds, round **down** (or apply the ceiling after rounding).
   The Customer table would otherwise show "never above Cerved" and then a higher number two rows later.
2. **The minimum can also exceed the Cerved ceiling** (Cerved suggests 2,000 → minimum 5,000). Decide:
   minimum does not apply when the Cerved ceiling binds (my proposal), or it is stated as a rule exception.
3. **Too many parameters for one screen.** SPEC lists about 21; the Lab shows 15 and moves rounding
   direction, exempt-not-in-Cerved coefficient, EUR rate, tier thresholds and the three class/code lists
   to "Other settings", and the reference date and invoice window to the Data page (they are data, not formula).
4. **Buffer and multiplier both scale M1** (2 × 1.10 = 2.2 months). Two knobs with the same effect confuse
   the discussion. Keep both for now (v3 is decided) but the sensitivity offers the multiplier first, and the
   Rules page states the combined figure. For v4 consider dropping the buffer.
5. **Mixed populations in KPIs** (totals on 2,116 actives, over limit on 1,598 in scope) must be labelled
   on every tile; or use the scope for all KPIs and show actives only on Data. I would prefer one population.
6. **Results and Customer follow the Lab scenario.** SPEC does not say; I made it explicit with the
   sidebar badge and banner.
7. **Approval vs inflated current limits:** since current limits were inflated on purpose, the ±20%
   approval count will be large and say little. Show it, but keep it neutral (grey) and out of row 1.

## 10. v3.2: customer age and the customer master MD105 (21/11/2026)

The age bands are on by default. Everything below appears only while `age_bands_enabled` is on (the minimum-invoices
rows also when `behaviour_min_invoices` > 0); with both off the screens are the v3.1 ones.

- **Data page**: a fourth file card "Anagrafica clienti MD105 (opzionale)" / "Customer master MD105 (optional)"
  (grey "Missing" badge when absent, with `file_md105_missing`); the sidebar data badge still counts only the three
  required files. Quality rows: `dq_ar_short_history` (no MD105 and AR124 shorter than consolidated + 6 months),
  `dq_age_before_opening` (first invoice > 31 days before the MD105 opening: earlier date used; detail table with
  both dates), `dq_md_missing`, `dq_md_no_code`, `dq_md_dup_code`.
- **Results**: under the KPI tiles a static table `age_tbl_title` (band, customers, current limits, proposed
  limits, over a positive limit, over limit total, total row); a multiselect filter `flt_age`; column `col_age`
  in "More columns"; warning `banner_short_history` when the ages come from a short AR124 without MD105.
- **Customer**: a coloured badge `cust_age_badge` (orange new, blue young, green consolidated; grey
  `cust_age_badge_none`), the warning `cust_new_warning` for new customers, step 2 of the table says
  `st_2_calc_age` ("turnover 40,000 ÷ 4 months active (young customer)"), the payment-behaviour step says
  `st_beh_calc_new` / `st_beh_calc_few`; the days box adds opened (MD105), first invoice, age, months active,
  invoices already due; same banner as Results.
- **Left-censoring**: a customer whose age comes from a first AR124 invoice in the first 31 days of the file is
  consolidated; badge `cust_age_badge_min` ("≥ N months"), days box `pd_age_min`, step S_AGE_CENSORED.
- **Lab**: group `grp_age` between "Payment behaviour" and "Ceilings": toggle `p_age_on`, numbers `p_age_new`
  and `p_age_consolidated` (shown only when on; consolidated never below new), `p_beh_min_inv`; caption
  `lab_age_caption` with the scope split by band and the customers without bonus/malus; sensitivity offers the
  three numbers.
- **Rules**: `rl_age_on` / `rl_age_off` after the turnover rule, `rl_beh_min` / `rl_beh_min_off` after the bonus /
  malus rule, `{div}` in the formula ("T12 / months active (12 for consolidated customers)"); glossary `g_age`.
- **Reasons**: `R_NEW_CUSTOMER` "New customer: turnover ÷ 4 months, to confirm", `R_YOUNG_CUSTOMER`; why it
  changes `C_HIGHER_AGE` / `C_LOWER_AGE`; flag `flag_new_customer` in the Notes column.
- All "v3.1" labels of the shell and the Lab are now "v3.2" (the base scenario is the v3.2 default).

