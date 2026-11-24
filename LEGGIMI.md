# Simulatore Fido SIAD Romania (v3.2, versione 3.6)

Calcola il fido proposto per i clienti di SIAD Romania (società 42, RON) con la formula v3.2,
lo confronta con il fido attuale e spiega ogni differenza.

**Formula v3.2 (default dal 21/11/2026): anzianità del cliente.** L'anzianità = mesi dalla **data di apertura
del conto** (anagrafica clienti JDE **MD105**) alla data di riferimento; se la prima fattura AR124 è più vecchia
dell'apertura di oltre 31 giorni (codice ricreato) si usa la fattura; senza MD105 (o per un cliente che non c'è)
la prima fattura AR124; se quella fattura cade nei primi 31 giorni del file AR124 il cliente può aver comprato prima
ed è trattato come **consolidato** ("≥ N mesi"). Tre fasce: **nuovo** (sotto 3 mesi), **giovane** (3–12 mesi), **consolidato** (da 12 mesi).
Per nuovi e giovani il fatturato mensile = fatturato 12 mesi ÷ mesi di attività (almeno 1, al massimo 12: es.
40.000 in 4 mesi → 10.000 al mese), non ÷ 12; i nuovi non ricevono bonus/malus e il loro fatturato va confermato
con la stima commerciale. Il bonus/malus richiede almeno **3 fatture già scadute** nella finestra, altrimenti 0%.
I consolidati e i clienti senza storico restano con la regola v3.1 (÷ 12). Tutto nel Laboratorio, gruppo
**Anzianità cliente**: fasce spente e minimo fatture 0 = formula v3.1 identica.

**Formula v3.1 (21/11/2026, resta la base della v3.2).** Il Bisogno (M1) usa i **termini contrattuali** del cliente
(almeno 15 giorni; senza termini 30), mai i giorni effettivi: così chi paga male non riceve più credito. Il
comportamento di pagamento cambia il fido con un **bonus/malus**: ritardo = giorni misurati − termini; in tempo
o in anticipo **+5%**; fino a 5 giorni di ritardo 0%; oltre, un malus che cresce fino a **−10%** a 30 giorni di
ritardo. Si applica dopo il coefficiente di rischio e prima del tetto Cerved (che resta rigido). La formula v3
precedente (giorni misurati con massimo termini + 15, nessun bonus/malus) si ritrova nel Laboratorio:
"Giorni per il Bisogno (M1)" = Misurati e bonus/malus spento. Tutto gira in locale sul PC:
nessun dato esce dal computer.

## Come si avvia

- **Windows**: doppio clic su `run.bat`.
- macOS / Linux: `./run.sh` da un terminale.

Serve Python 3.10 o superiore (python.org). Al primo avvio lo script crea un ambiente Python
isolato (cartella `.venv`) e installa le librerie: ci vuole qualche minuto e serve internet.
Dai giorni successivi parte in pochi secondi. L'app si apre nel browser; per chiuderla basta
chiudere la finestra nera del terminale.

**Dopo un aggiornamento** (nuovi file scaricati o `git pull`) chiudere la finestra nera del simulatore e
riaprire `run.bat`: un simulatore già aperto continua a usare il codice vecchio. La versione in uso è
scritta in fondo alla barra laterale (es. "Versione 3.6 · 22/11/2026").

## Caricare i file

L'app parte **vuota**. Nella pagina **Dati** trascina i quattro file (tre obbligatori più MD105 opzionale ma
consigliato; anche tutti insieme; il nome non conta, il tipo si riconosce dalle colonne):

