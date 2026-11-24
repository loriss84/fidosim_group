# Simulatore Fido SIAD v3 — specifica

> **Versione 4.0 (24/11/2026): multi-paese.** La specifica sotto è quella della Romania e resta valida parola per
> parola per la Romania (stessi numeri: `tests/fixtures/golden_ro.json.gz`). Per gli altri paesi cambiano solo:
> valuta (tutti gli importi "RON" sono in valuta locale), prefisso IVA tolto nell'abbinamento Cerved, valori locali
> (`min_limit`, `rounding_step`, `approval_min_change`, `eur_rate`, `intercompany_codes`: `core/country.py`) e la
> fonte del bilancio pubblico (`core/bs_providers.py`: RO ANAF, SK RÚZ, AT/CZ/DE/HU valori scritti a mano).
> Nuovo parametro `country` (dati, non formula). Cerved resta facoltativo: senza, tutti "non in Cerved".

## 1. Perché esiste

Loris Sambinelli (Project Manager Finance, SIAD S.p.A.) sta definendo come calcolare
automaticamente il fido (credit limit) dei clienti di SIAD Romania (JDE company 42, valuta RON).
Il vecchio simulatore (`fidosim`, nella cartella padre) è troppo complesso e confusionario.
Questo è un simulatore NUOVO, separato, con due scopi soltanto:

1. **Simulare i fidi proposti con la nuova formula e confrontarli con quelli attuali, spiegando il perché**
   di ogni differenza, cliente per cliente e in totale.
2. **Laboratorio dei parametri**: cambiare i parametri della formula e vedere subito l'effetto,
   per discutere con il team rumeno quale sia la formula migliore.

Lo userà Loris al PC e in riunione, proiettato, con colleghi rumeni (credit controller, finance)
che parlano inglese. Interfaccia bilingue **italiano / inglese** con un selettore.

Contesto da sapere: i fidi attuali sono stati gonfiati di proposito dal team locale per non bloccare mai
i clienti. Il confronto con i fidi attuali serve a capire cosa cambia, NON a giudicare la formula: il
metro di giudizio è l'esposizione reale e chi finisce oltre fido.

## 2. Principi di design (vincolanti)

- **Semplice prima di tutto.** Poche pagine, una domanda per pagina. Niente opzioni che servono a pochi.
  Massimo ~15 parametri modificabili, raggruppati e spiegati in una riga ciascuno.
- **Ogni numero si spiega da solo**: etichetta chiara, unità (RON), e dove serve la definizione.
- **Ogni fido proposto ha un motivo** in una frase leggibile ("Limitato dal fido suggerito Cerved",
  "Massima cautela Cerved: fido zero", "Minimo 5.000 RON"...), e un dettaglio passo per passo.
- **Nessuna sorpresa nascosta**: le regole attive sono scritte in linguaggio naturale da qualche parte visibile.
- I default dei parametri sono le regole **v3.2** decise (sezione 4; v3.1 e v3 restano riproducibili con i parametri). "Ripristina default" sempre disponibile.
- Codice pulito, leggibile, commentato dove serve; logica di calcolo separata dall'interfaccia;
  nessuna chiamata di rete; tutto in locale.
- Windows è la piattaforma dell'utente (Python 3.10+). Avvio con doppio clic su `run.bat`.

## 3. Dati in ingresso (tre file obbligatori + MD105 opzionale, riconosciuti dalle colonne)

L'app parte vuota: l'utente carica i tre file nella pagina Dati (area di upload, anche tutti insieme). Il caricamento automatico da una cartella avviene solo se la variabile d'ambiente `FIDO_DATA_DIR` è impostata (usata dai test con i file reali in `data/`). Riconoscimento per firma delle colonne, non per nome del file.

1. **Check fidi (CreditBoard)** — xlsx, foglio "Result". Colonne: `Code` (codice cliente, leggere come
   stringa), `Name`, `Company Code`, `Company`, `Balance`, `Current`, `Overdue`, `Ordered`, `Delivered`,
   `Credit Limit` (fido attuale, impostato a mano), `% Fill`, `Code  Risk Class (AMF)` (classe di rischio;
   nota: doppio spazio nel nome), `Code  Cod. DORIS`, `Block Description`, `Turnover 12 months`, `Turnover`
   (NON usare: non è un dato a 12 mesi), `VAT`. 12.527 righe, importi RON. Celle vuote = 0 per gli importi.
2. **Cerved Slim Report** — xls (serve xlrd). Colonne chiave: `RIFERIMENTO` (= Code, letto come float),
   `PARTITA_IVA` (es. "RO 14697790"), `RAGIONE_SOCIALE`, `SCORE SEMAFORICO` (AFFIDABILE / CAUTELA /
   MASSIMA CAUTELA), `VALORE_FIDO` (fido suggerito), `VALUTA` (RON; una riga EUR), `CLASSE_AFFIDABILITA`,
   `FATTURATO_NO_BIL` (fatturato totale del cliente, RON). Problemi noti: 12 codici RIFERIMENTO duplicati
   (quasi sempre lo stesso cliente due volte; 30006208 è assegnato a due aziende diverse: AVI-TOP e AVICOD),
   4 righe senza RIFERIMENTO. NON c'è il patrimonio netto.
