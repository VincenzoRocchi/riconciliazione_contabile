"""
Parser locali per scheda contabile e estratto conto
Usa solo pdfplumber (CPU locale, gratis, veloce)
Nessun OCR/AI necessario - PDF nativi vettoriali

"""
import pdfplumber
import pandas as pd
import re
from datetime import datetime
from typing import Dict, Any, List, Tuple
import logging

logger = logging.getLogger(__name__)

# Regex/Pattern helpers
BANK_DATE_REGEX = re.compile(r'^\d{2}[./-]\d{2}[./-]\d{2,4}')
CURRENCY_REGEX = re.compile(r'^[\d.,-]+$')

# Keywords to identify table sections in estratto conto
BANK_HEADER_KEYWORDS = {"DATA", "VALUTA", "MOVIMENTI", "DESCRIZIONE"}
BANK_FOOTER_FIRST_WORDS = {
    "SALDO", "TOTALE", "RIEPILOGO", "NUMERO", "OPERAZIONI", "COMPETENZE", "INTERESSI", "IMPOSTE"
}
BANK_BALANCE_MARKERS = (
    "SALDO INIZIALE",
    "SALDO FINALE",
    "SALDO DISPONIBILE",
    "SALDO AGGIORNATO",
    "SALDO CONTABILE"
)
BANK_FOOTER_CONTAINS = (
    "RIEPILOGO",
    "TOTALE MOVIMENTI",
    "NUMERO OPERAZIONI",
    "VALUTA INTERESSI",
    "SCALARE"
)

CONTABILE_FOOTER_KEYWORDS = {
    "SALDO",
    "TOTALE",
    "RIEPILOGO",
    "PROGRESSIVO",
    "CHIUSURA",
    "FIRMA"
}

DATE_FORMATS = ["%d.%m.%y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y"]


def group_words_by_rows(words: List[dict], tolerance: float = 2.5) -> List[Tuple[float, List[dict]]]:
    """
    Raggruppa le parole estratte da pdfplumber per riga (coordinate Y simili).
    Restituisce una lista di tuple (top_y, row_words ordinati per X).
    """
    if not words:
        return []
    
    words_sorted = sorted(words, key=lambda w: w['top'])
    grouped: List[Tuple[float, List[dict]]] = []
    
    for word in words_sorted:
        top_y = word['top']
        if not grouped or abs(grouped[-1][0] - top_y) > tolerance:
            grouped.append((top_y, [word]))
        else:
            grouped[-1][1].append(word)
    
    # Ordina le parole per X per ogni riga
    normalized = []
    for top_y, row_words in grouped:
        row_words.sort(key=lambda w: w['x0'])
        normalized.append((top_y, row_words))
    
    return normalized


def parse_bank_date_token(raw_date: str):
    """Prova a convertire un token data dell'estratto conto in datetime.date"""
    if not raw_date:
        return None
    
    clean_token = raw_date.replace('*', '').strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(clean_token, fmt).date()
        except ValueError:
            continue
    
    # fallback: prova formato ggmmaa senza separatori
    return parse_date_contabile(clean_token)


def is_balance_row(text_upper: str) -> bool:
    """True se la riga fa riferimento ai saldi (iniziale/finale/aggiornato)."""
    return "SALDO" in text_upper and any(marker in text_upper for marker in BANK_BALANCE_MARKERS)


def is_footer_row(first_word_upper: str, text_upper: str) -> bool:
    """True se la riga appartiene al footer/riepilogo dell'estratto conto."""
    if first_word_upper in BANK_FOOTER_FIRST_WORDS:
        return True
    if set(text_upper.strip()) <= {"-", " "}:
        return True
    return any(marker in text_upper for marker in BANK_FOOTER_CONTAINS)