1. **Check fidi** (CreditBoard, `.xlsx`): clienti, esposizione, fido attuale, fatturato 12 mesi.
2. **Cerved Slim Report** (`.xls`): score, fido suggerito, fatturato totale del cliente.
3. **AR124** (JDE, `.xlsx`): fatture degli ultimi 12 mesi, da cui si misurano i giorni di pagamento.
4. **Anagrafica clienti MD105** (JDE, `.xlsx`, **opzionale, consigliato**): foglio "MD105.Customer Master" con il
   titolo in riga 1; servono le colonne "Cliente" e "Date - Account Opened" (data di apertura del conto, da cui
   l'anzianità del cliente; il 31/08/2006 è la data di migrazione JDE = cliente aperto prima del 2006).

Basta Check fidi per un primo calcolo; senza Cerved o senza AR124 l'app dice chiaramente cosa non
può calcolare. **Senza MD105** l'anzianità viene dalla prima fattura AR124: con soli 12 mesi di fatture un
acquirente occasionale sembra un cliente nuovo, quindi la pagina Dati lo segnala e Risultati e Cliente
mostrano un avviso (caricare MD105, oppure un AR124 di almeno 18 mesi); le fasce restano accese. I file restano caricati finché la finestra del browser è aperta: a ogni nuovo avvio
si ricaricano.

Per chi preferisce un avvio già compilato: impostando la variabile d'ambiente `FIDO_DATA_DIR`
con il percorso di una cartella, l'app carica automaticamente i file che trova lì.

## Le pagine (una domanda per pagina)

| Pagina | Domanda | Cosa si trova |
|---|---|---|
| **Dati** | I dati sono completi e affidabili? | I quattro file (MD105 opzionale), i clienti attivi, l'abbinamento con Cerved, i controlli di qualità e la data di riferimento. |
| **Risultati** | Cosa cambia con la nuova formula? | Riquadri nuovo vs attuale: in primo piano i clienti **oltre un fido positivo** (117 contro 202 oggi; v3.1: 130), accanto il totale oltre fido (277 = 160 a fido 0 per regola + 117); totale fidi sia sul **perimetro del controllo ordini** (1.598 clienti: 33,60 mln, +1,50 mln) sia su **tutti gli attivi** (2.116: 40,56 mln, +0,56 mln); esposizione oltre fido, ordini aperti, da approvare; la tabella **per anzianità** (nuovi / giovani / consolidati / senza storico: clienti, fidi, oltre fido) e il filtro per anzianità. Due grafici, la tabella clienti (codice, nome, attuale, proposto, differenza, oltre fido, motivo breve; "Più colonne" per il resto), il download Excel. Un clic su una riga apre il cliente con il testo completo. |
| **Cliente** | Come si arriva a questo fido? | L'etichetta di anzianità (es. "Cliente giovane · 4 mesi"), il calcolo in 11 passi (il passo 2 dice come si ottiene il fatturato mensile: "fatturato 40.000 ÷ 4 mesi di attività") con i numeri (il passo 7 è il bonus/malus di pagamento; 10 passi con l'opzione spenta) (si può rifare a mano), il motivo e il "perché cambia" (sempre veri per il cliente: "la formula dà X RON"), dati Cerved (fido suggerito in RON interi, motivo se la riga Cerved è di un'altra partita IVA), giorni di pagamento (misurati, termini, ritardo e bonus/malus), controlli, fatture. Esenti e classi speciali: oltre fido "non controllato". |
| **Laboratorio** | Quale formula funziona meglio? | I parametri a sinistra; a destra i KPI confrontati con la formula v3.2, i clienti che cambiano, l'analisi di sensibilità e gli scenari salvati. |
| **Regole** | Quali regole sono attive? | La formula in una riga e i passi in ordine, con la provenienza di ogni dato, perché ×2, perché massima cautela = 0, a cosa serve il fido di monitoraggio; un glossario e le classi di rischio speciali ed esenti. Scaricabili in testo per il verbale. |

La lingua (IT / EN) si cambia nella barra laterale e non cambia nessun numero. Nella barra
laterale si vede sempre se si sta guardando la formula v3.2 o una formula modificata.

### La pagina Cliente (v3.3)

In alto il nome con le etichette colorate (anzianità, score Cerved, classe, esente/speciale e, se già letto,
il giudizio del bilancio), i quattro riquadri (fido attuale, proposto, esposizione, oltre fido) e la
risposta in due frasi. Subito sotto, sempre visibile, il riquadro **Controllo sul bilancio (ANAF)** con
il tasto e il verdetto. Sotto ancora, quattro schede: **Calcolo del fido** (gli 11 passi), **Cerved, pagamenti e
controlli**, **Bilancio pubblico (ANAF)**, **Fatture**.

Nella scheda **Calcolo del fido**, sotto gli 11 passi, il grafico **Acquisti e blocchi mese per mese**
sugli ultimi 12 mesi di calendario (dal 1° all'ultimo giorno; il mese in corso arriva alla data di
riferimento):

- barre: fatturato del mese (AR124);
- linea scura: esposizione più alta del mese, cioè le partite aperte giorno per giorno. Ogni fattura conta
  dal giorno di emissione al giorno in cui è pagata, anche se resta aperta nei mesi dopo o è scaduta. In
  Romania la consegna si fattura subito, quindi le fatture rappresentano le consegne; mancano solo gli ordini
  non ancora consegnati e le partite aperte più vecchie del file AR124;
- linea rossa: la parte **scaduta da più di 5 giorni** (la tolleranza del bonus/malus). Un cliente puntuale ha
  comunque l'esposizione alta quanto i suoi termini: con 90 giorni sono circa 3 mesi di acquisti (es. PHINIA
  DELPHI 71779810: linea scura che sale fino a 275.870 perché comprano di più, linea rossa sempre a 0);