3. **AR124 Invoices (JDE)** — xlsx. Intestazioni con a-capo: `Customer\nNumber`, `Document\nNumber`,
   `Name\nAlpha`, `Individual\nTax\nID`, `Tax ID`, ..., `Invoice Date`, `Due Date`, `Gross\nAmount`,
   `Date Invoice Closed` (vuota = partita aperta). Contiene righe di totale ("Total 30000029"): tenere solo
   le righe con Customer Number interamente numerico. ~52.000 righe, 12 mesi a ritroso dal 20/11/2026.

4. **Anagrafica clienti MD105 (JDE)** — xlsx, **opzionale ma consigliato** (v3.2, decisione del 21/11/2026).
   Foglio "MD105.Customer Master": riga 1 = titolo, intestazioni in riga 2 (il riconoscimento prova le righe di
   intestazione 1, 2 e 3). Firma: `Cliente` + `Date - Account Opened` (+ `Descrizione Cliente`). Colonne usate:
   `Cliente` (= Code di Check fidi, stessa normalizzazione dei codici), `Date - Account Opened` (data di apertura del
   conto, date Excel 2006-08-31 … 2026-11-20; il 31/08/2006 è la data di migrazione JDE = "aperto prima del 2006",
   usata così com'è: cliente consolidato); facoltative `Descrizione Cliente`, `Stato Cliente`, `Tax ID`,
   `Payment Terms - A/R` (codici E01/E60…, letti ma **non ancora usati**). 5.293 righe, 47 colonne. Codice ripetuto:
   si tiene la data di apertura più vecchia (MD_DUP_CODE); righe senza codice scartate (MD_NO_CODE). Il file non
   conta tra i "mancanti": senza MD105 l'app funziona e l'anzianità viene da AR124.

La **data di riferimento** della simulazione è un parametro (default: la data più recente tra le fatture
AR124, cioè 20/11/2026).

## 4. Regole di calcolo v3.2 (default)

**v3.2 (decisione dell'utente del 21/11/2026): anzianità del cliente.** Le regole v3.1 sotto restano valide; la v3.2
cambia solo il fatturato mensile del Bisogno M1 e chi riceve il bonus/malus. `params.V31 = {"age_bands_enabled": False,
"behaviour_min_invoices": 0}` riproduce **esattamente** la v3.1 (con e senza MD105; fissato nei test).

- **Data di inizio dell'anzianità** (per cliente): la data di apertura del conto MD105; se la **prima fattura AR124**
  (importo > 0, in tutto il file, nessuna finestra, datata fino alla data di riferimento) è precedente all'apertura di
  **oltre 31 giorni** (codice ricreato in JDE) si usa la fattura (`age_source = "ar124_earlier"`, avviso
  AGE_INVOICE_BEFORE_OPENING con l'elenco: 81 clienti nel perimetro sui dati reali); senza MD105, o per un cliente che
  non c'è (avviso MD_CUSTOMER_MISSING), la prima fattura AR124 (`"ar124"`); né l'una né l'altra: nessuno storico.
- **Anzianità** (`age_months`) = mesi di calendario dalla data di inizio alla data di riferimento, con la frazione
  del mese successivo raggiunta (20/11/2025 → 20/11/2026 = 12; 20/08/2026 → 20/11/2026 = 3; 21/11/2025 → 20/11/2026 =
  11 + 30/31); apertura dopo la data di riferimento = 0.
- **Fasce** (parametri del gruppo "Anzianità cliente", primari): `age_bands_enabled` (sì), `new_customer_months` (3),
  `consolidated_months` (12), `behaviour_min_invoices` (3); validazione nuovo ≤ consolidato.
  - **NEW** (anzianità < 3): fatturato mensile = fatturato 12 mesi ÷ mesi di attività; bonus/malus sempre 0% (fascia
    bonus/malus `NEW_CUSTOMER`); segnalazione "cliente nuovo: confermare il fatturato con la stima commerciale"
    (`revenue_check_flag`).
  - **YOUNG** (3 ≤ anzianità < 12): fatturato 12 mesi ÷ mesi di attività; bonus/malus solo se c'è il minimo di fatture.
  - **CONSOLIDATED** (anzianità ≥ 12): regola v3.1 (÷ 12); bonus/malus come v3.1, anch'esso soggetto al minimo fatture.
  - **NO_HISTORY** (nessuna data MD105 e nessuna fattura): ÷ 12, bonus/malus 0%. Un cliente in MD105 senza fatture ha
    la fascia della sua data di apertura (bonus/malus comunque 0%: niente giorni misurati).
  - **Mesi di attività** (`months_active`) = anzianità, almeno 1 e **mai più di 12** (il fatturato è a 12 mesi; con
    `consolidated_months` > 12 un giovane di 15 mesi divide per 12); 12 per consolidati, senza storico e con le fasce
    spente. Esempio: 40.000 in 4 mesi → 10.000 al mese → M1 11.000 → fido 22.000 (v3.1: 17.000).
  - Bisogno **M1** = `monthly_revenue_used` × giorni / 30 × (1 + buffer).
- **Minimo fatture per il bonus/malus**: fatture con importo > 0 nella finestra dei giorni di pagamento, già scadute
  alla data di riferimento (scadenza ≤ data di riferimento) = `behaviour_invoices_n`; se < `behaviour_min_invoices`
  il bonus/malus è 0% (fascia `FEW_INVOICES`). Vale anche con le fasce spente (0 = nessun minimo).
- **Motivi**: sopra le regole di v3.1, dove il fido è la formula stessa (non zero, tetto, minimo o bonus/malus
  decisivo) e il fatturato è diviso per meno di 12 mesi (come mostrato, 1 decimale), il motivo è `R_NEW_CUSTOMER` /
  `R_YOUNG_CUSTOMER`; "perché cambia" `C_HIGHER_AGE` / `C_LOWER_AGE` (con fatturato, mesi, fatturato mensile).
- **Controllo dati** (`engine.coverage_finding`): con le fasce accese e **senza MD105**, se AR124 copre meno di
  `consolidated_months` + 6 mesi (dalla prima all'ultima data fattura; 18 con i default) → avviso AR_SHORT_HISTORY nella
  pagina Dati ("AR124 copre N mesi: … caricare MD105 per anzianità affidabili, oppure un AR124 di almeno 18 mesi") e
  banner su Risultati e Cliente. Con MD105 nessun avviso. Le fasce non si spengono mai da sole.

- **Censura a sinistra** (decisione del 21/11/2026): quando l'anzianità viene dalla prima fattura AR124 (senza MD105,
  cliente non in MD105, oppure codice ricreato con la fattura precedente all'apertura) e quella fattura cade entro
  **31 giorni dall'inizio del file AR124** (la data fattura più vecchia del file), la fattura non prova che il cliente
  è giovane (può aver comprato prima): cliente **CONSOLIDATO**, anzianità "almeno N mesi" (`age_censored`; pagina
  Cliente "≥ N mesi", passo S_AGE_CENSORED). Vale anche per i codici ricreati (62 degli 81 sui dati reali).

**Numeri di riferimento v3.2** (default; dati reali con MD105; fissati in `test_regression_v32_default`): attivi 2.116
· perimetro 1.598 (tutti in MD105) · fasce nel perimetro: nuovi **49**, giovani **205**, consolidati **1.344** (di cui
62 per censura a sinistra), senza storico 0 · fidi proposti **40.562.858** sugli attivi e **33.601.858** nel perimetro
· oltre fido nuovo **277** = **117** oltre un fido positivo + 160 a fido 0 · sforamento 7,04 M · più alto 803 / più
basso 618 / uguale 177 · da approvare 426 · bonus 729, tolleranza 221, malus 385, senza giorni misurati 55, senza
bonus/malus perché nuovi 49, per poche fatture 159 · effetto netto bonus/malus +423.000 (perimetro +348.000).
Per fascia (perimetro), v3.1 → v3.2: nuovi 244.000 → 448.000 RON (oltre un fido positivo 7 → 2); giovani 1.959.519 →
2.329.747 (22 → 14); consolidati 30.824.111 → 30.824.111 (101 → 101).
Senza MD105 (anzianità da AR124 di 12 mesi, con l'avviso; 1.138 clienti censurati → consolidati): nuovi 78, giovani
327, consolidati 1.138, senza storico 55; fidi 41.011.825 (perimetro 33.923.825), oltre fido 275 (115 oltre un fido
positivo).

### Regole v3.1 (base della v3.2)

**v3.1 (decisione dell'utente del 21/11/2026)**: il Bisogno M1 usa i **termini contrattuali**, mai i giorni
effettivi (altrimenti chi paga male riceve più credito); il comportamento di pagamento modifica il fido finale con
un **bonus/malus**. Default: `m1_days_basis = "contractual"`, `behaviour_enabled = sì` (bonus +5%, tolleranza 5
giorni, malus fino a −10% raggiunto a 30 giorni di ritardo). La formula **v3** precedente si ottiene con
`m1_days_basis = "measured"` e `behaviour_enabled = no` (`params.OLD_V3`); i suoi numeri restano fissati nei test.

Popolazione:
- Cliente **attivo** = `Balance ≠ 0` OPPURE `Turnover 12 months > 0`.
- **Intercompany esclusi** dall'intera simulazione: elenco modificabile, default
  `30001069` (SIAD BULGARIA EOOD), `30005389` (SIAD MACCHINE IMPIANTI SPA), `30001070` (SIAD SpA).
- **Esposizione** = Balance + Ordered + Delivered.
- Classi **speciali** (fido 0, cliente già bloccato in CreditBoard): S09, EV9, EV8, EK9, ES1, ET1, ET2, ET8, ET9, EU9.
- Classi **esenti** (mai bloccate; fido calcolato solo per monitoraggio): A8, EKM, EPS, EPU.
- Perimetro del **controllo ordini** (chi JDE fermerebbe davvero) = attivi, non intercompany, non speciali, non esenti.

Abbinamento Check fidi ↔ Cerved:
- Codici cliente normalizzati allo stesso modo nei tre file: spazi tolti; i codici numerici si confrontano per
  valore intero (`0030001`, `30001.0`, ` 30001 ` → `30001`).
- Prima per codice: `Code` = `str(int(RIFERIMENTO))`. **Decisione 20/11/2026**: se entrambe le partite IVA
  (normalizzate) sono presenti e diverse, la riga Cerved **non si usa** (conflitto IVA): si prova l'abbinamento
  per IVA; se nulla corrisponde, il cliente è "non in Cerved" (avviso con l'elenco, es. 71782284 AMERICAN FC).
  Se lo stesso codice compare più volte in Cerved, preferire la riga la cui partita IVA normalizzata coincide con
  quella di Check fidi; altrimenti la prima tra quelle senza conflitto. Parametro nascosto
  `cerved_reject_vat_conflict` (default sì; no = regola precedente, abbinamento per codice anche con IVA diversa).
- Poi, per i clienti non abbinati, per partita IVA normalizzata (solo lettere e cifre, maiuscolo, togliere
  il prefisso "RO" iniziale); se in Cerved più righe hanno la stessa IVA, la prima.
- Segnalare nella pagina Dati: codici duplicati, codici abbinati con IVA diversa, righe Cerved non abbinate.

Giorni di pagamento (per cliente), dalle fatture AR124:
- Fatture con data fattura negli ultimi `finestra` mesi (default 12) fino alla data di riferimento,
  solo importi > 0.
- Giorni per fattura, **come si vedevano alla data di riferimento** (nessun "senno di poi"): pagata entro la data
  di riferimento → `chiusura − fattura`; aperta alla data di riferimento (anche se chiusa dopo) e scaduta →
  `data riferimento − fattura` (ancora non pagata, valore minimo); aperta non scaduta → `scadenza − fattura`
  (si assume pagata a termine). Le fatture con data successiva alla data di riferimento si ignorano.
- Giorni misurati = **mediana ponderata per importo** (ordinare per giorni, prendere il valore in cui il peso
  cumulato raggiunge metà del totale).
- Termini contrattuali = mediana semplice di (`scadenza − fattura`) sulle fatture del cliente con **importo > 0**
  (note di credito escluse; decisione 20/11/2026), datate fino alla data di riferimento. Parametro nascosto
  `terms_positive_only` (default sì; no = regola precedente, tutte le righe).
- **Giorni per M1** (parametro `m1_days_basis`):
  - `"contractual"` (**default v3.1**): giorni usati = termini contrattuali con **minimo 15** (parametro); senza
    termini 30 giorni (parametro). Chi paga tardi non ottiene un M1 più grande; il comportamento agisce solo con il
    bonus/malus. Nessun massimo serve (giorni_max ≥ giorni usati sempre).
  - `"measured"` (v3): giorni usati = misurati (senza fatture: termini; senza nemmeno quelli: 30 giorni), con
    **minimo 15** e **massimo = termini + 15** (parametro; i termini del massimo hanno a loro volta minimo 15,
    fallback 30). Chi paga tardi ha un M1 più grande fino al massimo: il malus può non compensarlo.
- I giorni misurati restano calcolati e visibili (pagina Cliente) come base del bonus/malus.

Fido proposto:
1. Bisogno **M1** = (`Turnover 12 months` / 12) × (giorni usati / 30) × (1 + buffer). Buffer default 10%.
   (v3.2: / mesi di attività per i clienti nuovi e giovani, vedi sopra.)
   Fatturato negativo → 0.
2. Fido base = **moltiplicatore** (default **2**) × M1.
3. **Coefficiente di rischio** dallo score Cerved: AFFIDABILE 1,0 · CAUTELA 0,7 · MASSIMA CAUTELA 0,0 ·
   cliente non in Cerved (o senza score) 0,5. Fido = fido base × coefficiente.
   Parametro aggiuntivo: coefficiente per i clienti **esenti non in Cerved** (default = 0,5 come gli altri).
3b. **Bonus/malus di pagamento** (`behaviour_enabled`, default sì in v3.1). Ritardo = giorni misurati − termini
   contrattuali, entrambi come calcolati da AR124 **prima** di minimo 15 e massimo termini + 15 (colonna
   `delay_days`). Solo i clienti con giorni misurati lo ricevono; gli altri 0% (fascia "nessun dato").
   - ritardo ≤ 0 (paga in tempo o in anticipo): **+bonus_max** (default 5%), fascia BONUS;
   - 0 < ritardo ≤ `behaviour_tolerance_days` (default 5): 0%, fascia TOLERANCE;
   - ritardo > tolleranza: malus lineare da 0 alla tolleranza a **−malus_max** (default 10%) a
     `behaviour_full_malus_days` (default 30), poi resta −malus_max; fascia MALUS.
     Con i default: −10 → +5% · 0 → +5% · 5 → 0% · 6 → −0,4% · 17,5 → −5% · 30 → −10% · 60 → −10%.
   Fido = fido dopo il coefficiente × (1 + pct) (`limit_after_behaviour`), **prima** del tetto Cerved,
   dell'arrotondamento e del minimo: il tetto Cerved resta rigido, le classi speciali restano 0. Validazione:
   bonus e malus 0–50%, giorni ≥ 0, malus pieno > tolleranza. Il motore calcola anche il fido senza bonus/malus
   (`proposed_limit_no_behaviour`) e l'effetto netto (`behaviour_effect`). Motivo `R_BEHAVIOUR_BONUS` /
   `R_BEHAVIOUR_MALUS` quando il fido è la formula (coefficiente / formula piena) e il bonus/malus lo cambia
   (tetto, minimo e regole a zero vincono); "perché cambia" `C_HIGHER_BONUS` / `C_LOWER_MALUS` quando è decisivo
   (senza bonus non sarebbe più alto dell'attuale; senza malus non sarebbe più basso).
4. **Tetto Cerved**: se il cliente è in Cerved e VALORE_FIDO è valorizzato, fido = min(fido, VALORE_FIDO in RON).
   Con il tetto rigido (default) il valore usato è già quello in **RON interi**: VALORE_FIDO in RON **arrotondato a
   6 decimali e poi troncato** all'unità (4.582,72 → 4.582; 4.999,9999999 → 5.000), così passo 4, passo per passo,
   Excel e pagina Cliente mostrano lo stesso numero del fido proposto.
   VALORE_FIDO in EUR convertito al cambio (parametro RON per 1 EUR, default 4,975); valuta vuota = RON (con avviso);
   altra valuta (es. USD) o VALORE_FIDO negativo → nessun tetto per quel cliente, con avviso (mai assumere RON).
   VALORE_FIDO = 0 → fido 0. Il tetto si può disattivare (parametro).
5. Classi speciali → 0. Fatturato 12 mesi ≤ 0 → 0.
6. **Arrotondamento per eccesso** al multiplo di 1.000 RON (parametro: passo; e scelta eccesso / difetto).
7. **Minimo** 5.000 RON (parametro) per chi ha un fido > 0 dopo i passi precedenti.
8. **Il tetto Cerved è rigido** (parametro `ceiling_is_hard`, default sì; decisione 20/11/2026):
   fido finale = min(fido arrotondato con il minimo applicato, tetto Cerved), usando **il valore del tetto in RON
   interi** (troncato all'unità, non arrotondato per difetto al passo: un fido JDE non ha decimali). Esempi: bisogno
   4.526, Cerved 4.583 → 4.583 (non 4.000); Cerved 4.582,72 → 4.582; Cerved 867,14 → 867. Il minimo non
   porta mai un fido sopra il tetto; tetto 0 → 0. Un cliente il cui fido finale è uguale al tetto ha motivo
   "Limitato dal fido suggerito Cerved" (es. 30001755: 867, prima 0). Con `ceiling_is_hard = no` (più i due
   parametri nascosti sopra a "no") si riproducono i numeri di riferimento originali.

Controlli e indicatori per cliente:
- **Oltre fido** (nuovo / attuale): esposizione > fido, solo per i clienti nel perimetro del controllo.
- **Plausibilità**: `Turnover 12 months` / `FATTURATO_NO_BIL` > soglia (default **10%**) → "revisione manuale".
- **Approvazione**: serve se la variazione rispetto al fido attuale è oltre ±20% (parametro `approval_threshold`)
  **e** oltre 5.000 RON in valore assoluto (parametro `approval_min_change`, in "Altre impostazioni"; decisione
  finale 20/11/2026). Un cliente senza fido attuale con un fido proposto sopra 5.000 RON richiede approvazione.
- **Livello di approvazione** per importo in EUR (al cambio parametro): Tier 1 ≤ 50.000 €, Tier 2 ≤ 200.000 €,
  Tier 3 oltre (soglie parametro; provvisorie).
- **Motivo** (un codice + frase IT/EN) di ciò che ha determinato il fido proposto, in quest'ordine di priorità:
  intercompany (escluso) · classe speciale · nessun fatturato · massima cautela / fido Cerved zero ·
  tetto Cerved · minimo applicato · coefficiente < 1 (cautela / non in Cerved) · bisogno pieno (affidabile);
  "bisogno pieno" senza score affidabile (es. coefficiente "non in Cerved" portato a 1) ha una frase neutra
  (codice R_FULL_NEED_NEUTRAL), mai "affidabile".
  E un secondo testo: **perché cambia rispetto all'attuale**, sempre vero per il cliente: si cita "la formula dà
  X RON" (passo 6), mai "bisogno reale"; quando decide il tetto Cerved lo si dice (codici C_HIGHER_CERVED_CAP,
  C_*_MINIMUM_CAPPED, C_*_ROUNDED_CAPPED: il minimo o l'arrotondamento supererebbero il fido suggerito Cerved);
  il minimo ha codici propri (C_HIGHER_MINIMUM, C_LOWER_MINIMUM); C_HIGHER_ROUNDED quando solo l'arrotondamento
  porta sopra l'attuale. Elenco in `core/explain.py`, frasi in `core/texts.py`.
  Se i giorni sono limitati dal massimo: "Giorni di pagamento misurati 119; la formula ne conta al massimo 75
  (termini + 15)".
  **Un termine per concetto** (IT/EN): "Bisogno (M1)" / "Need (M1)" solo per M1; "moltiplicatore" / "multiplier"
  solo per il ×2; "coefficiente di rischio" / "risk factor" per il coefficiente dello score; "fido suggerito
  Cerved" per VALORE_FIDO, "tetto Cerved" per la regola.
  Motivo `R_CERVED_ZERO` quando il tetto in RON interi è 0 e il fido è 0 (es. Cerved 0,40 RON); un fido finale
  uguale al tetto in RON interi per effetto del tetto ha sempre motivo `R_CERVED_CAP`.

KPI principali (sui clienti nel perimetro del controllo, salvo diversa indicazione):
totale fidi proposti vs attuali **sia su tutti gli attivi sia sul perimetro** (due riquadri etichettati con la
popolazione), esposizione totale, clienti oltre fido nuovo vs attuale **divisi in oltre un fido positivo
(riquadro principale) e a fido 0 per regola** (massima cautela, Cerved 0, nessun fatturato...; per l'attuale: fido 0
in CreditBoard), con il totale sempre visibile,
esposizione oltre fido (somma degli sforamenti) nuovo vs attuale, clienti con fido più alto / più basso / uguale,
clienti a fido zero con fatturato, clienti con ordini aperti (Ordered > 0) oltre fido nuovo vs attuale,
clienti in revisione per plausibilità, clienti da approvare (con la materialità), ripartizione per score Cerved.

**Numeri di riferimento v3.1** (`params.V31`; default dal 21/11/2026 al passaggio a v3.2; fissati in `tests/test_regression.py`,
`test_regression_v31_default`): attivi 2.116 · perimetro 1.598 · fidi proposti **39.970.630** su tutti gli attivi
(v3: 39.714.684) e **33.027.630** nel perimetro (v3: 33.155.684; attuali 32,10 M) · oltre fido nuovo **290** =
**130** oltre un fido positivo + **160** a fido 0 (come v3) · sforamento **7,18 M** (v3: 6,98 M) · più alto **796** /
più basso **625** / uguale **177** · da approvare **425** (Tier 1 407, Tier 2 17, Tier 3 1) · nel perimetro: bonus
**868**, tolleranza **240**, malus **435**, senza giorni misurati **55** · effetto netto del bonus/malus
**+414.000** RON sugli attivi (+340.000 nel perimetro) · giorni limitati 0 · oltre fido nuovo per score: massima
cautela 96, cautela 84, non in Cerved 75, affidabile 35.

**Numeri di riferimento v3** (formula precedente, `params.OLD_V3`; decisioni del 20/11/2026 incluse; fissati in
`tests/test_regression.py`): attivi 2.116 (intercompany esclusi) · esposizione 36,12 M · fidi attuali 40,00 M ·
fidi proposti **39,71 M** · perimetro controllo 1.598 clienti · oltre fido nuovo **290** (sforamento **6,98 M**) ·
oltre fido attuale 267 (sforamento 9,86 M) · oltre fido nuovo **130 oltre un fido positivo + 160 a fido 0 per
regola**; attuale **202 + 65** · fidi nel perimetro attuali 32,10 M → proposti **33,16 M** (+1,06 M; sugli attivi
−0,29 M) · da approvare **421** (Tier 1 401, Tier 2 19, Tier 3 1; senza la materialità erano 1.295) ·
più alto **796** / più basso **614** / uguale **188** · zero con
fatturato (non speciali) **166** · plausibilità >10%: 22 clienti, 2,00 M di esposizione · in Cerved **1.174** attivi
(71% dell'esposizione) · oltre fido nuovo per score: massima cautela **96**, cautela **79**, non in Cerved 77,
affidabile 38.

Cosa cambia rispetto alla versione precedente (tetto rigido arrotondato per difetto: 39,69 M, oltre fido 293):
31 clienti cambiano fido, 3 cambiano stato di oltre fido.
- 29 per il tetto rigido "valore del tetto in RON interi": il fido sale al valore Cerved troncato all'unità
  (es. 30001755 da 0 a 867, 71856834 da 4.000 a 4.582, 30001539 Silcotub da 5.041.000 a 5.041.500). Tutti i fidi
  proposti sono in RON interi.
- 2 per il conflitto IVA: 71782284 AMERICAN FC (prima abbinato ad AMERICAN FOOD CATERING, fido Cerved 0) e
  71890497 RUSTIC FARM (prima massima cautela) diventano "non in Cerved" → minimo 5.000. In tutto 5 clienti hanno
  un conflitto IVA: 3 restano senza Cerved (71848719 MED LIFE sucursala, 71782284, 71890497), 2 si riabbinano
  per IVA (30004008 e 71623853, codici scambiati in Cerved); i loro fidi non cambiano.
- Termini solo da fatture positive: nessun fido cambia sui dati reali.

**Numeri di riferimento originali** (calcolati da tre implementazioni indipendenti; riprodotti esattamente con
`ceiling_is_hard = no`, `cerved_reject_vat_conflict = no`, `terms_positive_only = no`):
attivi 2.116 · esposizione 36,12 M · fidi attuali 40,00 M · fidi proposti 39,75 M ·
perimetro controllo 1.598 clienti · oltre fido nuovo 292 (sforamento 6,97 M) · oltre fido attuale 267
(sforamento 9,86 M) · più alto 797 / più basso 613 / uguale 188 · zero con fatturato (non speciali) 168 ·
plausibilità >10%: 22 clienti, 2,00 M di esposizione · in Cerved 1.177 attivi (71% dell'esposizione) ·
oltre fido nuovo per score: massima cautela 97, cautela 80, non in Cerved 77, affidabile 38.
Nota: il riferimento è stato calcolato con cambio EUR 5,0415 per l'unica riga Cerved in EUR; con 4,975 il
risultato non cambia. Implementazione di riferimento: `/home/claude/fido_v3_ref/`
(model.py + variants.py + variants2.py; risultati per cliente in reference_results.parquet).

**Robustezza dei file** (avvisi nella pagina Dati, mai errori criptici): AR124 con sole intestazioni accettato
(nessuna fattura); importi in testo letti in modo robusto ("12.500,00", "12,500.00", spazi, segni meno), quelli
non leggibili contati in un avviso; date in testo lette giorno/mese/anno (europeo), con avviso se non leggibili;
Check fidi con più Company Code: si tiene la società più frequente, con avviso; i file si leggono con
`dtype=object` (pandas non deve trasformare il testo "12.500" in 12,5); importi con soli separatori ambigui
("12.500", "120,000" senza altri indizi nella colonna) letti come migliaia nelle colonne di importo, con avviso
AMBIGUOUS_NUMBERS; date numeriche: seriali Excel (1–106.749), oppure date giuliane JDE (CYYDDD, es. 126001 =
01/01/2026) se tutta la colonna ha questa forma; altri numeri → data vuota + avviso BAD_DATES, mai file non
utilizzabile; gli avvisi di abbinamento seguono la regola di abbinamento attiva (MATCH_VAT_CONFLICT con la regola
di default, MATCH_VAT_DIFFERS con quella precedente); `terms_positive_only = no` usa davvero tutte le righe
(qualunque data e segno); `min_limit` e `rounding_step` sono numeri interi; colonne facoltative mancanti
(VAT di Check fidi; PARTITA_IVA, VALUTA, FATTURATO_NO_BIL, CLASSE_AFFIDABILITA di Cerved) disattivano solo la
funzione che ne dipende, con avviso.

## 5. Pagine dell'app

1. **Dati** — caricamento dei tre file (più MD105 opzionale, quarta scheda "Anagrafica clienti MD105 (opzionale)" /
   "Customer master MD105 (optional)") e stato: righe lette, clienti attivi, intercompany esclusi, abbinamenti
   Cerved (per codice / per IVA / nessuno), avvisi di qualità (duplicati, IVA diverse, righe di totale scartate),
   data di riferimento. Se manca un file, dire chiaramente cosa non si può calcolare.
2. **Risultati** — la risposta alla domanda "cosa cambia con la nuova formula?" (v3.2, con le fasce accese: tabella
   "per anzianità" — clienti, fidi attuali e proposti, oltre un fido positivo, oltre fido totale per fascia — e filtro
   per fascia; colonna "Anzianità" tra le "Più colonne"; banner se l'anzianità viene da un AR124 corto senza MD105):
   riquadri KPI nuovo vs attuale; grafici semplici (distribuzione della variazione; oltre fido per score);
   tabella clienti filtrabile (ricerca per nome/codice, score, più alto/più basso, oltre fido, revisione)
   con colonne: codice, nome, fido attuale, fido proposto, differenza, oltre fido, motivo breve (visibili senza
   scorrere a 1366 px); con "Più colonne": score, esposizione, scaduto, perché cambia, note; il testo completo è
   nella pagina Cliente; download Excel dei risultati.
3. **Cliente** — (v3.2: etichetta della fascia di anzianità con mesi e fonte; avviso "confermare il fatturato" per i
   nuovi; nel riquadro giorni: apertura MD105, prima fattura, anzianità, mesi di attività, fatture già scadute; il
   passo 2 mostra "fatturato 40.000 ÷ 4 mesi di attività") scelta di un cliente e calcolo passo per passo in linguaggio naturale con i numeri
   (come una tabella di esempio: passo / calcolo / RON), confronto con fido attuale ed esposizione,
   dati Cerved (fido suggerito in RON interi; motivo del rifiuto se la riga Cerved ha un'altra partita IVA),
   giorni di pagamento (misurati, termini, usati), plausibilità, approvazione. Esenti e classi speciali: oltre fido
   "non controllato" (per gli esenti: sopra / entro il fido di monitoraggio).
4. **Laboratorio** — (v3.2: gruppo "Anzianità cliente" con fasce sì/no, soglie nuovo / consolidato, minimo fatture
   per il bonus/malus; le tre soglie anche nella sensibilità) parametri modificabili a sinistra (raggruppati: Bisogno, Rischio, Tetti e arrotondamenti,
   Controlli), KPI dello scenario a confronto con lo scenario base (default v3) con le differenze;
   elenco dei clienti che cambiano rispetto allo scenario base (fido o stato oltre fido);
   analisi di sensibilità: scegliere UN parametro e un intervallo → grafico/tabella di fidi totali e clienti
   oltre fido al variare del parametro; salvare scenari con un nome e confrontarli in una tabella;
   esportare/importare scenari (JSON nella cartella `workspace/`).
5. **Regole** — le regole attive scritte in linguaggio naturale (generate dai parametri), in modo che un fido si
   possa rifare a mano: la formula in una riga, poi i passi in ordine con la provenienza di ogni dato (fatturato 12
   mesi da CreditBoard; giorni da AR124 con il trattamento delle fatture aperte; termini e tetto termini + 15; score
   e fido suggerito Cerved), perché ×2 (un cliente che paga come al solito usa circa metà del fido; il resto copre
   nuovi ordini e consegne non fatturate), perché massima cautela = 0 (ordini con pagamento anticipato, garanzia o
   eccezione approvata), a cosa serve il fido di monitoraggio degli esenti, cosa vuol dire "nel perimetro del
   controllo ordini", il minimo 5.000 salvo fido Cerved più basso. Non si afferma che 1.000.000 EUR sia il massimo
   Cerved (non confermato). Più un glossario e le classi speciali/esenti.

Selettore lingua IT / EN nella barra laterale. Tutte le stringhe in un unico modulo di testi.

## 6. Struttura del codice (consigliata)

```
fido_v3/
  app.py              # solo interfaccia Streamlit, sottile
  core/
    __init__.py
    loaders.py        # lettura e riconoscimento dei tre file, pulizia, avvisi di qualità
    params.py         # dataclass dei parametri con default v3, validazione, (de)serializzazione JSON
    engine.py         # calcolo vettoriale per cliente (pandas/numpy), nessuna dipendenza da Streamlit
    explain.py        # motivi, "perché cambia", passo-passo per cliente (IT/EN)
    kpi.py            # KPI e confronti tra scenari
    sensitivity.py    # variazione di un parametro
    export.py         # Excel dei risultati (xlsxwriter o openpyxl)
    texts.py          # tutte le stringhe IT/EN
  tests/              # test eseguibili con `python -m tests.run_all` (senza pytest obbligatorio)
  data/               # i tre file (già presenti per lo sviluppo)
  workspace/          # scenari salvati
  requirements.txt    # streamlit, pandas, numpy, openpyxl, xlrd, xlsxwriter
  run.bat / run.sh    # come quelli del vecchio fidosim (ambiente .venv isolato)
  LEGGIMI.md          # breve guida in italiano
```
Prestazioni: 12.527 righe Check fidi e ~52.000 fatture: caricamento e parsing in cache (st.cache_data),
ricalcolo di uno scenario < 1 s, analisi di sensibilità con ~10 punti in pochi secondi.