def append_description_continuation(rows_accumulator: List[dict], row_words: List[dict], desc_min_x: float) -> bool:
    """
    Se la riga è un proseguo della descrizione (nessuna data/importo, solo testo nella colonna descrizione),
    aggiunge il testo all'ultima transazione e restituisce True. Altrimenti False.
    """
    if not rows_accumulator:
        return False
    
    # Tutte le parole devono stare nell'area descrizione
    centers = [((w['x0'] + w['x1']) / 2) for w in row_words]
    if not centers or any(center < desc_min_x for center in centers):
        return False
    
    if any(CURRENCY_REGEX.match(w['text'].replace('*', '').strip()) for w in row_words):
        return False
    
    continuation = " ".join(
        w['text'].strip()
        for w in row_words
        if w['text'].strip() not in {"*", "!"}
    ).strip()
    
    if not continuation:
        return False
    
    rows_accumulator[-1]["descrizione"] = (
        f"{rows_accumulator[-1]['descrizione']} {continuation}".strip()
    )
    return True


def extract_credit_agricole_transaction(
    row_words: List[dict],
    dare_range: Tuple[float, float],
    avere_range: Tuple[float, float],
    desc_x_min: float
) -> Dict[str, Any]:
    """Estrae una singola transazione dall'estratto conto Credit Agricole."""
    raw_date = row_words[0]['text'].strip()
    date_obj = parse_bank_date_token(raw_date)
    if not date_obj:
        return None
    
    mov_dare_str = ""
    mov_avere_str = ""
    desc_words: List[str] = []
    
    for word in row_words[1:]:
        word_text = word['text'].strip()
        if not word_text or word_text in {"*", "!"}:
            continue
        
        word_center = (word['x0'] + word['x1']) / 2
        normalized = word_text.replace('*', '')
        
        # Skip colonna valuta (riporta ancora una data)
        if BANK_DATE_REGEX.match(normalized) and 60 <= word_center <= 110:
            continue
        
        if dare_range[0] <= word_center <= dare_range[1]:
            if CURRENCY_REGEX.match(normalized):
                mov_dare_str = normalized
            continue
        
        if avere_range[0] <= word_center <= avere_range[1]:
            if CURRENCY_REGEX.match(normalized):
                mov_avere_str = normalized
            continue
        
        if word_center >= desc_x_min and not re.match(r'^\d{10,}$', normalized):
            desc_words.append(normalized)
    
    mov_dare = clean_italian_currency(mov_dare_str) if mov_dare_str else 0.0
    mov_avere = clean_italian_currency(mov_avere_str) if mov_avere_str else 0.0
    
    if mov_dare <= 0 and mov_avere <= 0:
        return None
    
    tipo = "DARE" if mov_dare > 0 else "AVERE"
    importo = mov_dare if mov_dare > 0 else mov_avere
    desc = " ".join(desc_words).replace('\n', ' ').strip()
    
    if not desc or not any(ch.isalpha() for ch in desc):
        # Descrizione priva di testo -> probabilmente righe riepilogo/scalare
        return None
    
    return {
        "data": date_obj,
        "descrizione": desc,
        "importo": abs(importo),
        "tipo": tipo,
        "fonte": "BANCA"
    }


def is_contabile_data_row(row_words: List[dict]) -> bool:
    if not row_words:
        return False
    first_word = row_words[0]['text'].strip()
    return bool(re.match(r'^\d{6}', first_word))


def looks_like_contabile_footer(row_words: List[dict], data_started: bool) -> bool:
    """
    Heuristic to detect footer rows on scheda contabile last page.
    Trigger only after we have seen at least one data row on that page.
    """
    if not data_started or not row_words:
        return False
    
    row_text = " ".join(w['text'] for w in row_words).strip()
    row_text_upper = row_text.upper()
    first_word_upper = row_words[0]['text'].strip().upper()
    
    if set(row_text.replace('-', '').strip()) == set():
        return True
    
    if first_word_upper in CONTABILE_FOOTER_KEYWORDS:
        return True
    
    if any(keyword in row_text_upper for keyword in CONTABILE_FOOTER_KEYWORDS):
        return True
    
    # Very short row with no numeric tokens after data block -> likely footer separator
    meaningful_tokens = [w for w in row_words if w['text'].strip()]
    if len(meaningful_tokens) <= 2 and not re.search(r'\d', row_text):
        return True
    
    return False


