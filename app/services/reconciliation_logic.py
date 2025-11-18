"""
Logica di riconciliazione tra estratto conto e scheda contabile

Questa funzione confronta i due DataFrame e identifica:
1. Cosa è presente nell'estratto conto ma NON nella scheda contabile (MANCANTE)
2. Cosa è presente nella scheda contabile ma NON nell'estratto conto (NON TROVATO IN BANCA)

Il matching viene fatto SOLO su:
- Importo (con tolleranza configurabile)
- Data (con tolleranza giorni configurabile)

I saldi sono calcolati solo a scopo informativo e NON vengono usati per il matching.
"""
import pandas as pd
from typing import Dict, Any, Tuple, List
import logging

logger = logging.getLogger(__name__)


def riconcilia_saldi(
    df_banca: pd.DataFrame,
    df_contabilita: pd.DataFrame,
    amount_tolerance: float = 0.01,
    date_tolerance_days: int = 5
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Riconciliazione bidirezionale tra estratto conto e scheda contabile.
    
    Verifica ENTRAMBE le direzioni:
    1. Estratto conto → Scheda contabile: cosa c'è in banca ma non in contabilità?
    2. Scheda contabile → Estratto conto: cosa c'è in contabilità ma non in banca?
    
    Il matching viene fatto SOLO su:
    - Importo (confronto valore assoluto con tolleranza)
    - Data (finestra di tolleranza in giorni)
    
    NOTA: I saldi vengono calcolati solo a scopo informativo e NON influenzano il matching.
    
    Args:
        df_banca: DataFrame estratto conto con colonne: data, descrizione, importo
        df_contabilita: DataFrame scheda contabile con colonne: data, descrizione, importo
        amount_tolerance: Tolleranza per confronto importi in euro (default 0.01 = 1 centesimo)
        date_tolerance_days: Finestra di tolleranza per date in giorni (default ±5 giorni)
        
    Returns:
        Tuple (risultati_df, summary_dict)
        - risultati_df: DataFrame con risultati matching, contiene:
          * Stato "OK": trovato in entrambi
          * Stato "MANCANTE": presente in estratto conto ma NON in scheda contabile
          * Stato "NON TROVATO IN BANCA": presente in scheda contabile ma NON in estratto conto
        - summary_dict: Statistiche (matched, missing, orfani) e saldi informativi
    """
    logger.info(f"Starting reconciliation: {len(df_banca)} bank transactions vs {len(df_contabilita)} accounting entries")
    
    # Creiamo copie per non modificare gli originali
    banca = df_banca.copy()
    contab = df_contabilita.copy()
    
    # Assicura che le colonne necessarie esistano
    required_banca = ["data", "importo"]
    required_contab = ["data", "importo"]
    
    for col in required_banca:
        if col not in banca.columns:
            raise ValueError(f"Missing required column '{col}' in bank DataFrame")
    
    for col in required_contab:
        if col not in contab.columns:
            raise ValueError(f"Missing required column '{col}' in accounting DataFrame")
    
    # Converti date se necessario
    if not pd.api.types.is_datetime64_any_dtype(banca['data']):
        banca['data'] = pd.to_datetime(banca['data'], errors='coerce')
    if not pd.api.types.is_datetime64_any_dtype(contab['data']):
        contab['data'] = pd.to_datetime(contab['data'], errors='coerce')
    
    # Converti importi
    banca['importo'] = pd.to_numeric(banca['importo'], errors='coerce')
    contab['importo'] = pd.to_numeric(contab['importo'], errors='coerce')
    
    # Aggiungi colonna per stato match
    banca['match_id'] = None
    contab['match_id'] = None
    
    # ============================================================================
    # Costruzione indici per matching più veloce
    # ============================================================================
    # Crea indici per importi nella contabilità per ricerca O(1) invece di O(n)
    # L'indice mappa importo -> lista di indici con quell'importo (entro tolleranza)
    def build_amount_index(df: pd.DataFrame, tolerance: float) -> Dict[float, List[Any]]:
        """
        Costruisce un indice che mappa importi (arrotondati alla tolleranza) a liste di indici.
        Permette ricerca veloce di candidati con importo simile.
        """
        index: Dict[float, List[Any]] = {}
        for idx, row in df.iterrows():
            amount = abs(row['importo'])
            if pd.isna(amount):
                continue
            # Arrotonda alla tolleranza per raggruppare importi simili
            rounded_amount = round(amount / tolerance) * tolerance
            if rounded_amount not in index:
                index[rounded_amount] = []
            index[rounded_amount].append(idx)
        return index
    
    contab_amount_index = build_amount_index(contab, amount_tolerance)
    
    risultati = []
    used_contab_indices = set()
    
    # Traccia duplicati per report
    duplicates_tracker: Dict[float, Dict[str, Any]] = {}  # importo -> {banca_count, contab_count, matched_count}
    
    # ============================================================================
    # ITERAZIONE 1: Verifica Estratto Conto → Scheda Contabile
    # ============================================================================
    # Per ogni movimento nell'estratto conto, verifica se è presente nella scheda contabile.
    # Obiettivo: trovare cosa c'è in banca ma NON in contabilità (MANCANTE).
    #
    # Matching basato SOLO su:
    # - Importo: valore assoluto con tolleranza (es. ±0.01 euro)
    # - Data: finestra di tolleranza (es. ±5 giorni)
    #
    # NOTA: Il saldo NON viene usato per il matching, solo importo e data.
    # ============================================================================
    
    # Traccia importi per rilevare duplicati
    banca_amount_counts: Dict[float, int] = {}
    
    for idx_b, row_b in banca.iterrows():
        # Estrai importo e data dal movimento bancario
        imp_b = abs(row_b['importo'])  # Usa valore assoluto per matching (ignora segno)
        data_b = row_b.get('data')
        
        # Skip se importo mancante/NaN
        if pd.isna(imp_b):
            logger.debug(f"Skipping bank transaction {idx_b} due to missing importo")
            continue
        
        # Traccia conteggio importi per duplicati
        rounded_imp = round(imp_b / amount_tolerance) * amount_tolerance
        banca_amount_counts[rounded_imp] = banca_amount_counts.get(rounded_imp, 0) + 1
        
        # Usa indice per ricerca veloce di candidati
        # Cerca nell'indice importi simili (entro tolleranza)
        candidate_indices = []
        for indexed_amount in contab_amount_index.keys():
            if abs(indexed_amount - imp_b) <= amount_tolerance:
                candidate_indices.extend(contab_amount_index[indexed_amount])
        
        # Filtra solo candidati non ancora usati
        candidati = contab.loc[
            [idx for idx in candidate_indices if idx in contab.index and pd.isna(contab.at[idx, 'match_id'])]
        ]
        
        # Inizializza risultato: assumiamo che non sia stato trovato (MANCANTE)
        status = "MANCANTE"
        desc_match = ""
        data_match = None
        importo_match = None
        date_diff_days = None
        note = ""
        
        if not candidati.empty:
            # Scegliamo il candidato con data più vicina (se disponibile)
            def _date_diff(candidate_row):
                candidate_date = candidate_row['data']
                if pd.isna(data_b) or pd.isna(candidate_date):
                    return float('inf')
                return abs((data_b - candidate_date).days)
            
            best_idx = min(candidati.index, key=lambda idx_c: _date_diff(candidati.loc[idx_c]))
            best_match = contab.loc[best_idx]
            
            contab.at[best_idx, 'match_id'] = idx_b
            used_contab_indices.add(best_idx)
            status = "OK"
            desc_match = best_match.get('descrizione', '')
            data_match = best_match['data']
            importo_match = best_match['importo']
            
            # Aggiorna tracker duplicati (il conteggio contab verrà aggiornato dopo)
            if rounded_imp not in duplicates_tracker:
                duplicates_tracker[rounded_imp] = {
                    'importo': rounded_imp,
                    'banca_count': 0,
                    'contab_count': 0,  # Verrà aggiornato dopo
                    'matched_count': 0
                }
            duplicates_tracker[rounded_imp]['matched_count'] = duplicates_tracker[rounded_imp].get('matched_count', 0) + 1
            
            if pd.notna(data_b) and pd.notna(data_match):
                date_diff_days = abs((data_b - data_match).days)
                note = f"Δ data {date_diff_days}g"
                if date_diff_days > date_tolerance_days:
                    note += " (fuori tolleranza)"
        # Aggiorna conteggio banca per duplicati
        if rounded_imp in duplicates_tracker:
            duplicates_tracker[rounded_imp]['banca_count'] = banca_amount_counts.get(rounded_imp, 0)
        
        # Aggiungi risultato: se status è "MANCANTE", significa che questo movimento
        # è presente in estratto conto ma NON nella scheda contabile
        risultati.append({
            "Data Banca": data_b,
            "Importo Banca": row_b['importo'],
            "Descrizione Banca": row_b.get('descrizione', ''),
            "Stato": status,
            "Data Contabilità": data_match,
            "Importo Contabilità": importo_match,
            "Descrizione Contabilità": desc_match,
            "Delta Giorni": date_diff_days,
            "Note": note
        })
    
    # ============================================================================
    # ITERAZIONE 2: Verifica Scheda Contabile → Estratto Conto
    # ============================================================================
    # Trova le voci nella scheda contabile che NON sono state matchate nell'iterazione 1.
    # Obiettivo: trovare cosa c'è in contabilità ma NON in banca (NON TROVATO IN BANCA).
    #
    # Queste voci possono indicare:
    # - Errori di registrazione in contabilità
    # - Registrazioni doppie
    # - Movimenti contabili che non hanno corrispondenza bancaria
    # ============================================================================
    orfani = contab[contab['match_id'].isnull()]  # Voci non matchate = orfani
    
    # Conta importi nella contabilità per duplicati
    contab_amount_counts: Dict[float, int] = {}
    for idx, row in contab.iterrows():
        imp = abs(row['importo'])
        if not pd.isna(imp):
            rounded_imp = round(imp / amount_tolerance) * amount_tolerance
            contab_amount_counts[rounded_imp] = contab_amount_counts.get(rounded_imp, 0) + 1
    
    # Aggiorna tracker duplicati con conteggi contabilità
    for rounded_imp, count in contab_amount_counts.items():
        if rounded_imp not in duplicates_tracker:
            duplicates_tracker[rounded_imp] = {
                'importo': rounded_imp,
                'banca_count': 0,
                'contab_count': count,
                'matched_count': 0
            }
        else:
            duplicates_tracker[rounded_imp]['contab_count'] = count
    
    for idx, row in orfani.iterrows():
        risultati.append({
            "Data Banca": None,  # Non presente in banca
            "Importo Banca": None,
            "Descrizione Banca": "---",
            "Stato": "NON TROVATO IN BANCA (Possibile Errore/Doppione)",
            "Data Contabilità": row['data'],
            "Importo Contabilità": row['importo'],
            "Descrizione Contabilità": row.get('descrizione', ''),
            "Delta Giorni": None,
            "Note": ""
        })
    
    risultati_df = pd.DataFrame(risultati)
    
    # ============================================================================
    # Calcolo Statistiche
    # ============================================================================
    matched = len(risultati_df[risultati_df['Stato'] == 'OK'])  # Trovati in entrambi
    missing = len(risultati_df[risultati_df['Stato'] == 'MANCANTE'])  # In banca ma non in contabilità
    orfani_count = len(risultati_df[risultati_df['Stato'].str.contains('NON TROVATO', na=False)])  # In contabilità ma non in banca
    date_mismatch = len(risultati_df[risultati_df['Note'].str.contains('fuori tolleranza', na=False)])
    
    # ============================================================================
    # Calcolo Saldi (SOLO A SCOPO INFORMATIVO - NON usati per matching)
    # ============================================================================
    # I saldi vengono calcolati solo per fornire informazioni aggiuntive nel report.
    # NON vengono usati per determinare se una voce è matchata o meno.
    # Il matching si basa SOLO su importo e data (vedi iterazioni sopra).
    saldo_banca = banca['importo'].sum()
    saldo_contabilita = contab['importo'].sum()
    differenza_saldo = saldo_banca - saldo_contabilita
    
    # Importi totali delle voci mancanti (in banca ma non in contabilità)
    missing_amount = risultati_df[risultati_df['Stato'] == 'MANCANTE']['Importo Banca'].sum()
    if pd.isna(missing_amount):
        missing_amount = 0.0
    
    # Importi totali delle voci orfane (in contabilità ma non in banca)
    orfani_amount = risultati_df[risultati_df['Stato'].str.contains('NON TROVATO', na=False)]['Importo Contabilità'].sum()
    if pd.isna(orfani_amount):
        orfani_amount = 0.0
    
    # ============================================================================
    # Analisi Duplicati
    # ============================================================================
    # Identifica importi che compaiono più volte e verifica se tutti sono matchati
    duplicates_report = []
    for rounded_imp, info in duplicates_tracker.items():
        banca_count = info.get('banca_count', 0)
        contab_count = info.get('contab_count', 0)
        matched_count = info.get('matched_count', 0)
        
        # Considera duplicato se compare più di una volta in almeno uno dei due
        if banca_count > 1 or contab_count > 1:
            # Calcola quanti non sono matchati
            unmatched_banca = max(0, banca_count - matched_count)
            unmatched_contab = max(0, contab_count - matched_count)
            
            if unmatched_banca > 0 or unmatched_contab > 0:
                duplicates_report.append({
                    'importo': rounded_imp,
                    'occorrenze_banca': banca_count,
                    'occorrenze_contabilita': contab_count,
                    'matchati': matched_count,
                    'non_matchati_banca': unmatched_banca,
                    'non_matchati_contabilita': unmatched_contab
                })
    
    summary = {
        "total_banca": len(banca),
        "total_contabilita": len(contab),
        "matched": matched,
        "missing_in_contabilita": missing,
        "orfani_in_contabilita": orfani_count,
        "completion_rate": (matched / len(banca) * 100) if len(banca) > 0 else 0.0,
        "date_mismatch": date_mismatch,
        "saldo_banca": float(saldo_banca),
        "saldo_contabilita": float(saldo_contabilita),
        "differenza_saldo": float(differenza_saldo),
        "importo_mancante": float(missing_amount),
        "importo_orfano": float(orfani_amount),
        "is_balanced": abs(differenza_saldo) < amount_tolerance,
        "duplicates": duplicates_report  # Lista di importi duplicati con dettagli
    }
    
    logger.info(f"Reconciliation complete: {matched} matched, {missing} missing, {orfani_count} orphans")
    
    return risultati_df, summary

