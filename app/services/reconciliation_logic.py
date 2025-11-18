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
from itertools import combinations
from math import comb
from typing import Optional

logger = logging.getLogger(__name__)


def find_subset_sum_backtrack(
    candidates: List[Tuple[Any, float]],  # Lista di (idx, importo)
    target: float,
    tolerance: float = 0.01,
    max_size: int = 5
) -> Optional[List[Any]]:
    """
    Trova una combinazione di candidati che somma al target usando backtracking.
    Molto più efficiente del brute force perché si ferma alla prima soluzione
    e esclude branch impossibili.
    
    Args:
        candidates: Lista di tuple (idx, importo) dei candidati
        target: Importo target da raggiungere
        tolerance: Tolleranza per il matching
        max_size: Dimensione massima della combinazione
        
    Returns:
        Lista di indici che formano la combinazione, o None se non trovata
    """
    # Filtra candidati validi e ordina per importo decrescente (più probabili prima)
    valid_candidates = [(idx, abs(amt)) for idx, amt in candidates if not pd.isna(amt) and abs(amt) > 0]
    valid_candidates.sort(reverse=True, key=lambda x: x[1])
    
    if not valid_candidates:
        return None
    
    def backtrack(start: int, current_sum: float, path: List[Any]) -> Optional[List[Any]]:
        # Se abbiamo raggiunto il target (entro tolleranza), ritorna la soluzione
        if abs(current_sum - target) <= tolerance:
            return path[:]
        
        # Se la somma corrente è già troppo grande, esci (pruning)
        if current_sum > target + tolerance:
            return None
        
        # Se abbiamo raggiunto la dimensione massima, esci
        if len(path) >= max_size:
            return None
        
        # Prova ogni candidato rimanente
        for i in range(start, len(valid_candidates)):
            idx, amt = valid_candidates[i]
            
            # Pruning: se aggiungere questo importo supererebbe il target, skip
            if current_sum + amt > target + tolerance:
                continue
            
            # Aggiungi alla combinazione corrente
            path.append(idx)
            result = backtrack(i + 1, current_sum + amt, path)
            
            if result is not None:
                return result
            
            # Backtrack: rimuovi l'ultimo elemento
            path.pop()
        
        return None
    
    return backtrack(0, 0.0, [])


