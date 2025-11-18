"""
Script di debug per analizzare la struttura dei PDF
Mostra esattamente cosa vede pdfplumber: testo, tabelle, parole, coordinate
"""
import pdfplumber
import json
import sys
from pathlib import Path

def analyze_pdf(pdf_path: str, output_prefix: str):
    """Analizza un PDF e genera report dettagliati"""
    print(f"\n{'='*80}")
    print(f"ANALISI PDF: {pdf_path}")
    print(f"{'='*80}\n")
    
    with pdfplumber.open(pdf_path) as pdf:
        print(f"Numero pagine: {len(pdf.pages)}\n")
        
        for page_num, page in enumerate(pdf.pages):
            print(f"\n{'─'*80}")
            print(f"PAGINA {page_num + 1}")
            print(f"{'─'*80}")
            print(f"Dimensioni: {page.width:.2f} x {page.height:.2f} pt\n")
            
            # 1. ESTRAZIONE TESTO COMPLETO
            print("=" * 80)
            print("1. TESTO COMPLETO (extract_text)")
            print("=" * 80)
            text = page.extract_text()
            if text:
                print(text[:2000])  # Prime 2000 caratteri
                if len(text) > 2000:
                    print(f"\n... (troncato, totale {len(text)} caratteri)")
            else:
                print("NESSUN TESTO ESTRATTO")
            print()
            
            # 2. ESTRAZIONE PAROLE CON COORDINATE
            print("=" * 80)
            print("2. PAROLE CON COORDINATE (extract_words) - Prime 30")
            print("=" * 80)
            words = page.extract_words()
            print(f"Totale parole trovate: {len(words)}\n")
            for i, word in enumerate(words[:30]):
                print(f"  [{i+1}] '{word['text']}' | "
                      f"x0={word['x0']:.1f} x1={word['x1']:.1f} | "
                      f"y0={word['top']:.1f} y1={word['bottom']:.1f}")
            if len(words) > 30:
                print(f"\n... (altre {len(words)-30} parole)")
            print()
            
            # 3. ESTRAZIONE TABELLE
            print("=" * 80)
            print("3. TABELLE (extract_table)")
            print("=" * 80)
            
            # Prova diverse strategie
            strategies = [
                {"vertical_strategy": "text", "horizontal_strategy": "text"},
                {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
                {"vertical_strategy": "explicit", "horizontal_strategy": "text"},
            ]
            
            for idx, strategy in enumerate(strategies):
                print(f"\n--- Strategia {idx+1}: {strategy} ---")
                try:
                    table = page.extract_table(strategy)
                    if table:
                        print(f"Trovata tabella con {len(table)} righe")
                        print(f"Prima riga: {len(table[0]) if table[0] else 0} colonne")
                        print("Prime 5 righe:")
                        for i, row in enumerate(table[:5]):
                            print(f"  Riga {i}: {row}")
                    else:
                        print("NESSUNA TABELLA TROVATA")
                except Exception as e:
                    print(f"ERRORE: {e}")
            print()
            
            # 4. ANALISI RIGHE - Raggruppa parole per riga
            print("=" * 80)
            print("4. ANALISI RIGHE (parole raggruppate per coordinata Y)")
            print("=" * 80)
            if words:
                # Raggruppa per riga (tolleranza 3px)
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
                print(f"Trovate {len(sorted_rows)} righe\n")
                
                # Mostra prime 10 righe
                for i, (top_y, row_words) in enumerate(sorted_rows[:10]):
                    row_words.sort(key=lambda w: w['x0'])
                    row_text = " | ".join([w['text'] for w in row_words])
                    print(f"Riga {i+1} (Y={top_y:.1f}): {row_text}")
                
                if len(sorted_rows) > 10:
                    print(f"\n... (altre {len(sorted_rows)-10} righe)")
            print()
            
            # 5. CERCA SEPARATORI "!"
            print("=" * 80)
            print("5. RICERCA SEPARATORI '!' NELLE PAROLE")
            print("=" * 80)
            exclamation_words = [w for w in words if '!' in w['text']]
            print(f"Trovate {len(exclamation_words)} parole con '!'")
            if exclamation_words:
                print("Prime 10:")
                for w in exclamation_words[:10]:
                    print(f"  '{w['text']}' a X={w['x0']:.1f}, Y={w['top']:.1f}")
            print()
            
            # 6. SALVA DATI IN JSON PER ANALISI
            output_file = f"{output_prefix}_page_{page_num+1}_data.json"
            output_data = {
                "page_num": page_num + 1,
                "dimensions": {"width": page.width, "height": page.height},
                "text": text,
                "words_count": len(words),
                "words_sample": words[:50],  # Prime 50 parole
                "tables_found": []
            }
            
            # Prova extract_table con strategia text
            try:
                table = page.extract_table({"vertical_strategy": "text", "horizontal_strategy": "text"})
                if table:
                    output_data["tables_found"].append({
                        "strategy": "text/text",
                        "rows": len(table),
                        "cols": len(table[0]) if table[0] else 0,
                        "sample": table[:10]  # Prime 10 righe
                    })
            except:
                pass
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False, default=str)
            print(f"Dati salvati in: {output_file}")
            
            # Solo prima pagina per ora (puoi cambiare)
            if page_num == 0:
                break

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug_pdf.py <pdf_file>")
        print("Esempio: python debug_pdf.py contabile.pdf")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    if not Path(pdf_path).exists():
        print(f"ERRORE: File {pdf_path} non trovato")
        sys.exit(1)
    
    output_prefix = Path(pdf_path).stem
    analyze_pdf(pdf_path, output_prefix)


