# Riconciliazione Contabile

Sistema locale per riconciliazione tra estratto conto bancario e scheda contabile. Verifica che ogni transazione dell'estratto conto (ground truth) sia presente nella scheda contabile.

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
    ├── processing.py       # Riconciliazione completa
    └── test_ocr.py         # Test parsing OCR

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

- **API Docs**: http://localhost:8000/docs
- **Test OCR**: http://localhost:8000/test-ocr
- **Health Check**: http://localhost:8000/health

## Utilizzo

### Test Parsing (Consigliato Prima)

1. Vai su http://localhost:8000/test-ocr
2. Seleziona tipo documento (Scheda Contabile o Estratto Conto)
3. Carica un PDF di test (poche pagine)
4. Verifica i dati estratti nella pagina HTML
5. Se tutto ok, procedi con il file completo

### Riconciliazione Completa

1. **Upload documenti** via API:
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

## Logica di Matching

Il sistema verifica che ogni transazione dell'estratto conto sia presente nella scheda contabile:

- **Matching su importo**: Valore assoluto con tolleranza (default ±0.01€)
- **Matching su data**: Finestra di tolleranza (default ±5 giorni)
- **Voci mancanti**: Alert per transazioni banca non trovate in contabilità
- **Voci orfane**: Warning per transazioni contabilità non presenti in banca
- **Calcolo saldi**: Verifica differenza saldo totale

## Output Report

Il report include:

- **Statistiche**: 
  - Totale transazioni estratte
  - Matched / Missing / Orfani
  - Completion rate
  
- **Saldi**:
  - Saldo totale estratto conto
  - Saldo totale scheda contabile
  - Differenza saldo
  
- **Dettagli**:
  - CSV con tutte le voci e stato matching
  - Flags per ogni problema rilevato

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
- **Formati valuta**: Gestisce automaticamente italiano (1.250,50) e inglese (1,250.50)
- **Date**: Gestisce formati vari (DD/MM/YYYY, DD.MM.YY, formato compatto 011024!)

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

## Licenza

Uso interno - Sistema proprietario
