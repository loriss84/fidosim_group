"""All user-facing strings, IT / EN, keyed by code.

Structure: ``TABLE[code][lang]`` (lang = "it" | "en"). Sentences use placeholders
with custom format specs, rendered by ``render(template, lang, **values)``:
``{x:amt}`` amount in RON with thousands separator, ``{x:pct}`` fraction as %,
``{x:days}`` integer days, ``{x:num}`` number with 2 decimals; plain ``{x}`` as is.
None values render as "-".

The calculation core only emits codes; the UI owner may extend these dicts
(e.g. PARAM_TEXTS, page labels) without touching the core.
"""
from __future__ import annotations

import math
import string
from typing import Any

LANGS = ("it", "en")


def fmt_amount(x: Any, lang: str = "it", decimals: int = 0) -> str:
    """1234567.8 -> '1.234.568' (it) / '1,234,568' (en)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    if isinstance(x, float) and math.isinf(x):
        return "∞"
    s = f"{x:,.{decimals}f}"
    if lang == "it":
        s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return s


class _Fmt(string.Formatter):
    def __init__(self, lang: str) -> None:
        self.lang = lang

    def format_field(self, value: Any, spec: str) -> str:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return "-"
        if spec == "amt":
            return fmt_amount(value, self.lang)
        if spec == "pct":
            if isinstance(value, float) and math.isinf(value):
                return "∞"
            return fmt_amount(value * 100, self.lang, 1 if abs(value * 100) < 10 else 0) + "%"
        if spec == "days":
            return fmt_amount(value, self.lang)
        if spec == "num":
            return fmt_amount(value, self.lang, 2)
        if spec in ("dd", "sdd"):  # days with up to 1 decimal (17,5); "sdd" signed (+17,5 / −3 / 0)
            txt = fmt_amount(abs(value) if spec == "sdd" else value, self.lang, 1)
            txt = txt[:-2] if txt[-2:] in (",0", ".0") else txt
            if spec == "sdd" and round(value, 1) != 0:
                txt = ("+" if value > 0 else "−") + txt
            return txt
        if spec == "spct":  # signed percentage: +5%, −6,0%, 0%
            if round(value * 100, 1) == 0:
                return "0%"
            body = fmt_amount(abs(value) * 100, self.lang, 1)
            body = (body[:-2] if body[-2:] in (",0", ".0") else body) + "%"
            return ("+" if value > 0 else "−") + body
        if spec == "x":  # compact multiplier: 2 -> '2', 2.5 -> '2,5' / '2.5'
            return fmt_amount(value, self.lang, 2).rstrip("0").rstrip(",.")
        return super().format_field(value, spec)


def render(template: str, lang: str = "it", **values: Any) -> str:
    """Fill a template; missing placeholders render as '-'."""
    class _D(dict):
        def __missing__(self, k: str) -> None:
            return None
    return _Fmt(lang).vformat(template, (), _D(values))


def t(table: dict[str, dict[str, Any]], code: str, lang: str = "it", **values: Any) -> str:
    """Sentence for ``code`` from ``table`` in ``lang`` (falls back to EN, then the code)."""
    entry = table.get(code)
    if entry is None:
        return code
    tpl = entry.get(lang) or entry.get("en") or code
    if isinstance(tpl, dict):  # step texts: use the "calc" part
        tpl = tpl.get("calc", "")
    if "bucket" in values and "score_lbl" not in values:  # score label in the sentence's language
        values = dict(values, score_lbl=SCORE_TEXTS.get(values["bucket"], {}).get(lang, values["bucket"]))
    if "age_source_code" in values and "age_src" not in values:  # source of the customer age, in the language
        src = values["age_source_code"]
        values = dict(values, age_src=AGE_SOURCE_TEXTS.get(src, {}).get(lang) if isinstance(src, str) else None)
    return render(tpl, lang, **values)


# ---------------------------------------------------------------------------
# Score buckets
# ---------------------------------------------------------------------------
SCORE_TEXTS = {
    "AFFIDABILE": {"it": "Affidabile", "en": "Reliable"},
    "CAUTELA": {"it": "Cautela", "en": "Caution"},
    "MASSIMA CAUTELA": {"it": "Massima cautela", "en": "Maximum caution"},
    "NONE": {"it": "Non in Cerved", "en": "Not in Cerved"},
}

MATCH_TEXTS = {  # Cerved match method (Excel column, Customer page)
    "code": {"it": "codice", "en": "code"},
    "vat": {"it": "partita IVA", "en": "VAT number"},
    "none": {"it": "non in Cerved", "en": "not in Cerved"},
}

DIRECTION_TEXTS = {
    "HIGHER": {"it": "Più alto", "en": "Higher"},
    "LOWER": {"it": "Più basso", "en": "Lower"},
    "EQUAL": {"it": "Uguale", "en": "Same"},
}

# ---------------------------------------------------------------------------
# Reason for the proposed limit (explain.REASON_CODES); values: explain.text_values
# ---------------------------------------------------------------------------
REASON_TEXTS = {  # short form (tables, Excel; fits the 1366 px table). "(0,70)" = the risk factor; the long
    # form (Customer page) names it "coefficiente di rischio" / "risk factor".
    "R_INTERCOMPANY": {"it": "Intercompany: escluso", "en": "Intercompany: excluded"},
    "R_SPECIAL": {"it": "Classe speciale {risk_class}: fido 0", "en": "Special class {risk_class}: limit 0"},
    "R_NO_TURNOVER": {"it": "Nessun fatturato 12 mesi: fido 0", "en": "No 12-month turnover: limit 0"},
    "R_MAX_CAUTION": {"it": "Massima cautela: nessun credito", "en": "Maximum caution: no credit"},
    "R_ZERO_COEF": {"it": "Coefficiente di rischio 0: fido 0", "en": "Risk factor 0: limit 0"},
    "R_CERVED_ZERO": {"it": "Fido suggerito Cerved 0: fido 0", "en": "Cerved suggested limit 0: limit 0"},
    "R_ROUNDED_ZERO": {"it": "Arrotondato per difetto a 0", "en": "Rounded down to 0"},
    "R_MINIMUM_OVER_CAP": {"it": "Minimo {min_limit:amt} RON (Cerved {cerved_limit:amt} RON)",
                           "en": "Minimum {min_limit:amt} RON (Cerved {cerved_limit:amt} RON)"},
    "R_CERVED_CAP": {"it": "Fido suggerito Cerved", "en": "Cerved suggested limit"},
    "R_MINIMUM": {"it": "Minimo {min_limit:amt} RON", "en": "Minimum {min_limit:amt} RON"},
    "R_COEF_CAUTION": {"it": "Score Cautela ({coefficient:num})", "en": "Caution score ({coefficient:num})"},
    "R_COEF_NOT_IN_CERVED": {"it": "Non in Cerved ({coefficient:num})", "en": "Not in Cerved ({coefficient:num})"},
    "R_COEF_REDUCED": {"it": "Coefficiente di rischio {coefficient:num}", "en": "Risk factor {coefficient:num}"},
    "R_FULL_NEED": {"it": "Formula piena (affidabile)", "en": "Full formula (Reliable)"},
    "R_FULL_NEED_NEUTRAL": {"it": "Formula piena ({coefficient:num})", "en": "Full formula ({coefficient:num})"},
    "R_BEHAVIOUR_BONUS": {"it": "Bonus pagamenti {behaviour_pct:spct}", "en": "Payment bonus {behaviour_pct:spct}"},
    "R_BEHAVIOUR_MALUS": {"it": "Malus ritardo {behaviour_pct:spct} ({delay:sdd} gg)",
                          "en": "Late-payment malus {behaviour_pct:spct} ({delay:sdd} days)"},
    "R_NEW_CUSTOMER": {"it": "Cliente nuovo: fatturato ÷ {months:dd} mesi, da confermare",
                       "en": "New customer: turnover ÷ {months:dd} months, to confirm"},
    "R_YOUNG_CUSTOMER": {"it": "Cliente giovane: fatturato ÷ {months:dd} mesi",
                         "en": "Young customer: turnover ÷ {months:dd} months"},
}

# Long form for the Customer page (same codes and placeholders). Factual: "the formula gives X RON",
# never "real need"; "Bisogno (M1)" / "Need (M1)" is only M1.
REASON_LONG_TEXTS = {
    "R_INTERCOMPANY": {"it": "Società del gruppo SIAD: esclusa dalla simulazione, il fido resta quello attuale.",
                       "en": "SIAD group company: left out of the simulation; the limit stays as it is."},
    "R_SPECIAL": {"it": "Classe di rischio {risk_class}: il cliente è già bloccato in CreditBoard, quindi fido 0 RON.",
                  "en": "Risk class {risk_class}: the customer is already blocked in CreditBoard, so the limit is 0 RON."},
    "R_NO_TURNOVER": {"it": "Nessun fatturato negli ultimi 12 mesi: la formula dà 0, quindi fido 0 RON.",
                      "en": "No turnover in the last 12 months: the formula gives 0, so the limit is 0 RON."},
    "R_MAX_CAUTION": {"it": "Cerved valuta questa società Massima cautela. La nostra regola: nessun credito non "
                            "garantito con questo score (coefficiente di rischio {coefficient:num}), quindi fido 0 RON; "
                            "gli ordini richiedono pagamento anticipato, una garanzia o un'eccezione approvata.",
                      "en": "Cerved rates this company Maximum caution. Our rule: no unsecured credit for this score "
                            "(risk factor {coefficient:num}), so the limit is 0 RON; orders need prepayment, a "
                            "guarantee or an approved exception."},
    "R_ZERO_COEF": {"it": "Il coefficiente di rischio per lo score {score_lbl} è 0, quindi fido 0 RON.",
                    "en": "The risk factor for the score {score_lbl} is 0, so the limit is 0 RON."},
    "R_CERVED_ZERO": {"it": "Score Cerved {score_lbl}, ma Cerved suggerisce un fido di {cerved_limit:amt} RON: il fido "
                            "non supera mai il fido suggerito Cerved, quindi fido 0 RON; gli ordini richiedono "
                            "pagamento anticipato, una garanzia o un'eccezione approvata.",
                      "en": "Cerved score {score_lbl}, but Cerved suggests a limit of {cerved_limit:amt} RON: the limit "
                            "never goes above the Cerved suggested limit, so it is 0 RON; orders need prepayment, a "
                            "guarantee or an approved exception."},
    "R_ROUNDED_ZERO": {"it": "La formula dà {before_round:amt} RON che, arrotondati per difetto, diventano 0 RON.",
                       "en": "The formula gives {before_round:amt} RON, which rounded down becomes 0 RON."},
    "R_MINIMUM_OVER_CAP": {"it": "La formula dà {formula:amt} RON, sotto il minimo: si applica il fido minimo di "
                                 "{min_limit:amt} RON, anche se Cerved suggerisce {cerved_limit:amt} RON (tetto Cerved "
                                 "non rigido).",
                           "en": "The formula gives {formula:amt} RON, below the minimum: the {min_limit:amt} RON "
                                 "minimum limit applies, even though Cerved suggests {cerved_limit:amt} RON (Cerved "
                                 "ceiling not hard)."},
    "R_CERVED_CAP": {"it": "Il fido è il fido suggerito Cerved ({cerved_limit:amt} RON): non lo superiamo mai, "
                           "nemmeno con l'arrotondamento o il minimo di {min_limit:amt} RON.",
                     "en": "The limit is the Cerved suggested limit ({cerved_limit:amt} RON): we never go above it, "
                           "not even with rounding or the {min_limit:amt} RON minimum."},
    "R_MINIMUM": {"it": "La formula dà {formula:amt} RON, sotto il minimo: si applica il fido minimo di "
                        "{min_limit:amt} RON.",
                  "en": "The formula gives {formula:amt} RON, below the minimum: the {min_limit:amt} RON minimum "
                        "limit applies."},
    "R_COEF_CAUTION": {"it": "Score Cerved Cautela: il fido base è moltiplicato per il coefficiente di rischio "
                             "{coefficient:num}.",
                       "en": "Cerved score Caution: the base limit is multiplied by the risk factor {coefficient:num}."},
    "R_COEF_NOT_IN_CERVED": {"it": "Cliente non valutato da Cerved (o non abbinato): il fido base è moltiplicato per "
                                   "il coefficiente di rischio {coefficient:num}.",
                             "en": "Customer not rated by Cerved (or not matched): the base limit is multiplied by "
                                   "the risk factor {coefficient:num}."},
    "R_COEF_NOT_IN_CERVED_EXEMPT": {"it": "Classe esente {risk_class}, non valutata da Cerved: fido di monitoraggio "
                                          "con coefficiente di rischio {coefficient:num}.",
                                    "en": "Exempt class {risk_class}, not rated by Cerved: monitoring limit with "
                                          "risk factor {coefficient:num}."},
    "R_COEF_REDUCED": {"it": "Il fido base è moltiplicato per il coefficiente di rischio {coefficient:num} "
                             "(score {score_lbl}).",
                       "en": "The base limit is multiplied by the risk factor {coefficient:num} (score {score_lbl})."},
    "R_FULL_NEED": {"it": "Score Cerved Affidabile (coefficiente di rischio {coefficient:num}): il fido è la formula "
                          "piena, moltiplicatore ×{mult:x} × Bisogno (M1).",
                    "en": "Cerved score Reliable (risk factor {coefficient:num}): the limit is the full formula, "
                          "×{mult:x} multiplier × Need (M1)."},
    "R_FULL_NEED_NEUTRAL": {"it": "Coefficiente di rischio {coefficient:num}: il fido è la formula piena, "
                                  "moltiplicatore ×{mult:x} × Bisogno (M1).",
                            "en": "Risk factor {coefficient:num}: the limit is the full formula, ×{mult:x} "
                                  "multiplier × Need (M1)."},
    "R_BEHAVIOUR_BONUS": {"it": "Paga puntuale: giorni misurati {days_measured:dd} con termini di {days_terms:dd} "
                                "(ritardo {delay:sdd} giorni). Dopo il coefficiente di rischio {coefficient:num} la "
                                "formula dà {risk_limit:amt} RON; il bonus di pagamento {behaviour_pct:spct} la porta a "
                                "{after_coef:amt} RON.",
                          "en": "Pays on time: measured {days_measured:dd} days against terms of {days_terms:dd} "
                                "(delay {delay:sdd} days). After the risk factor {coefficient:num} the formula gives "
                                "{risk_limit:amt} RON; the payment bonus {behaviour_pct:spct} takes it to "
                                "{after_coef:amt} RON."},
    "R_BEHAVIOUR_MALUS": {"it": "Paga in ritardo: giorni misurati {days_measured:dd} con termini di {days_terms:dd} "
                                "(ritardo {delay:sdd} giorni, oltre la tolleranza). Dopo il coefficiente di rischio "
                                "{coefficient:num} la formula dà {risk_limit:amt} RON; il malus di pagamento "
                                "{behaviour_pct:spct} la porta a {after_coef:amt} RON.",
                          "en": "Pays late: measured {days_measured:dd} days against terms of {days_terms:dd} "
                                "(delay {delay:sdd} days, beyond the tolerance). After the risk factor "
                                "{coefficient:num} the formula gives {risk_limit:amt} RON; the payment malus "
                                "{behaviour_pct:spct} takes it to {after_coef:amt} RON."},
    "R_NEW_CUSTOMER": {"it": "Cliente nuovo: cliente da {age:dd} mesi ({age_src}). Il fatturato 12 mesi {turnover:amt} "
                             "RON è diviso per {months:dd} mesi di attività ({monthly:amt} RON al mese invece di "
                             "{monthly12:amt}); con il coefficiente di rischio {coefficient:num} la formula dà "
                             "{after_coef:amt} RON. Nessun bonus/malus di pagamento finché è nuovo. Confermare il "
                             "fatturato con la stima commerciale.",
                       "en": "New customer: a customer for {age:dd} months ({age_src}). The 12-month turnover "
                             "{turnover:amt} RON is divided by {months:dd} months active ({monthly:amt} RON a month "
                             "instead of {monthly12:amt}); with the risk factor {coefficient:num} the formula gives "
                             "{after_coef:amt} RON. No payment bonus/malus while it is new. Confirm the revenue with "
                             "the sales estimate."},
    "R_YOUNG_CUSTOMER": {"it": "Cliente giovane: cliente da {age:dd} mesi ({age_src}). Il fatturato 12 mesi "
                               "{turnover:amt} RON è diviso per {months:dd} mesi di attività ({monthly:amt} RON al "
                               "mese invece di {monthly12:amt}); con il coefficiente di rischio {coefficient:num} la "
                               "formula dà {after_coef:amt} RON.",
                         "en": "Young customer: a customer for {age:dd} months ({age_src}). The 12-month turnover "
                               "{turnover:amt} RON is divided by {months:dd} months active ({monthly:amt} RON a month "
                               "instead of {monthly12:amt}); with the risk factor {coefficient:num} the formula gives "
                               "{after_coef:amt} RON."},
}

# ---------------------------------------------------------------------------
# Why it changes vs the current limit (explain.CHANGE_CODES). Every sentence is true for the customer
# it is used for. {after_coef} = the formula (step 6, after the payment bonus / malus when it is on), {formula} = the formula as rounded when it is
# below the minimum, {cerved_limit} = Cerved suggested limit in whole RON.
# ---------------------------------------------------------------------------
CHANGE_TEXTS = {
    "C_EQUAL": {"it": "Uguale al fido di oggi ({current:amt} RON).", "en": "Same as today's limit ({current:amt} RON)."},
    "C_EXCLUDED": {"it": "Escluso (intercompany).", "en": "Excluded (intercompany)."},
    "C_HIGHER_NO_CURRENT": {"it": "Più alto: oggi il fido in CreditBoard è {current:amt} RON; la formula dà "
                                  "{after_coef:amt} RON.",
                            "en": "Higher: today's limit in CreditBoard is {current:amt} RON; the formula gives "
                                  "{after_coef:amt} RON."},
    "C_HIGHER_MINIMUM": {"it": "Più alto: la formula dà {formula:amt} RON, sotto il minimo, quindi si applica il fido "
                               "minimo di {min_limit:amt} RON; il fido di oggi è {current:amt} RON.",
                         "en": "Higher: the formula gives {formula:amt} RON, below the minimum, so the "
                               "{min_limit:amt} RON minimum limit applies; today's limit is {current:amt} RON."},
    "C_HIGHER_NEED": {"it": "Più alto: la formula dà {after_coef:amt} RON; il fido di oggi è {current:amt} RON.",
                      "en": "Higher: the formula gives {after_coef:amt} RON; today's limit is {current:amt} RON."},
    "C_HIGHER_ROUNDED": {"it": "Più alto: la formula dà {after_coef:amt} RON, arrotondati per eccesso a "
                               "{proposed:amt} RON; il fido di oggi è {current:amt} RON.",
                         "en": "Higher: the formula gives {after_coef:amt} RON, rounded up to {proposed:amt} RON; "
                               "today's limit is {current:amt} RON."},
    "C_HIGHER_CERVED_CAP": {"it": "Più alto di oggi ({current:amt} RON), ma fermato al fido suggerito Cerved "
                                  "({cerved_limit:amt} RON); la formula da sola darebbe {after_coef:amt} RON.",
                            "en": "Higher than today ({current:amt} RON), but held at the Cerved suggested limit "
                                  "({cerved_limit:amt} RON); the formula alone would give {after_coef:amt} RON."},
    "C_HIGHER_MINIMUM_CAPPED": {"it": "Più alto: la formula dà {after_coef:amt} RON; il minimo di {min_limit:amt} RON "
                                      "supererebbe il fido suggerito Cerved, quindi il fido è il valore Cerved "
                                      "({cerved_limit:amt} RON); il fido di oggi è {current:amt} RON.",
                                "en": "Higher: the formula gives {after_coef:amt} RON; the {min_limit:amt} RON minimum "
                                      "would be above the Cerved suggested limit, so the limit is the Cerved value "
                                      "({cerved_limit:amt} RON); today's limit is {current:amt} RON."},
    "C_HIGHER_ROUNDED_CAPPED": {"it": "Più alto: la formula dà {after_coef:amt} RON; l'arrotondamento supererebbe il "
                                      "fido suggerito Cerved, quindi il fido è il valore Cerved ({cerved_limit:amt} "
                                      "RON); il fido di oggi è {current:amt} RON.",
                                "en": "Higher: the formula gives {after_coef:amt} RON; rounding up would be above the "
                                      "Cerved suggested limit, so the limit is the Cerved value ({cerved_limit:amt} "
                                      "RON); today's limit is {current:amt} RON."},
    "C_LOWER_SPECIAL": {"it": "Più basso: classe speciale {risk_class} (già bloccato in CreditBoard), fido 0 RON; "
                              "oggi {current:amt} RON.",
                        "en": "Lower: special class {risk_class} (already blocked in CreditBoard), limit 0 RON; "
                              "today {current:amt} RON."},
    "C_LOWER_NO_TURNOVER": {"it": "Più basso: nessun fatturato negli ultimi 12 mesi, fido 0 RON; oggi {current:amt} RON.",
                            "en": "Lower: no turnover in the last 12 months, limit 0 RON; today {current:amt} RON."},
    "C_LOWER_MAX_CAUTION": {"it": "Più basso: score Cerved Massima cautela, coefficiente di rischio {coefficient:num}: "
                                  "fido 0 RON; oggi {current:amt} RON.",
                            "en": "Lower: Cerved score Maximum caution, risk factor {coefficient:num}: limit 0 RON; "
                                  "today {current:amt} RON."},
    "C_LOWER_ZERO_COEF": {"it": "Più basso: coefficiente di rischio 0 per lo score {score_lbl}: fido 0 RON; oggi "
                                "{current:amt} RON.",
                          "en": "Lower: risk factor 0 for the score {score_lbl}: limit 0 RON; today {current:amt} RON."},
    "C_LOWER_CERVED_ZERO": {"it": "Più basso: Cerved suggerisce {cerved_limit:amt} RON (score {score_lbl}): fido 0 RON; "
                                  "oggi {current:amt} RON.",
                            "en": "Lower: Cerved suggests {cerved_limit:amt} RON (score {score_lbl}): limit 0 RON; "
                                  "today {current:amt} RON."},
    "C_LOWER_ROUNDED_ZERO": {"it": "Più basso: la formula dà {before_round:amt} RON, arrotondati per difetto a 0; oggi "
                                   "{current:amt} RON.",
                             "en": "Lower: the formula gives {before_round:amt} RON, rounded down to 0; today "
                                   "{current:amt} RON."},
    "C_LOWER_CERVED_CAP": {"it": "Più basso: fermato al fido suggerito Cerved ({cerved_limit:amt} RON); la formula dà "
                                 "{after_coef:amt} RON; il fido di oggi è {current:amt} RON.",
                           "en": "Lower: held at the Cerved suggested limit ({cerved_limit:amt} RON); the formula gives "
                                 "{after_coef:amt} RON; today's limit is {current:amt} RON."},
    "C_LOWER_MINIMUM_CAPPED": {"it": "Più basso: la formula dà {after_coef:amt} RON; il minimo di {min_limit:amt} RON "
                                     "supererebbe il fido suggerito Cerved, quindi il fido è il valore Cerved "
                                     "({cerved_limit:amt} RON); il fido di oggi è {current:amt} RON.",
                               "en": "Lower: the formula gives {after_coef:amt} RON; the {min_limit:amt} RON minimum "
                                     "would be above the Cerved suggested limit, so the limit is the Cerved value "
                                     "({cerved_limit:amt} RON); today's limit is {current:amt} RON."},
    "C_LOWER_ROUNDED_CAPPED": {"it": "Più basso: la formula dà {after_coef:amt} RON; l'arrotondamento supererebbe il "
                                     "fido suggerito Cerved, quindi il fido è il valore Cerved ({cerved_limit:amt} RON); "
                                     "il fido di oggi è {current:amt} RON.",
                               "en": "Lower: the formula gives {after_coef:amt} RON; rounding up would be above the "
                                     "Cerved suggested limit, so the limit is the Cerved value ({cerved_limit:amt} "
                                     "RON); today's limit is {current:amt} RON."},
    "C_LOWER_MINIMUM": {"it": "Più basso: la formula dà {formula:amt} RON, sotto il minimo, quindi si applica il fido "
                              "minimo di {min_limit:amt} RON; il fido di oggi è {current:amt} RON.",
                        "en": "Lower: the formula gives {formula:amt} RON, below the minimum, so the {min_limit:amt} "
                              "RON minimum limit applies; today's limit is {current:amt} RON."},
    "C_LOWER_CAUTION": {"it": "Più basso: score Cerved Cautela (coefficiente di rischio {coefficient:num}): la formula "
                              "dà {formula:amt} RON; il fido di oggi è {current:amt} RON.",
                        "en": "Lower: Cerved score Caution (risk factor {coefficient:num}): the formula gives "
                              "{formula:amt} RON; today's limit is {current:amt} RON."},
    "C_LOWER_NOT_IN_CERVED": {"it": "Più basso: non in Cerved (coefficiente di rischio {coefficient:num}): la formula dà "
                                    "{formula:amt} RON; il fido di oggi è {current:amt} RON.",
                              "en": "Lower: not in Cerved (risk factor {coefficient:num}): the formula gives "
                                    "{formula:amt} RON; today's limit is {current:amt} RON."},
    "C_LOWER_COEF": {"it": "Più basso: coefficiente di rischio {coefficient:num}: la formula dà {formula:amt} RON; il "
                           "fido di oggi è {current:amt} RON.",
                     "en": "Lower: risk factor {coefficient:num}: the formula gives {formula:amt} RON; today's limit "
                           "is {current:amt} RON."},
    "C_HIGHER_BONUS": {"it": "Più alto grazie al bonus di pagamento ({behaviour_pct:spct}, ritardo {delay:sdd} giorni): "
                             "senza bonus sarebbe {no_behaviour:amt} RON, con il bonus {proposed:amt} RON; il fido di "
                             "oggi è {current:amt} RON.",
                       "en": "Higher because of the payment bonus ({behaviour_pct:spct}, delay {delay:sdd} days): "
                             "without the bonus it would be {no_behaviour:amt} RON, with it {proposed:amt} RON; "
                             "today's limit is {current:amt} RON."},
    "C_LOWER_MALUS": {"it": "Più basso per il malus di pagamento ({behaviour_pct:spct}, ritardo {delay:sdd} giorni oltre "
                            "i termini): senza malus sarebbe {no_behaviour:amt} RON, con il malus {proposed:amt} RON; "
                            "il fido di oggi è {current:amt} RON.",
                      "en": "Lower because of the payment malus ({behaviour_pct:spct}, delay {delay:sdd} days past "
                            "the terms): without the malus it would be {no_behaviour:amt} RON, with it "
                            "{proposed:amt} RON; today's limit is {current:amt} RON."},
    "C_HIGHER_AGE": {"it": "Più alto: cliente attivo da {age:dd} mesi, il fatturato {turnover:amt} RON conta su {months:dd} "
                           "mesi ({monthly:amt} RON al mese); la formula dà {formula:amt} RON; il fido di oggi è "
                           "{current:amt} RON.",
                     "en": "Higher: customer active for {age:dd} months, its turnover {turnover:amt} RON counts over "
                           "{months:dd} months ({monthly:amt} RON a month); the formula gives {formula:amt} RON; "
                           "today's limit is {current:amt} RON."},
    "C_LOWER_AGE": {"it": "Più basso: anche con il fatturato diviso per {months:dd} mesi di attività ({monthly:amt} RON al "
                          "mese) la formula dà {formula:amt} RON; il fido di oggi è {current:amt} RON.",
                    "en": "Lower: even with the turnover divided by {months:dd} months active ({monthly:amt} RON a "
                          "month) the formula gives {formula:amt} RON; today's limit is {current:amt} RON."},
    "C_LOWER_NEED": {"it": "Più basso: per questo fatturato e questi giorni di pagamento la formula dà {formula:amt} "
                           "RON; il fido di oggi è {current:amt} RON.",
                     "en": "Lower: for this turnover and payment pace the formula gives {formula:amt} RON; today's "
                           "limit is {current:amt} RON."},
}

# ---------------------------------------------------------------------------
# Step by step (explain.steps): label = "Passo" column, calc = "Calcolo" column
# ---------------------------------------------------------------------------
STEP_TEXTS = {
    "S_INTERCOMPANY": {"it": {"label": "Intercompany", "calc": "Cliente {code} escluso dalla simulazione"},
                       "en": {"label": "Intercompany", "calc": "Customer {code} excluded from the simulation"}},
    "S_TURNOVER": {"it": {"label": "Fatturato 12 mesi", "calc": "Da Check fidi (CreditBoard), colonna Turnover 12 months"},
                   "en": {"label": "Turnover 12 months", "calc": "From Check fidi (CreditBoard), column Turnover 12 months"}},
    "S_DAYS_MEASURED": {"it": {"label": "Giorni di pagamento misurati",
                               "calc": "Mediana ponderata per importo di {n:days} fatture AR124 (ultimi {window} mesi)"},
                        "en": {"label": "Measured payment days",
                               "calc": "Amount-weighted median of {n:days} AR124 invoices (last {window} months)"}},
    "S_DAYS_TERMS": {"it": {"label": "Giorni di pagamento", "calc": "Nessuna fattura utile: si usano i termini contrattuali"},
                     "en": {"label": "Payment days", "calc": "No usable invoices: contract terms used"}},
    "S_DAYS_CONTRACTUAL": {"it": {"label": "Giorni di pagamento",
                                  "calc": "Bisogno (M1) sui termini contrattuali (parametro), non sui giorni misurati"},
                           "en": {"label": "Payment days",
                                  "calc": "Need (M1) on the contractual terms (parameter), not on measured days"}},
    "S_DAYS_FALLBACK": {"it": {"label": "Giorni di pagamento", "calc": "Nessuna fattura né termini: {fallback} giorni"},
                        "en": {"label": "Payment days", "calc": "No invoices and no terms: {fallback} days"}},
    "S_TERMS": {"it": {"label": "Termini contrattuali", "calc": "Mediana di (scadenza − data fattura)"},
                "en": {"label": "Contract terms", "calc": "Median of (due date − invoice date)"}},
    "S_DAYS_MIN": {"it": {"label": "Minimo giorni", "calc": "{raw:days} giorni portati al minimo di {min_days}"},
                   "en": {"label": "Minimum days", "calc": "{raw:days} days raised to the minimum of {min_days}"}},
    "S_DAYS_CAPPED": {"it": {"label": "Massimo giorni (termini + {extra})",
                             "calc": "Misurati {raw:days}; la formula ne conta al massimo {terms:days} + {extra}"},
                      "en": {"label": "Maximum days (terms + {extra})",
                             "calc": "Measured {raw:days}; the formula counts at most {terms:days} + {extra}"}},
    "S_DAYS_USED": {"it": {"label": "Giorni usati", "calc": "Giorni usati nel calcolo"},
                    "en": {"label": "Days used", "calc": "Days used in the calculation"}},
    "S_AGE_NEW": {"it": {"label": "Anzianità: cliente nuovo",
                         "calc": "Dal {first} ({src}; {age:dd} mesi, sotto {new}): fatturato {turnover:amt} ÷ "
                                 "{months:dd} mesi di attività; confermare con la stima commerciale"},
                  "en": {"label": "Customer age: new",
                         "calc": "Since {first} ({src}; {age:dd} months, under {new}): turnover {turnover:amt} ÷ "
                                 "{months:dd} months active; confirm with the sales estimate"}},
    "S_AGE_YOUNG": {"it": {"label": "Anzianità: cliente giovane",
                           "calc": "Dal {first} ({src}; {age:dd} mesi, sotto {consolidated}): fatturato "
                                   "{turnover:amt} ÷ {months:dd} mesi di attività"},
                    "en": {"label": "Customer age: young",
                           "calc": "Since {first} ({src}; {age:dd} months, under {consolidated}): turnover "
                                   "{turnover:amt} ÷ {months:dd} months active"}},
    "S_AGE_CONSOLIDATED": {"it": {"label": "Anzianità: cliente consolidato",
                                  "calc": "Dal {first} ({src}; {age:dd} mesi): fatturato {turnover:amt} ÷ 12"},
                           "en": {"label": "Customer age: consolidated",
                                  "calc": "Since {first} ({src}; {age:dd} months): turnover {turnover:amt} ÷ 12"}},
    "S_AGE_CENSORED": {"it": {"label": "Anzianità: cliente consolidato (almeno)",
                              "calc": "Prima fattura {first} all'inizio del file AR124 (dal {ar_start}): il cliente può "
                                      "aver comprato prima, anzianità ≥ {age:dd} mesi → consolidato, fatturato "
                                      "{turnover:amt} ÷ 12"},
                       "en": {"label": "Customer age: consolidated (at least)",
                              "calc": "First invoice {first} at the start of the AR124 file (from {ar_start}): the "
                                      "customer may have bought before, age ≥ {age:dd} months → consolidated, turnover "
                                      "{turnover:amt} ÷ 12"}},
    "S_AGE_NO_HISTORY": {"it": {"label": "Anzianità: nessuno storico",
                                "calc": "Nessuna data di apertura in MD105 e nessuna fattura in AR124: fatturato {turnover:amt} ÷ 12, nessun bonus/malus"},
                         "en": {"label": "Customer age: no history",
                                "calc": "No opening date in MD105 and no invoice in AR124: turnover {turnover:amt} ÷ 12, no bonus/malus"}},
    "S_M1": {"it": {"label": "Bisogno (M1)",
                    "calc": "{turnover:amt} / {months:dd} × {days:days} / 30 × (1 + {buffer:pct})"},
             "en": {"label": "Need (M1)",
                    "calc": "{turnover:amt} / {months:dd} × {days:days} / 30 × (1 + {buffer:pct})"}},
    "S_BASE": {"it": {"label": "Fido base", "calc": "moltiplicatore {multiplier:num} × {m1:amt}"},
               "en": {"label": "Base limit", "calc": "multiplier {multiplier:num} × {m1:amt}"}},
    "S_COEF": {"it": {"label": "Coefficiente di rischio", "calc": "{base:amt} × {coefficient:num} (score: {bucket})"},
               "en": {"label": "Risk factor", "calc": "{base:amt} × {coefficient:num} (score: {bucket})"}},
    "S_BEHAVIOUR_BONUS": {"it": {"label": "Comportamento di pagamento: bonus",
                                 "calc": "Ritardo {delay:sdd} gg (misurati {measured:dd} − termini {terms:dd}) ≤ 0: "
                                         "{before:amt} × (1 + {pct_abs:pct})"},
                          "en": {"label": "Payment behaviour: bonus",
                                 "calc": "Delay {delay:sdd} days (measured {measured:dd} − terms {terms:dd}) ≤ 0: "
                                         "{before:amt} × (1 + {pct_abs:pct})"}},
    "S_BEHAVIOUR_TOLERANCE": {"it": {"label": "Comportamento di pagamento: tolleranza",
                                     "calc": "Ritardo {delay:sdd} gg entro {tolerance} gg: nessun bonus né malus"},
                              "en": {"label": "Payment behaviour: tolerance",
                                     "calc": "Delay {delay:sdd} days within {tolerance} days: no bonus, no malus"}},
    "S_BEHAVIOUR_MALUS": {"it": {"label": "Comportamento di pagamento: malus",
                                 "calc": "Ritardo {delay:sdd} gg (misurati {measured:dd} − termini {terms:dd}), oltre "
                                         "{tolerance} gg (malus pieno da {full} gg): {before:amt} × (1 − {pct_abs:pct})"},
                          "en": {"label": "Payment behaviour: malus",
                                 "calc": "Delay {delay:sdd} days (measured {measured:dd} − terms {terms:dd}), beyond "
                                         "{tolerance} days (full malus from {full} days): {before:amt} × (1 − {pct_abs:pct})"}},
    "S_BEHAVIOUR_NEW": {"it": {"label": "Comportamento di pagamento: cliente nuovo",
                               "calc": "Cliente nuovo (meno di {new} mesi) o senza storico: nessun bonus né malus"},
                        "en": {"label": "Payment behaviour: new customer",
                               "calc": "New customer (under {new} months) or no history: no bonus, no malus"}},
    "S_BEHAVIOUR_FEW": {"it": {"label": "Comportamento di pagamento: poche fatture",
                               "calc": "{n:days} fatture già scadute (minimo {min_invoices}): nessun bonus né malus"},
                        "en": {"label": "Payment behaviour: too few invoices",
                               "calc": "{n:days} invoices already due (minimum {min_invoices}): no bonus, no malus"}},
    "S_BEHAVIOUR_NONE": {"it": {"label": "Comportamento di pagamento",
                                "calc": "Nessun giorno misurato da AR124: nessun bonus né malus"},
                         "en": {"label": "Payment behaviour",
                                "calc": "No measured days from AR124: no bonus, no malus"}},
    "S_CEILING_DISABLED": {"it": {"label": "Tetto Cerved", "calc": "Tetto disattivato"},
                           "en": {"label": "Cerved ceiling", "calc": "Ceiling switched off"}},
    "S_NO_CEILING": {"it": {"label": "Tetto Cerved", "calc": "Nessun fido suggerito Cerved"},
                     "en": {"label": "Cerved ceiling", "calc": "No Cerved suggested limit"}},
    "S_CEILING_INVALID": {"it": {"label": "Tetto Cerved", "calc": "Fido suggerito {orig:amt} {currency} non utilizzabile: nessun tetto"},
                          "en": {"label": "Cerved ceiling", "calc": "Suggested limit {orig:amt} {currency} not usable: no ceiling"}},
    "S_CEILING_BINDS": {"it": {"label": "Tetto Cerved", "calc": "min({before:amt}; {ceiling:amt}) → limitato dal fido suggerito"},
                        "en": {"label": "Cerved ceiling", "calc": "min({before:amt}; {ceiling:amt}) → held at the suggested limit"}},
    "S_CEILING_NOT_BINDING": {"it": {"label": "Tetto Cerved", "calc": "Fido suggerito {ceiling:amt}: non limita"},
                              "en": {"label": "Cerved ceiling", "calc": "Suggested limit {ceiling:amt}: not binding"}},
    "S_ZERO_SPECIAL": {"it": {"label": "Classe speciale", "calc": "Classe {risk_class}: fido zero"},
                       "en": {"label": "Special class", "calc": "Class {risk_class}: zero limit"}},
    "S_ZERO_NO_TURNOVER": {"it": {"label": "Nessun fatturato", "calc": "Fatturato 12 mesi ≤ 0: fido zero"},
                           "en": {"label": "No turnover", "calc": "Turnover 12 months ≤ 0: zero limit"}},
    "S_ROUND_UP": {"it": {"label": "Arrotondamento", "calc": "{before:amt} per eccesso a multipli di {step:amt}"},
                   "en": {"label": "Rounding", "calc": "{before:amt} rounded up to multiples of {step:amt}"}},
    "S_ROUND_DOWN": {"it": {"label": "Arrotondamento", "calc": "{before:amt} per difetto a multipli di {step:amt}"},
                     "en": {"label": "Rounding", "calc": "{before:amt} rounded down to multiples of {step:amt}"}},
    "S_MINIMUM": {"it": {"label": "Minimo", "calc": "{before:amt} portato al minimo di {min_limit:amt}"},
                  "en": {"label": "Minimum", "calc": "{before:amt} raised to the minimum of {min_limit:amt}"}},
    "S_HARD_CAP": {"it": {"label": "Tetto Cerved rigido",
                          "calc": "Mai sopra il fido suggerito {ceiling:amt}: {before:amt} → {final:amt} (RON interi)"},
                   "en": {"label": "Hard Cerved ceiling",
                          "calc": "Never above the suggested limit {ceiling:amt}: {before:amt} → {final:amt} (whole RON)"}},
    "S_PROPOSED": {"it": {"label": "Fido proposto", "calc": ""},
                   "en": {"label": "Proposed limit", "calc": ""}},
    "S_CURRENT": {"it": {"label": "Fido attuale", "calc": "Differenza {diff:amt} ({diff_pct:pct})"},
                  "en": {"label": "Current limit", "calc": "Difference {diff:amt} ({diff_pct:pct})"}},
}

# ---------------------------------------------------------------------------
# Data-quality findings (loaders.Finding.code). Values: count, plus details.
# ---------------------------------------------------------------------------
DQ_TEXTS = {
    "AR_TOTAL_ROWS_DROPPED": {"it": "AR124: {count} righe di totale scartate",
                              "en": "AR124: {count} total rows dropped"},
    "AR_NO_INVOICE_DATE": {"it": "AR124: {count} righe senza data fattura (ignorate)",
                           "en": "AR124: {count} rows without invoice date (ignored)"},
    "CF_NO_CODE": {"it": "Check fidi: {count} righe senza codice (scartate)",
                   "en": "Check fidi: {count} rows without code (dropped)"},
    "CF_DUP_CODE": {"it": "Check fidi: {count} codici duplicati (tenuta la prima riga)",
                    "en": "Check fidi: {count} duplicated codes (first row kept)"},
    "CF_LIMIT_BLANK": {"it": "Check fidi: {count} clienti con fido vuoto (letto come 0)",
                       "en": "Check fidi: {count} customers with blank limit (read as 0)"},
    "CV_NO_CODE": {"it": "Cerved: {count} righe senza RIFERIMENTO (abbinabili solo per IVA)",
                   "en": "Cerved: {count} rows without RIFERIMENTO (VAT match only)"},
    "CV_DUP_CODE": {"it": "Cerved: {count} codici RIFERIMENTO duplicati",
                    "en": "Cerved: {count} duplicated RIFERIMENTO codes"},
    "CV_EUR_LIMIT": {"it": "Cerved: {count} fidi suggeriti in EUR, convertiti in RON al cambio",
                     "en": "Cerved: {count} suggested limits in EUR, converted to RON"},
    "CV_NO_CURRENCY": {"it": "Cerved: {count} fidi suggeriti senza valuta (letti come RON)",
                       "en": "Cerved: {count} suggested limits without currency (read as RON)"},
    "CV_OTHER_CURRENCY": {"it": "Cerved: {count} fidi suggeriti in un'altra valuta ({currencies}): nessun tetto Cerved",
                          "en": "Cerved: {count} suggested limits in another currency ({currencies}): no Cerved ceiling"},
    "CV_NEGATIVE_LIMIT": {"it": "Cerved: {count} fidi suggeriti negativi (non validi): nessun tetto Cerved",
                          "en": "Cerved: {count} negative suggested limits (invalid): no Cerved ceiling"},
    "MATCH_VAT_CONFLICT": {"it": "{count} clienti con codice Cerved ma partita IVA diversa: riga Cerved non usata "
                                 "({rematched_by_vat} riabbinati per IVA, {not_in_cerved} non in Cerved)",
                           "en": "{count} customers with a Cerved code but a different VAT number: Cerved row not used "
                                 "({rematched_by_vat} re-matched by VAT, {not_in_cerved} not in Cerved)"},
    "CF_MULTI_COMPANY": {"it": "Check fidi: più società nel file; tenuta la società {kept}, scartate {count} righe",
                         "en": "Check fidi: several companies in the file; company {kept} kept, {count} rows dropped"},
    "COLUMN_MISSING": {"it": "Colonne facoltative mancanti ({kind}): {count}; funzioni disattivate",
                       "en": "Optional columns missing ({kind}): {count}; features switched off"},
    "BAD_NUMBERS": {"it": "{kind}: {count} importi non leggibili come numeri (letti come 0 / vuoti)",
                    "en": "{kind}: {count} amounts that cannot be read as numbers (read as 0 / blank)"},
    "AMBIGUOUS_NUMBERS": {"it": "{kind}: {count} importi con separatore ambiguo (es. 12.500), letti come migliaia",
                          "en": "{kind}: {count} amounts with an ambiguous separator (e.g. 12.500), read as thousands"},
    "BAD_DATES": {"it": "{kind}: {count} date non leggibili (lette come vuote)",
                  "en": "{kind}: {count} dates that cannot be read (read as blank)"},
    "FILE_EMPTY": {"it": "File senza righe di dati ({kind})", "en": "File with no data rows ({kind})"},
    "CV_UNKNOWN_SCORE": {"it": "Cerved: {count} score non riconosciuti (trattati come non in Cerved)",
                         "en": "Cerved: {count} unknown scores (treated as not in Cerved)"},
    "CV_UNMATCHED": {"it": "Cerved: {count} righe non abbinate a nessun cliente attivo",
                     "en": "Cerved: {count} rows not matched to any active customer"},
    "MATCH_VAT_DIFFERS": {"it": "{count} clienti abbinati per codice con partita IVA diversa",
                          "en": "{count} customers matched by code with a different VAT number"},
    "MISSING_CHECKFIDI": {"it": "Manca il file Check fidi: nessun calcolo possibile",
                          "en": "Check fidi file missing: nothing can be calculated"},
    "MISSING_CERVED": {"it": "Manca il file Cerved: niente score, tetto Cerved e plausibilità (tutti 'non in Cerved')",
                       "en": "Cerved file missing: no score, Cerved cap or plausibility (all 'not in Cerved')"},
    "MISSING_AR124": {"it": "Manca il file AR124: giorni di pagamento = valore di default per tutti",
                      "en": "AR124 file missing: payment days = default value for everyone"},
    "FILE_INVALID": {"it": "File non utilizzabile: {message}", "en": "File not usable: {message}"},
    "AR_SHORT_HISTORY": {"it": "AR124 copre {months:dd} mesi e manca l'anagrafica MD105: l'anzianità viene dalla prima "
                               "fattura (chi ha la prima fattura nei primi 31 giorni del file è trattato come "
                               "consolidato), e un cliente la cui prima fattura cade in questo periodo può essere un "
                               "acquirente occasionale e non un cliente nuovo; caricare MD105 per anzianità affidabili, "
                               "oppure un AR124 di almeno {needed} mesi",
                         "en": "AR124 covers {months:dd} months and the customer master MD105 is missing: the age comes "
                               "from the first invoice (a first invoice in the file's first 31 days counts as "
                               "consolidated), and a customer whose first invoice falls in this period may be "
                               "an occasional buyer rather than a new one; load MD105 for reliable ages, or an AR124 "
                               "covering at least {needed} months"},
    "AGE_INVOICE_BEFORE_OPENING": {"it": "{count} clienti con la prima fattura AR124 più di 31 giorni prima della data di "
                                         "apertura MD105 (codice ricreato): si usa la data più vecchia",
                                   "en": "{count} customers whose first AR124 invoice is more than 31 days before the "
                                         "MD105 opening date (code re-created): the earlier date is used"},
    "MD_CUSTOMER_MISSING": {"it": "{count} clienti non presenti in MD105: anzianità dalla prima fattura AR124",
                            "en": "{count} customers not in MD105: age from the first AR124 invoice"},
    "MD_NO_CODE": {"it": "MD105: {count} righe senza codice cliente (scartate)",
                   "en": "MD105: {count} rows without customer code (dropped)"},
    "MD_DUP_CODE": {"it": "MD105: {count} codici ripetuti (tenuta la data di apertura più vecchia)",
                    "en": "MD105: {count} repeated codes (earliest opening date kept)"},
    "FILE_DUPLICATE_KIND": {"it": "Due file dello stesso tipo ({kind}): tenuto {kept}",
                            "en": "Two files of the same kind ({kind}): kept {kept}"},
}

UNAVAILABLE_TEXTS = {
    "everything": {"it": "tutto", "en": "everything"},
    "cerved_score": {"it": "score Cerved", "en": "Cerved score"},
    "cerved_ceiling": {"it": "tetto Cerved", "en": "Cerved cap"},
    "plausibility": {"it": "controllo di plausibilità", "en": "plausibility check"},
    "payment_days_measured": {"it": "giorni di pagamento misurati", "en": "measured payment days"},
    "contract_terms": {"it": "termini contrattuali", "en": "contract terms"},
    "default_reference_date": {"it": "data di riferimento automatica", "en": "automatic reference date"},
    "vat_matching": {"it": "abbinamento Cerved per partita IVA", "en": "Cerved matching by VAT number"},
    "currency": {"it": "valuta del fido Cerved (tutti letti come RON)", "en": "Cerved limit currency (all read as RON)"},
    "reliability_class": {"it": "classe di affidabilità Cerved", "en": "Cerved reliability class"},
}

# ---------------------------------------------------------------------------
# KPI labels (kpi.KPI_KEYS)
# ---------------------------------------------------------------------------
KPI_TEXTS = {
    "n_active": {"it": "Clienti attivi", "en": "Active customers"},
    "n_scope": {"it": "Clienti nel perimetro del controllo ordini", "en": "Customers in the order-check scope"},
    "limits_current_active": {"it": "Fidi attuali (attivi)", "en": "Current limits (active)"},
    "limits_proposed_active": {"it": "Fidi proposti (attivi)", "en": "Proposed limits (active)"},
    "exposure_active": {"it": "Esposizione (attivi)", "en": "Exposure (active)"},
    "limits_current_scope": {"it": "Fidi attuali (perimetro)", "en": "Current limits (scope)"},
    "limits_proposed_scope": {"it": "Fidi proposti (perimetro)", "en": "Proposed limits (scope)"},
    "exposure_scope": {"it": "Esposizione (perimetro)", "en": "Exposure (scope)"},
    "over_new_n": {"it": "Clienti oltre fido nuovo", "en": "Customers over new limit"},
    "over_current_n": {"it": "Clienti oltre fido attuale", "en": "Customers over current limit"},
    "over_new_positive_n": {"it": "Oltre un fido positivo (nuovo)", "en": "Over a positive limit (new)"},
    "over_new_zero_n": {"it": "Oltre fido a fido 0 per regola (nuovo)", "en": "Over limit at limit 0 by rule (new)"},
    "over_current_positive_n": {"it": "Oltre un fido positivo (attuale)", "en": "Over a positive limit (current)"},
    "over_current_zero_n": {"it": "Oltre fido a fido 0 (attuale)", "en": "Over limit at limit 0 (current)"},
    "excess_new": {"it": "Sforamento sul fido nuovo", "en": "Excess over new limits"},
    "excess_current": {"it": "Sforamento sul fido attuale", "en": "Excess over current limits"},
    "higher_n": {"it": "Fido più alto", "en": "Higher limit"},
    "lower_n": {"it": "Fido più basso", "en": "Lower limit"},
    "equal_n": {"it": "Fido uguale", "en": "Same limit"},
    "zero_with_turnover_n_active": {"it": "Fido zero con fatturato (non speciali)",
                                    "en": "Zero limit with turnover (not special)"},
    "orders_over_new_n": {"it": "Con ordini aperti oltre fido nuovo", "en": "With open orders over new limit"},
    "orders_over_current_n": {"it": "Con ordini aperti oltre fido attuale",
                              "en": "With open orders over current limit"},
    "plausibility_n": {"it": "Clienti in revisione (plausibilità)", "en": "Customers to review (plausibility)"},
    "plausibility_exposure": {"it": "Esposizione in revisione", "en": "Exposure to review"},
    "in_cerved_n_active": {"it": "Clienti attivi in Cerved", "en": "Active customers in Cerved"},
    "in_cerved_exposure_share_active": {"it": "Quota esposizione in Cerved", "en": "Exposure share in Cerved"},
    "approval_n": {"it": "Variazioni da approvare", "en": "Changes needing approval"},
    "approval_tier1_n": {"it": "Da approvare – Tier 1", "en": "Approval – Tier 1"},
    "approval_tier2_n": {"it": "Da approvare – Tier 2", "en": "Approval – Tier 2"},
    "approval_tier3_n": {"it": "Da approvare – Tier 3", "en": "Approval – Tier 3"},
    "days_capped_n": {"it": "Giorni limitati (termini + margine)", "en": "Days capped (terms + margin)"},
    "behaviour_bonus_n": {"it": "Clienti con bonus di pagamento (perimetro)",
                          "en": "Customers with a payment bonus (scope)"},
    "behaviour_malus_n": {"it": "Clienti con malus di pagamento (perimetro)",
                          "en": "Customers with a payment malus (scope)"},
    "behaviour_tolerance_n": {"it": "Clienti nella tolleranza, né bonus né malus (perimetro)",
                              "en": "Customers within the tolerance, no bonus or malus (scope)"},
    "behaviour_no_history_n": {"it": "Clienti senza giorni misurati (perimetro)",
                               "en": "Customers without measured days (scope)"},
    "behaviour_effect_active": {"it": "Effetto netto bonus/malus sui fidi (attivi)",
                                "en": "Net bonus/malus effect on limits (active)"},
    "behaviour_effect_scope": {"it": "Effetto netto bonus/malus sui fidi (perimetro)",
                               "en": "Net bonus/malus effect on limits (scope)"},
    "behaviour_new_n": {"it": "Senza bonus/malus perché nuovi (perimetro)",
                        "en": "No bonus/malus because new (scope)"},
    "behaviour_few_n": {"it": "Senza bonus/malus per poche fatture scadute (perimetro)",
                        "en": "No bonus/malus for too few invoices due (scope)"},
}

# Payment-behaviour band (engine.behaviour_pct and the v3.2 gates)
BAND_TEXTS = {
    "NEW_CUSTOMER": {"it": "Cliente nuovo (nessun bonus/malus)", "en": "New customer (no bonus/malus)"},
    "FEW_INVOICES": {"it": "Poche fatture scadute (nessun bonus/malus)", "en": "Too few invoices due (no bonus/malus)"},
    "BONUS": {"it": "Bonus (in tempo o in anticipo)", "en": "Bonus (on time or early)"},
    "TOLERANCE": {"it": "Tolleranza (nessun bonus né malus)", "en": "Tolerance (no bonus, no malus)"},
    "MALUS": {"it": "Malus (ritardo)", "en": "Malus (late)"},
    "NONE": {"it": "Nessun giorno misurato", "en": "No measured days"},
}
# Source of the customer age (engine.customer_history): short, used inside sentences and in Excel
AGE_SOURCE_TEXTS = {
    "md105": {"it": "apertura conto MD105", "en": "account opened, MD105"},
    "ar124_earlier": {"it": "prima fattura AR124, precedente all'apertura MD105",
                      "en": "first AR124 invoice, earlier than the MD105 opening"},
    "ar124": {"it": "prima fattura AR124", "en": "first AR124 invoice"},
}

# Customer-age band (engine.age_band, v3.2)
AGE_BAND_TEXTS = {
    "NEW": {"it": "Nuovo", "en": "New"},
    "YOUNG": {"it": "Giovane", "en": "Young"},
    "CONSOLIDATED": {"it": "Consolidato", "en": "Consolidated"},
    "NO_HISTORY": {"it": "Nessuno storico", "en": "No history"},
}
for _b, _lab in (("new", AGE_BAND_TEXTS["NEW"]), ("young", AGE_BAND_TEXTS["YOUNG"]),
                 ("consolidated", AGE_BAND_TEXTS["CONSOLIDATED"]), ("no_history", AGE_BAND_TEXTS["NO_HISTORY"])):
    KPI_TEXTS[f"age_{_b}_n"] = {"it": f"Clienti per anzianità – {_lab['it']} (perimetro)",
                                "en": f"Customers by age – {_lab['en']} (scope)"}
for _b, _lab in (("reliable", SCORE_TEXTS["AFFIDABILE"]), ("caution", SCORE_TEXTS["CAUTELA"]),
                 ("max_caution", SCORE_TEXTS["MASSIMA CAUTELA"]), ("not_in_cerved", SCORE_TEXTS["NONE"])):
    KPI_TEXTS[f"n_{_b}"] = {"it": f"Clienti – {_lab['it']}", "en": f"Customers – {_lab['en']}"}
    KPI_TEXTS[f"over_new_n_{_b}"] = {"it": f"Oltre fido nuovo – {_lab['it']}", "en": f"Over new limit – {_lab['en']}"}
    KPI_TEXTS[f"over_current_n_{_b}"] = {"it": f"Oltre fido attuale – {_lab['it']}",
                                         "en": f"Over current limit – {_lab['en']}"}

# ---------------------------------------------------------------------------
# Friendly column names (export, tables). Keys = engine.simulate columns.
# ---------------------------------------------------------------------------
COLUMN_TEXTS = {
    "code": ("Codice", "Code"), "name": ("Nome", "Name"), "risk_class": ("Classe rischio", "Risk class"),
    "vat": ("Partita IVA", "VAT"), "score_bucket": ("Score Cerved", "Cerved score"),
    "in_cerved": ("In Cerved", "In Cerved"), "match_method": ("Abbinamento Cerved", "Cerved match"),
    "cerved_limit_ron": ("Fido suggerito Cerved (RON interi)", "Cerved suggested limit (whole RON)"),
    "cerved_turnover": ("Fatturato totale Cerved", "Cerved total turnover"),
    "balance": ("Saldo", "Balance"), "overdue": ("Scaduto", "Overdue"), "ordered": ("Ordinato", "Ordered"),
    "delivered": ("Consegnato", "Delivered"), "exposure": ("Esposizione", "Exposure"),
    "turnover_12m": ("Fatturato 12 mesi", "Turnover 12 months"),
    "days_measured": ("Giorni misurati", "Measured days"), "days_terms": ("Termini (giorni)", "Terms (days)"),
    "days_used": ("Giorni usati", "Days used"), "days_capped": ("Giorni limitati", "Days capped"),
    "m1": ("Bisogno (M1)", "Need (M1)"), "base_limit": ("Fido base", "Base limit"),
    "coefficient": ("Coefficiente di rischio", "Risk factor"), "limit_after_coef": ("Dopo coefficiente di rischio", "After risk factor"),
    "ceiling": ("Tetto Cerved (RON interi)", "Cerved ceiling (whole RON)"), "limit_before_rounding": ("Prima dell'arrotondamento", "Before rounding"),
    "proposed_limit": ("Fido proposto", "Proposed limit"), "current_limit": ("Fido attuale", "Current limit"),
    "diff": ("Differenza", "Difference"), "diff_pct": ("Differenza %", "Difference %"),
    "direction": ("Variazione", "Change"),
    "in_scope": ("Nel perimetro controllo", "In order-check scope"),
    "is_exempt": ("Esente", "Exempt"), "is_special": ("Speciale", "Special"),
    "over_new": ("Oltre fido nuovo", "Over new limit"), "over_current": ("Oltre fido attuale", "Over current limit"),
    "excess_new": ("Sforamento nuovo", "Excess new"), "excess_current": ("Sforamento attuale", "Excess current"),
    "plausibility_ratio": ("Rapporto plausibilità", "Plausibility ratio"),
    "plausibility_flag": ("Revisione manuale", "Manual review"),
    "approval_needed": ("Serve approvazione", "Approval needed"), "tier": ("Livello approvazione", "Approval tier"),
    "reason": ("Perché questo fido", "Why this limit"), "why_change": ("Perché cambia", "Why it changes"),
    "reason_code": ("Codice motivo", "Reason code"), "change_code": ("Codice variazione", "Change code"),
    "delay_days": ("Ritardo vs termini (giorni)", "Delay vs terms (days)"),
    "behaviour_band": ("Comportamento di pagamento", "Payment behaviour"),
    "behaviour_pct": ("Bonus/malus %", "Bonus/malus %"),
    "limit_after_behaviour": ("Dopo bonus/malus", "After bonus/malus"),
    "proposed_limit_no_behaviour": ("Fido senza bonus/malus", "Limit without bonus/malus"),
    "behaviour_effect": ("Effetto bonus/malus", "Bonus/malus effect"),
    "first_invoice_date": ("Prima fattura AR124", "First AR124 invoice"),
    "opened_date": ("Apertura conto MD105", "Account opened (MD105)"),
    "age_start_date": ("Inizio anzianità", "Age start date"),
    "age_source": ("Fonte anzianità", "Age source"),
    "age_censored": ("Anzianità almeno (prima fattura a inizio AR124)", "Age at least (first invoice at AR124 start)"),
    "age_months": ("Anzianità (mesi)", "Age (months)"),
    "age_band": ("Fascia di anzianità", "Age band"),
    "months_active": ("Mesi di attività usati", "Months active used"),
    "monthly_revenue_used": ("Fatturato mensile usato", "Monthly revenue used"),
    "behaviour_invoices_n": ("Fatture già scadute (finestra)", "Invoices already due (window)"),
    "revenue_check_flag": ("Confermare fatturato con stima commerciale", "Confirm revenue with sales estimate"),
}

# Export sheet names / headers
EXPORT_TEXTS = {
    "sheet_customers": {"it": "Clienti", "en": "Customers"},
    "sheet_kpi": {"it": "KPI", "en": "KPIs"},
    "sheet_params": {"it": "Parametri", "en": "Parameters"},
    "col_kpi": {"it": "Indicatore", "en": "Indicator"},
    "col_value": {"it": "Valore", "en": "Value"},
    "col_param": {"it": "Parametro", "en": "Parameter"},
}

# Parameter labels/help: owned by the UI (keys = params.PARAM_META keys); filled at the end of
# this module from the UI copy deck (TEXTS), see PARAM_LABEL_KEYS.
PARAM_TEXTS: dict[str, dict[str, Any]] = {}


# ===========================================================================
# UI copy deck (UX.md section 6). TEXTS[key][lang]; the UI renders it with ``T``:
# plain ``str.format`` placeholders, numbers passed already formatted by the UI.
# A missing key renders as the key itself, so a hole is visible (and caught by tests).
# ===========================================================================
_DECK: list[tuple[str, str, str]] = [
    # --- 6.1 shell, navigation, common ---
    ("app_title", "Simulatore Fido", "Credit Limit Simulator"),
    ("app_subtitle", "SIAD Romania · società 42 · RON", "SIAD Romania · company 42 · RON"),
    ("lang_label", "Lingua", "Language"),
    ("nav_data", "Dati", "Data"),
    ("nav_results", "Risultati", "Results"),
    ("nav_customer", "Cliente", "Customer"),
    ("nav_lab", "Laboratorio", "Lab"),
    ("nav_rules", "Regole", "Rules"),
    ("badge_data_ok", "Dati: 3 file su 3", "Data: 3 of 3 files"),
    ("badge_data_partial", "Dati: mancano {n} file",
     "Data: {n} files missing"),
    ("badge_data_partial_1", "Dati: manca 1 file",
     "Data: 1 file missing"),
    ("badge_data_none", "Nessun dato caricato", "No data loaded"),
    ("badge_ref_date", "Data di riferimento {date}", "Reference date {date}"),
    ("badge_scn_default", "Formula: default v3.2", "Formula: v3.2 default"),
    ("badge_scn_modified", "Formula modificata ({n} parametri)", "Formula changed ({n} parameters)"),
    ("badge_scn_name", "Scenario «{name}»", "Scenario \"{name}\""),
    ("banner_scenario", "Stai guardando lo scenario «{name}»: {changes}.",
     "You are looking at scenario \"{name}\": {changes}."),
    ("scn_unsaved", "non salvato", "unsaved"),
    ("btn_reset_defaults", "Ripristina default v3.2", "Reset to v3.2 defaults"),
    ("btn_reset_help", "Riporta tutti i parametri alle regole v3.2. Salva prima lo scenario se vuoi tenerlo.",
     "Puts every parameter back to the v3.2 rules. Save the scenario first if you want to keep it."),
    ("go_data", "Vai alla pagina Dati", "Go to the Data page"),
    ("calculating", "Calcolo in corso...", "Calculating..."),
    ("loading_files", "Lettura dei file...", "Reading the files..."),
    ("yes", "Sì", "Yes"),
    ("no", "No", "No"),
    ("on", "Sì", "On"),
    ("off", "No", "Off"),
    ("ron", "RON", "RON"),
    ("days_unit", "gg", "days"),
    ("mln", "mln RON", "M RON"),
    ("vs_current", "rispetto all'attuale", "vs current"),
    ("vs_v3", "rispetto a v3.2", "vs v3.2"),
    ("not_applicable", "non si applica", "does not apply"),
    ("dash", "-", "-"),
    ("none_word", "nessuno", "none"),

    # --- 6.2 Data page ---
    ("data_title", "I dati sono completi e affidabili?", "Is the data complete and reliable?"),
    ("data_subtitle", "I file di partenza (tre obbligatori, più l'anagrafica MD105 opzionale), cosa contengono e cosa abbiamo controllato.",
     "The input files (three required, plus the optional customer master MD105), what they contain and what we checked."),
    ("file_checkfidi", "Check fidi (CreditBoard)", "Check fidi (CreditBoard)"),
    ("file_cerved", "Cerved Slim Report", "Cerved Slim Report"),
    ("file_ar124", "Fatture AR124 (JDE)", "AR124 invoices (JDE)"),
    ("file_checkfidi_role", "Clienti, esposizione, fido attuale, fatturato 12 mesi.",
     "Customers, exposure, current limit, 12-month turnover."),
    ("file_cerved_role", "Score, fido suggerito e fatturato totale del cliente.",
     "Score, suggested limit and the customer's total turnover."),
    ("file_ar124_role", "Fatture: da qui termini contrattuali e giorni di pagamento misurati (bonus/malus).",
     "Invoices: contractual terms and measured payment days (bonus/malus) come from here."),
    ("file_loaded", "Caricato", "Loaded"),
    ("file_missing", "Manca", "Missing"),
    ("file_rows", "{n} righe", "{n} rows"),
    ("file_uploaded", "caricato a mano", "uploaded"),
    ("upload_title", "Carica o sostituisci i file", "Upload or replace files"),
    ("upload_label", "Trascina qui i file (anche tutti e tre insieme)",
     "Drop the files here (all three together is fine)"),
    ("upload_help", "Trascina qui i file (Check fidi, Cerved, AR124 e, se c'è, MD105), anche tutti insieme: il tipo si riconosce dalle colonne, il nome non conta.",
     "Drop the files here (Check fidi, Cerved, AR124 and, if available, MD105), even all together: the type is recognised from its columns; the name does not matter."),
    ("upload_active", "File caricati a mano in uso: {names}", "Uploaded files in use: {names}"),
    ("btn_clear_uploads", "Rimuovi i file caricati", "Remove the uploaded files"),
    ("err_unrecognised", "«{name}» non sembra né Check fidi, né Cerved, né AR124: mancano le colonne attese.",
     "\"{name}\" does not look like Check fidi, Cerved or AR124: the expected columns are missing."),
    ("err_missing_cols", "«{name}» sembra un file {kind}, ma mancano le colonne: {cols}.",
     "\"{name}\" looks like a {kind} file, but these columns are missing: {cols}."),
    ("err_unreadable", "«{name}» non si riesce a leggere: deve essere un file Excel (.xlsx o .xls).",
     "\"{name}\" cannot be read: it must be an Excel file (.xlsx or .xls)."),
    ("err_duplicate_kind", "«{name}» è un secondo file {kind}: si usa «{kept}».",
     "\"{name}\" is a second {kind} file: \"{kept}\" is used."),
    ("data_population", "Clienti", "Customers"),
    ("m_rows_checkfidi", "Righe Check fidi", "Check fidi rows"),
    ("m_active", "Clienti attivi", "Active customers"),
    ("m_intercompany", "Intercompany esclusi", "Intercompany excluded"),
    ("m_scope", "Perimetro controllo ordini", "Order-check scope"),
    ("m_ref_date", "Data di riferimento", "Reference date"),
    ("help_rows_checkfidi", "Tutte le righe del file Check fidi, anche i clienti senza movimenti.",
     "Every row of the Check fidi file, customers without activity included."),
    ("help_active", "Saldo diverso da zero oppure fatturato negli ultimi 12 mesi. Intercompany esclusi.",
     "Balance not zero or turnover in the last 12 months. Intercompany excluded."),
    ("help_intercompany", "Società del gruppo SIAD: fuori dalla simulazione.",
     "SIAD group companies: left out of the simulation."),
    ("help_scope", "Clienti nel perimetro del controllo ordini: attivi, non intercompany, non in classi speciali né esenti. Solo loro contano come oltre fido.",
     "Customers in the order-check scope: active, not intercompany, no special or exempt class. Only they count as over limit."),
    ("help_ref_date", "La data a cui si misurano giorni di pagamento e scaduto. Di default l'ultima fattura AR124.",
     "The date payment days and overdue are measured at. By default the latest AR124 invoice."),
    ("data_matching", "Abbinamento con Cerved", "Matching with Cerved"),
    ("m_match_code", "Abbinati per codice", "Matched by code"),
    ("m_match_vat", "Abbinati per partita IVA", "Matched by VAT number"),
    ("m_match_none", "Non in Cerved", "Not in Cerved"),
    ("m_cerved_orphans", "Righe Cerved senza cliente", "Cerved rows with no customer"),
    ("help_match_code", "Codice cliente uguale al riferimento Cerved.", "Customer code equals the Cerved reference."),
    ("help_match_vat", "Codice non trovato, ma stessa partita IVA.", "Code not found, but same VAT number."),
    ("help_match_none", "Clienti attivi senza dati Cerved: ricevono il coefficiente di rischio \"non in Cerved\".",
     "Active customers without Cerved data: they get the \"not in Cerved\" risk factor."),
    ("help_cerved_orphans", "Righe Cerved che non corrispondono a nessun cliente attivo.",
     "Cerved rows that match no active customer."),
    ("data_cerved_share", "In Cerved: {n} clienti attivi, {pct} dell'esposizione.",
     "In Cerved: {n} active customers, {pct} of exposure."),
    ("data_quality", "Controlli di qualità", "Data quality checks"),
    ("dq_col_check", "Controllo", "Check"),
    ("dq_col_count", "Quanti", "Count"),
    ("dq_col_meaning", "Cosa significa", "What it means"),
    ("dq_details", "Vedi le righe interessate", "See the rows concerned"),
    ("dq_pick", "Controllo", "Check"),
    ("dq_examples", "Esempi: {list}", "Examples: {list}"),
    ("dq_all_ok", "Nessun problema trovato nei dati.", "No problems found in the data."),
    ("dq_c_code", "Codice", "Code"),
    ("dq_c_name", "Nome", "Name"),
    ("dq_c_vat", "Partita IVA", "VAT number"),
    ("dq_c_cv_name", "Nome in Cerved", "Name in Cerved"),
    ("dq_c_cv_vat", "Partita IVA in Cerved", "VAT number in Cerved"),
    ("dq_c_value", "Valore", "Value"),
    ("data_settings", "Impostazioni dei dati", "Data settings"),
    ("data_settings_help", "Scelte sui dati, non sulla formula: valgono per tutti gli scenari.",
     "Choices about the data, not the formula: they apply to every scenario."),
    ("p_ref_date", "Data di riferimento", "Reference date"),
    ("p_ref_date_help", "Di default l'ultima data fattura AR124.", "By default the latest AR124 invoice date."),
    ("p_window_months", "Finestra fatture (mesi)", "Invoice window (months)"),
    ("p_window_months_help", "Quanti mesi di fatture usare per i giorni di pagamento.",
     "How many months of invoices to use for payment days."),
    ("empty_data", "Carica i tre file (più MD105, consigliato) per iniziare. Basta Check fidi per un primo calcolo.",
     "Upload the three files (plus MD105, recommended) to start. Check fidi alone is enough for a first calculation."),

    # --- 6.3 missing-file impact ---
    ("missing_checkfidi_impact", "Senza Check fidi non si può calcolare nulla: mancano clienti, esposizione e fatturato.",
     "Without Check fidi nothing can be calculated: customers, exposure and turnover are missing."),
    ("missing_cerved_impact", "Cerved manca: tutti i clienti sono trattati come \"non in Cerved\" (coefficiente di rischio {coef}), nessun tetto Cerved, nessun controllo di plausibilità.",
     "Cerved is missing: every customer is treated as \"not in Cerved\" (risk factor {coef}), no Cerved ceiling, no plausibility check."),
    ("missing_ar124_impact", "AR124 manca: i giorni di pagamento sono {days} giorni per tutti.",
     "AR124 is missing: payment days are {days} days for everyone."),
    ("empty_results", "Nessun risultato: serve almeno il file Check fidi.",
     "No results yet: at least the Check fidi file is needed."),
    ("chart_needs_cerved", "Questo grafico richiede il file Cerved.", "This chart needs the Cerved file."),
    ("help_review_needs_cerved", "Il controllo di plausibilità usa il fatturato totale Cerved.",
     "The plausibility check uses the Cerved total turnover."),

    # --- 6.4 data-quality checks ---
    ("dq_total_rows", "Righe di totale scartate (AR124)", "Total rows skipped (AR124)"),
    ("dq_total_rows_m", "Righe \"Total ...\" di JDE: non sono fatture, non contano.",
     "JDE \"Total ...\" rows: not invoices, not counted."),
    ("dq_dup_codes", "Codici Cerved duplicati", "Duplicate Cerved codes"),
    ("dq_dup_codes_m", "Stesso codice due volte in Cerved: usiamo la riga con la stessa partita IVA, altrimenti la prima.",
     "Same code twice in Cerved: we use the row with the same VAT number, otherwise the first."),
    ("dq_dup_diff_company", "Codice Cerved su due aziende diverse", "Cerved code on two different companies"),
    ("dq_dup_diff_company_m", "Es. {examples}: da correggere in Cerved.", "E.g. {examples}: to be fixed in Cerved."),
    ("dq_vat_mismatch", "Codice uguale ma partita IVA diversa", "Same code but different VAT number"),
    ("dq_vat_mismatch_m", "Abbinati per codice, ma la partita IVA non coincide: controllare.",
     "Matched by code, but the VAT number differs: please check."),
    ("dq_no_ref", "Righe Cerved senza riferimento", "Cerved rows with no reference"),
    ("dq_no_ref_m", "Abbinabili solo per partita IVA.", "Can be matched only by VAT number."),
    ("dq_cerved_eur", "Fido Cerved in EUR", "Cerved limit in EUR"),
    ("dq_cerved_eur_m", "Convertito in RON al cambio {rate}.", "Converted to RON at {rate}."),
    ("dq_neg_turnover", "Fatturato 12 mesi negativo", "Negative 12-month turnover"),
    ("dq_neg_turnover_m", "Trattato come zero: fido 0.", "Treated as zero: limit 0."),
    ("dq_no_invoices", "Clienti attivi senza fatture nella finestra", "Active customers with no invoices in the window"),
    ("dq_no_invoices_m", "Giorni = termini contrattuali, o {days} giorni se mancano anche quelli.",
     "Days = contractual terms, or {days} days if those are missing too."),
    ("dq_no_current_limit", "Clienti attivi con fido attuale zero", "Active customers with current limit zero"),
    ("dq_no_current_limit_m", "Il confronto con l'attuale per loro è \"nuovo fido\".",
     "For them the comparison reads \"new limit\"."),
    ("dq_unmatched", "Righe Cerved senza cliente", "Cerved rows with no customer"),
    ("dq_unmatched_m", "Aziende in Cerved che non corrispondono a nessun cliente attivo: non usate.",
     "Companies in Cerved that match no active customer: not used."),
    ("dq_limit_blank", "Fido attuale vuoto in Check fidi", "Blank current limit in Check fidi"),
    ("dq_limit_blank_m", "Letto come 0.", "Read as 0."),
    ("dq_cf_no_code", "Righe Check fidi senza codice", "Check fidi rows without code"),
    ("dq_cf_no_code_m", "Scartate: senza codice non si può abbinare nulla.", "Dropped: without a code nothing can be matched."),
    ("dq_cf_dup_code", "Codici duplicati in Check fidi", "Duplicate codes in Check fidi"),
    ("dq_cf_dup_code_m", "Si tiene la prima riga.", "The first row is kept."),
    ("dq_no_currency", "Fido Cerved senza valuta", "Cerved limit without currency"),
    ("dq_no_currency_m", "Letto come RON.", "Read as RON."),
    ("dq_unknown_score", "Score Cerved non riconosciuto", "Unknown Cerved score"),
    ("dq_unknown_score_m", "Trattato come \"non in Cerved\".", "Treated as \"not in Cerved\"."),
    ("dq_vat_conflict", "Codice Cerved con partita IVA diversa", "Cerved code with a different VAT number"),
    ("dq_vat_conflict_m", "Stesso codice ma partita IVA diversa: la riga Cerved non si usa; si cerca per IVA ({rematched} trovati), altrimenti \"non in Cerved\" ({none}).",
     "Same code but different VAT number: the Cerved row is not used; the VAT number is tried instead ({rematched} found), otherwise \"not in Cerved\" ({none})."),
    ("dq_other_currency", "Fido Cerved in un'altra valuta", "Cerved limit in another currency"),
    ("dq_other_currency_m", "Valuta {currencies}: nessun tetto Cerved per questi clienti.", "Currency {currencies}: no Cerved ceiling for these customers."),
    ("dq_negative_limit", "Fido Cerved negativo", "Negative Cerved limit"),
    ("dq_negative_limit_m", "Valore non valido: nessun tetto Cerved per questi clienti.", "Invalid value: no Cerved ceiling for these customers."),
    ("dq_multi_company", "Più società in Check fidi", "Several companies in Check fidi"),
    ("dq_multi_company_m", "Tenuta solo la società {kept} (la più frequente); le righe delle altre società sono scartate ({companies}).",
     "Only company {kept} (the most frequent) is kept; rows of the other companies are dropped ({companies})."),
    ("dq_column_missing", "Colonne facoltative mancanti", "Optional columns missing"),
    ("dq_column_missing_m", "Mancano {columns}: non disponibile {features}.", "Missing {columns}: not available {features}."),
    ("dq_bad_numbers", "Importi non leggibili", "Amounts that cannot be read"),
    ("dq_bad_numbers_m", "Testo che non è un numero ({columns}): letto come 0 o vuoto. Es. {examples}.",
     "Text that is not a number ({columns}): read as 0 or blank. E.g. {examples}."),
    ("dq_bad_dates", "Date non leggibili", "Dates that cannot be read"),
    ("dq_bad_dates_m", "Date non riconosciute ({columns}; attese giorno/mese/anno, data Excel o data giuliana JDE): lette come vuote. Es. {examples}.",
     "Dates not recognised ({columns}; expected day/month/year, an Excel date or a JDE Julian date): read as blank. E.g. {examples}."),
    ("dq_ambiguous_numbers", "Importi con separatore ambiguo",
     "Amounts with an ambiguous separator"),
    ("dq_ambiguous_numbers_m", "Valori come 12.500 o 120,000 senza altri indizi nella colonna ({columns}): letti con il separatore delle migliaia (12.500 = 12500). Es. {examples}.",
     "Values such as 12.500 or 120,000 with no other clue in the column ({columns}): read with a thousands separator (12.500 = 12500). E.g. {examples}."),
    ("dq_file_empty", "File senza righe", "File with no rows"),
    ("dq_file_empty_m", "{files}: il file ha le intestazioni ma nessuna riga di dati.", "{files}: the file has the headers but no data rows."),
    ("dq_no_invoice_date", "Righe AR124 senza data fattura", "AR124 rows without invoice date"),
    ("dq_no_invoice_date_m", "Ignorate nel calcolo dei giorni.", "Ignored for payment days."),

    # --- 6.5 notes next to the reason ---
    ("r_EXEMPT_note", "Classe esente {cls}: JDE non blocca mai gli ordini; il fido serve solo come riferimento di monitoraggio.",
     "Exempt class {cls}: JDE never stops its orders; the limit is a monitoring reference only."),
    ("w_suffix_late", "Giorni di pagamento misurati {meas}; la formula ne conta al massimo {days} (termini + {over}).",
     "Measured payment days {meas}; the formula counts at most {days} (terms + {over})."),

    # --- 6.7 Results page ---
    ("res_title", "Cosa cambia con la nuova formula?", "What changes with the new formula?"),
    ("res_subtitle", "Fidi proposti a confronto con quelli attuali. Il metro di giudizio è l'esposizione reale.",
     "Proposed limits compared with the current ones. The yardstick is real exposure."),
    ("kpi_over_n", "Oltre fido, totale",
     "Over limit, total"),
    ("help_over_n", "Tutti i clienti del perimetro controllo ordini con esposizione sopra il fido proposto, compresi quelli a fido 0 per regola (massima cautela, fido suggerito Cerved 0, nessun fatturato). Con i fidi attuali: {cur}.",
     "All order-check scope customers with exposure above the proposed limit, including those at limit 0 by rule (maximum caution, Cerved suggested limit 0, no turnover). With today's limits: {cur}."),
    ("kpi_over_pos", "Oltre un fido positivo",
     "Over a positive limit"),
    ("help_over_pos", "Clienti del perimetro controllo ordini con esposizione sopra un fido proposto maggiore di 0: il loro prossimo ordine sarebbe fermato. Con i fidi attuali (fido maggiore di 0): {cur}.",
     "Order-check scope customers whose exposure is above a proposed limit greater than 0: their next order would be stopped. With today's limits (limit greater than 0): {cur}."),
    ("kpi_over_split", "{z} a fido 0 per regola + {p} oltre un fido positivo (oggi {zc} + {pc})",
     "{z} at limit 0 by rule + {p} over a positive limit (today {zc} + {pc})"),
    ("kpi_over_amt", "Esposizione oltre fido", "Exposure over limit"),
    ("help_over_amt", "Somma degli sforamenti (esposizione meno fido) dei clienti oltre fido, perimetro controllo. Valore esatto: {amt}. Con i fidi attuali: {cur}.",
     "Sum of the excess (exposure minus limit) of customers over limit, order-check scope. Exact value: {amt}. With current limits: {cur}."),
    ("kpi_limits", "Totale fidi · tutti gli attivi ({n} clienti)",
     "Total limits · all active ({n} customers)"),
    ("help_limits", "Somma dei fidi proposti di tutti i clienti attivi, anche esenti (fido di monitoraggio) e classi speciali (fido 0). Valore esatto: {amt}. Attuali: {cur}.",
     "Sum of the proposed limits of all active customers, exempt (monitoring limit) and special classes (limit 0) included. Exact value: {amt}. Today: {cur}."),
    ("kpi_limits_scope", "Totale fidi · perimetro controllo ({n} clienti)",
     "Total limits · order-check scope ({n} customers)"),
    ("help_limits_scope", "Somma dei fidi proposti dei clienti nel perimetro del controllo ordini. Valore esatto: {amt}. Attuali: {cur}.",
     "Sum of the proposed limits of the customers in the order-check scope. Exact value: {amt}. Today: {cur}."),
    ("kpi_exposure", "Esposizione · tutti gli attivi",
     "Exposure · all active"),
    ("help_exposure", "Saldo + ordinato + consegnato, tutti i clienti attivi. Non dipende dalla formula. Valore esatto: {amt}.",
     "Balance + ordered + delivered, all active customers. It does not depend on the formula. Exact value: {amt}."),
    ("kpi_moves", "Più alto / più basso / uguale", "Higher / lower / same"),
    ("help_moves", "Clienti del perimetro controllo il cui fido proposto è più alto, più basso o uguale all'attuale.",
     "Customers in the order-check scope whose proposed limit is higher, lower or the same as the current one."),
    ("kpi_zero", "Fido zero con fatturato", "Zero limit with turnover"),
    ("help_zero", "Clienti attivi che fatturano ma ricevono fido 0 (classi speciali escluse). Con i fidi attuali (0 in CreditBoard oggi, che può voler dire anche «non controllato»): {cur}.",
     "Active customers with turnover who get limit 0 (special classes excluded). With today's limits (0 in CreditBoard today, which may also mean \"not checked\"): {cur}."),
    ("kpi_orders_over", "Ordini aperti oltre fido", "Open orders over limit"),
    ("help_orders_over", "Clienti oltre fido con ordini aperti oggi: il loro prossimo ordine sarebbe fermato. Con i fidi attuali: {cur}.",
     "Customers over limit with open orders today: their next order would be stopped. With today's limits: {cur}."),
    ("kpi_review", "Da rivedere", "To review"),
    ("help_review", "Nostro fatturato sopra il {pct} del fatturato totale Cerved: il dato va controllato a mano. Perimetro controllo.",
     "Our turnover above {pct} of the Cerved total turnover: the data needs a manual check. Order-check scope."),
    ("kpi_review_caption", "{amt} di esposizione", "{amt} of exposure"),
    ("kpi_approval", "Da approvare",
     "Need approval"),
    ("help_approval", "Clienti del perimetro il cui fido proposto cambia più del {pct} e più di {amt} rispetto all'attuale. Per livello: Tier 1 {t1}, Tier 2 {t2}, Tier 3 {t3}.",
     "Scope customers whose proposed limit changes more than {pct} and more than {amt} vs today's limit. By tier: Tier 1 {t1}, Tier 2 {t2}, Tier 3 {t3}."),
    ("kpi_cerved_mix", "In Cerved: {n} clienti attivi, {pct} dell'esposizione.",
     "In Cerved: {n} active customers, {pct} of exposure."),
    ("kpi_scope_caption", "Oltre fido, più alto / più basso e approvazioni: perimetro controllo ordini ({n} clienti). Totali «tutti gli attivi»: {m} clienti.",
     "Over limit, higher / lower and approvals: order-check scope ({n} customers). \"All active\" totals: {m} customers."),
    ("delta_vs_current", "{d} rispetto all'attuale ({cur})", "{d} vs current ({cur})"),
    ("delta_vs_current_short", "{d} rispetto all'attuale", "{d} vs current"),
    ("chart_over_by_score", "Oltre fido per score Cerved", "Over limit by Cerved score"),
    ("chart_over_by_score_x", "Clienti oltre fido", "Customers over limit"),
    ("chart_change_buckets", "Come cambiano i fidi", "How limits change"),
    ("chart_change_y", "Clienti", "Customers"),
    ("chart_amounts_by_score", "Fidi ed esposizione per score (mln RON)", "Limits and exposure by score (M RON)"),
    ("chart_more", "Altri grafici", "More charts"),
    ("chart_score", "Score", "Score"),
    ("chart_series", "Serie", "Series"),
    ("chart_bucket", "Variazione", "Change"),
    ("series_current", "Attuale", "Current"),
    ("series_new", "Nuovo", "New"),
    ("series_current_limits", "Fidi attuali", "Current limits"),
    ("series_new_limits", "Fidi proposti", "Proposed limits"),
    ("series_exposure", "Esposizione", "Exposure"),
    ("score_AFFIDABILE", "Affidabile", "Reliable"),
    ("score_CAUTELA", "Cautela", "Caution"),
    ("score_MASSIMA CAUTELA", "Massima cautela", "Maximum caution"),
    ("score_NONE", "Non in Cerved", "Not in Cerved"),
    ("b_TO_ZERO", "A zero", "To zero"),
    ("b_DOWN_50", "-50% e oltre", "-50% or more"),
    ("b_DOWN_20_50", "Da -20% a -50%",
     "-20% to -50%"),
    ("b_WITHIN_20", "Entro ±20%",
     "Within ±20%"),
    ("b_UP_20_50", "Da +20% a +50%",
     "+20% to +50%"),
    ("b_UP_50", "+50% e oltre", "+50% or more"),
    ("b_FROM_ZERO", "Nuovo fido (attuale 0)", "New limit (current 0)"),
    ("tbl_title", "Clienti", "Customers"),
    ("flt_search", "Cerca", "Search"),
    ("flt_search_ph", "codice o nome", "code or name"),
    ("flt_score", "Score Cerved", "Cerved score"),
    ("flt_change", "Variazione", "Change"),
    ("flt_all", "Tutti", "All"),
    ("flt_higher", "Più alto", "Higher"),
    ("flt_lower", "Più basso", "Lower"),
    ("flt_same", "Uguale", "Same"),
    ("flt_only", "Mostra solo", "Show only"),
    ("flt_over_new", "Oltre fido (nuovo)", "Over limit (new)"),
    ("flt_becomes_over", "Diventano oltre fido", "Become over limit"),
    ("flt_leaves_over", "Non più oltre fido", "No longer over limit"),
    ("flt_review", "Da rivedere", "To review"),
    ("flt_approval", "Serve approvazione", "Need approval"),
    ("flt_scope_all", "Tutti gli attivi", "All active customers"),
    ("flt_scope_all_help", "Mostra anche esenti e classi speciali (fuori dal controllo ordini).",
     "Also show exempt and special classes (outside the order check)."),
    ("flt_more_cols", "Più colonne", "More columns"),
    ("flt_more_cols_help", "Score Cerved, esposizione, scaduto, perché cambia, note.",
     "Cerved score, exposure, overdue, why it changes, notes."),
    ("tbl_count", "{shown} clienti su {total}", "{shown} of {total} customers"),
    ("tbl_empty", "Nessun cliente con questi filtri.", "No customer matches these filters."),
    ("tbl_select_hint", "Clicca una riga per aprire il dettaglio del cliente (motivo completo e calcolo).",
     "Click a row to open the customer's details (full reason and calculation)."),
    ("col_code", "Codice", "Code"),
    ("col_name", "Cliente", "Customer"),
    ("col_score", "Score Cerved", "Cerved score"),
    ("col_exposure", "Esposizione (RON)", "Exposure (RON)"),
    ("col_overdue", "Scaduto (RON)", "Overdue (RON)"),
    ("col_cur", "Attuale (RON)", "Current (RON)"),
    ("col_new", "Proposto (RON)", "Proposed (RON)"),
    ("col_diff", "Differenza (RON)",
     "Difference (RON)"),
    ("col_over", "Oltre fido", "Over limit"),
    ("col_over_help", "Attuale → nuovo. Una sola parola se non cambia.", "Current → new. One word if it does not change."),
    ("col_reason", "Perché questo fido",
     "Why this limit"),
    ("col_why", "Perché cambia", "Why it changes"),
    ("col_flags", "Note", "Notes"),
    ("flag_review", "Da rivedere", "To review"),
    ("flag_approval", "Approvazione Tier {t}", "Approval Tier {t}"),
    ("flag_late", "Giorni limitati",
     "Days capped"),
    ("flag_exempt", "Esente", "Exempt"),
    ("btn_excel", "Scarica Excel", "Download Excel"),
    ("btn_excel_help", "Tutti i clienti attivi con tutti i passaggi del calcolo, i KPI e i parametri usati.",
     "All active customers with every step of the calculation, the KPIs and the parameters used."),
    ("btn_open_customer", "Apri il dettaglio di {name}", "Open details for {name}"),
    ("excel_filename", "fidi_RO_{date}.xlsx", "credit_limits_RO_{date}.xlsx"),

    # --- 6.8 Customer page ---
    ("cust_title", "Come si arriva a questo fido?", "How do we get to this limit?"),
    ("cust_subtitle", "Il calcolo passo per passo per un cliente, con i numeri.",
     "The step-by-step calculation for one customer, with the numbers."),
    ("cust_pick", "Cliente", "Customer"),
    ("cust_pick_help", "Scrivi il codice o il nome per cercare.", "Type the code or the name to search."),
    ("cust_header", "Codice {code} · P. IVA {vat} · classe {cls} · score {score}",
     "Code {code} · VAT {vat} · class {cls} · score {score}"),
    ("cust_t_cur", "Fido attuale", "Current limit"),
    ("cust_t_new", "Fido proposto", "Proposed limit"),
    ("cust_t_expo", "Esposizione oggi", "Exposure today"),
    ("cust_t_over", "Oltre fido", "Over limit"),
    ("cust_t_over_caption", "Con il fido attuale: {v}",
     "With today's limit: {v}"),
    ("cust_over_not_checked", "Non controllato",
     "Not checked"),
    ("cust_over_special_caption", "Classe speciale: già bloccato in CreditBoard",
     "Special class: already blocked in CreditBoard"),
    ("cust_over_exempt_above", "Esente: sopra il fido di monitoraggio",
     "Exempt: above the monitoring limit"),
    ("cust_over_exempt_within", "Esente: entro il fido di monitoraggio",
     "Exempt: within the monitoring limit"),
    ("steps_title", "Calcolo passo per passo", "Step-by-step calculation"),
    ("st_col_n", "#", "#"),
    ("st_col_step", "Passo", "Step"),
    ("st_col_calc", "Calcolo", "Calculation"),
    ("st_col_ron", "RON", "RON"),
    ("st_1", "Fatturato ultimi 12 mesi", "Turnover, last 12 months"),
    ("st_1_calc", "da Check fidi", "from Check fidi"),
    ("st_2", "Fatturato mensile", "Monthly turnover"),
    ("st_2_calc", "{t12} / 12", "{t12} / 12"),
    ("st_3", "Giorni di pagamento usati", "Payment days used"),
    ("st_3_calc", "{src} {meas} gg; minimo {min}, massimo termini {terms} (almeno {min}) + {over} = {max} → {used} gg",
     "{src} {meas} days; minimum {min}, maximum terms {terms} (at least {min}) + {over} = {max} → {used} days"),
    ("st_3_calc_nocap", "{src} {meas} gg; minimo {min}, nessun massimo → {used} gg",
     "{src} {meas} days; minimum {min}, no maximum → {used} days"),
    ("st_3_src_measured", "misurati", "measured"),
    ("st_3_src_terms", "termini contrattuali (nessuna fattura)", "contractual terms (no invoices)"),
    ("st_3_src_default", "default (né fatture né termini)", "default (no invoices, no terms)"),
    ("st_3_src_contract", "termini contrattuali", "contractual terms"),
    ("st_3_calc_contract", "{src} {meas} gg (parametro: Bisogno M1 sui termini); minimo {min} → {used} gg",
     "{src} {meas} days (parameter: Need M1 on terms); minimum {min} → {used} days"),
    ("st_beh", "Comportamento di pagamento: {band}", "Payment behaviour: {band}"),
    ("st_beh_calc_bonus", "ritardo {delay} gg (misurati {meas} − termini {terms}) ≤ 0 → {before} × (1 + {pct})",
     "delay {delay} days (measured {meas} − terms {terms}) ≤ 0 → {before} × (1 + {pct})"),
    ("st_beh_calc_tol", "ritardo {delay} gg (misurati {meas} − termini {terms}), entro {tol} gg → nessun bonus né malus",
     "delay {delay} days (measured {meas} − terms {terms}), within {tol} days → no bonus, no malus"),
    ("st_beh_calc_malus", "ritardo {delay} gg (misurati {meas} − termini {terms}), oltre {tol} gg (malus pieno da {full}) → {before} × (1 − {pct})",
     "delay {delay} days (measured {meas} − terms {terms}), beyond {tol} days (full malus from {full}) → {before} × (1 − {pct})"),
    ("st_beh_calc_none", "nessun giorno misurato da AR124 → nessun bonus né malus",
     "no measured days from AR124 → no bonus, no malus"),
    ("beh_BONUS", "bonus", "bonus"),
    ("beh_TOLERANCE", "tolleranza", "tolerance"),
    ("beh_MALUS", "malus", "malus"),
    ("beh_NONE", "nessun dato", "no data"),
    ("st_4", "Bisogno (M1)",
     "Need (M1)"),
    ("st_4_calc", "{m} × {used} / 30 × (1 + {buf})", "{m} × {used} / 30 × (1 + {buf})"),
    ("st_5", "Fido base (moltiplicatore ×{mult})",
     "Base limit (×{mult} multiplier)"),
    ("st_5_calc", "{mult} × {m1}", "{mult} × {m1}"),
    ("st_6", "Coefficiente di rischio: {score}",
     "Risk factor: {score}"),
    ("st_6_calc", "{base} × {coef}", "{base} × {coef}"),
    ("st_6_exempt", "{score}, classe esente", "{score}, exempt class"),
    ("st_7", "Tetto Cerved", "Cerved ceiling"),
    ("st_7_calc_applies", "Cerved suggerisce {amt} → vale il minore", "Cerved suggests {amt} → the lower one applies"),
    ("st_7_calc_no", "Cerved suggerisce {amt}: non serve", "Cerved suggests {amt}: not needed"),
    ("st_7_calc_none", "nessun fido suggerito Cerved", "no Cerved suggested limit"),
    ("st_7_calc_off", "tetto Cerved disattivato", "Cerved ceiling switched off"),
    ("st_8", "Classe speciale / nessun fatturato", "Special class / no turnover"),
    ("st_8_calc_special", "classe {cls} → 0", "class {cls} → 0"),
    ("st_8_calc_noturn", "nessun fatturato → 0", "no turnover → 0"),
    ("st_9", "Arrotondamento", "Rounding"),
    ("st_9_calc_up", "per eccesso al {step} successivo", "up to the next {step}"),
    ("st_9_calc_down", "per difetto al {step} precedente", "down to the previous {step}"),
    ("st_9_calc_hard", "per eccesso darebbe {up}, sopra il fido suggerito Cerved ({ceil}): vale il fido suggerito → {final}",
     "rounding up would give {up}, above the Cerved suggested limit ({ceil}): the suggested limit applies → {final}"),
    ("st_7_calc_invalid", "fido suggerito Cerved non utilizzabile ({amt}): nessun tetto",
     "Cerved suggested limit not usable ({amt}): no ceiling"),
    ("st_10", "Fido minimo", "Minimum limit"),
    ("st_10_calc_applies", "sotto {min} → {min}", "below {min} → {min}"),
    ("st_10_calc_no", "{min}: non si applica", "{min}: does not apply"),
    ("st_10_calc_capped", "sotto {min}, ma il minimo non supera il fido suggerito Cerved ({ceil}) → {final}",
     "below {min}, but the minimum never goes above the Cerved suggested limit ({ceil}) → {final}"),
    ("st_total", "Fido proposto", "Proposed limit"),
    ("expo_sentence", "Esposizione oggi {expo} = saldo {bal} + ordinato {ord} + consegnato {dlv}.",
     "Exposure today {expo} = balance {bal} + ordered {ord} + delivered {dlv}."),
    ("expo_over_new", "Con il fido proposto è **oltre fido di {amt}**.", "With the proposed limit it is **over limit by {amt}**."),
    ("expo_ok_new", "Con il fido proposto resta {amt} di margine.", "With the proposed limit {amt} of headroom remains."),
    ("expo_cur_over", "Con il fido attuale ({cur}) è oltre fido di {amt}.", "With the current limit ({cur}) it is over limit by {amt}."),
    ("expo_cur_ok", "Con il fido attuale ({cur}) non lo è.", "With the current limit ({cur}) it is not."),
    ("expo_exempt", "Classe esente: JDE non blocca mai i suoi ordini; il confronto con il fido di monitoraggio è solo informativo.",
     "Exempt class: JDE never stops its orders; the comparison with the monitoring limit is for information only."),
    ("expo_over_monitor", "Rispetto al fido di monitoraggio è **sopra di {amt}**.",
     "Against the monitoring limit it is **above by {amt}**."),
    ("expo_ok_monitor", "Resta {amt} sotto il fido di monitoraggio.",
     "It stays {amt} below the monitoring limit."),
    ("expo_special", "Classe speciale: il cliente è già bloccato in CreditBoard.",
     "Special class: the customer is already blocked in CreditBoard."),
    ("box_cerved", "Cerved", "Cerved"),
    ("cv_score", "Score", "Score"),
    ("cv_limit", "Fido suggerito", "Suggested limit"),
    ("cv_limit_eur", "{eur} EUR = {ron} al cambio {rate}", "{eur} EUR = {ron} at {rate}"),
    ("cv_class", "Classe di affidabilità", "Reliability class"),
    ("cv_turnover", "Fatturato totale del cliente", "Customer's total turnover"),
    ("cv_match", "Abbinato per", "Matched by"),
    ("cv_match_code", "codice", "code"),
    ("cv_match_vat", "partita IVA", "VAT number"),
    ("cv_vat_differs", "Attenzione: partita IVA diversa in Cerved ({vat}).", "Note: different VAT number in Cerved ({vat})."),
    ("cv_not_found", "Cliente non presente in Cerved.", "Customer not in Cerved."),
    ("cv_vat_conflict", "La riga Cerved con codice {code} ha un'altra partita IVA ({cv_name}, {cv_vat}): non usata.",
     "The Cerved row with code {code} belongs to another VAT number ({cv_name}, {cv_vat}): not used."),
    ("box_days", "Giorni di pagamento", "Payment days"),
    ("pd_measured", "Misurati (mediana ponderata)", "Measured (weighted median)"),
    ("pd_terms", "Termini contrattuali", "Contractual terms"),
    ("pd_used", "Usati nel calcolo", "Used in the calculation"),
    ("pd_invoices", "Fatture considerate", "Invoices counted"),
    ("days_capped", "Giorni di pagamento misurati {meas}; la formula ne conta al massimo {days} (termini + {over}).",
     "Measured payment days {meas}; the formula counts at most {days} (terms + {over})."),
    ("days_floored", "Paga presto: contati almeno {days} giorni.", "Fast payer: at least {days} days counted."),
    ("box_checks", "Controlli", "Checks"),
    ("ck_plaus", "Plausibilità", "Plausibility"),
    ("ck_plaus_ok", "{pct} del fatturato Cerved: OK (soglia {thr})", "{pct} of Cerved turnover: OK (threshold {thr})"),
    ("ck_plaus_review", "{pct} del fatturato Cerved: da rivedere (soglia {thr})", "{pct} of Cerved turnover: to review (threshold {thr})"),
    ("ck_plaus_na", "non calcolabile (manca il fatturato Cerved)", "cannot be calculated (no Cerved turnover)"),
    ("ck_change", "Variazione rispetto all'attuale", "Change vs current"),
    ("ck_change_new", "nuovo fido (attuale 0)", "new limit (current 0)"),
    ("ck_change_none", "nessuna (fido 0 in entrambi)",
     "none (0 in both)"),
    ("ck_approval", "Serve approvazione", "Approval needed"),
    ("ck_approval_yes", "Sì: variazione oltre ±{thr} e oltre {amt}",
     "Yes: change above ±{thr} and above {amt}"),
    ("ck_approval_no", "No (soglie: ±{thr} e {amt})",
     "No (thresholds: ±{thr} and {amt})"),
    ("ck_tier", "Livello di approvazione", "Approval tier"),
    ("ck_tier_val", "Tier {t} ({ron} = {eur} EUR)", "Tier {t} ({ron} = {eur} EUR)"),
    ("ck_tier_na", "non si applica (fido 0)",
     "does not apply (limit 0)"),
    ("cust_invoices", "Fatture del cliente (AR124)", "Customer invoices (AR124)"),
    ("cust_invoices_caption", "Fatture della finestra usate per i giorni di pagamento ({n}).",
     "Invoices of the window used for payment days ({n})."),
    ("cust_no_invoices", "Nessuna fattura nella finestra.", "No invoices in the window."),
    ("inv_date", "Data fattura", "Invoice date"),
    ("inv_due", "Scadenza", "Due date"),
    ("inv_closed", "Chiusa il", "Closed on"),
    ("inv_amount", "Importo (RON)", "Amount (RON)"),
    ("inv_days", "Giorni contati", "Days counted"),
    ("inv_open", "aperta", "open"),

    # --- 6.9 Lab page ---
    ("lab_title", "Quale formula funziona meglio?", "Which formula works best?"),
    ("lab_subtitle", "Cambia i parametri a sinistra: tutto si ricalcola subito ed è confrontato con la formula v3.2.",
     "Change the parameters on the left: everything recalculates at once and is compared with the v3.2 formula."),
    ("lab_changed", "Modificati: {list}", "Changed: {list}"),
    ("lab_unchanged", "Nessuna modifica: è la formula v3.2.", "No changes: this is the v3.2 formula."),
    ("grp_need", "Bisogno (M1)",
     "Need (M1)"),
    ("grp_risk", "Rischio (coefficienti di rischio)",
     "Risk (risk factors)"),
    ("grp_caps", "Tetti e arrotondamenti", "Ceilings and rounding"),
    ("grp_checks", "Controlli (non cambiano i fidi)", "Checks (do not change limits)"),
    ("grp_other", "Altre impostazioni", "Other settings"),
    ("p_buffer_pct", "Margine sul Bisogno (M1)",
     "Buffer on Need (M1)"),
    ("p_buffer_pct_help", "Bisogno (M1) × (1 + margine).",
     "Need (M1) × (1 + buffer)."),
    ("p_multiplier", "Moltiplicatore (× Bisogno M1)",
     "Multiplier (× Need M1)"),
    ("p_multiplier_help", "Fido base = moltiplicatore × Bisogno (M1). Con 2 un cliente che paga come al solito usa circa metà del fido.",
     "Base limit = multiplier × Need (M1). With 2 a customer paying as usual uses about half of the limit."),
    ("p_days_min", "Giorni minimi", "Minimum days"),
    ("p_days_min_help", "Il Bisogno (M1) conta comunque almeno questi giorni (termini brevi o pagamenti rapidi).", "The Need (M1) counts at least this many days (short terms or fast payers)."),
    ("p_days_cap_on", "Limita chi paga tardi", "Cap slow payers"),
    ("p_days_cap_on_help", "Solo con Bisogno (M1) sui giorni misurati: chi paga tardi non ottiene un fido più alto.", "Only with the Need (M1) on measured days: slow payers do not get a higher limit."),
    ("p_days_over_terms", "Giorni oltre i termini", "Days over terms"),
    ("p_days_over_terms_help", "Solo con Bisogno (M1) sui giorni misurati: giorni massimi = termini contrattuali + questi.", "Only with the Need (M1) on measured days: maximum days = contractual terms + this."),
    ("p_days_default", "Giorni se mancano i dati", "Days when data is missing"),
    ("p_days_default_help", "Usati se il cliente non ha fatture né termini.", "Used when a customer has no invoices and no terms."),
    ("p_coef_reliable", "Affidabile", "Reliable"),
    ("p_coef_reliable_help", "Coefficiente di rischio per Cerved \"Affidabile\".",
     "Risk factor for Cerved \"Reliable\"."),
    ("p_coef_caution", "Cautela", "Caution"),
    ("p_coef_caution_help", "Coefficiente di rischio per Cerved \"Cautela\".",
     "Risk factor for Cerved \"Caution\"."),
    ("p_coef_max_caution", "Massima cautela", "Maximum caution"),
    ("p_coef_max_caution_help", "Coefficiente di rischio per \"Massima cautela\". 0 = nessun credito non garantito.",
     "Risk factor for \"Maximum caution\". 0 = no unsecured credit."),
    ("p_coef_not_in_cerved", "Non in Cerved", "Not in Cerved"),
    ("p_coef_not_in_cerved_help", "Coefficiente di rischio per i clienti non valutati da Cerved.",
     "Risk factor for customers not rated by Cerved."),
    ("p_coef_exempt_nf", "Esenti non in Cerved", "Exempt, not in Cerved"),
    ("p_coef_exempt_nf_help", "Coefficiente di rischio per i clienti esenti (es. ospedali) non valutati da Cerved.",
     "Risk factor for exempt customers (e.g. hospitals) not rated by Cerved."),
    ("p_cerved_cap_on", "Tetto Cerved", "Cerved ceiling"),
    ("p_cerved_cap_on_help", "Il fido non supera mai il fido suggerito da Cerved.", "The limit never exceeds the Cerved suggested limit."),
    ("p_ceiling_hard", "Tetto Cerved rigido", "Hard Cerved ceiling"),
    ("p_vat_conflict", "Scarta abbinamenti Cerved con IVA diversa", "Reject Cerved matches with a different VAT"),
    ("p_terms_positive", "Termini solo da fatture (no note di credito)", "Terms from invoices only (no credit notes)"),
    ("p_round_step", "Arrotondamento (RON)", "Rounding (RON)"),
    ("p_round_step_help", "I fidi sono arrotondati a questo importo.", "Limits are rounded to this amount."),
    ("p_round_dir", "Direzione arrotondamento", "Rounding direction"),
    ("p_round_up", "Per eccesso", "Up"),
    ("p_round_down", "Per difetto", "Down"),
    ("p_min_limit", "Fido minimo (RON)", "Minimum limit (RON)"),
    ("p_min_limit_help", "Fido più piccolo per chi riceve credito.", "Smallest limit for a customer who gets credit."),
    ("p_plaus_pct", "Soglia plausibilità", "Plausibility threshold"),
    ("p_plaus_pct_help", "Da rivedere se il nostro fatturato supera questa quota del fatturato totale del cliente (Cerved).",
     "Review if our turnover is above this share of the customer's total turnover (Cerved)."),
    ("p_approval_pct", "Soglia approvazione (%)",
     "Approval threshold (%)"),
    ("p_approval_pct_help", "Serve approvazione se il fido cambia più di questa percentuale e più della soglia in RON.",
     "Approval needed if the limit changes more than this percentage and more than the RON threshold."),
    ("p_approval_min", "Soglia approvazione (RON)",
     "Approval threshold (RON)"),
    ("p_approval_min_help", "Serve approvazione solo se il fido cambia anche di più di questo importo.",
     "Approval only when the limit also changes by more than this amount."),
    ("p_eur_rate", "Cambio (RON per 1 EUR)", "Exchange rate (RON per 1 EUR)"),
    ("p_eur_rate_help", "Per i fidi Cerved in EUR e per i livelli di approvazione.", "For Cerved limits in EUR and for approval tiers."),
    ("p_tier1", "Tier 1 fino a (EUR)", "Tier 1 up to (EUR)"),
    ("p_tier2", "Tier 2 fino a (EUR)", "Tier 2 up to (EUR)"),
    ("p_tier_help", "Soglie provvisorie. Oltre Tier 2 è Tier 3.", "Provisional thresholds. Above Tier 2 is Tier 3."),
    ("p_intercompany", "Codici intercompany", "Intercompany codes"),
    ("p_special", "Classi speciali (fido 0)", "Special classes (limit 0)"),
    ("p_exempt", "Classi esenti (mai bloccate)", "Exempt classes (never blocked)"),
    ("p_lists_help", "Scrivi un codice nuovo e premi Invio per aggiungerlo.", "Type a new code and press Enter to add it."),
    ("grp_behaviour", "Comportamento di pagamento", "Payment behaviour"),
    ("p_behaviour_on", "Bonus / malus sul comportamento di pagamento", "Bonus / malus on payment behaviour"),
    ("p_behaviour_on_help", "Ritardo = giorni misurati − termini contrattuali (solo clienti con fatture AR124). In tempo o in anticipo: bonus; entro la tolleranza: niente; oltre: malus crescente. Si applica dopo il coefficiente di rischio, prima del tetto Cerved.",
     "Delay = measured days − contractual terms (customers with AR124 invoices only). On time or early: bonus; within the tolerance: nothing; beyond: a growing malus. Applied after the risk factor, before the Cerved ceiling."),
    ("p_beh_bonus", "Bonus (in tempo o in anticipo)", "Bonus (on time or early)"),
    ("p_beh_bonus_help", "Aumento del fido per chi paga entro i termini (ritardo ≤ 0). Da 0% a 50%.",
     "Increase for customers who pay within terms (delay ≤ 0). From 0% to 50%."),
    ("p_beh_malus", "Malus massimo", "Maximum malus"),
    ("p_beh_malus_help", "Riduzione massima per chi paga molto in ritardo. Da 0% a 50%.",
     "Largest reduction for customers who pay very late. From 0% to 50%."),
    ("p_beh_tol", "Tolleranza (giorni di ritardo)", "Tolerance (days late)"),
    ("p_beh_tol_help", "Fino a questi giorni di ritardo nessun bonus né malus.", "Up to this many days late: no bonus, no malus."),
    ("p_beh_full", "Malus pieno da (giorni di ritardo)", "Full malus from (days late)"),
    ("p_beh_full_help", "Il malus cresce in linea retta dalla tolleranza fino a qui, poi resta al massimo. Deve essere oltre la tolleranza.",
     "The malus grows in a straight line from the tolerance to here, then stays at the maximum. Must be above the tolerance."),
    ("p_m1_basis", "Giorni per il Bisogno (M1)", "Days for the Need (M1)"),
    ("p_m1_basis_help", "Con «misurati» chi paga tardi ha un Bisogno (M1) più grande, che il malus può non compensare; con «termini contrattuali» il comportamento conta solo con bonus/malus.",
     "With \"measured\" a late payer gets a larger Need (M1), which the malus may not offset; with \"contractual terms\" behaviour acts only through the bonus/malus."),
    ("p_m1_measured", "Misurati", "Measured"),
    ("p_m1_contractual", "Termini contrattuali", "Contractual terms"),
    ("lab_kpi_bonus", "Clienti con bonus", "Customers with bonus"),
    ("lab_kpi_malus", "Clienti con malus", "Customers with malus"),
    ("lab_kpi_beh_effect", "Effetto netto bonus/malus · attivi", "Net bonus/malus effect · all active"),
    ("lab_beh_caption", "Perimetro del controllo ordini: inoltre {tol} nella tolleranza e {none} senza giorni misurati (0%). Effetto netto sul totale dei fidi di tutti gli attivi; nel perimetro {scope}.",
     "Order-check scope: also {tol} within the tolerance and {none} without measured days (0%). Net effect on the total of all active limits; in the scope {scope}."),
    ("pd_delay", "Ritardo rispetto ai termini", "Delay vs terms"),
    ("pd_behaviour", "Bonus / malus", "Bonus / malus"),
    ("pd_basis_contract", "Il Bisogno (M1) usa i termini contrattuali ({days} gg), non i giorni misurati.",
     "The Need (M1) uses the contractual terms ({days} days), not the measured days."),
    ("flag_bonus", "Bonus pagamenti", "Payment bonus"),
    ("flag_malus", "Malus pagamenti", "Payment malus"),
    ("rl_beh_formula", " × (1 + bonus/malus di pagamento)", " × (1 + payment bonus/malus)"),
    ("rl_behaviour_on", "**Comportamento di pagamento**: ritardo = giorni misurati − termini contrattuali (dalle fatture AR124, prima di minimo e massimo; chi non ha giorni misurati: 0%). Ritardo ≤ 0 (paga in tempo o in anticipo) → bonus {bonus}; ritardo fino a {tol} giorni → 0%; oltre, malus che cresce in linea retta da 0 a {tol} giorni fino a {malus} a {full} giorni e poi resta {malus}. Il fido dopo il coefficiente di rischio si moltiplica per (1 + bonus/malus), prima del tetto Cerved, dell'arrotondamento e del minimo: il tetto Cerved resta rigido e le classi speciali restano a 0.",
     "**Payment behaviour**: delay = measured days − contractual terms (from the AR124 invoices, before minimum and maximum; without measured days: 0%). Delay ≤ 0 (pays on time or early) → bonus {bonus}; delay up to {tol} days → 0%; beyond, a malus growing in a straight line from 0 at {tol} days to {malus} at {full} days, then staying at {malus}. The limit after the risk factor is multiplied by (1 + bonus/malus), before the Cerved ceiling, rounding and the minimum: the Cerved ceiling stays hard and special classes stay at 0."),
    ("rl_behaviour_off", "**Comportamento di pagamento**: nessun bonus né malus (opzione disattivata); il ritmo di pagamento conta solo nei giorni del Bisogno (M1).",
     "**Payment behaviour**: no bonus and no malus (option off); the payment pace counts only through the days of the Need (M1)."),
    ("rl_days_basis_contract", "**Il Bisogno (M1) usa i termini contrattuali**, non i giorni misurati: almeno {min} giorni; senza termini {days} giorni. Chi paga tardi non ottiene un Bisogno (M1) più grande: il comportamento conta solo con il bonus/malus, calcolato sui giorni misurati qui sotto.",
     "**The Need (M1) uses the contractual terms**, not the measured days: at least {min} days; without terms {days} days. Late payers do not get a larger Need (M1): behaviour counts only through the bonus/malus, based on the measured days below."),
    ("lab_kpi_over_n", "Oltre fido, totale",
     "Over limit, total"),
    ("lab_kpi_over_pos", "Oltre un fido positivo",
     "Over a positive limit"),
    ("lab_over_split", "di cui {z} a fido 0 per regola",
     "of which {z} at limit 0 by rule"),
    ("lab_kpi_over_amt", "Esposizione oltre fido", "Exposure over limit"),
    ("lab_kpi_limits", "Totale fidi · tutti gli attivi",
     "Total limits · all active"),
    ("lab_kpi_limits_scope", "Totale fidi · perimetro",
     "Total limits · scope"),
    ("lab_kpi_zero", "Fido zero con fatturato", "Zero limit with turnover"),
    ("lab_kpi_approval", "Da approvare", "Need approval"),
    ("lab_delta", "{d} rispetto a v3.2", "{d} vs v3.2"),
    ("lab_help_base", "Formula v3.2: {v}.", "v3.2 formula: {v}."),
    ("lab_current_ref", "Per riferimento, con i fidi attuali: {pos} clienti oltre un fido positivo, {over} oltre fido in totale, {amt} oltre fido.",
     "For reference, with today's limits: {pos} customers over a positive limit, {over} over limit in total, {amt} over limit."),
    ("tab_effect", "Effetto", "Effect"),
    ("tab_sens", "Sensibilità", "Sensitivity"),
    ("tab_scn", "Scenari", "Scenarios"),
    ("chg_summary", "{n} clienti cambiano: {up} più alto, {down} più basso; {into} diventano oltre fido, {out} non lo sono più.",
     "{n} customers change: {up} higher, {down} lower; {into} become over limit, {out} no longer are."),
    ("chg_filter_all", "Tutti", "All"),
    ("chg_filter_limit", "Cambia il fido", "Limit changes"),
    ("chg_filter_status", "Cambia l'oltre fido", "Over-limit status changes"),
    ("chg_filter_label", "Mostra", "Show"),
    ("chg_col_v3", "Fido v3.2 (RON)", "Limit v3.2 (RON)"),
    ("chg_col_scn", "Fido scenario (RON)", "Limit scenario (RON)"),
    ("chg_col_over", "Oltre fido (v3.2 → scenario)", "Over limit (v3.2 → scenario)"),
    ("chg_col_why", "Perché questo fido (scenario)",
     "Why this limit (scenario)"),
    ("chg_none", "Uguale a v3.2: cambia un parametro a sinistra.", "Same as v3.2: change a parameter on the left."),
    ("sens_param", "Parametro", "Parameter"),
    ("sens_from", "Da", "From"),
    ("sens_to", "A", "To"),
    ("btn_run_sens", "Calcola", "Run"),
    ("sens_running", "Calcolo di 9 scenari...", "Calculating 9 scenarios..."),
    ("sens_stale", "I parametri sono cambiati: premi Calcola per aggiornare.", "Parameters changed: press Run to update."),
    ("sens_chart_limits", "Totale fidi, tutti gli attivi (mln RON)", "Total limits, all active (M RON)"),
    ("sens_chart_over", "Clienti oltre fido, totale", "Customers over limit, total"),
    ("sens_now", "valore attuale", "current value"),
    ("sens_cur_limits", "fidi attuali", "current limits"),
    ("sens_legend", "Linea tratteggiata blu: valore attuale del parametro. Linea tratteggiata grigia: con i fidi attuali.",
     "Blue dashed line: current value of the parameter. Grey dashed line: with today's limits."),
    ("sens_col_value", "Valore", "Value"),
    ("sens_col_limits", "Totale fidi, tutti gli attivi (RON)", "Total limits, all active (RON)"),
    ("sens_col_over", "Oltre fido, totale", "Over limit, total"),
    ("sens_col_excess", "Esposizione oltre fido (RON)", "Exposure over limit (RON)"),
    ("sens_col_zero", "Fido zero con fatturato", "Zero limit with turnover"),
    ("sens_caption", "9 valori di «{param}» da {a} a {b}; tutti gli altri parametri come nello scenario attivo.",
     "9 values of \"{param}\" from {a} to {b}; every other parameter as in the active scenario."),
    ("sens_empty", "Scegli un parametro e un intervallo, poi premi Calcola.", "Pick a parameter and a range, then press Run."),
    ("sens_range_err", "«Da» deve essere minore di «A».", "\"From\" must be lower than \"To\"."),
    ("scn_name", "Nome dello scenario", "Scenario name"),
    ("scn_name_ph", "es. Moltiplicatore 2,5",
     "e.g. Multiplier 2.5"),
    ("btn_save", "Salva", "Save"),
    ("scn_saved", "Scenario «{name}» salvato.", "Scenario \"{name}\" saved."),
    ("scn_overwrite", "Esiste già: sovrascrivi", "It already exists: overwrite"),
    ("scn_exists", "Esiste già uno scenario con questo nome: spunta «sovrascrivi» per sostituirlo.",
     "A scenario with this name already exists: tick \"overwrite\" to replace it."),
    ("scn_name_empty", "Dai un nome allo scenario.", "Give the scenario a name."),
    ("scn_col_name", "Scenario", "Scenario"),
    ("scn_col_diff", "Cosa cambia rispetto a v3.2", "What differs from v3.2"),
    ("scn_col_limits", "Totale fidi, tutti gli attivi (RON)", "Total limits, all active (RON)"),
    ("scn_col_over", "Oltre fido, totale", "Over limit, total"),
    ("scn_col_over_pos", "Oltre un fido positivo",
     "Over a positive limit"),
    ("scn_col_excess", "Esposizione oltre fido (RON)", "Exposure over limit (RON)"),
    ("scn_col_zero", "Fido zero con fatturato", "Zero limit with turnover"),
    ("scn_col_approval", "Da approvare", "Need approval"),
    ("scn_v3", "Default v3.2", "v3.2 default"),
    ("scn_current_limits", "Fidi attuali", "Current limits"),
    ("scn_current_limits_diff", "fidi di oggi in CreditBoard", "today's limits in CreditBoard"),
    ("scn_active", "(attivo)", "(active)"),
    ("scn_pick", "Scenario salvato", "Saved scenario"),
    ("btn_load", "Carica", "Load"),
    ("btn_delete", "Elimina", "Delete"),
    ("btn_export_json", "Esporta JSON", "Export JSON"),
    ("scn_import", "Importa uno scenario (JSON)", "Import a scenario (JSON)"),
    ("scn_import_ok", "Scenario «{name}» importato.", "Scenario \"{name}\" imported."),
    ("scn_import_err", "Il file non è uno scenario valido.", "The file is not a valid scenario."),
    ("scn_import_ignored", "Parametri sconosciuti ignorati: {list}", "Unknown parameters ignored: {list}"),
    ("scn_loaded", "Scenario «{name}» caricato.", "Scenario \"{name}\" loaded."),
    ("scn_deleted", "Scenario «{name}» eliminato.", "Scenario \"{name}\" deleted."),
    ("scn_empty", "Nessuno scenario salvato. Dai un nome alle impostazioni attuali e premi Salva.",
     "No saved scenarios. Name the current settings and press Save."),
    ("scn_folder", "Gli scenari sono file JSON nella cartella {path}.", "Scenarios are JSON files in the folder {path}."),

    # --- 6.10 / 7 Rules page and glossary ---
    ("rules_title", "Quali regole sono attive?", "Which rules are active?"),
    ("rules_subtitle", "Le regole dello scenario attivo, scritte dai parametri. Se non suonano come la nostra politica del credito, i parametri vanno cambiati.",
     "The rules of the active scenario, written from the parameters. If they do not read like our credit policy, the parameters need changing."),
    ("rules_h_who", "Chi è nel calcolo", "Who is in the calculation"),
    ("rules_h_formula", "La formula in una riga", "The formula in one line"),
    ("rules_h_limit", "Come si calcola il fido (si può rifare a mano)",
     "How the limit is calculated (you can redo it by hand)"),
    ("rules_h_checks", "Controlli", "Checks"),
    ("rules_changed_tag", "(modificato)", "(changed)"),
    ("rules_download", "Scarica le regole (txt)", "Download the rules (txt)"),
    ("rules_filename", "regole_fido_RO.txt", "credit_limit_rules_RO.txt"),
    ("gloss_title", "Glossario", "Glossary"),
    ("gloss_term", "Termine", "Term"),
    ("gloss_meaning", "Significato", "Meaning"),
    ("classes_title", "Classi di rischio con regole proprie", "Risk classes with their own rules"),
    ("classes_col_class", "Classe", "Class"),
    ("classes_col_meaning", "Significato", "Meaning"),
    ("classes_col_rule", "Regola", "Rule"),
    ("classes_rule_exempt", "esente", "exempt"),
    ("classes_rule_special", "speciale", "special"),
    ("rl_active", "Un cliente è **attivo** se ha un saldo diverso da zero o fatturato negli ultimi 12 mesi.",
     "A customer is **active** if it has a balance other than zero or turnover in the last 12 months."),
    ("rl_intercompany", "Le società del gruppo ({list}) sono escluse dalla simulazione.",
     "Group companies ({list}) are left out of the simulation."),
    ("rl_special", "Le classi {list} sono **speciali**: fido 0, il cliente è già bloccato in CreditBoard.",
     "Classes {list} are **special**: limit 0, the customer is already blocked in CreditBoard."),
    ("rl_exempt", "Le classi {list} sono **esenti**: JDE non blocca mai i loro ordini. Il fido si calcola come per gli altri (se non in Cerved con coefficiente di rischio {enf}) ed è solo un **fido di monitoraggio**: mostra quando l'esposizione è molto sopra un fido normale. Gli esenti non contano negli indicatori di oltre fido, ma sono nel totale fidi «tutti gli attivi».",
     "Classes {list} are **exempt**: JDE never stops their orders. The limit is calculated as for everyone else (risk factor {enf} when not in Cerved) and is only a **monitoring limit**: it shows when exposure is far above a normal limit. Exempt customers are not counted in the over-limit figures but are in the \"all active\" total of limits."),
    ("rl_scope", "**Nel perimetro del controllo ordini** = attivi, non intercompany, non in classi speciali né esenti ({n} clienti): sono i clienti di cui JDE controlla il fido a ogni ordine, gli unici contati come oltre fido, più alto / più basso e da approvare.",
     "**In scope of the order check** = active, not intercompany, no special or exempt class ({n} customers): the customers whose limit JDE checks at every order, and the only ones counted as over limit, higher / lower and needing approval."),
    ("rl_scope_nocount", "**Nel perimetro del controllo ordini** = attivi, non intercompany, non in classi speciali né esenti: sono i clienti di cui JDE controlla il fido a ogni ordine, gli unici contati come oltre fido, più alto / più basso e da approvare.",
     "**In scope of the order check** = active, not intercompany, no special or exempt class: the customers whose limit JDE checks at every order, and the only ones counted as over limit, higher / lower and needing approval."),
    ("rl_exposure", "**Esposizione** = saldo + ordinato + consegnato.", "**Exposure** = balance + ordered + delivered."),
    ("rl_days", "**Giorni di pagamento**: dalle fatture AR124 con data fattura negli ultimi {months} mesi fino alla data di riferimento ({ref}), solo importi positivi. Ogni fattura conta: pagata → data chiusura − data fattura; ancora aperta e scaduta → {ref} − data fattura (il cliente non ha ancora pagato); aperta e non scaduta → i suoi termini (scadenza − data fattura). Giorni misurati = mediana ponderata per importo (ordinate le fatture per giorni, il valore in cui si raggiunge metà dell'importo).",
     "**Payment days**: from the AR124 invoices dated in the last {months} months up to the reference date ({ref}), positive amounts only. Each invoice counts: paid → closing date − invoice date; still open and overdue → {ref} − invoice date (the customer has not paid yet); open and not yet due → its terms (due date − invoice date). Measured days = amount-weighted median (invoices sorted by days, the value where half of the amount is reached)."),
    ("rl_days_min", "Si contano almeno {min} giorni.", "At least {min} days are counted."),
    ("rl_days_cap", "Si contano al massimo i termini contrattuali (almeno {min} giorni) + {over} giorni: chi paga tardi non ottiene un fido più alto.",
     "At most the contract terms (at least {min} days) + {over} days are counted: slow payers do not get a higher limit."),
    ("rl_days_nocap", "Non c'è un massimo: chi paga tardi ottiene un fido più alto.",
     "There is no maximum: slow payers get a higher limit."),
    ("rl_days_default", "Senza fatture si usano i termini contrattuali; senza nemmeno quelli, {days} giorni.",
     "Without invoices the contractual terms are used; without those either, {days} days."),
    ("rl_terms_positive", "I termini contrattuali sono la mediana di scadenza − data fattura sulle fatture (note di credito escluse).",
     "Contract terms are the median of due date − invoice date over the invoices (credit notes excluded)."),
    ("rl_terms_all", "I termini contrattuali sono la mediana di scadenza − data fattura su tutte le righe, note di credito comprese.",
     "Contract terms are the median of due date − invoice date over all rows, credit notes included."),
    ("rl_t12", "**Fatturato 12 mesi (T12)**: colonna «Turnover 12 months» di Check fidi (CreditBoard); non la colonna «Turnover» e non le fatture AR124.",
     "**Turnover 12 months (T12)**: column \"Turnover 12 months\" of Check fidi (CreditBoard); not the \"Turnover\" column and not the AR124 invoices."),
    ("rl_formula", "fido = min( max( arrotondamento per {dir} a {step} di ( {mult} × Bisogno (M1) × coefficiente di rischio{beh} ), {min} ), fido suggerito Cerved in RON interi ), con Bisogno (M1) = T12 / {div} × giorni / 30 × (1 + {buf}). Fido 0 per classi speciali, nessun fatturato, coefficiente di rischio 0 o fido suggerito Cerved 0. I passi, uno per uno, sono sotto.",
     "limit = min( max( round {dir} to {step} of ( {mult} × Need (M1) × risk factor{beh} ), {min} ), Cerved suggested limit in whole RON ), with Need (M1) = T12 / {div} × days / 30 × (1 + {buf}). Limit 0 for special classes, no turnover, risk factor 0 or Cerved suggested limit 0. The steps, one by one, are below."),
    ("rl_formula_nocap", "fido = max( arrotondamento per {dir} a {step} di ( {mult} × Bisogno (M1) × coefficiente di rischio{beh} ), {min} ), con Bisogno (M1) = T12 / {div} × giorni / 30 × (1 + {buf}). Fido 0 per classi speciali, nessun fatturato o coefficiente di rischio 0. I passi, uno per uno, sono sotto.",
     "limit = max( round {dir} to {step} of ( {mult} × Need (M1) × risk factor{beh} ), {min} ), with Need (M1) = T12 / {div} × days / 30 × (1 + {buf}). Limit 0 for special classes, no turnover or risk factor 0. The steps, one by one, are below."),
    ("rl_max_caution_why", "Massima cautela con coefficiente 0: per questo score non diamo credito non garantito; gli ordini richiedono pagamento anticipato, una garanzia o un'eccezione approvata.",
     "Maximum caution with risk factor 0: for this score we give no unsecured credit; orders need prepayment, a guarantee or an approved exception."),
    ("rl_share_half", "circa la metà ({pct})",
     "about half ({pct})"),
    ("rl_match_reject", "Cerved si abbina per codice cliente; se la partita IVA è diversa la riga Cerved non si usa e si cerca per partita IVA, altrimenti il cliente è \"non in Cerved\".",
     "Cerved is matched by customer code; if the VAT number differs the Cerved row is not used and the VAT number is tried instead, otherwise the customer is \"not in Cerved\"."),
    ("rl_match_keep", "Cerved si abbina per codice cliente anche se la partita IVA è diversa; i clienti senza codice si cercano per partita IVA.",
     "Cerved is matched by customer code even if the VAT number differs; customers without a code match are looked up by VAT number."),
    ("rl_need", "**Bisogno (M1)** = T12 / {div} × giorni di pagamento / 30 × (1 + {buf}): quanto il cliente ci deve normalmente al suo ritmo di pagamento, più un margine del {buf}.",
     "**Need (M1)** = T12 / {div} × payment days / 30 × (1 + {buf}): what the customer normally owes us at its payment pace, plus a {buf} buffer."),
    ("rl_mult", "**Fido base** = {mult} × Bisogno (M1). Perché il moltiplicatore ×{mult}: un cliente che paga come al solito usa {share} del fido; il resto copre i nuovi ordini e le consegne non ancora fatturate.",
     "**Base limit** = {mult} × Need (M1). Why the ×{mult} multiplier: a customer paying as usual uses {share} of the limit; the rest covers new orders and deliveries not yet invoiced."),
    ("rl_coef", "**Coefficiente di rischio** dallo score Cerved: affidabile {r}, cautela {c}, massima cautela {mc}, non in Cerved {nf} (esenti non in Cerved {enf}). Fido = fido base × coefficiente di rischio.",
     "**Risk factor** from the Cerved score: reliable {r}, caution {c}, maximum caution {mc}, not in Cerved {nf} (exempt not in Cerved {enf}). Limit = base limit × risk factor."),
    ("rl_cap_on", "**Tetto Cerved**: il fido non supera mai il **fido suggerito Cerved** (colonna VALORE_FIDO del Cerved Slim Report: il credito non garantito che Cerved suggerisce a un fornitore di concedere a questa società), preso in RON interi (troncato all'unità: 4.582,72 → 4.582). Se Cerved suggerisce 0, il fido è 0. I valori in EUR si convertono a {rate} RON per EUR.",
     "**Cerved ceiling**: the limit never goes above the **Cerved suggested limit** (column VALORE_FIDO of the Cerved Slim Report: the unsecured credit Cerved suggests a supplier grants this company), taken in whole RON (truncated: 4,582.72 → 4,582). If Cerved suggests 0, the limit is 0. Values in EUR are converted at {rate} RON per EUR."),
    ("rl_cap_hard", "Il tetto è rigido: né l'arrotondamento né il fido minimo lo superano.",
     "The ceiling is hard: neither rounding nor the minimum limit goes above it."),
    ("rl_cap_off", "Il fido suggerito da Cerved **non** è usato come tetto.", "The Cerved suggested limit is **not** used as a ceiling."),
    ("rl_zero", "**Fido 0** per le classi speciali e per chi non ha fatturato negli ultimi 12 mesi.",
     "**Limit 0** for special classes and for customers with no turnover in the last 12 months."),
    ("rl_round", "**Arrotondamento** per {dir} a multipli di {step} RON.",
     "**Rounding** {dir} to multiples of {step} RON."),
    ("rl_round_up_word", "eccesso", "up"),
    ("rl_round_down_word", "difetto", "down"),
    ("rl_min", "**Fido minimo**: chi riceve credito ha almeno {min} RON, salvo che il fido suggerito Cerved sia più basso (allora il fido è il valore Cerved).",
     "**Minimum limit**: a customer who gets credit has at least {min} RON, unless the Cerved suggested limit is lower (then the limit is the Cerved value)."),
    ("rl_over", "**Oltre fido** = esposizione sopra il fido, solo nel perimetro del controllo ordini: il **prossimo** ordine del cliente sarebbe fermato da JDE. I clienti a fido 0 per regola (massima cautela, fido Cerved 0, nessun fatturato) sono oltre fido appena hanno esposizione: Risultati e Laboratorio li contano a parte.",
     "**Over limit** = exposure above the limit, order-check scope only: the customer's **next** order would be stopped by JDE. Customers at limit 0 by rule (maximum caution, Cerved 0, no turnover) are over limit as soon as they have exposure: Results and Lab count them separately."),
    ("rl_plaus", "**Da rivedere** se il nostro fatturato supera il {pct} del fatturato totale del cliente secondo Cerved.",
     "**To review** if our turnover is above {pct} of the customer's total turnover according to Cerved."),
    ("rl_approval", "Serve **approvazione** se il fido proposto cambia più del {pct} **e** più di {amt} RON rispetto all'attuale (anche un fido nuovo, da 0, sopra {amt} RON).",
     "**Approval** is needed if the proposed limit changes more than {pct} **and** more than {amt} RON vs today's limit (a new limit from 0 too, when above {amt} RON)."),
    ("rl_tiers", "Il livello di approvazione dipende dal fido proposto (non dalla variazione) in EUR, al cambio {rate} RON per EUR: Tier 1 fino a {t1} EUR, Tier 2 fino a {t2} EUR, Tier 3 oltre (soglie provvisorie).",
     "The approval tier depends on the proposed limit (not on the change) in EUR, at {rate} RON per EUR: Tier 1 up to {t1} EUR, Tier 2 up to {t2} EUR, Tier 3 above (provisional thresholds)."),
    ("g_exposure_t", "Esposizione", "Exposure"),
    ("g_exposure", "Quanto il cliente ci deve o ci dovrà a breve: saldo + ordinato + consegnato non fatturato. È il metro con cui giudichiamo il fido.",
     "What the customer owes us or soon will: balance + ordered + delivered not yet invoiced. It is the yardstick for the limit."),
    ("g_m1_t", "Bisogno (M1)",
     "Need (M1)"),
    ("g_m1", "Quanto il cliente ci deve normalmente se paga ai termini concordati: fatturato 12 mesi / 12 × termini contrattuali (giorni) / 30, più un margine (con l'opzione «misurati»: i giorni di pagamento misurati).",
     "What the customer normally owes us when it pays at the agreed terms: 12-month turnover / 12 × contractual terms (days) / 30, plus a buffer (with the \"measured\" option: the measured payment days)."),
    ("g_mult_t", "Moltiplicatore", "Multiplier"),
    ("g_mult", "Fido base = moltiplicatore × Bisogno (M1). Con 2 un cliente che paga come al solito usa circa metà del fido; il resto copre nuovi ordini e consegne non ancora fatturate.",
     "Base limit = multiplier × Need (M1). With 2 a customer paying as usual uses about half of the limit; the rest covers new orders and deliveries not yet invoiced."),
    ("g_coef_t", "Coefficiente di rischio",
     "Risk factor"),
    ("g_coef", "Riduce il fido base secondo lo score Cerved: 1 = formula piena, 0 = nessun credito non garantito.",
     "Reduces the base limit according to the Cerved score: 1 = full formula, 0 = no unsecured credit."),
    ("g_cap_t", "Fido suggerito Cerved (tetto Cerved)",
     "Cerved suggested limit (Cerved ceiling)"),
    ("g_cap", "VALORE_FIDO del Cerved Slim Report: il credito non garantito che Cerved suggerisce di concedere alla società. Il nostro fido non lo supera mai (in RON interi).",
     "VALORE_FIDO of the Cerved Slim Report: the unsecured credit Cerved suggests granting the company. Our limit never goes above it (in whole RON)."),
    ("g_scope_t", "Nel perimetro del controllo ordini",
     "In scope of the order check"),
    ("g_scope", "I clienti di cui JDE controlla il fido a ogni ordine: attivi, non intercompany, non speciali, non esenti. Solo loro contano come oltre fido.",
     "The customers whose limit JDE checks at every order: active, not intercompany, not special, not exempt. Only they count as over limit."),
    ("g_over_t", "Oltre fido", "Over limit"),
    ("g_over", "Esposizione sopra il fido. Nel perimetro significa che il prossimo ordine sarebbe fermato (non che oggi un ordine sia bloccato).",
     "Exposure above the limit. In the scope it means the next order would be stopped (not that an order is blocked today)."),
    ("g_plaus_t", "Plausibilità", "Plausibility"),
    ("g_plaus", "Se il nostro fatturato con il cliente è una quota troppo alta del suo fatturato totale (Cerved), uno dei due dati è probabilmente sbagliato: va controllato a mano.",
     "If our turnover with the customer is too high a share of its total turnover (Cerved), one of the two figures is probably wrong: check it by hand."),
    ("g_approval_t", "Livello di approvazione", "Approval tier"),
    ("g_approval", "Chi deve approvare un fido che cambia molto (oltre la soglia % e la soglia in RON): dipende dal fido proposto in EUR (Tier 1, 2, 3).",
     "Who must approve a limit that changes a lot (above the % and the RON thresholds): it depends on the proposed limit in EUR (Tier 1, 2, 3)."),
    ("g_ic_t", "Intercompany", "Intercompany"),
    ("g_ic", "Società del gruppo SIAD: fuori dalla simulazione.", "SIAD group companies: left out of the simulation."),
    ("g_exempt_t", "Classi esenti", "Exempt classes"),
    ("g_exempt", "Clienti che JDE non blocca mai (società controllate SIAD, ospedali, sanità privata, pubblica amministrazione): il fido è solo un fido di monitoraggio.",
     "Customers JDE never stops (SIAD subsidiaries, hospitals, private healthcare, public administration): the limit is only a monitoring limit."),
    ("g_monitor_t", "Fido di monitoraggio",
     "Monitoring limit"),
    ("g_monitor", "Il fido calcolato per i clienti esenti: JDE non li blocca mai; serve a vedere quando l'esposizione è molto sopra un fido normale.",
     "The limit calculated for exempt customers: JDE never stops them; it shows when exposure is far above a normal limit."),
    ("g_zero_rule_t", "Fido 0 per regola",
     "Limit 0 by rule"),
    ("g_zero_rule", "Fido 0 deciso da una regola, non dal calcolo: massima cautela, fido suggerito Cerved 0, nessun fatturato, coefficiente di rischio 0. Questi clienti sono oltre fido appena hanno esposizione.",
     "Limit 0 set by a rule, not by the calculation: maximum caution, Cerved suggested limit 0, no turnover, risk factor 0. These customers are over limit as soon as they have exposure."),
    ("g_special_t", "Classi speciali", "Special classes"),
    ("g_special", "Clienti già bloccati in CreditBoard (fallimenti, legale, recupero crediti, accordi transattivi, amministrazione controllata): fido 0.",
     "Customers already blocked in CreditBoard (bankruptcy, lawyer, debt collection, settlement agreements, controlled administration): limit 0."),
    ("g_days_t", "Giorni di pagamento", "Payment days"),
    ("g_days", "Quanti giorni il cliente impiega davvero a pagare, misurati sulle fatture: confrontati con i termini danno il ritardo, base del bonus/malus.",
     "How many days the customer really takes to pay, measured on its invoices: compared with the terms they give the delay behind the bonus/malus."),
    # --- v3.2: customer age (anzianità cliente) and the customer master MD105 ---------------------
    ("file_md105", "Anagrafica clienti MD105 (opzionale)", "Customer master MD105 (optional)"),
    ("file_md105_role", "Data di apertura del conto: da qui l'anzianità del cliente (consigliato).",
     "Account opening date: the customer age comes from here (recommended)."),
    ("file_md105_missing", "Senza MD105 l'anzianità viene dalla prima fattura AR124: con 12 mesi di fatture un acquirente occasionale sembra un cliente nuovo.",
     "Without MD105 the age comes from the first AR124 invoice: with 12 months of invoices an occasional buyer looks like a new customer."),
    ("age_NEW", "Nuovo", "New"),
    ("age_YOUNG", "Giovane", "Young"),
    ("age_CONSOLIDATED", "Consolidato", "Consolidated"),
    ("age_NO_HISTORY", "Nessuno storico", "No history"),
    ("grp_age", "Anzianità cliente", "Customer age"),
    ("p_age_on", "Fasce di anzianità (nuovo / giovane / consolidato)", "Age bands (new / young / consolidated)"),
    ("p_age_on_help", "Anzianità = mesi dalla data di apertura del conto (MD105; senza MD105 dalla prima fattura AR124) alla data di riferimento. Nuovi e giovani: fatturato mensile = fatturato 12 mesi ÷ mesi di attività (almeno 1, al massimo 12). Consolidati e senza storico: ÷ 12.",
     "Age = months from the account opening date (MD105; without MD105 the first AR124 invoice) to the reference date. New and young: monthly revenue = 12-month turnover ÷ months active (at least 1, at most 12). Consolidated and no history: ÷ 12."),
    ("p_age_new", "Cliente nuovo sotto (mesi)", "New customer below (months)"),
    ("p_age_new_help", "Sotto questa anzianità il cliente è nuovo: fatturato annualizzato, nessun bonus/malus, fatturato da confermare con la stima commerciale.",
     "Below this age the customer is new: annualised revenue, no bonus/malus, revenue to confirm with the sales estimate."),
    ("p_age_consolidated", "Cliente consolidato da (mesi)", "Consolidated from (months)"),
    ("p_age_consolidated_help", "Da questa anzianità il cliente è consolidato: fatturato 12 mesi ÷ 12, come in v3.1. Tra le due soglie è giovane.",
     "From this age the customer is consolidated: 12-month turnover ÷ 12, as in v3.1. Between the two thresholds it is young."),
    ("p_beh_min_inv", "Fatture scadute minime per il bonus/malus", "Minimum invoices due for the bonus/malus"),
    ("p_beh_min_inv_help", "Fatture con importo > 0 nella finestra dei giorni di pagamento, già scadute alla data di riferimento. Con meno fatture il bonus/malus è 0%. 0 = nessun minimo (come v3.1).",
     "Invoices with amount > 0 in the payment-days window, already due at the reference date. With fewer the bonus/malus is 0%. 0 = no minimum (as v3.1)."),
    ("lab_age_caption", "Perimetro per anzianità: nuovi {new} · giovani {young} · consolidati {cons} · senza storico {none}. Senza bonus/malus: {bnew} perché nuovi, {bfew} per poche fatture scadute.",
     "Scope by age: new {new} · young {young} · consolidated {cons} · no history {none}. No bonus/malus: {bnew} because new, {bfew} for too few invoices due."),
    ("flag_new_customer", "Nuovo: confermare il fatturato con la stima commerciale", "New: confirm the revenue with the sales estimate"),
    ("st_2_calc_age", "fatturato {t12} ÷ {months} mesi di attività (cliente {band})", "turnover {t12} ÷ {months} months active ({band} customer)"),
    ("st_beh_calc_new", "cliente nuovo (sotto {new} mesi) o senza storico → nessun bonus né malus",
     "new customer (under {new} months) or no history → no bonus, no malus"),
    ("st_beh_calc_few", "{n} fatture già scadute, minimo {min} → nessun bonus né malus",
     "{n} invoices already due, minimum {min} → no bonus, no malus"),
    ("beh_NEW_CUSTOMER", "cliente nuovo", "new customer"),
    ("beh_FEW_INVOICES", "poche fatture", "too few invoices"),
    ("dq_md_no_code", "MD105: righe senza codice cliente", "MD105: rows without customer code"),
    ("dq_md_no_code_m", "Righe scartate: senza codice non si possono abbinare.", "Rows dropped: without a code they cannot be matched."),
    ("dq_md_dup_code", "MD105: codici cliente ripetuti", "MD105: repeated customer codes"),
    ("dq_md_dup_code_m", "Si tiene la data di apertura più vecchia. Esempi: {examples}.", "The earliest opening date is kept. Examples: {examples}."),
    ("dq_ar_short_history", "Anzianità dalle sole fatture AR124 (manca MD105)", "Age from AR124 invoices only (MD105 missing)"),
    ("dq_ar_short_history_m", "AR124 copre {months} mesi: un cliente la cui prima fattura cade in questo periodo può essere un acquirente occasionale e non un cliente nuovo (chi ha la prima fattura nei primi 31 giorni del file è trattato come consolidato). Caricare l'anagrafica MD105 per anzianità affidabili, oppure un AR124 di almeno {needed} mesi.",
     "AR124 covers {months} months: a customer whose first invoice falls in this period may be an occasional buyer rather than a new one (a first invoice within the file's first 31 days counts as consolidated). Load the customer master MD105 for reliable ages, or an AR124 covering at least {needed} months."),
    ("dq_age_before_opening", "Prima fattura precedente all'apertura MD105", "First invoice before the MD105 opening date"),
    ("dq_age_before_opening_m", "Prima fattura AR124 più di 31 giorni prima della data di apertura in MD105 (codice ricreato): per l'anzianità si usa la data più vecchia. Nel perimetro: {scope_n}.",
     "First AR124 invoice more than 31 days before the MD105 opening date (code re-created): the earlier date is used for the age. In scope: {scope_n}."),
    ("dq_md_missing", "Clienti attivi non presenti in MD105", "Active customers not in MD105"),
    ("dq_md_missing_m", "Anzianità dalla prima fattura AR124 (senza fatture: nessuno storico, fatturato ÷ 12). Nel perimetro: {scope_n}.",
     "Age from the first AR124 invoice (without invoices: no history, turnover ÷ 12). In scope: {scope_n}."),
    ("dq_c_opened", "Apertura MD105", "Opened (MD105)"),
    ("dq_c_first_inv", "Prima fattura AR124", "First AR124 invoice"),
    ("banner_short_history", "Fasce di anzianità dalle sole fatture AR124 ({months} mesi): un acquirente occasionale può sembrare un cliente nuovo o giovane. Caricare l'anagrafica MD105 (o un AR124 di almeno {needed} mesi) nella pagina Dati.",
     "Age bands from AR124 invoices only ({months} months): an occasional buyer may look like a new or young customer. Load the customer master MD105 (or an AR124 covering at least {needed} months) on the Data page."),
    ("age_tbl_title", "Per anzianità del cliente (perimetro)", "By customer age (scope)"),
    ("age_col_band", "Anzianità", "Age"),
    ("age_col_n", "Clienti", "Customers"),
    ("age_col_cur", "Fidi attuali", "Current limits"),
    ("age_col_new", "Fidi proposti", "Proposed limits"),
    ("age_col_over_pos", "Oltre un fido positivo", "Over a positive limit"),
    ("age_col_over", "Oltre fido, totale", "Over limit, total"),
    ("age_tbl_total", "Totale", "Total"),
    ("flt_age", "Anzianità cliente", "Customer age"),
    ("col_age", "Anzianità", "Age"),
    ("cust_age_badge", "Cliente {band} · {months} mesi ({src})", "{band} customer · {months} months ({src})"),
    ("cust_age_badge_min", "Cliente {band} · ≥ {months} mesi ({src}: prima fattura a inizio file)",
     "{band} customer · ≥ {months} months ({src}: first invoice at the start of the file)"),
    ("cust_age_badge_none", "Nessuno storico: nessuna data MD105 né fattura AR124", "No history: no MD105 date and no AR124 invoice"),
    ("cust_new_warning", "Cliente nuovo: il fatturato 12 mesi è diviso per {months} mesi di attività. Confermare il fatturato con la stima commerciale.",
     "New customer: the 12-month turnover is divided by {months} months active. Confirm the revenue with the sales estimate."),
    ("pd_opened", "Apertura conto (MD105)", "Account opened (MD105)"),
    ("pd_first_invoice", "Prima fattura (AR124)", "First invoice (AR124)"),
    ("pd_age", "Anzianità", "Age"),
    ("pd_age_min", "≥ {months} (prima fattura a inizio AR124)", "≥ {months} (first invoice at the AR124 start)"),
    ("pd_months_active", "Mesi di attività usati", "Months active used"),
    ("pd_inv_due", "Fatture già scadute (finestra)", "Invoices already due (window)"),
    ("months_unit", "mesi", "months"),
    ("rl_age_on", "**Anzianità del cliente**: mesi dalla data di apertura del conto (anagrafica MD105; se la prima fattura AR124 è più vecchia di oltre 31 giorni si usa quella; senza MD105 la prima fattura AR124) alla data di riferimento. Un'anzianità presa da una fattura nei primi 31 giorni del file AR124 è solo un minimo («≥ N mesi»: il cliente può aver comprato prima): cliente consolidato. Sotto {new} mesi: **nuovo** (fatturato mensile = T12 ÷ mesi di attività, almeno 1; nessun bonus/malus; fatturato da confermare con la stima commerciale). Da {new} a meno di {cons} mesi: **giovane** (T12 ÷ mesi di attività, al massimo 12). Da {cons} mesi: **consolidato** (T12 ÷ 12). Senza data né fatture: **nessuno storico** (T12 ÷ 12, nessun bonus/malus).",
     "**Customer age**: months from the account opening date (customer master MD105; if the first AR124 invoice is more than 31 days older, that one; without MD105 the first AR124 invoice) to the reference date. An age taken from an invoice in the first 31 days of the AR124 file is only a minimum (“≥ N months”: the customer may have bought before): consolidated customer. Under {new} months: **new** (monthly revenue = T12 ÷ months active, at least 1; no bonus/malus; revenue to confirm with the sales estimate). From {new} to under {cons} months: **young** (T12 ÷ months active, at most 12). From {cons} months: **consolidated** (T12 ÷ 12). With no date and no invoices: **no history** (T12 ÷ 12, no bonus/malus)."),
    ("rl_age_off", "**Anzianità del cliente**: fasce disattivate, fatturato mensile = T12 ÷ 12 per tutti (come v3.1).",
     "**Customer age**: bands switched off, monthly revenue = T12 ÷ 12 for everyone (as v3.1)."),
    ("rl_beh_min", "Il bonus/malus si applica solo con almeno {n} fatture (importo > 0, ultimi {months} mesi) già scadute alla data di riferimento; con meno: 0%.",
     "The bonus/malus applies only with at least {n} invoices (amount > 0, last {months} months) already due at the reference date; with fewer: 0%."),
    ("rl_beh_min_off", "Nessun minimo di fatture per il bonus/malus.", "No minimum number of invoices for the bonus/malus."),
    ("rl_div_age", "mesi di attività (12 per i consolidati)", "months active (12 for consolidated customers)"),
    ("g_age_t", "Anzianità del cliente", "Customer age"),
    ("g_age", "Mesi dall'apertura del conto (MD105) alla data di riferimento: nuovo, giovane o consolidato. Per nuovi e giovani il fatturato 12 mesi si divide per i mesi di attività, perché non hanno ancora 12 mesi di storia.",
     "Months from the account opening (MD105) to the reference date: new, young or consolidated. For new and young customers the 12-month turnover is divided by the months active, because they do not have 12 months of history yet."),
]

TEXTS: dict[str, dict[str, str]] = {k: {"it": it, "en": en} for k, it, en in _DECK}
assert len(TEXTS) == len(_DECK), "duplicate key in the UI copy deck"

# Meaning of the risk classes with their own rule (SIAD blocking rules).
CLASS_TEXTS: dict[str, dict[str, str]] = {
    "A8": {"it": "Società controllate SIAD", "en": "SIAD subsidiaries"},
    "EKM": {"it": "Istituti ospedalieri", "en": "Hospital institutions"},
    "EPS": {"it": "Sanità privata", "en": "Private healthcare"},
    "EPU": {"it": "Pubblica amministrazione", "en": "Public administration"},
    "S09": {"it": "Fallimento", "en": "Bankruptcy"},
    "EV9": {"it": "Passato al legale", "en": "Sent to the lawyer"},
    "EV8": {"it": "Recupero crediti", "en": "Debt collection"},
    "EK9": {"it": "Mandati cliente per perdite", "en": "Customer mandates for losses"},
    "ES1": {"it": "Fallimento con recupero IVA", "en": "Bankruptcy with VAT recovery"},
    "ET1": {"it": "Accordi transattivi e quote concordate", "en": "Settlement agreements and pre-agreed quotes"},
    "ET2": {"it": "Accordi transattivi e quote concordate", "en": "Settlement agreements and pre-agreed quotes"},
    "ET8": {"it": "Accordi transattivi e quote concordate", "en": "Settlement agreements and pre-agreed quotes"},
    "ET9": {"it": "Accordi transattivi e quote concordate", "en": "Settlement agreements and pre-agreed quotes"},
    "EU9": {"it": "Amministrazione controllata", "en": "Controlled administration"},
}

# Core parameter key -> copy-deck key of its label (used by the UI and by the Excel export).
PARAM_LABEL_KEYS: dict[str, str] = {
    "reference_date": "p_ref_date", "window_months": "p_window_months",
    "fallback_days": "p_days_default", "min_days": "p_days_min", "cap_extra_days": "p_days_over_terms",
    "cap_days_enabled": "p_days_cap_on", "buffer": "p_buffer_pct", "multiplier": "p_multiplier",
    "coef_reliable": "p_coef_reliable", "coef_caution": "p_coef_caution",
    "coef_max_caution": "p_coef_max_caution", "coef_not_in_cerved": "p_coef_not_in_cerved",
    "coef_exempt_not_in_cerved": "p_coef_exempt_nf", "cerved_cap_enabled": "p_cerved_cap_on",
    "ceiling_is_hard": "p_ceiling_hard", "cerved_reject_vat_conflict": "p_vat_conflict",
    "terms_positive_only": "p_terms_positive", "eur_ron": "p_eur_rate", "rounding_step": "p_round_step",
    "rounding_mode": "p_round_dir", "min_limit": "p_min_limit",
    "plausibility_threshold": "p_plaus_pct", "approval_threshold": "p_approval_pct",
    "approval_min_change_ron": "p_approval_min", "m1_days_basis": "p_m1_basis",
    "behaviour_enabled": "p_behaviour_on", "behaviour_bonus_max": "p_beh_bonus",
    "behaviour_malus_max": "p_beh_malus", "behaviour_tolerance_days": "p_beh_tol",
    "behaviour_full_malus_days": "p_beh_full",
    "age_bands_enabled": "p_age_on", "new_customer_months": "p_age_new", "consolidated_months": "p_age_consolidated",
    "behaviour_min_invoices": "p_beh_min_inv",
    "tier1_eur": "p_tier1", "tier2_eur": "p_tier2", "intercompany_codes": "p_intercompany",
    "special_classes": "p_special", "exempt_classes": "p_exempt",
}
PARAM_TEXTS.update({k: dict(TEXTS[v]) for k, v in PARAM_LABEL_KEYS.items()})


class _Keep(dict):
    """format_map helper: unknown placeholders stay visible as {name}."""

    def __missing__(self, k: str) -> str:
        return "{" + k + "}"


def T(key: str, lang: str = "it", **values: Any) -> str:
    """UI string ``key`` in ``lang`` filled with already-formatted ``values``.

    Unknown key -> the key itself (a visible hole, caught by the UI tests).
    """
    entry = TEXTS.get(key)
    if entry is None:
        return key
    tpl = entry.get(lang) or entry.get("en") or key
    return tpl.format_map(_Keep(values)) if values else tpl



# ---------------------------------------------------------------------------
# Customer page layout (v3.3) and public balance sheet (ANAF): second opinion, not part of the formula
# ---------------------------------------------------------------------------
_BALANCE_DECK = [
    # layout
    ("cust_tab_calc", "Calcolo del fido", "Limit calculation"),
    ("cust_tab_profile", "Cerved, pagamenti e controlli", "Cerved, payments and checks"),
    ("cust_tab_balance", "Bilancio pubblico (ANAF)", "Public balance sheet (ANAF)"),
    ("cust_tab_invoices", "Fatture", "Invoices"),
    ("cust_answer", "In breve", "In short"),
    ("cust_badge_class", "Classe {cls}", "Class {cls}"),
    ("cust_badge_exempt", "Esente: mai bloccato", "Exempt: never blocked"),
    ("cust_badge_special", "Classe speciale: fido 0", "Special class: limit 0"),
    ("cust_badge_bs", "Bilancio {year}: {v}", "Balance sheet {year}: {v}"),
    ("cust_ids", "Codice {code} · partita IVA {vat}", "Code {code} · VAT {vat}"),
    # balance sheet: intro and states
    ("bs_intro", "Leggiamo l'ultimo bilancio che l'azienda ha depositato allo Stato rumeno (servizio pubblico ANAF) "
     "e controlliamo se il fido proposto è proporzionato alla sua solidità. È un secondo parere: "
     "non cambia il fido calcolato dalla formula.",
     "We read the last balance sheet the company filed with the Romanian State (ANAF public service) and "
     "check whether the proposed limit is in proportion to how solid it is. It is a second opinion: it "
     "does not change the limit calculated by the formula."),
    ("bs_btn", "Leggi l'ultimo bilancio", "Read the last balance sheet"),
    ("bs_btn_refresh", "Aggiorna da ANAF", "Refresh from ANAF"),
    ("bs_spinner", "Interrogo ANAF per il codice fiscale {cui}…", "Querying ANAF for tax code {cui}…"),
    ("bs_no_cui", "Questo cliente non ha una partita IVA rumena: il bilancio non si può cercare.",
     "This customer has no Romanian VAT number: the balance sheet cannot be looked up."),
    ("bs_foreign", "Partita IVA estera: ANAF ha solo i bilanci delle società rumene.",
     "Foreign VAT number: ANAF only has balance sheets of Romanian companies."),
    ("bs_not_found", "Nessun bilancio trovato per il codice fiscale {cui} ({years}). Succede per gli enti pubblici "
     "(ospedali, comuni), per le società appena nate e per chi non ha depositato il bilancio.",
     "No balance sheet found for tax code {cui} ({years}). This happens for public bodies (hospitals, town "
     "halls), newly founded companies and companies that did not file."),
    ("bs_error", "ANAF non risponde ({err}). Controllare la connessione o aprire il link: {url}",
     "ANAF does not answer ({err}). Check the connection or open the link: {url}"),
    ("bs_source", "{name} · codice fiscale {cui} · bilancio {year} · attività: {desc} · letto il {at} · "
     "[fonte ANAF]({url})",
     "{name} · tax code {cui} · {year} balance sheet · business: {desc} · read on {at} · [ANAF source]({url})"),
    ("bs_name_differs", "Il nome in ANAF ({name}) è diverso da quello in anagrafica: controllare la partita IVA.",
     "The ANAF name ({name}) differs from the customer master: check the VAT number."),
    # verdict
    ("bs_v_valid", "Il fido proposto di {lim} va bene per questa azienda.",
     "The proposed limit of {lim} is right for this company."),
    ("bs_v_valid_watch", "Il fido proposto di {lim} va bene, ma l'azienda ha dei punti deboli da tenere d'occhio.",
     "The proposed limit of {lim} is fine, but the company has weak points to keep an eye on."),
    ("bs_v_too_high", "Il fido proposto di {lim} è troppo alto per questa azienda. Un fido corretto è {sug}.",
     "The proposed limit of {lim} is too high for this company. A correct limit is {sug}."),
    ("bs_v_too_high_zero", "Il fido proposto di {lim} è troppo alto: l'azienda deve più di quello che possiede. "
     "Fido corretto: 0, solo con pagamento anticipato o garanzia.",
     "The proposed limit of {lim} is too high: the company owes more than it owns. Correct limit: 0, "
     "only with prepayment or a guarantee."),
    ("bs_v_zero_confirmed", "Il bilancio conferma il fido 0: l'azienda deve più di quello che possiede.",
     "The balance sheet confirms the limit of 0: the company owes more than it owns."),
    ("bs_v_zero_formula", "Il fido 0 viene dalla formula (rischio Cerved o classe), non dal bilancio: "
     "il bilancio da solo reggerebbe fino a {cap}.",
     "The limit of 0 comes from the formula (Cerved risk or class), not from the balance sheet: the balance "
     "sheet alone would carry up to {cap}."),
    ("bs_v_na", "Il bilancio pubblicato non riporta il patrimonio netto: non possiamo giudicare il fido.",
     "The published balance sheet has no net equity figure: we cannot judge the limit."),
    ("bs_why_capacity", "Regola: un'azienda può reggere un fido fino al {share} del suo patrimonio netto ({eq}), "
     "cioè {cap}.",
     "Rule: a company can carry a limit of up to {share} of its net equity ({eq}), i.e. {cap}."),
    ("bs_why_weak", "Abbiamo usato il {share} invece del {full} perché: {list}.",
     "We used {share} instead of {full} because: {list}."),
    ("bs_why_neg", "Il patrimonio netto è negativo ({eq}): se vendesse tutto non riuscirebbe a pagare i debiti.",
     "Net equity is negative ({eq}): selling everything would not cover its debts."),
    ("bs_weak_loss", "ha chiuso l'anno in perdita", "it closed the year with a loss"),
    ("bs_weak_leverage", "ha molti debiti rispetto al patrimonio", "it has a lot of debt compared with its equity"),
    ("bs_weak_liquidity", "ha poca liquidità per pagare i debiti", "it has little liquidity to pay its debts"),
    ("bs_old", "Attenzione: è il bilancio {year}, vecchio di {months} mesi. La situazione può essere cambiata.",
     "Note: this is the {year} balance sheet, {months} months old. The situation may have changed."),
    ("bs_k_proposed", "Fido proposto dalla formula", "Limit proposed by the formula"),
    ("bs_k_capacity", "Fido che il bilancio regge", "Limit the balance sheet carries"),
    ("bs_k_suggested", "Fido corretto secondo il bilancio", "Correct limit per the balance sheet"),
    ("bs_k_current", "Fido attuale in JDE", "Current limit in JDE"),
    ("bs_k_current_help", "Oggi è il {pct} del patrimonio netto.", "Today it is {pct} of net equity."),
    # plain reading
    ("bs_read_title", "Cosa dice il bilancio, in parole semplici", "What the balance sheet says, in plain words"),
    ("bs_q_size", "Quanto è grande?", "How big is it?"),
    ("bs_a_size", "Vende {to} all'anno con {emp} dipendenti.", "It sells {to} a year with {emp} employees."),
    ("bs_a_size_noemp", "Vende {to} all'anno.", "It sells {to} a year."),
    ("bs_q_profit", "Guadagna?", "Does it make money?"),
    ("bs_a_profit", "Sì: ha guadagnato {net}, cioè {m} ogni 100 RON venduti.",
     "Yes: it earned {net}, i.e. {m} for every 100 RON sold."),
    ("bs_a_loss", "No: ha perso {net}, cioè {m} ogni 100 RON venduti.",
     "No: it lost {net}, i.e. {m} for every 100 RON sold."),
    ("bs_a_profit_na", "Il risultato non è nel bilancio pubblicato.", "The result is not in the published statement."),
    ("bs_q_equity", "Quanto vale?", "What is it worth?"),
    ("bs_a_equity", "Se vendesse tutto quello che ha e pagasse tutti i debiti, resterebbero {eq}. "
     "È il cuscinetto che protegge i fornitori come SIAD.",
     "If it sold everything it has and paid all its debts, {eq} would remain. This is the cushion that "
     "protects suppliers like SIAD."),
    ("bs_a_equity_neg", "Deve più di quello che possiede: anche vendendo tutto mancherebbero {eq}.",
     "It owes more than it owns: even selling everything it would be {eq} short."),
    ("bs_q_debt", "Quanti debiti ha?", "How much debt does it have?"),
    ("bs_a_debt", "Ha {debts} di debiti: {x} RON per ogni RON di patrimonio. Oltre {max} sono tanti.",
     "It has {debts} of debt: {x} RON for every RON of equity. Above {max} is a lot."),
    ("bs_a_debt_neg", "Ha {debts} di debiti e nessun patrimonio a coprirli.",
     "It has {debts} of debt and no equity to cover them."),
    ("bs_q_liq", "Riesce a pagare i conti?", "Can it pay its bills?"),
    ("bs_a_liq", "Per ogni RON di debiti ha {x} RON tra cassa, soldi da incassare e magazzino. "
     "Sotto {min} può faticare a pagare.",
     "For every RON of debt it has {x} RON in cash, money to collect and stock. Below {min} it may "
     "struggle to pay."),
    ("bs_q_siad", "Quanto pesa SIAD?", "How much does SIAD weigh?"),
    ("bs_a_siad", "Gli ultimi 12 mesi di vendite SIAD valgono il {pct} del suo fatturato.",
     "SIAD's last 12 months of sales equal {pct} of its turnover."),
    ("bs_a_siad_na", "Non calcolabile.", "Cannot be calculated."),
    ("bs_lvl_good", "bene", "good"),
    ("bs_lvl_watch", "attenzione", "watch"),
    ("bs_lvl_bad", "male", "bad"),
    ("bs_lvl_info", "informazione", "information"),
    # technical details
    ("bs_tech", "Tutti i numeri del bilancio", "All balance-sheet figures"),
    ("bs_box_values", "Ultimo bilancio (RON)", "Last balance sheet (RON)"),
    ("bs_box_ratios", "Indicatori", "Indicators"),
    ("bs_turnover", "Fatturato netto", "Net turnover"),
    ("bs_net", "Risultato netto", "Net result"),
    ("bs_equity", "Patrimonio netto", "Net equity"),
    ("bs_debts", "Debiti totali", "Total debts"),
    ("bs_current", "Attivo circolante", "Current assets"),
    ("bs_receivables", "Crediti", "Receivables"),
    ("bs_inventory", "Magazzino", "Inventory"),
    ("bs_cash", "Cassa e banche", "Cash and banks"),
    ("bs_employees", "Dipendenti medi", "Average employees"),
    ("bs_r_margin", "Margine netto", "Net margin"),
    ("bs_r_leverage", "Debiti / patrimonio", "Debts / equity"),
    ("bs_r_liquidity", "Attivo circolante / debiti", "Current assets / debts"),
    ("bs_r_limit", "Fido proposto / patrimonio", "Proposed limit / equity"),
    ("bs_r_current", "Fido attuale / patrimonio", "Current limit / equity"),
    ("bs_r_siad", "Vendite SIAD 12 mesi / fatturato", "SIAD sales 12 months / turnover"),
    ("bs_raw", "Tutti gli indicatori pubblicati da ANAF", "All indicators published by ANAF"),
    ("bs_raw_code", "Codice", "Code"),
    ("bs_raw_desc", "Indicatore (rumeno)", "Indicator (Romanian)"),
    ("bs_raw_val", "Valore (RON)", "Value (RON)"),
    ("bs_strip_title", "Controllo sul bilancio (ANAF)", "Balance-sheet check (ANAF)"),
    ("bs_strip_sub", "il fido proposto è proporzionato all'azienda?", "is the proposed limit right for the company?"),
    ("bs_strip_todo", "Premi il tasto: leggiamo l'ultimo bilancio depositato e ti diciamo se il fido proposto va "
     "bene o quale sarebbe un fido corretto.",
     "Press the button: we read the last filed balance sheet and tell you whether the proposed limit is right "
     "or what a correct limit would be."),
    ("bs_strip_details", "Bilancio {year} spiegato in parole semplici nella scheda **Bilancio pubblico (ANAF)** qui sotto.",
     "The {year} balance sheet explained in plain words in the **Public balance sheet (ANAF)** tab below."),
    ("bs_tab_todo", "Premi \"Leggi l'ultimo bilancio\" nel riquadro qui sopra.",
     "Press \"Read the last balance sheet\" in the box above."),
    ("app_version", "Versione {v}", "Version {v}"),
    ("gap_chart_title", "Acquisti e blocchi mese per mese", "Purchases and holds month by month"),
    ("blk_cat_ok", "Nessun blocco", "No hold"),
    ("blk_cat_new", "Blocco solo con il fido proposto", "Hold with the proposed limit only"),
    ("blk_cat_both", "Blocco con entrambi i fidi", "Hold with both limits"),
    ("blk_cat_cur", "Blocco solo con il fido attuale", "Hold with the current limit only"),
    ("blk_tt_amount", "Fatturato del mese", "Invoiced in the month"),
    ("blk_tt_peak", "Esposizione più alta (partite aperte)", "Highest exposure (open items)"),
    ("blk_tt_cat", "Esito", "Outcome"),
    ("blk_line_cur", "fido attuale {v}", "current limit {v}"),
    ("blk_line_new", "fido proposto {v}", "proposed limit {v}"),
    ("blk_sum_new_yes", "**Con il fido proposto ({v})** gli ordini si sarebbero bloccati in **{n} mesi su 12**: {m}.",
     "**With the proposed limit ({v})** orders would have been held in **{n} months of 12**: {m}."),
    ("blk_sum_new_no", "**Con il fido proposto ({v})** nessun blocco negli ultimi 12 mesi.",
     "**With the proposed limit ({v})** no hold in the last 12 months."),
    ("blk_sum_cur_yes", "**Con il fido attuale ({v})** in **{n} mesi su 12**: {m}.",
     "**With the current limit ({v})** in **{n} months of 12**: {m}."),
    ("blk_sum_cur_no", "**Con il fido attuale ({v})** nessun blocco.", "**With the current limit ({v})** no hold."),
    ("blk_exempt", "Cliente esente: JDE non blocca i suoi ordini; i colori mostrano solo quando il saldo ha superato il fido.",
     "Exempt customer: JDE does not hold its orders; the colours only show when the balance went above the limit."),
    ("blk_special", "Classe speciale: fido 0, ogni ordine richiede pagamento anticipato o un'eccezione.",
     "Special class: limit 0, every order needs prepayment or an exception."),
    ("blk_caption", "Barre: fatturato del mese, dal 1° all'ultimo giorno. Linea scura: esposizione più alta del mese, "
     "cioè le fatture emesse e non ancora pagate (ognuna conta dal giorno di emissione al giorno del pagamento). "
     "Anche un cliente puntuale ha sempre aperte le fatture non ancora scadute: con {terms} giorni di termini "
     "l'esposizione normale è circa {terms} giorni di acquisti, e sale se crescono gli acquisti. Linea rossa: la "
     "parte scaduta da più di {d} giorni, quella che conta davvero. In Romania la consegna si fattura subito, "
     "quindi le fatture rappresentano le consegne; mancano solo gli ordini non ancora consegnati e le partite "
     "aperte più vecchie del file AR124. Linee tratteggiate: fido attuale (quello di oggi, applicato a tutto "
     "l'anno) e fido proposto. Il colore della barra dice se in quel mese l'esposizione ha superato il fido, cioè "
     "se un nuovo ordine sarebbe andato in blocco. * mese in corso, dati fino al {ref}.",
     "Bars: invoiced in the month, 1st to last day. Dark line: highest exposure of the month, i.e. invoices issued "
     "and not yet paid (each counts from issue to payment). Even a punctual customer always has the invoices not "
     "yet due open: with {terms} days' terms the normal exposure is about {terms} days of purchases, and it rises "
     "when purchases grow. Red line: the part overdue by more than {d} days, the one that really matters. In "
     "Romania deliveries are invoiced at once, so invoices stand for deliveries; only orders not yet delivered "
     "and open items older than the AR124 file are missing. Dashed lines: current limit (today's, applied to the "
     "whole year) and proposed limit. The bar colour says whether the exposure went above the limit that month, "
     "i.e. whether a new order would have been held. * month in progress, data up to {ref}."),
    ("blk_tt_od", "Scaduto da più di {d} giorni", "Overdue by more than {d} days"),
    ("blk_od_no", "**Scaduto da più di {d} giorni:** mai negli ultimi 12 mesi. L'esposizione è tutta di fatture non "
     "ancora scadute (o pagate entro la tolleranza).",
     "**Overdue by more than {d} days:** never in the last 12 months. The exposure is all invoices not yet due "
     "(or paid within the tolerance)."),
    ("blk_od_yes", "**Scaduto da più di {d} giorni:** al massimo {v} ({m}).",
     "**Overdue by more than {d} days:** at most {v} ({m})."),
    ("gap_axis_month", "Mese", "Month"),
    ("gap_axis_amount", "Fatturato (RON)", "Invoiced (RON)"),
    ("gap_tt_period", "Periodo", "Period"),
    ("gap_note", "**Mesi senza acquisti: {empty} su 12** ({ranges}). La formula divide il fatturato dei 12 mesi "
     "per 12: **{m12} al mese**. Nei {bought} mesi in cui ha comprato la media è **{mb} al mese**. "
     "Con quella media il fido sarebbe circa **{alt}** invece di {lim}.",
     "**Months without purchases: {empty} of 12** ({ranges}). The formula divides the 12-month turnover by "
     "12: **{m12} a month**. In the {bought} months it bought, the average is **{mb} a month**. With that "
     "average the limit would be about **{alt}** instead of {lim}."),
    ("gap_note_capped", "**Mesi senza acquisti: {empty} su 12** ({ranges}). La formula divide il fatturato dei 12 "
     "mesi per 12: **{m12} al mese**; nei {bought} mesi in cui ha comprato la media è **{mb} al mese**. "
     "Il fido resterebbe comunque {lim} per il tetto Cerved.",
     "**Months without purchases: {empty} of 12** ({ranges}). The formula divides the 12-month turnover by "
     "12: **{m12} a month**; in the {bought} months it bought, the average is **{mb} a month**. The limit "
     "would still be {lim} because of the Cerved ceiling."),
    ("gap_note_expo", "Oggi l'esposizione ({expo}) supera già il fido proposto.",
     "Today's exposure ({expo}) is already above the proposed limit."),
    ("gap_note_tail", "Solo un'informazione, la formula non cambia. Se il cliente compra davvero a intermittenza "
     "(stagionale o occasionale) la media su 12 mesi è giusta; se ha ripreso a comprare con regolarità, il fido "
     "proposto può essere stretto: valutare un'eccezione in approvazione.",
     "Information only, the formula does not change. If the customer really buys on and off (seasonal or "
     "occasional) the 12-month average is right; if it has started buying regularly again, the proposed "
     "limit may be tight: consider an exception at approval."),
    ("gap_months_short", "gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic", "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"),
    ("bs_rules", "Regole del controllo bilancio", "Balance-sheet check rules"),
    ("bs_rules_caption", "Valori di prova, solo per questa sessione: non cambiano la formula.",
     "Test values, this session only: they do not change the formula."),
    ("bs_p_share", "Fido massimo, % del patrimonio", "Maximum limit, % of equity"),
    ("bs_p_weak", "… se ha punti deboli", "… with weak points"),
    ("bs_p_lev", "Debiti / patrimonio massimo", "Maximum debts / equity"),
    ("bs_p_liq", "Attivo circolante / debiti minimo", "Minimum current assets / debts"),
    ("bs_p_age", "Età massima del bilancio (mesi)", "Maximum balance-sheet age (months)"),
    ("bs_vs_valid", "va bene", "fine"),
    ("bs_vs_valid_watch", "va bene, da seguire", "fine, to watch"),
    ("bs_vs_too_high", "fido troppo alto", "limit too high"),
    ("bs_vs_zero_confirmed", "conferma lo 0", "confirms 0"),
    ("bs_vs_zero_formula", "reggerebbe un fido", "would carry a limit"),
    ("bs_vs_na", "non giudicabile", "cannot judge"),
]
TEXTS.update({k: {"it": it, "en": en} for k, it, en in _BALANCE_DECK})