def clean_italian_currency(val: Any) -> float:
    """
    Trasforma '1.250,50' in float 1250.50
    Gestisce anche valori già numerici
    (Versione robusta fornita dall'utente)
    """
    if not val:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    
    # Rimuovi tutto tranne numeri, virgole, punti e meno
    clean_str = re.sub(r'[^\d.,-]', '', str(val))
    
    if not clean_str or clean_str == '-':
        return 0.0
    
    # Determina formato: italiano (1.250,50) o inglese (1,250.50)
    if ',' in clean_str and '.' in clean_str:
        # Ha entrambi: determina quale è il separatore decimale
        comma_pos = clean_str.rfind(',')
        dot_pos = clean_str.rfind('.')
        
        if comma_pos > dot_pos:
            # Formato italiano: 1.250,50
            clean_str = clean_str.replace('.', '').replace(',', '.')
        else:
            # Formato inglese: 1,250.50
            clean_str = clean_str.replace(',', '')
    elif ',' in clean_str:
        # Solo virgola: probabilmente decimale (es. 1,50)
        if len(clean_str.split(',')) == 2 and len(clean_str.split(',')[1]) <= 2:
            clean_str = clean_str.replace(',', '.')
        else:
             # Probabilmente migliaia (es. 1,250)
            clean_str = clean_str.replace(',', '')
    elif '.' in clean_str:
         # Solo punto: probabilmente decimale (es. 1250.50) o migliaia (1.250)
        parts = clean_str.split('.')
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) != 2):
             # Migliaia (es. 1.250.000) o (1.250)
            clean_str = clean_str.replace('.', '')
        # Se è 1250.50 (decimale), è già corretto
    
    try:
        return float(clean_str)
    except ValueError:
        return 0.0


def parse_date_contabile(date_str: str) -> Any:
    """
    Gestisce il formato sporco della contabilità: '011024!', '0410241', etc.
    Estrae formato ggmmAA e converte in date
    """
    if not date_str:
        return None
    
    # Prende solo i primi 6 numeri (ggmmyy)
    match = re.search(r'(\d{2})(\d{2})(\d{2})', str(date_str))
    if match:
        day, month, year = match.groups()
        try:
            # Assumiamo anno 20xx
            return datetime.strptime(f"{day}/{month}/20{year}", "%d/%m/%Y").date()
        except ValueError:
            return None
    
    return None