- linee tratteggiate: fido attuale (quello di oggi, applicato a tutto l'anno) e fido proposto;
- colore della barra: in quel mese l'esposizione ha superato il fido proposto, quello attuale, entrambi o
  nessuno, cioè un nuovo ordine sarebbe andato in blocco. Sotto, in una frase, i mesi di blocco con ciascun fido.

Se un cliente consolidato ha **3 o più mesi senza acquisti** su 12, in cima alla scheda compare un avviso:
la media su 12 mesi contro la media dei soli mesi con acquisti e il fido che ne verrebbe. Esempio ACTIV
METAL GAZ (30002232): nessun acquisto da dicembre ad aprile, 22.940 contro 39.325 al mese, fido 53.000
contro circa 91.000 (oggi 90.000); con 53.000 gli ordini si sarebbero bloccati in 5 mesi (giugno, luglio,
agosto, ottobre, novembre), con 90.000 mai. È solo una spiegazione: **la formula non cambia**.

### Bilancio pubblico (ANAF)

Il tasto **"Leggi l'ultimo bilancio"** (nel riquadro sopra le schede) interroga il servizio pubblico ANAF
(`https://webservicesp.anaf.ro/bilant?an=ANNO&cui=CUI`, gratuito, senza credenziali) con la partita IVA
del cliente e prende l'ultimo anno depositato (l'anno scorso, poi i due precedenti). È un **secondo
parere: non entra nella formula.**

1. **Il verdetto**, in una frase: il fido proposto va bene / va bene ma da seguire / è troppo alto e
   **un fido corretto è X**. Accanto: fido proposto, fido che il bilancio regge, fido corretto, fido attuale.
2. **La regola**: un'azienda regge un fido fino al **10% del patrimonio netto**; il **5%** se ha un punto
   debole (perdita d'esercizio, debiti oltre 3 volte il patrimonio, attivo circolante sotto 0,8 volte i
   debiti). Arrotondato per difetto al migliaio. Patrimonio negativo: fido corretto 0 (solo con anticipo o
   garanzia). Se la formula dà 0 ma il bilancio è sano, si dice fino a quanto il bilancio reggerebbe.
   Un bilancio più vecchio di 18 mesi è segnalato.
3. **Il bilancio in parole semplici**, sei domande: quanto è grande, guadagna, quanto vale, quanti debiti
   ha, riesce a pagare i conti, quanto pesa SIAD. Verde = bene, arancio = attenzione, rosso = male.
