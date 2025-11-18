"""
Analisi approfondita della struttura PDF per identificare:
- Header iniziali (variabili)
- Intestazioni tabella
- Righe dati valide
- Footer finali (raggruppamenti/saldi)
"""
import pdfplumber
import re

def analyze_pdf_structure(pdf_path, pdf_name):
    """Analizza struttura completa del PDF"""
    print(f"\n{'='*100}")
    print(f"ANALISI STRUTTURA COMPLETA: {pdf_name}")
    print(f"{'='*100}\n")
    
    with pdfplumber.open(pdf_path) as pdf:
        print(f"📄 Numero pagine: {len(pdf.pages)}\n")
        
        for page_num, page in enumerate(pdf.pages[:3]):  # Prime 3 pagine
            print(f"\n{'─'*100}")
            print(f"PAGINA {page_num + 1}")
            print(f"{'─'*100}\n")
            
            words = page.extract_words()
            if not words:
                print("❌ Nessuna parola trovata")
                continue
            
            # Raggruppa per riga
            rows_dict = {}
            tolerance = 3
            
            for word in words:
                top_y = word['top']
                found_row = None
                for existing_top in rows_dict.keys():
                    if abs(existing_top - top_y) <= tolerance:
                        found_row = existing_top
                        break
                
                if found_row is not None:
                    rows_dict[found_row].append(word)
                else:
                    rows_dict[top_y] = [word]
            
            sorted_rows = sorted(rows_dict.items(), key=lambda x: x[0])
            
            print(f"Trovate {len(sorted_rows)} righe totali\n")
            
            # Analizza PRIME 10 righe (header)
            print("=" * 100)
            print("PRIME 10 RIGHE (HEADER/INTESTAZIONI):")
            print("=" * 100)
            for i, (top_y, row_words) in enumerate(sorted_rows[:10]):
                row_words.sort(key=lambda w: w['x0'])
                row_text = " | ".join([f"'{w['text']}'" for w in row_words])
                print(f"Riga {i+1:3d} (Y={top_y:7.1f}): {row_text}")
            
            # Analizza RIGHE CENTRALI (dati)
            print("\n" + "=" * 100)
            print("RIGHE CENTRALI (DATI - prime 15):")
            print("=" * 100)
            start_idx = 10
            end_idx = min(25, len(sorted_rows))
            for i, (top_y, row_words) in enumerate(sorted_rows[start_idx:end_idx], start=start_idx+1):
                row_words.sort(key=lambda w: w['x0'])
                row_text = " | ".join([f"'{w['text']}'" for w in row_words])
                
                # Identifica pattern
                first_word = row_words[0]['text'].strip() if row_words else ""
                is_data_row = False
                pattern = ""
                
                if re.match(r'^\d{6}', first_word):  # Scheda contabile: 041024!
                    is_data_row = True
                    pattern = "DATA_CONTABILE"
                elif re.match(r'^\d{2}\.\d{2}\.\d{2}', first_word):  # Estratto conto: 01.10.24
                    is_data_row = True
                    pattern = "DATA_BANCA"
                elif "DATA" in first_word.upper() or "VALUTA" in first_word.upper():
                    pattern = "INTESTAZIONE_TABELLA"
                elif "SALDO" in first_word.upper() or "TOTALE" in first_word.upper():
                    pattern = "FOOTER/SALDO"
                else:
                    pattern = "ALTRO"
                
                marker = "✅ DATI" if is_data_row else f"⚠️  {pattern}"
                print(f"Riga {i:3d} (Y={top_y:7.1f}) [{marker}]: {row_text}")
            
            # Analizza ULTIME 10 righe (footer)
            print("\n" + "=" * 100)
            print("ULTIME 10 RIGHE (FOOTER/RAGGRUPPAMENTI):")
            print("=" * 100)
            for i, (top_y, row_words) in enumerate(sorted_rows[-10:], start=len(sorted_rows)-9):
                row_words.sort(key=lambda w: w['x0'])
                row_text = " | ".join([f"'{w['text']}'" for w in row_words])
                
                first_word = row_words[0]['text'].strip() if row_words else ""
                if "SALDO" in first_word.upper() or "TOTALE" in first_word.upper() or "------" in first_word:
                    marker = "⚠️  FOOTER"
                elif re.match(r'^\d{6}', first_word) or re.match(r'^\d{2}\.\d{2}\.\d{2}', first_word):
                    marker = "✅ DATI"
                else:
                    marker = "⚠️  ALTRO"
                
                print(f"Riga {i:3d} (Y={top_y:7.1f}) [{marker}]: {row_text}")
            
            # Identifica pattern per righe dati valide
            print("\n" + "=" * 100)
            print("ANALISI PATTERN RIGHE DATI VALIDE:")
            print("=" * 100)
            
            data_rows = []
            header_rows = []
            footer_rows = []
            
            for top_y, row_words in sorted_rows:
                row_words.sort(key=lambda w: w['x0'])
                first_word = row_words[0]['text'].strip() if row_words else ""
                
                if re.match(r'^\d{6}', first_word):  # Scheda contabile
                    data_rows.append((top_y, first_word))
                elif re.match(r'^\d{2}\.\d{2}\.\d{2}', first_word):  # Estratto conto
                    data_rows.append((top_y, first_word))
                elif "DATA" in first_word.upper() or "VALUTA" in first_word.upper() or "------" in first_word:
                    header_rows.append((top_y, first_word))
                elif "SALDO" in first_word.upper() or "TOTALE" in first_word.upper() or len(row_words) < 3:
                    footer_rows.append((top_y, first_word))
            
            print(f"\nRighe dati trovate: {len(data_rows)}")
            if data_rows:
                print(f"  Prima riga dati: Y={data_rows[0][0]:.1f}, testo='{data_rows[0][1]}'")
                print(f"  Ultima riga dati: Y={data_rows[-1][0]:.1f}, testo='{data_rows[-1][1]}'")
            
            print(f"\nRighe header/intestazioni: {len(header_rows)}")
            if header_rows:
                print(f"  Prima intestazione: Y={header_rows[0][0]:.1f}, testo='{header_rows[0][1]}'")
                print(f"  Ultima intestazione: Y={header_rows[-1][0]:.1f}, testo='{header_rows[-1][1]}'")
            
            print(f"\nRighe footer/raggruppamenti: {len(footer_rows)}")
            if footer_rows:
                print(f"  Primo footer: Y={footer_rows[0][0]:.1f}, testo='{footer_rows[0][1]}'")
            
            # Suggerimenti per filtraggio
            print("\n" + "=" * 100)
            print("SUGGERIMENTI PER FILTRAGGIO:")
            print("=" * 100)
            
            if data_rows:
                first_data_y = data_rows[0][0]
                last_data_y = data_rows[-1][0]
                
                # Trova Y minimo/massimo per header/footer
                header_y_max = max([y for y, _ in header_rows]) if header_rows else 0
                footer_y_min = min([y for y, _ in footer_rows]) if footer_rows else float('inf')
                
                print(f"\nPer SCHEDA CONTABILE:")
                print(f"  - Skip righe con Y < {first_data_y:.1f} (header)")
                print(f"  - Skip righe con Y > {last_data_y:.1f} (footer)")
                print(f"  - Pattern data: ^\\d{{6}}")
                print(f"  - Skip se contiene: 'DATA', 'COD', 'DESCRIZIONE', 'SALDO', '------'")
                
                print(f"\nPer ESTRATTO CONTO:")
                print(f"  - Skip righe con Y < {first_data_y:.1f} (header)")
                print(f"  - Skip righe con Y > {last_data_y:.1f} (footer)")
                print(f"  - Pattern data: ^\\d{{2}}\\.\\d{{2}}\\.\\d{{2}}")
                print(f"  - Skip se contiene: 'DATA', 'VALUTA', 'MOVIMENTI', 'SALDO', 'TOTALE'")
            
            if page_num >= 2:  # Solo prime 3 pagine
                break

if __name__ == "__main__":
    pdfs = [
        ("contabile.pdf", "SCHEDA CONTABILE"),
        ("estratto_conto.pdf", "ESTRATTO CONTO")
    ]
    
    for pdf_file, pdf_name in pdfs:
        try:
            analyze_pdf_structure(pdf_file, pdf_name)
        except FileNotFoundError:
            print(f"❌ File {pdf_file} non trovato")
        except Exception as e:
            print(f"❌ Errore: {e}")
            import traceback
            traceback.print_exc()