def parse_scheda_contabile_wolters_kluwer(pdf_path: str) -> pd.DataFrame:
    """
    Parser deterministico per scheda contabile Wolters Kluwer (OSRA BPoint) basato su analisi PDF
    
    Struttura identificata:
    - Header: Y < 137.1 (skip)
    - Dati: Y tra 137.1 e ~701.1 (pagina normale), fino a 197.1 (ultima pagina)
    - Footer: Y > 197.1 (solo ultima pagina, skip)
    - Formato riga: DATA! COD!DESCRIZIONE ! ! ! ! ! DARE SALDO D/A
    - DARE: X tra 405-441 (media ≈428)
    - AVERE: Non presente nelle righe analizzate (solo DARE)
    - SALDO: X tra 526-570 (non usato per matching)
    - Descrizione: X tra 56-182 (prima dei separatori "!")
    
    Strategia: usa extract_words() + filtri header/footer + coordinate X fisse.
    """
    logger.info(f"Parsing scheda contabile Wolters Kluwer (DETERMINISTIC COORDINATE-BASED): {pdf_path}")
    rows = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Coordinate X identificate dall'analisi completa
            DARE_X_MIN = 405
            DARE_X_MAX = 441
            AVERE_X_MIN = 488  # Colonna AVERE identificata
            AVERE_X_MAX = 505
            DESC_X_MIN = 56
            DESC_X_MAX = 182  # Descrizione finisce prima dei separatori
            
            # Filtri Y per header/footer
            HEADER_Y_MAX = 130  # Skip righe prima di questo Y
            for page_num, page in enumerate(pdf.pages):
                
                words = page.extract_words()
                if not words:
                    continue
                
                rows_by_y = group_words_by_rows(words, tolerance=3)
                is_last_page = (page_num == len(pdf.pages) - 1)
                data_started_on_page = False
                
                # Processa ogni riga
                for top_y, row_words in rows_by_y:
                    # Skip header
                    if top_y < HEADER_Y_MAX:
                        continue
                    
                    if not row_words:
                        continue
                    
                    row_words.sort(key=lambda w: w['x0'])
                    
                    if is_last_page and looks_like_contabile_footer(row_words, data_started_on_page):
                        break
                    
                    # Identifica riga dati: prima parola deve essere data (6 cifre con "!")
                    if not is_contabile_data_row(row_words):
                        continue
                    
                    data_started_on_page = True
                    
                    # Estrai data (rimuovi "!" finale se presente)
                    raw_date = re.sub(r'[!]', '', row_words[0]['text'].strip())
                    
                    # Inizializza
                    desc_words = []
                    dare_str = ""
                    avere_str = ""
                    
                    # Processa parole della riga
                    for word in row_words[1:]:  # Salta data
                        word_text = word['text'].strip()
                        word_x0 = word['x0']
                        word_x1 = word['x1']
                        word_center = (word_x0 + word_x1) / 2
                        
                        if not word_text or word_text == "!":
                            continue
                        
                        # Skip indicatore D/A e saldo (X≈548+)
                        if word_text in ["D", "A"] or word_center > 520:
                            continue
                        
                        # Assegna in base a coordinate X
                        if DARE_X_MIN <= word_center <= DARE_X_MAX:
                            # È nella colonna DARE
                            if re.match(r'^[\d.,]+$', word_text):
                                dare_str = word_text
                        elif AVERE_X_MIN <= word_center <= AVERE_X_MAX:
                            # È nella colonna AVERE
                            if re.match(r'^[\d.,]+$', word_text):
                                avere_str = word_text
                        elif DESC_X_MIN <= word_center <= DESC_X_MAX:
                            # È parte della descrizione
                            # Salta codice (pattern tipo "150!" o "160!")
                            if not re.match(r'^\d+!?$', word_text) and word_text != "!":
                                desc_words.append(word_text)
                    
                    # Pulisci e converti valori
                    desc = " ".join(desc_words).strip()
                    dare = clean_italian_currency(dare_str) if dare_str else 0.0
                    avere = clean_italian_currency(avere_str) if avere_str else 0.0
                    
                    if dare == 0 and avere == 0:
                        continue
                    
                    # Parsing data
                    date_obj = parse_date_contabile(raw_date)
                    if not date_obj:
                        continue
                    
                    # Crea voci separate per DARE e AVERE
                    if dare > 0:
                        rows.append({
                            "data": date_obj,
                            "descrizione": desc,
                            "dare": dare,
                            "avere": 0.0,
                            "importo": abs(dare),  # Valore assoluto
                            "tipo": "DARE",
                            "fonte": "CONTABILITA"
                        })
                    
                    if avere > 0:
                        rows.append({
                            "data": date_obj,
                            "descrizione": desc,
                            "dare": 0.0,
                            "avere": avere,
                            "importo": abs(avere),  # Valore assoluto
                            "tipo": "AVERE",
                            "fonte": "CONTABILITA"
                        })
        
        if not rows:
            logger.warning("No transactions found in scheda contabile Wolters Kluwer")
            return pd.DataFrame(columns=["data", "descrizione", "dare", "avere", "importo", "tipo", "fonte"])
        
        df = pd.DataFrame(rows)
        logger.info(f"Successfully parsed {len(df)} transactions from scheda contabile Wolters Kluwer")
        return df
        
    except Exception as e:
        logger.error(f"FATAL Error parsing scheda contabile Wolters Kluwer: {e}")
        raise


def parse_scheda_contabile(pdf_path: str, accounting_type: str = "") -> pd.DataFrame:
    """
    Parser generico per scheda contabile che delega al parser specifico del gestionale
    
    Args:
        pdf_path: Percorso del PDF
        accounting_type: Tipo di gestionale:
            - wolters_kluwer (OSRA BPoint)
            - altre gestioni (in arrivo)
    
    Returns:
        DataFrame con colonne: data, descrizione, importo, tipo, fonte
    """
    logger.info(f"Parsing scheda contabile con accounting_type={accounting_type}")
    
    # Default a wolters_kluwer se non specificato
    if not accounting_type:
        accounting_type = "wolters_kluwer"
    
    func_name = f"parse_scheda_contabile_{accounting_type}"
    parser_func = globals().get(func_name)
    
    if parser_func and callable(parser_func):
        return parser_func(pdf_path)
    else:
        raise ValueError(f"Accounting type '{accounting_type}' not supported. Could not find function '{func_name}'.")


