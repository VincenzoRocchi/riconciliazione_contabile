# Istruzioni per test locale

## Prerequisiti essenziali

Docker e Docker Compose devono essere installati sul sistema e la porta 8000 deve risultare libera prima di avviare i container.

## Setup e avvio

### Passo 1 – Posizionati nella cartella del progetto

```powershell
cd E:\riconciliazione_contabile
```

Assicurati che le directory `app\routers`, `app\services` e `app\core` siano presenti.

### Passo 2 – Build e avvio dei container

Esegui `docker compose up --build` per avviare in foreground oppure `docker compose up -d --build` per lanciare i servizi in background. Verifica poi lo stato con `docker ps` e controlla che il container `riconcilia_contabile` risulti attivo.

### Passo 3 – Accesso alle interfacce

Apri il browser e raggiungi:

Home page: [http://localhost:8000](http://localhost:8000)  
Test Parser OCR: [http://localhost:8000/test-ocr](http://localhost:8000/test-ocr)  
Debugger PDF: [http://localhost:8000/debug-pdf](http://localhost:8000/debug-pdf)  
Documentazione interna: [http://localhost:8000/documentation](http://localhost:8000/documentation)  
API Docs FastAPI: [http://localhost:8000/docs](http://localhost:8000/docs)  
Health Check: [http://localhost:8000/health](http://localhost:8000/health)

## Percorsi di test consigliati

### Scenario A – Test parser OCR

Accedi a `/test-ocr`, scegli il tipo di documento (scheda contabile oppure estratto conto), carica un PDF di poche pagine e verifica le statistiche e la tabella risultante. Controlla che date, importi e descrizioni siano consistenti. In caso di layout inediti usa questo step prima della riconciliazione completa.

### Scenario B – Analisi struttura PDF

Utilizza `/debug-pdf` per caricare un PDF e visualizzare testo, coordinate e tabelle estratte da pdfplumber. Lo strumento è utile quando devi capire come adattare i parser o quando ricevi documenti fuori standard.

### Scenario C – Riconciliazione end-to-end

Dalla home seleziona il tipo di banca per l'estratto conto, carica l'estratto conto nella sezione dedicata e la scheda contabile nell'area sottostante, quindi premi "Avvia riconciliazione". Attendi la conclusione del job e analizza la pagina dei risultati: pannello riepilogativo con statistiche, verifica saldi, tabelle separate per movimenti mancanti/orfani/differenze date, e dettaglio completo espandibile. **Importante**: Dopo aver consultato i risultati, clicca sul pulsante "Elimina job" per rimuovere i dati dalla memoria del server. Puoi utilizzare la funzione di stampa del browser (Ctrl+P / Cmd+P) o fare uno screenshot se necessario.

### Scenario D – Consultazione documentazione

Apri `/documentation` per leggere README e istruzioni di test direttamente dall’interfaccia. È il riferimento unico per operatori e sviluppatori, aggiornato automaticamente dai file Markdown del repository.

## Logging e diagnostica

Visualizza i log in tempo reale con `docker compose logs -f web` oppure limita l’output agli ultimi messaggi tramite `docker compose logs --tail=50 web`. In caso di errori al boot usa `docker compose logs web` e, se necessario, ricostruisci tutto con `docker compose down` seguito da `docker compose up --build --force-recreate`.

## Risoluzione problemi comuni

Porta 8000 occupata: modifica la sezione `ports` in `docker-compose.yml` (esempio `8001:8000`) e accedi tramite la nuova porta.  
PDF non parsato: assicurati che il file sia nativo, verifica i log, testa il documento con `/test-ocr` e ispeziona la struttura con `/debug-pdf`.  
Directory mancanti: crea `data_input` e `data_output` se non esistono (`mkdir data_input`, `mkdir data_output`).  
Pulizia file temporanei: al termine delle prove esegui `docker compose down -v` per rimuovere container e volumi, oppure `docker compose down --rmi all` per eliminare anche le immagini.

## Note operative

I file caricati vengono salvati provvisoriamente in `data_input`, i report JSON/CSV finiscono in `data_output` e l'intero sistema lavora in locale senza chiamate esterne. I job di riconciliazione vengono mantenuti in memoria e devono essere eliminati manualmente dall'utente tramite il pulsante "Elimina job" nella pagina risultati, oppure vengono eliminati automaticamente ogni giorno a mezzanotte tramite un job di pulizia automatica se non eliminati manualmente. L'autoreload di Uvicorn è attivo, quindi le modifiche al codice vengono applicate automaticamente durante lo sviluppo.
