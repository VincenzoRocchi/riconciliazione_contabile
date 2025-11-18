"""
Pagina risultati riconciliazione
Mostra i risultati del controllo in formato HTML moderno
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
import logging
from app.routers.processing import jobs_storage
from app.core.models import ProcessingStatus

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/results/{job_id}", response_class=HTMLResponse)
async def show_results(job_id: str):
    """
    Mostra i risultati della riconciliazione in formato HTML
    """
    if job_id not in jobs_storage:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs_storage[job_id]
    
    # Se ancora in processing, mostra pagina di attesa
    if job["status"] != ProcessingStatus.COMPLETED:
        return _render_loading_page(job_id, job["status"])
    
    # Recupera risultato
    result = job.get("result")
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    
    # Renderizza pagina risultati
    return _render_results_page(result)


@router.post("/results/{job_id}/cleanup")
async def cleanup_result(job_id: str):
    """
    Rimuove il job dalla memoria dopo che l'utente ha salvato/stampato il report.
    """
    if job_id not in jobs_storage:
        raise HTTPException(status_code=404, detail="Job not found")
    
    del jobs_storage[job_id]
    return JSONResponse({"status": "deleted"})


def _render_loading_page(job_id: str, status: str) -> HTMLResponse:
    """Pagina di attesa durante il processing"""
    status_text = {
        ProcessingStatus.PENDING: "In attesa di elaborazione...",
        ProcessingStatus.PROCESSING: "Parsing documenti in corso...",
        ProcessingStatus.VALIDATING: "Riconciliazione in corso...",
        ProcessingStatus.FAILED: "Errore durante l'elaborazione"
    }.get(status, "Elaborazione in corso...")
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta http-equiv="refresh" content="2">
        <title>Elaborazione in corso...</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            .container {{
                background: white;
                border-radius: 16px;
                padding: 60px;
                text-align: center;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                max-width: 500px;
            }}
            .spinner {{
                border: 4px solid #f3f3f3;
                border-top: 4px solid #667eea;
                border-radius: 50%;
                width: 60px;
                height: 60px;
                animation: spin 1s linear infinite;
                margin: 0 auto 30px;
            }}
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
            h1 {{
                color: #333;
                margin-bottom: 15px;
                font-size: 1.8em;
            }}
            p {{
                color: #666;
                font-size: 1.1em;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="spinner"></div>
            <h1>⏳ {status_text}</h1>
            <p>Attendere prego, la pagina si aggiornerà automaticamente...</p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


def _render_results_page(result) -> HTMLResponse:
    """Pagina risultati completa"""
    matching = result.matching_result
    summary = matching.summary
    job_id = getattr(result, "job_id", "")
    
    # Determina colore in base al risultato
    if result.overall_verdict == "valid":
        status_color = "#15803d"
        status_text = "Nessuna anomalia rilevata"
    elif result.overall_verdict == "needs_review":
        status_color = "#b45309"
        status_text = "Verifica consigliata"
    else:
        status_color = "#b91c1c"
        status_text = "Discrepanze rilevate"
    
    # Genera tabella problemi (collassabile)
    problems_html = ""
    if result.flags:
        problems_count = len(result.flags)
        problems_html = f"""
        <details class="section-toggle">
            <summary class="section-header">Problemi rilevati ({problems_count})</summary>
            <div class="problems-list">
        """
        for flag in result.flags:
            severity_class = "error" if flag.severity == "error" else "warning"
            problems_html += f"""
            <div class="problem-item {severity_class}">
                <div class="problem-header">
                    <span class="problem-icon">{'❌' if flag.severity == 'error' else '⚠️'}</span>
                    <strong>{flag.message}</strong>
                </div>
                <div class="problem-details">
                    {_format_flag_value(flag.value)}
                </div>
            </div>
            """
        problems_html += """
            </div>
        </details>
        """
    
    # Genera tabella risultati
    issue_tables = ""
    detail_table_html = ""
    detail_row_count = 0
    if "risultati_df" in summary:
        import pandas as pd
        df = pd.DataFrame(summary["risultati_df"])
        
        missing_df = df[df['Stato'] == 'MANCANTE'][[
            'Data Banca', 'Importo Banca', 'Descrizione Banca', 'Note'
        ]]
        orfani_df = df[df['Stato'].str.contains('NON TROVATO', na=False)][[
            'Data Contabilità', 'Importo Contabilità', 'Descrizione Contabilità'
        ]]
        delta_df = df[
            (df['Stato'] == 'OK') &
            (df['Note'].str.contains('fuori tolleranza', na=False))
        ][[
            'Data Banca', 'Data Contabilità', 'Importo Banca', 'Descrizione Banca', 'Note'
        ]]
        
        def _df_to_html(dataframe, classes):
            return dataframe.to_html(classes=classes, escape=False, index=False)
        
        if not missing_df.empty:
            issue_tables += f"""
            <details class="section-toggle">
                <summary class="section-header">Movimenti in banca non registrati ({len(missing_df)})</summary>
                <div class="section-content">
                    {_df_to_html(missing_df, 'results-table')}
                </div>
            </details>
            """
        
        if not orfani_df.empty:
            issue_tables += f"""
            <details class="section-toggle">
                <summary class="section-header">Movimenti in contabilità assenti in banca ({len(orfani_df)})</summary>
                <div class="section-content">
                    {_df_to_html(orfani_df, 'results-table')}
                </div>
            </details>
            """
        
        if not delta_df.empty:
            issue_tables += f"""
            <details class="section-toggle">
                <summary class="section-header">Match trovati oltre la tolleranza data ({len(delta_df)})</summary>
                <div class="section-content">
                    {_df_to_html(delta_df, 'results-table')}
                </div>
            </details>
            """
        
        if not df.empty:
            detail_row_count = len(df)
            detail_table_html = df.to_html(classes='results-table full-table', escape=False, index=False)

    # Genera sezione duplicati (collassabile, in cima)
    duplicates_html = ""
    duplicates_list = summary.get('duplicates', [])
    if duplicates_list:
        duplicates_html = f"""
        <details class="section-toggle">
            <summary class="section-header">Importi duplicati con problemi ({len(duplicates_list)})</summary>
            <div class="section-content">
                <table class="results-table duplicates-table">
                    <thead>
                        <tr>
                            <th>Importo</th>
                            <th>Occorrenze Banca</th>
                            <th>Occorrenze Contabilità</th>
                            <th>Matchati</th>
                            <th>Non Matchati Banca</th>
                            <th>Non Matchati Contabilità</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        for dup in duplicates_list:
            duplicates_html += f"""
                        <tr>
                            <td>€ {dup.get('importo', 0):,.2f}</td>
                            <td>{dup.get('occorrenze_banca', 0)}</td>
                            <td>{dup.get('occorrenze_contabilita', 0)}</td>
                            <td>{dup.get('matchati', 0)}</td>
                            <td class="{'error-cell' if dup.get('non_matchati_banca', 0) > 0 else ''}">{dup.get('non_matchati_banca', 0)}</td>
                            <td class="{'error-cell' if dup.get('non_matchati_contabilita', 0) > 0 else ''}">{dup.get('non_matchati_contabilita', 0)}</td>
                        </tr>
            """
        duplicates_html += """
                    </tbody>
                </table>
            </div>
        </details>
        """
    
    detail_section_html = ""
    if detail_table_html:
        detail_section_html = f"""
        <details class="section-toggle">
            <summary class="section-header">Dettaglio completo ({detail_row_count} righe)</summary>
            <div class="section-content">
                {detail_table_html}
            </div>
        </details>
        """
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Risultati Riconciliazione</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #f5f5f5;
                padding: 20px;
                line-height: 1.6;
            }}
            .container {{
                max-width: 1500px;
                width: 95%;
                margin: 0 auto;
                background: white;
                border-radius: 16px;
                box-shadow: 0 8px 24px rgba(0,0,0,0.08);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #1b2640 0%, #273248 100%);
                color: white;
                padding: 36px 70px;
                text-align: center;
            }}
            .header h1 {{
                font-size: 2.4em;
                margin-bottom: 8px;
                font-weight: 600;
                letter-spacing: -0.5px;
            }}
            .status-badge {{
                display: inline-flex;
                align-items: center;
                gap: 8px;
                background: #111827;
                border: 1px solid rgba(255,255,255,0.2);
                color: white;
                padding: 10px 22px;
                border-radius: 999px;
                font-size: 1.05em;
                font-weight: 500;
                margin-top: 15px;
            }}
            .content {{
                padding: 50px 70px;
            }}
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
                gap: 24px;
                margin-bottom: 40px;
            }}
            .stat-card {{
                background: #ffffff;
                padding: 22px;
                border-radius: 12px;
                border: 1px solid #e5e7eb;
                box-shadow: 0 6px 18px rgba(15, 23, 42, 0.08);
            }}
            .stat-card h4 {{
                color: #666;
                font-size: 0.9em;
                margin-bottom: 10px;
                text-transform: uppercase;
            }}
            .stat-card .value {{
                font-size: 2.2em;
                font-weight: 600;
                color: #111827;
            }}
            .stat-card .value.success {{ color: #15803d; }}
            .stat-card .value.error {{ color: #b91c1c; }}
            .problems-list {{
                margin-top: 20px;
            }}
            .problem-item {{
                padding: 18px;
                border-radius: 10px;
                margin-bottom: 15px;
                border: 1px solid #e5e7eb;
                background: #f8fafc;
            }}
            .problem-item.error {{
                border-color: #fecaca;
                background: #fef2f2;
            }}
            .problem-item.warning {{
                border-color: #fed7aa;
                background: #fff7ed;
            }}
            .problem-header {{
                font-weight: 600;
                margin-bottom: 8px;
                color: #111827;
            }}
            .problem-details {{
                color: #52525b;
                font-size: 0.92em;
            }}
            .results-table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
            }}
            .full-table {{
                margin-top: 0;
            }}
            .results-table th {{
                background: #1f2937;
                color: white;
                padding: 12px;
                text-align: left;
                font-weight: 500;
            }}
            .results-table td {{
                padding: 11px 12px;
                border-bottom: 1px solid #e5e7eb;
            }}
            .results-table tr:nth-child(even) {{
                background: #f9fafb;
            }}
            .actions {{
                margin-top: 40px;
                padding-top: 30px;
                border-top: 2px solid #eee;
                text-align: center;
            }}
            .btn {{
                display: inline-block;
                padding: 12px 24px;
                background: #667eea;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                margin: 0 10px;
                font-weight: 600;
                transition: background 0.3s;
            }}
            .btn:hover {{
                background: #5568d3;
            }}
            .btn-secondary {{
                background: #757575;
            }}
            .btn-secondary:hover {{
                background: #616161;
            }}
            .print-note {{
                margin-top: 10px;
                text-align: center;
                color: #777;
                font-size: 0.9em;
            }}
            .saldo-section {{
                background: #e3f2fd;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 30px;
            }}
            .saldo-section h3 {{
                color: #1976d2;
                margin-bottom: 15px;
            }}
            .saldo-row {{
                display: flex;
                justify-content: space-between;
                padding: 10px 0;
                border-bottom: 1px solid #90caf9;
            }}
            .saldo-row:last-child {{
                border-bottom: none;
                font-weight: 700;
                font-size: 1.1em;
            }}
            .section-toggle {{
                margin-top: 40px;
                margin-bottom: 30px;
                border: 1px solid #d1d5db;
                border-radius: 10px;
                background: #fafafa;
                overflow: hidden;
            }}
            .section-header {{
                cursor: pointer;
                font-weight: 600;
                padding: 16px 20px;
                background: #1f2937;
                color: white;
                font-size: 1.1em;
                list-style: none;
                position: relative;
                padding-left: 50px;
            }}
            .section-header::-webkit-details-marker {{
                display: none;
            }}
            .section-header::before {{
                content: '▶';
                position: absolute;
                left: 20px;
                transition: transform 0.2s ease;
                font-size: 0.9em;
            }}
            .section-toggle[open] .section-header::before {{
                transform: rotate(90deg);
            }}
            .section-toggle[open] .section-header {{
                border-bottom: 1px solid #374151;
            }}
            .section-content {{
                padding: 0;
                background: white;
                max-height: 70vh;
                overflow: auto;
            }}
            .section-content .results-table {{
                margin-top: 0;
                border-radius: 0;
            }}
            .section-toggle .problems-list {{
                padding: 20px;
                background: white;
            }}
            .duplicates-table {{
                margin-top: 0;
            }}
            .error-cell {{
                background-color: #fef2f2;
                color: #b91c1c;
                font-weight: 600;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📊 Risultati Riconciliazione</h1>
                <div class="status-badge">
                    {status_text}
                </div>
            </div>
            
            <div class="content">
                <div class="stats-grid">
                    <div class="stat-card">
                        <h4>Transazioni Estratto Conto</h4>
                        <div class="value">{summary.get('total_banca', 0)}</div>
                    </div>
                    <div class="stat-card">
                        <h4>Transazioni Scheda Contabile</h4>
                        <div class="value">{summary.get('total_contabilita', 0)}</div>
                    </div>
                    <div class="stat-card">
                        <h4>Match Trovati</h4>
                        <div class="value success">{summary.get('matched', 0)}</div>
                    </div>
                    <div class="stat-card">
                        <h4>Voci Mancanti</h4>
                        <div class="value error">{summary.get('missing_in_contabilita', 0)}</div>
                    </div>
                    <div class="stat-card">
                        <h4>Voci Orfane</h4>
                        <div class="value error">{summary.get('orfani_in_contabilita', 0)}</div>
                    </div>
                    <div class="stat-card">
                        <h4>Completion Rate</h4>
                        <div class="value">{summary.get('completion_rate', 0):.1f}%</div>
                    </div>
                </div>
                
                <div class="saldo-section">
                    <h3>💰 Verifica Saldi</h3>
                    <div class="saldo-row">
                        <span>Saldo Estratto Conto:</span>
                        <span>€ {summary.get('saldo_banca', 0):,.2f}</span>
                    </div>
                    <div class="saldo-row">
                        <span>Saldo Scheda Contabile:</span>
                        <span>€ {summary.get('saldo_contabilita', 0):,.2f}</span>
                    </div>
                    <div class="saldo-row">
                        <span>Differenza:</span>
                        <span style="color: {'#4caf50' if abs(summary.get('differenza_saldo', 0)) < 0.01 else '#f44336'}">
                            € {summary.get('differenza_saldo', 0):,.2f}
                        </span>
                    </div>
                </div>
                
                {duplicates_html}
                
                {issue_tables}
                
                {problems_html}
                
                {detail_section_html}
                
                <div class="actions">
                    <button type="button" class="btn" id="printBtn">Stampa o salva in PDF</button>
                    <a href="/" class="btn btn-secondary">Nuova riconciliazione</a>
                    <a href="/test-ocr" class="btn btn-secondary">Test OCR</a>
                </div>
                <p class="print-note">Dopo la stampa/salvataggio il report viene eliminato dalla memoria.</p>
            </div>
        </div>
        <script>
            const printBtn = document.getElementById('printBtn');
            if (printBtn) {{
                printBtn.addEventListener('click', async () => {{
                    printBtn.disabled = true;
                    window.print();
                    try {{
                        await fetch('/results/{job_id}/cleanup', {{
                            method: 'POST'
                        }});
                    }} catch (error) {{
                        console.error('Cleanup failed', error);
                    }}
                }});
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


def _format_flag_value(value):
    """Formatta il valore del flag per visualizzazione"""
    if not value:
        return ""
    
    if isinstance(value, dict):
        html = "<ul style='margin-left: 20px;'>"
        for k, v in value.items():
            html += f"<li><strong>{k}:</strong> {v}</li>"
        html += "</ul>"
        return html
    
    return str(value)