def parse_estratto_conto_credit_agricole(pdf_path: str) -> pd.DataFrame:
    """
    Parser deterministico per estratti conto Credit Agricole basato su analisi PDF
    
    """
    logger.info(f"Parsing estratto conto Credit Agricole (DETERMINISTIC COORDINATE-BASED): {pdf_path}")
    rows = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Coordinate X identificate dall'analisi completa
            dare_range = (150, 185)
            avere_range = (210, 250)
            desc_x_min = 240
            
            for page_num, page in enumerate(pdf.pages):
                
                words = page.extract_words()
                if not words:
                    continue
                
                rows_by_y = group_words_by_rows(words, tolerance=2.5)
                data_block_started = False
                page_rows = 0
                
                for top_y, row_words in rows_by_y:
                    if not row_words:
                        continue
                    
                    first_word = row_words[0]['text'].strip()
                    first_word_upper = first_word.upper()
                    row_text = " ".join([w['text'] for w in row_words]).strip()
                    row_text_upper = row_text.upper()
                    
                    if not row_text:
                        continue
                    
                    # Attiva la zona dati solo quando incontriamo la prima data valida
                    if not data_block_started:
                        if BANK_DATE_REGEX.match(first_word):
                            data_block_started = True
                            if is_balance_row(row_text_upper):
                                # Saldo iniziale: non conta come movimento ma sblocca la sezione dati
                                continue
                        elif any(keyword in first_word_upper for keyword in BANK_HEADER_KEYWORDS):
                            continue
                        else:
                            continue
                    
                    # Una volta nella sezione dati, interrompiamo se rileviamo footer/riepiloghi
                    if is_footer_row(first_word_upper, row_text_upper) or \
                       (is_balance_row(row_text_upper) and "INIZIALE" not in row_text_upper):
                        break
                    
                    is_data_row = BANK_DATE_REGEX.match(first_word) is not None
                    
                    if not is_data_row:
                        if append_description_continuation(rows, row_words, desc_x_min):
                            continue
                        # ignora righe descrittive/riassuntive
                        continue
                    
                    if "SALDO INIZIALE" in row_text_upper:
                        continue
                    
                    transaction = extract_credit_agricole_transaction(
                        row_words,
                        dare_range=dare_range,
                        avere_range=avere_range,
                        desc_x_min=desc_x_min
                    )
                    
                    if not transaction:
                        continue
                    
                    rows.append(transaction)
                    page_rows += 1
                
        
        if not rows:
            logger.warning("No transactions found in estratto conto Credit Agricole")
            return pd.DataFrame(columns=["data", "descrizione", "importo", "tipo", "fonte"])
        
        df = pd.DataFrame(rows)
        logger.info(f"Successfully parsed {len(df)} transactions from estratto conto Credit Agricole")
        return df
        
    except Exception as e:
        logger.error(f"FATAL Error parsing estratto conto Credit Agricole: {e}")
        raise


def parse_estratto_conto(pdf_path: str, bank_type: str = "") -> pd.DataFrame:
    """
    Parser generico per estratto conto che delega al parser specifico della banca
    
    Args:
        pdf_path: Percorso del PDF
        bank_type: Tipo di banca :
            - credit_agricole
            - altre banche
    
    Returns:
        DataFrame con colonne: data, descrizione, importo, fonte
    """
    logger.info(f"Parsing estratto conto con bank_type={bank_type}")
    
    func_name = f"parse_estratto_conto_{bank_type}"
    parser_func = globals().get(func_name)
    
    if parser_func and callable(parser_func):
        return parser_func(pdf_path)
    else:
        raise ValueError(f"Bank type '{bank_type}' not supported. Could not find function '{func_name}'.")