def riconcilia_saldi(
    df_banca: pd.DataFrame,
    df_contabilita: pd.DataFrame,
    amount_tolerance: float = 0.01,
    date_tolerance_days: int = 5,
    max_combinations: int = 5,
    max_brute_force_iterations: int = 50000,
    min_amount_for_brute_force: float = 100.0
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
        max_combinations: Massimo numero di voci da combinare nel brute force (default 5)
        max_brute_force_iterations: Limite sicurezza per evitare loop infiniti nel brute force (default 50000)
        min_amount_for_brute_force: Importo minimo per attivare brute force, solo per importi grandi (default 100.0)
        
    Returns:
        Tuple (risultati_df, summary_dict)
        - risultati_df: DataFrame con risultati matching, contiene:
          * Stato "OK": trovato in entrambi
          * Stato "MANCANTE": presente in estratto conto ma NON in scheda contabile
          * Stato "NON TROVATO IN BANCA": presente in scheda contabile ma NON in estratto conto
        - summary_dict: Statistiche (matched, missing, orfani) e saldi informativi
    """
    logger.info(f"Starting reconciliation: {len(df_banca)} bank transactions vs {len(df_contabilita)} accounting entries")
    
    # OTTIMIZZAZIONE: Valida DataFrame vuoti prima di iniziare
    if len(df_banca) == 0:
        logger.warning("Bank DataFrame is empty")
        return pd.DataFrame(), {"error": "Bank DataFrame is empty"}
    if len(df_contabilita) == 0:
        logger.warning("Accounting DataFrame is empty")
        return pd.DataFrame(), {"error": "Accounting DataFrame is empty"}
    
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
    
    # Pre-calcola valori assoluti degli importi per performance (evita calcoli ripetuti)
    banca['importo_abs'] = banca['importo'].abs()
    contab['importo_abs'] = contab['importo'].abs()
    
    # Aggiungi colonna per stato match
    # IMPORTANTE: match_id traccia quali voci sono state matchate per prevenire doppi match
    # Quando una voce viene matchata, viene settato contab.at[idx, 'match_id'] = idx_b
    # Questo garantisce che la stessa voce non possa essere rimatchata
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
    # OTTIMIZZAZIONE: Set per lookup veloce O(1) degli indici già usati
    used_indices_set = set()
    
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
    
    # OTTIMIZZAZIONE: Usa itertuples() invece di iterrows() per performance migliori (~10x più veloce)
    for row_tuple in banca.itertuples():
        idx_b = row_tuple.Index
        # Estrai importo e data dal movimento bancario (usa importo_abs pre-calcolato)
        imp_b = row_tuple.importo_abs if hasattr(row_tuple, 'importo_abs') else abs(row_tuple.importo)
        data_b = row_tuple.data if hasattr(row_tuple, 'data') else None
        
        # Skip se importo mancante/NaN
        if pd.isna(imp_b):
            logger.debug(f"Skipping bank transaction {idx_b} due to missing importo")
            continue
        
        # Traccia conteggio importi per duplicati
        rounded_imp = round(imp_b / amount_tolerance) * amount_tolerance
        banca_amount_counts[rounded_imp] = banca_amount_counts.get(rounded_imp, 0) + 1
        
        # OTTIMIZZAZIONE: Ricerca più efficiente nell'indice importi
        # Calcola range di ricerca invece di iterare su tutte le chiavi
        candidate_indices = []
        min_amount = imp_b - amount_tolerance
        max_amount = imp_b + amount_tolerance
        
        # Itera solo sulle chiavi nell'intervallo rilevante
        for indexed_amount in contab_amount_index.keys():
            if min_amount <= indexed_amount <= max_amount:
                candidate_indices.extend(contab_amount_index[indexed_amount])
        
        # Filtra solo candidati non ancora usati (usa set per lookup O(1))
        # OTTIMIZZAZIONE: Aggiorna il set con gli indici matchati finora
        used_indices_set.update(contab[contab['match_id'].notna()].index)
        candidate_indices_filtered = [
            idx for idx in candidate_indices 
            if idx in contab.index and idx not in used_indices_set
        ]
        
        if not candidate_indices_filtered:
            candidati = pd.DataFrame()
        else:
            candidati = contab.loc[candidate_indices_filtered]
        
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
            
            # OTTIMIZZAZIONE: Usa itertuples per accesso più veloce ai dati
            best_idx = min(candidati.index, key=lambda idx_c: _date_diff(candidati.loc[idx_c]))
            
            # SICUREZZA: Verifica doppio check che la voce non sia già stata matchata
            # (potrebbe essere successo tra il filtro e qui, anche se molto raro)
            if best_idx in used_indices_set or pd.notna(contab.at[best_idx, 'match_id']):
                # Voce già matchata, salta e passa al brute force
                logger.debug(f"Voce {best_idx} già matchata durante il matching diretto, passa al brute force")
            else:
                best_match = contab.loc[best_idx]
                best_importo = abs(best_match['importo'])
                
                # GESTIONE COMMISSIONI BULK: Se l'importo contabile è un multiplo dell'importo bancario
                # (es. 0.83€ bancario vs 2.49€ contabile = 3x), matcha come bulk
                # Questo gestisce il caso dove il contabile registra commissioni in bulk
                multiplier = best_importo / imp_b if imp_b > 0 else 0
                is_bulk_match = False
                multiplier_int = 0
                
                if multiplier > 1.0 and multiplier <= 50.0:  # Limite ragionevole (max 50 commissioni in bulk)
                    # Verifica se è un multiplo intero (entro tolleranza)
                    multiplier_int = round(multiplier)
                    expected_sum = imp_b * multiplier_int
                    
                    if abs(best_importo - expected_sum) <= amount_tolerance:
                        is_bulk_match = True
                        logger.debug(f"Trovato match bulk: {imp_b:.2f} x {multiplier_int} = {best_importo:.2f}")
                
                # Marca come matchata IMMEDIATAMENTE per prevenire doppi match
                contab.at[best_idx, 'match_id'] = idx_b
                used_contab_indices.add(best_idx)
                used_indices_set.add(best_idx)  # Aggiorna anche il set per lookup veloce
                
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
                    if is_bulk_match:
                        note = f"Bulk: {multiplier_int}x commissioni (Δ data {date_diff_days}g)"
                    else:
                        note = f"Δ data {date_diff_days}g"
                    if date_diff_days > date_tolerance_days:
                        note += " (fuori tolleranza)"
                elif is_bulk_match:
                    note = f"Bulk: {multiplier_int}x commissioni"
        
        # Se non abbiamo ancora trovato un match (status è ancora MANCANTE), prova brute force
        if status == "MANCANTE":
            # ========================================================================
            # GESTIONE COMMISSIONI BULK: Cerca voci contabili che sono multipli dell'importo bancario
            # ========================================================================
            # Questo gestisce il caso dove il contabile registra commissioni in bulk
            # (es. 49 occorrenze da 0.83€ in banca vs 17 voci in contabilità, alcune potrebbero essere multipli)
            # ========================================================================
            if pd.notna(data_b) and imp_b > 0:
                # Cerca voci contabili non matchate dello stesso giorno che potrebbero essere multipli
                unmatched_contab_for_bulk = contab[
                    (contab['match_id'].isnull()) &
                    (contab['data'].notna()) &
                    (abs((contab['data'] - data_b).dt.days) <= 1) &
                    (contab['importo'].abs() >= imp_b)  # Solo voci >= importo bancario
                ]
                
                # Prova multipli da 2 a 50
                for multiplier in range(2, 51):
                    expected_bulk_amount = imp_b * multiplier
                    
                    # Cerca voci che corrispondono a questo multiplo (entro tolleranza)
                    bulk_candidates = unmatched_contab_for_bulk[
                        abs(unmatched_contab_for_bulk['importo'].abs() - expected_bulk_amount) <= amount_tolerance
                    ]
                    
                    if not bulk_candidates.empty:
                        # Prendi la prima voce trovata (più vicina alla data se possibile)
                        best_bulk_idx = bulk_candidates.index[0]
                        if pd.notna(data_b):
                            # Scegli quella con data più vicina
                            bulk_candidates_with_date = bulk_candidates[bulk_candidates['data'].notna()]
                            if not bulk_candidates_with_date.empty:
                                best_bulk_idx = min(
                                    bulk_candidates_with_date.index,
                                    key=lambda idx: abs((bulk_candidates_with_date.loc[idx, 'data'] - data_b).days)
                                )
                        
                        # Verifica che non sia già stata matchata
                        if pd.isna(contab.at[best_bulk_idx, 'match_id']):
                            # Match bulk trovato!
                            contab.at[best_bulk_idx, 'match_id'] = idx_b
                            used_contab_indices.add(best_bulk_idx)
                            used_indices_set.add(best_bulk_idx)
                            
                            best_bulk_match = contab.loc[best_bulk_idx]
                            status = "OK"
                            desc_match = best_bulk_match.get('descrizione', '')
                            data_match = best_bulk_match['data']
                            importo_match = best_bulk_match['importo']
                            
                            if pd.notna(data_b) and pd.notna(data_match):
                                date_diff_days = abs((data_b - data_match).days)
                                note = f"Bulk: {multiplier}x commissioni (Δ data {date_diff_days}g)"
                            else:
                                note = f"Bulk: {multiplier}x commissioni"
                            
                            # Aggiorna tracker duplicati
                            if rounded_imp not in duplicates_tracker:
                                duplicates_tracker[rounded_imp] = {
                                    'importo': rounded_imp,
                                    'banca_count': 0,
                                    'contab_count': 0,
                                    'matched_count': 0
                                }
                            duplicates_tracker[rounded_imp]['matched_count'] = duplicates_tracker[rounded_imp].get('matched_count', 0) + 1
                            
                            logger.info(f"Trovato match bulk: {imp_b:.2f} x {multiplier} = {abs(importo_match):.2f}")
                            break  # Esci dal loop dei multipli
            
            # ========================================================================
            # BRUTE FORCE: Cerca combinazioni di 2-5 voci in contabilità
            # ========================================================================
            # Per assegni/pagamenti grandi che vengono registrati come più voci separate
            # nello stesso giorno, cerchiamo se la somma di più voci corrisponde
            # OTTIMIZZAZIONE: Attiva brute force solo per importi grandi (assegni/pagamenti)
            # ========================================================================
            if status == "MANCANTE" and pd.notna(data_b) and imp_b >= min_amount_for_brute_force:
                # Trova tutte le voci in contabilità non ancora matchate dello stesso giorno
                # (o entro 1 giorno di tolleranza per sicurezza)
                unmatched_contab = contab[
                    (contab['match_id'].isnull()) &
                    (contab['data'].notna()) &
                    (abs((contab['data'] - data_b).dt.days) <= 1)
                ]
                
                if len(unmatched_contab) >= 2:
                    # OTTIMIZZAZIONE: Limita candidati in modo intelligente
                    # Calcola somma totale degli importi disponibili
                    total_available = unmatched_contab['importo'].abs().sum()
                    
                    # Se la somma totale è molto più grande dell'importo target, 
                    # possiamo limitare i candidati prendendo solo quelli più rilevanti
                    # (es. se cerchiamo 60k e abbiamo 500k totali, non serve considerare tutte le voci)
                    unmatched_list = list(unmatched_contab.index)
                    
                    # Se ci sono troppi candidati, limita in modo intelligente:
                    # Prendi solo voci che potrebbero essere parte della combinazione
                    # (es. voci <= importo_target o voci che sommate ad altre potrebbero dare il target)
                    if len(unmatched_list) > 30:
                        # Calcola importi assoluti per filtrare
                        importi_abs = unmatched_contab['importo'].abs()
                        
                        # Mantieni solo voci che:
                        # 1. Sono <= importo_target (potrebbero essere parte della combinazione)
                        # 2. O sono tra le più grandi (potrebbero essere la voce principale)
                        # 3. O la loro somma con altre voci potrebbe dare il target
                        
                        # Prendi voci <= importo_target + tolleranza
                        candidates_small = unmatched_contab[importi_abs <= imp_b + amount_tolerance]
                        
                        # Prendi anche le N voci più grandi (potrebbero essere la voce principale)
                        candidates_large = unmatched_contab.nlargest(10, 'importo', keep='all')
                        
                        # Combina e rimuovi duplicati
                        filtered_contab = pd.concat([candidates_small, candidates_large]).drop_duplicates()
                        
                        if len(filtered_contab) < len(unmatched_contab):
                            logger.debug(f"Brute force: limitato da {len(unmatched_contab)} a {len(filtered_contab)} candidati per importo {imp_b:.2f}")
                            unmatched_list = list(filtered_contab.index)
                        else:
                            # Se il filtro non aiuta, limita a un numero ragionevole
                            # Prendi le voci più grandi (più probabili di essere parte della combinazione)
                            unmatched_list = list(unmatched_contab.nlargest(30, 'importo', keep='all').index)
                            logger.debug(f"Brute force: limitato a 30 candidati più grandi su {len(unmatched_contab)} disponibili per importo {imp_b:.2f}")
                    
                    found_combination = False
                    iteration_count = 0
                    
                    # OTTIMIZZAZIONE: Early exit se non ci sono abbastanza candidati
                    # Se abbiamo solo 2 voci e la loro somma non corrisponde, non serve provare combinazioni più grandi
                    if len(unmatched_list) == 2:
                        # Prova direttamente la combinazione di 2 voci
                        combo_indices = tuple(unmatched_list)
                        # Verifica che siano ancora non matchate
                        if all(pd.isna(contab.at[idx, 'match_id']) for idx in combo_indices):
                            importi_sum = sum(abs(contab.at[idx, 'importo']) for idx in combo_indices)
                            if pd.notna(importi_sum) and abs(importi_sum - imp_b) <= amount_tolerance:
                                # Match trovato, salta il loop delle combinazioni
                                for idx in combo_indices:
                                    contab.at[idx, 'match_id'] = idx_b
                                    used_contab_indices.add(idx)
                                    used_indices_set.add(idx)
                                status = "OK"
                                desc_match = " + ".join([str(contab.at[idx, 'descrizione']) for idx in combo_indices])
                                data_match = contab.at[combo_indices[0], 'data'] if pd.notna(contab.at[combo_indices[0], 'data']) else None
                                importo_match = importi_sum
                                if pd.notna(data_b) and pd.notna(data_match):
                                    date_diff_days = abs((data_b - data_match).days)
                                    note = f"Combinazione 2 voci (Δ data {date_diff_days}g)"
                                else:
                                    note = "Combinazione 2 voci"
                                found_combination = True
                                logger.info(f"Trovata combinazione 2 voci per importo {imp_b}: somma = {importi_sum}")
                    
                    if not found_combination:
                        # OTTIMIZZAZIONE: Usa backtracking invece di brute force con combinations
                        # Prepara candidati per backtracking
                        candidates_for_backtrack = [
                            (idx, abs(contab.at[idx, 'importo'])) 
                            for idx in unmatched_list 
                            if pd.isna(contab.at[idx, 'match_id']) and pd.notna(contab.at[idx, 'importo'])
                        ]
                        
                        if len(candidates_for_backtrack) >= 2:
                            # Prova con backtracking (molto più efficiente)
                            result_indices = find_subset_sum_backtrack(
                                candidates_for_backtrack,
                                imp_b,
                                tolerance=amount_tolerance,
                                max_size=max_combinations
                            )
                            
                            if result_indices is not None:
                                # Match trovato con backtracking!
                                combo_indices = result_indices
                                
                                # Verifica finale che tutte le voci siano ancora non matchate
                                final_check = all(pd.isna(contab.at[idx, 'match_id']) for idx in combo_indices)
                                if final_check:
                                    # Calcola dettagli della combinazione
                                    importi = []
                                    descrizioni = []
                                    date_list = []
                                    
                                    for idx in combo_indices:
                                        row = contab.loc[idx]
                                        imp = abs(row['importo'])
                                        importi.append(imp)
                                        descrizioni.append(row.get('descrizione', ''))
                                        if pd.notna(row['data']):
                                            date_list.append(row['data'])
                                    
                                    somma = sum(importi)
                                    
                                    # Marca tutte le voci come matchate IMMEDIATAMENTE
                                    for idx in combo_indices:
                                        contab.at[idx, 'match_id'] = idx_b
                                        used_contab_indices.add(idx)
                                        used_indices_set.add(idx)
                                    
                                    status = "OK"
                                    desc_match = " + ".join(descrizioni)
                                    data_match = date_list[0] if date_list else None
                                    importo_match = somma
                                    
                                    # Calcola differenza date (media delle date)
                                    if len(date_list) > 0:
                                        avg_date = pd.Timestamp(sum((d - date_list[0]).total_seconds() for d in date_list) / len(date_list) + date_list[0].timestamp(), unit='s')
                                        date_diff_days = abs((data_b - avg_date).days)
                                        note = f"Combinazione {len(combo_indices)} voci (Δ data {date_diff_days}g)"
                                    else:
                                        note = f"Combinazione {len(combo_indices)} voci"
                                    
                                    # Aggiorna tracker duplicati
                                    if rounded_imp not in duplicates_tracker:
                                        duplicates_tracker[rounded_imp] = {
                                            'importo': rounded_imp,
                                            'banca_count': 0,
                                            'contab_count': 0,
                                            'matched_count': 0
                                        }
                                    duplicates_tracker[rounded_imp]['matched_count'] = duplicates_tracker[rounded_imp].get('matched_count', 0) + 1
                                    
                                    found_combination = True
                                    logger.info(f"Trovata combinazione {len(combo_indices)} voci per importo {imp_b} usando backtracking: somma = {somma}")
        # Aggiorna conteggio banca per duplicati
        if rounded_imp in duplicates_tracker:
            duplicates_tracker[rounded_imp]['banca_count'] = banca_amount_counts.get(rounded_imp, 0)
        
        # Aggiungi risultato: se status è "MANCANTE", significa che questo movimento
        # è presente in estratto conto ma NON nella scheda contabile
        # OTTIMIZZAZIONE: Usa row_tuple invece di row_b (itertuples)
        risultati.append({
            "Data Banca": data_b,
            "Importo Banca": row_tuple.importo if hasattr(row_tuple, 'importo') else None,
            "Descrizione Banca": row_tuple.descrizione if hasattr(row_tuple, 'descrizione') else '',
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
    # Identifica commissioni piccole non matchate (probabilmente registrate in bulk)
    # ============================================================================
    small_commissions_threshold = 10.0  # Soglia per considerare una voce "piccola" (commissioni)
    small_unmatched = risultati_df[
        (risultati_df['Stato'] == 'MANCANTE') &
        (risultati_df['Importo Banca'].notna()) &
        (risultati_df['Importo Banca'].abs() <= small_commissions_threshold)
    ]
    
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
        "duplicates": duplicates_report,  # Lista di importi duplicati con dettagli
        "small_commissions_unmatched": len(small_unmatched),  # Numero di commissioni piccole non matchate
        "small_commissions_list": small_unmatched[['Data Banca', 'Importo Banca', 'Descrizione Banca']].to_dict('records') if not small_unmatched.empty else []  # Lista dettagliata delle commissioni piccole
    }
    
    logger.info(f"Reconciliation complete: {matched} matched, {missing} missing, {orfani_count} orphans")
    
    return risultati_df, summary

