# Riconciliazione Contabile

Sistema locale per verifica di coerenza tra estratto conto bancario e scheda contabile. Confronta le transazioni per identificare movimenti mancanti o non corrispondenti.

## Caratteristiche

- ✅ **100% Locale**: Nessun costo cloud, nessuna API esterna
- ✅ **Privato**: I dati non escono mai dal server
- ✅ **Veloce**: Parsing PDF nativi in < 1 secondo per 50 pagine
- ✅ **Deterministico**: Logica verificabile, nessuna allucinazione AI
- ✅ **Test Integrato**: Endpoint per testare il parsing prima di processare file completi

## Architettura

```
app/
├── core/                    # Configurazione, modelli Pydantic
│   ├── config.py           # Settings da .env
│   └── models.py           # Schemi request/response
├── services/               # Logica di business
│   ├── parsers.py          # Parser PDF (pdfplumber locale)
│   ├── ocr_service.py      # Wrapper per parsing
│   └── reconciliation_logic.py  # Logica di matching
└── routers/                # Endpoint FastAPI
    ├── health.py           # Health check
    ├── home.py             # Pagina principale con form upload
    ├── processing.py       # Riconciliazione completa (API)
    ├── results.py          # Pagina risultati HTML
    ├── test_ocr.py         # Test parsing OCR
    ├── debug_pdf.py        # Debugger struttura PDF
    └── documentation.py    # Pagina documentazione interna

data_input/                  # PDF da processare
data_output/                 # Report generati (JSON + CSV)
```

## Setup

### 1. Configurazione Ambiente

```bash
# Crea file .env (opzionale, per customizzazioni)
cp .env.example .env
```

### 2. Avvio con Docker

```bash
# Build e avvio
docker compose up --build

# In background
docker compose up -d --build
```

### 3. Accesso

- **Home Page**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Test Parser**: http://localhost:8000/test-ocr
- **Debugger PDF**: http://localhost:8000/debug-pdf
- **Documentazione**: http://localhost:8000/documentation
- **Health Check**: http://localhost:8000/health

## Utilizzo

### Interfaccia Web (Consigliato)

1. Accedi alla home page: http://localhost:8000
2. Seleziona il tipo di banca per l'estratto conto
3. Carica l'estratto conto bancario e la scheda contabile
4. Clicca "Avvia riconciliazione"
5. Attendi il completamento e visualizza i risultati nella pagina dedicata
6. Consulta i risultati nella pagina HTML
7. Dopo aver consultato i risultati, clicca su "Elimina job" per rimuovere i dati dalla memoria del server
8. Puoi utilizzare la funzione di stampa del browser (Ctrl+P / Cmd+P) o fare uno screenshot se necessario

### Test Parsing (Consigliato Prima)

1. Vai su http://localhost:8000/test-ocr
2. Seleziona tipo documento (Scheda Contabile o Estratto Conto)
3. Seleziona tipo banca (solo per estratto conto)
4. Carica un PDF di test (poche pagine)
5. Verifica i dati estratti nella pagina HTML
6. Se tutto ok, procedi con il file completo

### Riconciliazione via API

1. **Upload documenti**:
   ```bash
   curl -X POST "http://localhost:8000/api/v1/process" \
     -F "stratto_conto=@estratto_conto.pdf" \
     -F "scheda_contabile=@scheda_contabile.pdf" \
     -F "matching_tolerance=0.01"
   ```

2. **Recupera risultato**:
   ```bash
   curl "http://localhost:8000/api/v1/process/{job_id}"
   ```

3. **Output generato**:
   - `{job_id}_report.json`: Report completo JSON
   - `{job_id}_risultati.csv`: Tabella CSV con tutti i mismatch

## Workflow

```
1. Upload PDF → Estratto conto + Scheda contabile
2. Parsing Locale → pdfplumber estrae tabelle (CPU locale, gratis)
3. Riconciliazione → Pandas confronta i due DataFrame
4. Output → JSON report + CSV con mismatch evidenziati
```

