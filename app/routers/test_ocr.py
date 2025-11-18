"""
Endpoint di test per verificare il parsing OCR
Permette di testare il parsing su documenti di esempio prima di processare i file completi
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse
from typing import Optional
import logging
import pandas as pd
from app.services.ocr_service import OCRService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/test-ocr", response_class=HTMLResponse)
async def test_ocr(
    file: UploadFile = File(...),
    document_type: str = Form(..., description="Tipo documento: 'contabile' o 'estratto_conto'"),
    bank_type: str = Form("credit_agricole", description="Tipo di banca (solo per estratto conto)")
):
    """
    Endpoint di test per verificare il parsing OCR
    
    - **file**: PDF da testare (consigliato poche pagine)
    - **document_type**: 'contabile' per scheda contabile, 'estratto_conto' per estratto conto bancario
    - **bank_type**: Tipo di banca (solo per estratto conto, default: 'credit_agricole')
    
    Restituisce una pagina HTML che mostra i dati parsati
    """
    import os
    import tempfile
    
    if document_type not in ['contabile', 'estratto_conto']:
        raise HTTPException(status_code=400, detail="document_type deve essere 'contabile' o 'estratto_conto'")
    
    # Salva file temporaneamente
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"test_{file.filename}")
    
    try:
        # Salva file
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Parsing
        ocr_service = OCRService()
        
        if document_type == 'contabile':
            data = ocr_service.extract_from_accounting_sheet(temp_path)
            title = "Test Parsing Scheda Contabile"
        else:
            data = ocr_service.extract_from_bank_statement(temp_path, bank_type=bank_type)
            title = f"Test Parsing Estratto Conto ({bank_type})"
        
        df = data.get("dataframe")
        
        if df is None or df.empty:
            html_content = f"""
            <!DOCTYPE html>
            <html lang="it">
            <head>
                <title>{title}</title>
                <style>
                    body {{ font-family: 'Inter', 'Segoe UI', sans-serif; margin: 0; background: #152238; padding: 40px; color: #0f172a; }}
                    .panel {{
                        max-width: 900px;
                        margin: 0 auto;
                        background: #ffffff;
                        border-radius: 18px;
                        padding: 36px;
                        box-shadow: 0 24px 60px rgba(15,23,42,0.35);
                    }}
                    h1 {{
                        font-size: 1.8rem;
                        margin-bottom: 16px;
                        color: #b91c1c;
                    }}
                    .message {{
                        border: 1px solid #fecaca;
                        background: #fff1f2;
                        border-radius: 12px;
                        padding: 24px;
                    }}
                    ul {{ margin: 12px 0 0 20px; color: #374151; }}
                    a {{ color: #111827; text-decoration: none; font-weight: 600; }}
                </style>
            </head>
            <body>
                <div class="panel">
                    <h1>{title}</h1>
                    <div class="message">
                        <p>Non è stato possibile estrarre dati dal documento caricato.</p>
                        <ul>
                            <li>Formato PDF non conforme al layout previsto.</li>
                            <li>Documento vuoto o corrotto.</li>
                            <li>File rasterizzato (non nativo).</li>
                        </ul>
                        <p style="margin-top:16px;"><a href="/test-ocr">Torna al test</a></p>
                    </div>
                </div>
            </body>
            </html>
            """
            return HTMLResponse(content=html_content)
        
        # Genera HTML con tabella dei dati
        html_table = df.to_html(
            classes='data-table',
            table_id='parsed-data',
            escape=False,
            index=False
        )
        
        # Statistiche
        total_rows = len(df)
        if 'importo' in df.columns:
            total_importo = df['importo'].sum()
            stats = f"""
            <div class="stats">
                <h3>Statistiche</h3>
                <ul>
                    <li><strong>Righe estratte:</strong> {total_rows}</li>
                    <li><strong>Saldo totale:</strong> € {total_importo:,.2f}</li>
                </ul>
            </div>
            """
        else:
            stats = f"""
            <div class="stats">
                <h3>Statistiche</h3>
                <ul>
                    <li><strong>Righe estratte:</strong> {total_rows}</li>
                </ul>
            </div>
            """
        
        html_content = f"""
        <!DOCTYPE html>
        <html lang="it">
        <head>
            <title>{title}</title>
            <style>
                body {{
                    font-family: 'Inter', 'Segoe UI', sans-serif;
                    margin: 0;
                    background: #152238;
                    padding: 40px;
                }}
                .panel {{
                    max-width: 1100px;
                    margin: 0 auto;
                    background: #ffffff;
                    border-radius: 18px;
                    padding: 40px;
                    box-shadow: 0 24px 60px rgba(15,23,42,0.35);
                }}
                h1 {{
                    font-size: 2rem;
                    margin-bottom: 6px;
                    color: #0f172a;
                }}
                .subtitle {{
                    color: #6b7280;
                    margin-bottom: 24px;
                }}
                .notice {{
                    border: 1px solid #bae6fd;
                    background: #eff6ff;
                    border-radius: 12px;
                    padding: 18px 22px;
                    margin-bottom: 24px;
                }}
                .metrics {{
                    display: flex;
                    gap: 20px;
                    flex-wrap: wrap;
                    margin-bottom: 24px;
                }}
                .metric {{
                    flex: 1 1 220px;
                    border: 1px solid #e5e7eb;
                    border-radius: 14px;
                    padding: 18px;
                    background: #f8fafc;
                }}
                .metric label {{
                    font-size: 0.8rem;
                    text-transform: uppercase;
                    letter-spacing: 0.08em;
                    color: #6b7280;
                }}
                .metric span {{
                    display: block;
                    margin-top: 6px;
                    font-size: 1.8rem;
                    font-weight: 600;
                    color: #111827;
                }}
                .data-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 10px;
                }}
                .data-table th {{
                    background: #1f2937;
                    color: white;
                    padding: 12px;
                    text-align: left;
                }}
                .data-table td {{
                    padding: 11px 12px;
                    border-bottom: 1px solid #e5e7eb;
                }}
                .data-table tr:nth-child(even) {{
                    background: #f9fafb;
                }}
                .actions {{
                    margin-top: 28px;
                    display: flex;
                    gap: 12px;
                }}
                .btn {{
                    flex: 1;
                    text-align: center;
                    border-radius: 10px;
                    padding: 14px 16px;
                    text-decoration: none;
                    font-weight: 600;
                    border: 1px solid #e5e7eb;
                    color: #111827;
                }}
                .btn.primary {{
                    background: #111827;
                    color: white;
                    border-color: #111827;
                }}
            </style>
        </head>
        <body>
            <div class="panel">
                <h1>{title}</h1>
                <p class="subtitle">Risultato del parser locale.</p>
                <div class="notice">
                    Parsing completato. Verifica i dati estratti prima di procedere alla riconciliazione.
                </div>
                <div class="metrics">
                    <div class="metric">
                        <label>Righe estratte</label>
                        <span>{total_rows}</span>
                    </div>
                    {"<div class='metric'><label>Somma importi</label><span>€ {:,.2f}</span></div>".format(total_importo) if 'importo' in df.columns else ""}
                </div>
                {html_table}
                <div class="actions">
                    <a href="/" class="btn">Torna alla home</a>
                    <a href="/test-ocr" class="btn primary">Nuovo test</a>
                </div>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Error in test OCR: {e}")
        html_content = f"""
        <!DOCTYPE html>
        <html lang="it">
        <head>
            <title>Errore Test OCR</title>
            <style>
                body {{
                    font-family: 'Inter', 'Segoe UI', sans-serif;
                    margin: 0;
                    background: #152238;
                    padding: 40px;
                }}
                .panel {{
                    max-width: 720px;
                    margin: 0 auto;
                    background: #ffffff;
                    border-radius: 18px;
                    padding: 36px;
                    box-shadow: 0 24px 60px rgba(15,23,42,0.35);
                }}
                h1 {{
                    font-size: 1.9rem;
                    margin-bottom: 12px;
                    color: #b91c1c;
                }}
                .error {{
                    border: 1px solid #fecaca;
                    background: #fff1f2;
                    border-radius: 12px;
                    padding: 20px 24px;
                    color: #7f1d1d;
                }}
                a {{
                    display: inline-block;
                    margin-top: 20px;
                    text-decoration: none;
                    font-weight: 600;
                    color: #111827;
                }}
            </style>
        </head>
        <body>
            <div class="panel">
                    <h1>Errore durante il parsing</h1>
                <div class="error">
                    <p>{str(e)}</p>
                </div>
                <a href="/test-ocr">Torna al test</a>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    
    finally:
        # Pulisci file temporaneo
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass


@router.get("/test-ocr", response_class=HTMLResponse)
async def test_ocr_form():
    """
    Form HTML per testare il parsing OCR
    """
    html_content = """
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <title>Test Parsing OCR</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
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
                margin-bottom: 8px;
                color: #0f172a;
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
            select, input[type="file"] {
                width: 100%;
                padding: 14px;
                border-radius: 12px;
                border: 1px solid #d1d5db;
                font-size: 0.95rem;
                font-family: inherit;
            }
            .helper {
                font-size: 0.9rem;
                color: #6b7280;
                margin-bottom: 18px;
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
            button:hover {
                opacity: 0.95;
            }
            a {
                display: inline-block;
                margin-top: 20px;
                font-weight: 600;
                text-decoration: none;
                color: #111827;
            }
        </style>
    </head>
    <body>
        <div class="panel">
            <h1>Test parser OCR</h1>
            <p class="lead">Verifica rapidamente il parsing di un documento prima della riconciliazione.</p>
            <form action="/test-ocr" method="post" enctype="multipart/form-data">
                <div class="form-group">
                    <label for="document_type">Tipo documento</label>
                    <select id="document_type" name="document_type" required onchange="toggleBankType()">
                        <option value="">Seleziona</option>
                        <option value="contabile">Scheda contabile</option>
                        <option value="estratto_conto">Estratto conto bancario</option>
                    </select>
                </div>
                <div class="form-group" id="bank_type_group" style="display:none;">
                    <label for="bank_type">Banca</label>
                    <select id="bank_type" name="bank_type">
                        <option value="credit_agricole">Credit Agricole</option>
                        <option value="placeholder_1" disabled>Altro tipo 1</option>
                        <option value="placeholder_2" disabled>Altro tipo 2</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="file">File PDF</label>
                    <input type="file" id="file" name="file" accept=".pdf" required>
                </div>
                <p class="helper">Carica un PDF di poche pagine per ottenere un feedback immediato.</p>
                <button type="submit">Esegui parsing</button>
            </form>
            <a href="/">Torna alla home</a>
        </div>
        <script>
            function toggleBankType() {
                const docType = document.getElementById('document_type').value;
                document.getElementById('bank_type_group').style.display = (docType === 'estratto_conto') ? 'block' : 'none';
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

