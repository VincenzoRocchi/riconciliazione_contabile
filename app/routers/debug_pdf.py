"""
Endpoint temporaneo di debug per analizzare PDF
Da rimuovere dopo aver capito la struttura
"""
from fastapi import APIRouter, UploadFile, File
from fastapi.responses import HTMLResponse
import pdfplumber
import json
import tempfile
import os

router = APIRouter()

@router.get("/debug-pdf", response_class=HTMLResponse)
async def debug_pdf_form():
    """Form per caricare PDF da analizzare"""
    html_content = """
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <title>Analisi struttura PDF</title>
        <style>
            body {
                font-family: 'Inter', 'Segoe UI', sans-serif;
                background: #152238;
                min-height: 100vh;
                padding: 40px;
                color: #0f172a;
            }
            .panel {
                max-width: 720px;
                margin: 0 auto;
                background: #ffffff;
                border-radius: 18px;
                padding: 36px;
                box-shadow: 0 24px 60px rgba(15,23,42,0.35);
            }
            h1 {
                font-size: 2rem;
                margin-bottom: 10px;
            }
            .lead {
                color: #6b7280;
                margin-bottom: 24px;
            }
            .form-group {
                margin-bottom: 22px;
            }
            label {
                display: block;
                font-size: 0.85rem;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: #6b7280;
                margin-bottom: 6px;
            }
            input[type="file"] {
                width: 100%;
                padding: 14px;
                border-radius: 12px;
                border: 1px solid #d1d5db;
            }
            button {
                width: 100%;
                padding: 16px;
                border-radius: 12px;
                border: none;
                background: #111827;
                color: white;
                font-size: 1rem;
                font-weight: 600;
                cursor: pointer;
            }
            button:hover { opacity: 0.95; }
            a {
                display: inline-block;
                margin-top: 20px;
                text-decoration: none;
                font-weight: 600;
                color: #111827;
            }
        </style>
    </head>
    <body>
        <div class="panel">
            <h1>Analisi struttura PDF</h1>
            <p class="lead">Visualizza il contenuto visto da pdfplumber per definire nuovi parser o verificare i layout.</p>
            <form action="/debug-pdf" method="post" enctype="multipart/form-data">
                <div class="form-group">
                    <label for="file">File PDF</label>
                    <input type="file" id="file" name="file" accept=".pdf" required>
                </div>
                <button type="submit">Analizza documento</button>
            </form>
            <a href="/">Torna alla home</a>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@router.post("/debug-pdf", response_class=HTMLResponse)
async def debug_pdf(file: UploadFile = File(...)):
    """Endpoint per analizzare un PDF e vedere cosa vede pdfplumber"""
    
    # Salva file temporaneamente
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            content = await file.read()
            tmp.write(content)
            temp_path = tmp.name
        
        results = []
        
        with pdfplumber.open(temp_path) as pdf:
            for page_num, page in enumerate(pdf.pages[:1]):  # Solo prima pagina
                page_data = {
                    "page": page_num + 1,
                    "dimensions": {"width": page.width, "height": page.height},
                    "text": page.extract_text() or "",
                    "words": [],
                    "tables": [],
                    "rows_analysis": []
                }
                
                # Estrai parole
                words = page.extract_words()
                page_data["words_count"] = len(words)
                page_data["words"] = words[:100]  # Prime 100 parole
                
                # Prova extract_table
                try:
                    table = page.extract_table({
                        "vertical_strategy": "text",
                        "horizontal_strategy": "text"
                    })
                    if table:
                        page_data["tables"].append({
                            "strategy": "text/text",
                            "rows": len(table),
                            "cols": len(table[0]) if table[0] else 0,
                            "data": table[:20]  # Prime 20 righe
                        })
                except Exception as e:
                    page_data["tables"].append({"error": str(e)})
                
                # Analisi righe
                if words:
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
                    for top_y, row_words in sorted_rows[:30]:  # Prime 30 righe
                        row_words.sort(key=lambda w: w['x0'])
                        page_data["rows_analysis"].append({
                            "y": top_y,
                            "words": [{"text": w['text'], "x0": w['x0'], "x1": w['x1']} for w in row_words]
                        })
                
                results.append(page_data)
        
        # Genera HTML con risultati
        html = f"""
        <!DOCTYPE html>
        <html lang="it">
        <head>
            <title>Analisi PDF</title>
            <style>
                body {{ font-family: 'Inter', 'Segoe UI', sans-serif; margin: 0; background: #f1f5f9; padding: 32px; }}
                .section {{ background: white; padding: 24px; margin: 20px 0; border-radius: 16px; box-shadow: 0 10px 30px rgba(15,23,42,0.08); }}
                h1 {{ color: #111827; font-size: 2rem; margin-bottom: 24px; }}
                h2 {{ color: #111827; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px; margin-top: 12px; }}
                pre {{ background: #111827; color: #f8fafc; padding: 16px; border-radius: 10px; overflow-x: auto; font-family: 'JetBrains Mono', monospace; font-size: 0.9rem; }}
                table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 0.92rem; }}
                th, td {{ border: 1px solid #e5e7eb; padding: 8px; text-align: left; }}
                th {{ background: #111827; color: white; }}
            </style>
        </head>
        <body>
            <h1>Analisi PDF: {file.filename}</h1>
        """
        
        for page_data in results:
            html += f"""
            <div class="section">
                <h2>Pagina {page_data['page']}</h2>
                <p><strong>Dimensioni:</strong> {page_data['dimensions']['width']:.2f} x {page_data['dimensions']['height']:.2f} pt</p>
                
                <h3>1. Testo Completo (prime 2000 caratteri)</h3>
                <pre>{page_data['text'][:2000]}</pre>
                
                <h3>2. Parole Trovate: {page_data['words_count']}</h3>
                <p>Prime 50 parole con coordinate:</p>
                <table>
                    <tr><th>#</th><th>Testo</th><th>X0</th><th>X1</th><th>Y (top)</th></tr>
            """
            
            for i, word in enumerate(page_data['words'][:50]):
                html += f"""
                    <tr>
                        <td>{i+1}</td>
                        <td><strong>{word['text']}</strong></td>
                        <td>{word['x0']:.1f}</td>
                        <td>{word['x1']:.1f}</td>
                        <td>{word['top']:.1f}</td>
                    </tr>
                """
            
            html += "</table>"
            
            # Tabelle
            html += "<h3>3. Tabelle Trovate</h3>"
            for table_info in page_data['tables']:
                if 'error' in table_info:
                    html += f"<p style='color: red;'>Errore: {table_info['error']}</p>"
                else:
                    html += f"""
                    <p><strong>Strategia:</strong> {table_info['strategy']}</p>
                    <p><strong>Righe:</strong> {table_info['rows']}, <strong>Colonne:</strong> {table_info['cols']}</p>
                    <table>
                    """
                    for i, row in enumerate(table_info['data'][:10]):
                        html += "<tr>"
                        for cell in row:
                            html += f"<td>{cell or ''}</td>"
                        html += "</tr>"
                    html += "</table>"
            
            # Analisi righe
            html += f"<h3>4. Analisi Righe (prime 20)</h3>"
            html += "<table><tr><th>Riga</th><th>Y</th><th>Parole</th></tr>"
            for i, row_info in enumerate(page_data['rows_analysis'][:20]):
                words_str = " | ".join([f"'{w['text']}'" for w in row_info['words']])
                html += f"""
                <tr>
                    <td>{i+1}</td>
                    <td>{row_info['y']:.1f}</td>
                    <td>{words_str}</td>
                </tr>
                """
            html += "</table>"
            
            html += "</div>"
        
        html += """
            <div style="margin-top: 30px; padding: 20px; background: #e2e8f0; border-radius: 12px;">
                <a href="/" style="text-decoration:none; font-weight:600; color:#0f172a;">Torna alla home</a>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html)
        
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