## Logica di Verifica Coerenza

Il sistema esegue un controllo di coerenza tra estratto conto e scheda contabile:

- **Matching basato solo su importo**: Confronto valore assoluto con tolleranza configurabile (default ±0.01€)
- **Date per contesto**: Le date vengono estratte e utilizzate solo per identificare il match migliore quando ci sono più candidati con lo stesso importo, non per filtrare i match
- **Voci mancanti**: Identifica transazioni presenti in estratto conto ma non nella scheda contabile
- **Voci orfane**: Identifica transazioni presenti in scheda contabile ma non nell'estratto conto
- **Note su differenze date**: Quando un match viene trovato ma la differenza di data supera la tolleranza (default ±30 giorni), viene segnalato nelle note
- **Calcolo saldi**: Verifica differenza saldo totale a scopo informativo

## Output Report

Il report HTML include:

- **Statistiche riepilogative**: 
  - Totale transazioni estratte da entrambi i documenti
  - Match trovati / Voci mancanti / Voci orfane
  - Completion rate
  
- **Verifica saldi**:
  - Saldo totale estratto conto
  - Saldo totale scheda contabile
  - Differenza saldo
  
- **Tabelle problemi**:
  - Movimenti in banca non registrati in contabilità
  - Movimenti in contabilità assenti in banca
  - Match trovati ma con differenza data fuori tolleranza
  
- **Dettaglio completo**: Tabella espandibile con tutte le voci e stato matching

I report vengono mantenuti in memoria fino a quando l'utente non clicca sul pulsante "Elimina job" nella pagina dei risultati. Una pulizia automatica viene eseguita anche ogni giorno a mezzanotte per rimuovere job vecchi non eliminati manualmente.

## Reverse Proxy (Opzionale)

Per uso in produzione, si consiglia l'uso di **Nginx Proxy Manager** (o altro reverse proxy) per:

- Gestione domini multipli
- SSL/TLS
- Rate limiting
- Logging centralizzato

**Nota**: NPM non è incluso in questo progetto. Aggiungilo al tuo docker-compose principale se necessario.

Esempio configurazione NPM:
- Domain: `riconcilia.local`
- Forward: `riconcilia_contabile:8000`
- Schema: `http`

## Requisiti

- Docker e Docker Compose
- PDF nativi (non scansionati) per parsing ottimale
- Layout documenti compatibile con parser (vedi test OCR)

## Note Tecniche

- **Parser**: Usa pdfplumber per estrazione tabellare deterministica
- **Formati supportati**: PDF nativi vettoriali
- **Banche supportate**: Credit Agricole (altre in arrivo)
- **Formati valuta**: Gestisce automaticamente italiano (1.250,50) e inglese (1,250.50)
- **Date**: Gestisce formati vari (DD/MM/YYYY, DD.MM.YY, formato compatto 011024!)
- **Gestione memoria**: I job vengono eliminati manualmente dall'utente tramite il pulsante "Elimina job" nella pagina risultati, oppure automaticamente ogni giorno a mezzanotte se non eliminati manualmente
- **Configurazione**: Parametri configurabili via `.env` (tolleranza importi, tolleranza date, livello logging)

## Troubleshooting

**Parsing non funziona?**
- Usa `/test-ocr` per verificare il parsing su un documento di test
- Verifica che il PDF sia nativo (non scansionato)
- Controlla i logs: `docker compose logs web`

**Nessun match trovato?**
- Verifica che i formati date siano compatibili
- Controlla la tolleranza importi (default 0.01€)
- Verifica che le date siano entro la finestra di tolleranza (default ±5 giorni)

## Sviluppo

```bash
# Logs in tempo reale
docker compose logs -f web

# Restart servizio
docker compose restart web

# Rebuild completo
docker compose up --build --force-recreate
```