4. In un riquadro richiudibile tutti i numeri e gli indicatori pubblicati da ANAF; in un altro le soglie,
   modificabili per la sessione.

Esempi (bilanci 2025): SC Atmosferica 26.790 proposto → troppo alto, corretto 16.000 (debiti 7 volte il
patrimonio); Covrig Crocant e Spot Serv: il bilancio conferma lo 0 (patrimonio negativo); Prysmian va
bene ma è in perdita.

Serve la connessione a Internet; ANAF accetta una richiesta al secondo. Le risposte restano salvate in
`workspace/anaf/` e alla visita successiva si vedono senza rete (il tasto diventa "Aggiorna da ANAF").
Gli enti pubblici (ospedali, comuni) non depositano questo bilancio e risultano "non trovati";
le partite IVA estere non si possono cercare.

## Il Laboratorio con il team rumeno

1. Partire dalla formula v3.2 (pulsante **Ripristina default v3.2**) e mostrare i riquadri: clienti
   oltre un fido positivo, oltre fido in totale (con quelli a fido 0 per regola) ed esposizione
   oltre fido sono il metro di giudizio. I fidi attuali sono stati gonfiati di proposito: il
   confronto con l'attuale spiega cosa cambia, non giudica la formula.
2. Cambiare **un parametro alla volta** (es. moltiplicatore, coefficiente di rischio cautela, fido minimo).
   L'approvazione serve solo se il fido cambia più del 20% **e** più di 5.000 RON (soglia in RON in
   "Altre impostazioni"). In italiano i valori dei cursori sono scritti nell'etichetta (es. "Cautela: 0,70").
   I numeri si aggiornano subito; le frecce dicono la differenza rispetto a v3.2.
   Il gruppo **Anzianità cliente** accende/spegne le fasce, regola le soglie (nuovo sotto 3 mesi, consolidato da 12)
   e il minimo di fatture già scadute per il bonus/malus (3; 0 = nessun minimo).
   Il gruppo **Comportamento di pagamento** accende/spegne il bonus/malus e ne regola bonus, malus massimo,
   tolleranza e giorni del malus pieno; con l'opzione accesa compaiono i riquadri clienti con bonus / con malus
   ed effetto netto in RON. Nel gruppo Bisogno si sceglie se M1 usa i termini contrattuali o i giorni misurati. La scheda
   **Effetto** elenca i clienti che cambiano: un clic su una riga apre il dettaglio del cliente.
3. Per vedere l'effetto di un parametro su tutto un intervallo usare **Sensibilità**: scegliere
   il parametro, da / a, premere **Calcola** (9 valori).
4. Quando una proposta convince, darle un nome nella scheda **Scenari** e premere **Salva**. La
   tabella degli scenari mette a confronto v3.2, i fidi attuali e tutti gli scenari salvati.
5. Gli scenari sono file JSON nella cartella `workspace/` (uno scenario salvato prima della v3.2 non ha i nuovi
   parametri e si apre con i default v3.2: fasce di anzianità accese, minimo 3 fatture; prima della v3.1 anche
   termini contrattuali e bonus/malus acceso): si possono esportare, mandare per
   e-mail ai colleghi e reimportare. Tutte le pagine (Risultati, Cliente, Regole) seguono lo
   scenario attivo.

## Per chi mantiene il codice

- `app.py` è solo la cornice; le pagine sono in `ui/pages/`, lo stato condiviso in `ui/common.py`,
  la logica di presentazione (senza Streamlit) in `ui/logic.py`, gli scenari in `ui/scenarios.py`.
- Il calcolo è in `core/` (vedi `core/API.md`), tutte le frasi IT/EN in `core/texts.py`.
- Test: `python -m tests.run_all` (motore e interfaccia, circa un minuto).
- Le variabili d'ambiente `FIDO_DATA_DIR` e `FIDO_WORKSPACE_DIR` cambiano le cartelle dei dati e
  degli scenari (usate dai test).
