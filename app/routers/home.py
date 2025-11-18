"""
Home page e endpoint principali per upload documenti
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Optional
import logging
import os
import uuid
from datetime import datetime

from app.core.config import settings
from app.core.models import ProcessingResponse, ProcessingStatus
from app.routers.processing import jobs_storage, process_matching_async

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def home():
    """
    Pagina principale con form per upload documenti
    """
    html_content = """
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Riconciliazione Contabile</title>
        <style>
            :root {
                color-scheme: light dark;
            }
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Inter', 'Segoe UI', sans-serif;
                background: #152238;
                min-height: 100vh;
                padding: 32px;
                color: #0f172a;
            }
            .page {
                max-width: 1200px;
                margin: 0 auto;
            }
            .hero {
                text-align: left;
                color: white;
                margin-bottom: 32px;
            }
            .hero h1 {
                font-size: 2.4rem;
                font-weight: 600;
                letter-spacing: -0.02em;
                margin-bottom: 8px;
            }
            .hero p {
                font-size: 1.05rem;
                color: rgba(255,255,255,0.75);
            }
            .layout {
                display: grid;
                grid-template-columns: 3fr 1fr;
                gap: 24px;
            }
            .card {
                background: #ffffff;
                border-radius: 18px;
                padding: 32px;
                box-shadow: 0 24px 60px rgba(15,23,42,0.35);
            }
            .form-grid {
                display: grid;
                gap: 28px;
            }
            .section-title {
                font-size: 1rem;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: #6b7280;
                margin-bottom: 12px;
            }
            .upload-box {
                border: 1px dashed #94a3b8;
                border-radius: 14px;
                padding: 28px;
                background: #f8fafc;
                text-align: center;
            }
            .upload-box input[type="file"] {
                display: none;
            }
            .upload-box label {
                display: inline-flex;
                align-items: center;
                gap: 10px;
                padding: 12px 28px;
                background: #111827;
                color: white;
                border-radius: 999px;
                font-weight: 500;
                cursor: pointer;
                transition: transform 0.2s ease, box-shadow 0.2s ease;
            }
            .upload-box label:hover {
                transform: translateY(-1px);
                box-shadow: 0 10px 30px rgba(15,23,42,0.25);
            }
            .file-name {
                margin-top: 14px;
                font-size: 0.9rem;
                color: #475569;
            }
            select, button {
                width: 100%;
                padding: 14px 16px;
                border-radius: 12px;
                border: 1px solid #d1d5db;
                font-size: 0.95rem;
                font-family: inherit;
            }
            .actions {
                display: flex;
                gap: 16px;
                margin-top: 10px;
                justify-content: flex-end;
            }
            .btn {
                min-width: 220px;
                border: none;
                border-radius: 12px;
                padding: 16px 18px;
                font-size: 1rem;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s ease, box-shadow 0.2s ease;
                text-align: center;
                text-decoration: none;
            }
            .btn:hover {
                transform: translateY(-1px);
                box-shadow: 0 10px 30px rgba(15,23,42,0.15);
            }
            .btn-primary {
                background: #111827;
                color: white;
            }
            .btn-secondary {
                background: #e5e7eb;
                color: #111827;
            }
            .sidebar {
                display: flex;
                flex-direction: column;
                gap: 20px;
            }
            .sidebar-section {
                border: 1px solid #e5e7eb;
                border-radius: 14px;
                padding: 24px;
                background: #f8fafc;
            }
            .sidebar-section h3 {
                font-size: 1rem;
                text-transform: uppercase;
                letter-spacing: 0.1em;
                color: #475569;
                margin-bottom: 12px;
            }
            .link-list a {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 14px 16px;
                margin-bottom: 8px;
                border-radius: 12px;
                text-decoration: none;
                color: #111827;
                background: white;
                border: 1px solid #e2e8f0;
                font-weight: 500;
            }
            .link-list a:hover {
                border-color: #111827;
            }
            .helper-text {
                font-size: 0.9rem;
                color: #6b7280;
                margin-top: 6px;
            }
            .guidelines p {
                margin-bottom: 12px;
                color: #475569;
            }
            .loading {
                display: none;
                margin-top: 24px;
                text-align: center;
                color: #111827;
                font-weight: 500;
            }
            .loading.active { display: block; }
            @media (max-width: 900px) {
                .layout {
                    grid-template-columns: 1fr;
            }
                body {
                    padding: 20px;
                }
                .card {
                    padding: 24px;
                }
            }
        </style>
    </head>
    <body>
        <div class="page">
            <header class="hero">
                <h1>Riconciliazione Contabile</h1>
                <p>Confronto deterministico tra estratti conto bancari e schede contabili.</p>
            </header>
            <div class="layout">
                <section class="card">
                    <div class="form-grid">
                        <div>
                            <p class="section-title">Estratto conto bancario</p>
                            <div class="upload-box">
                                <input type="file" id="estratto_conto" name="estratto_conto" form="uploadForm" accept=".pdf" required>
                                <label for="estratto_conto">Seleziona file PDF</label>
                                <div class="file-name" id="estratto-name">Nessun file selezionato</div>
                            </div>
                            <div class="helper-text">Il file verrà elaborato localmente. Nessun dato lascia il server.</div>
                            <div style="margin-top:16px;">
                                <label for="bank_type" class="section-title" style="font-size:0.85rem; letter-spacing:0.08em;">Tipo di banca</label>
                                <select id="bank_type" name="bank_type" form="uploadForm">
                                    <option value="credit_agricole">Credit Agricole</option>
                                    <option value="placeholder_1" disabled>Altro tipo 1 (in arrivo)</option>
                                    <option value="placeholder_2" disabled>Altro tipo 2 (in arrivo)</option>
                                </select>
                </div>
                        </div>
                        <div>
                            <p class="section-title">Scheda contabile</p>
                            <div class="upload-box">
                                <input type="file" id="scheda_contabile" name="scheda_contabile" form="uploadForm" accept=".pdf" required>
                                <label for="scheda_contabile">Seleziona file PDF</label>
                                <div class="file-name" id="scheda-name">Nessun file selezionato</div>
                            </div>
                            <div class="helper-text">Usare il formato esportato dal gestionale per garantire la compatibilità.</div>
                            <div style="margin-top:16px;">
                                <label for="accounting_type" class="section-title" style="font-size:0.85rem; letter-spacing:0.08em;">Tipo di gestionale</label>
                                <select id="accounting_type" name="accounting_type" form="uploadForm">
                                    <option value="wolters_kluwer">Wolters Kluwer (OSRA BPoint)</option>
                                    <option value="placeholder_1" disabled>Altro tipo 1 (in arrivo)</option>
                                    <option value="placeholder_2" disabled>Altro tipo 2 (in arrivo)</option>
                                </select>
                            </div>
                        </div>
                    </div>
                    <form id="uploadForm" action="/process" method="post" enctype="multipart/form-data" style="margin-top:28px;">
                        <div class="actions">
                            <button type="submit" class="btn btn-primary" id="submitBtn">Avvia riconciliazione</button>
                        </div>
                    </form>
                    <div class="loading" id="loading">Elaborazione in corso…</div>
                </section>
                <aside class="sidebar">
                    <div class="sidebar-section">
                        <h3>Strumenti avanzati</h3>
                    <div class="link-list">
                        <a href="/test-ocr">Test parser OCR<span>&rarr;</span></a>
                        <a href="/debug-pdf">Analisi struttura PDF<span>&rarr;</span></a>
                        <a href="/documentation">Documentazione interna<span>&rarr;</span></a>
                    </div>
                        <p class="helper-text">Utilizza gli strumenti avanzati per verificare le estrazioni o analizzare nuovi layout prima di procedere con la riconciliazione completa.</p>
                    </div>
                    <div class="sidebar-section">
                        <h3>Linee guida</h3>
                        <div class="guidelines">
                            <p>I file devono essere PDF nativi esportati dal gestionale.</p>
                            <p>Validare i layout nuovi con il Test parser prima della riconciliazione.</p>
                            <p>Limitare la dimensione a 50 MB per garantire tempi rapidi.</p>
                        </div>
                </div>
                </aside>
            </div>
        </div>
        <script>
            (function() {
                'use strict';
                
                function bindFileInput(inputId, labelId) {
                    var input = document.getElementById(inputId);
                    var label = document.getElementById(labelId);
                    
                    if (!input || !label) {
                        return;
                    }
                    
                    input.addEventListener('change', function(e) {
                        var file = e.target.files[0];
                        var name = file ? file.name : 'Nessun file selezionato';
                        label.textContent = name;
                    });
                }
                
                function init() {
                    bindFileInput('estratto_conto', 'estratto-name');
                    bindFileInput('scheda_contabile', 'scheda-name');
                    
                    var uploadForm = document.getElementById('uploadForm');
                    if (uploadForm) {
                        uploadForm.addEventListener('submit', function() {
                            var submitBtn = document.getElementById('submitBtn');
                            var loading = document.getElementById('loading');
                            if (submitBtn) submitBtn.disabled = true;
                            if (loading) loading.classList.add('active');
                        });
                    }
                }
                
                if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', init);
                } else {
                    init();
                }
            })();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.post("/process", response_class=HTMLResponse)
async def process_upload(
    estratto_conto: UploadFile = File(...),
    scheda_contabile: UploadFile = File(...),
    bank_type: str = Form("credit_agricole"),
    accounting_type: str = Form("wolters_kluwer"),
    matching_tolerance: float = Form(0.01),
    background_tasks: BackgroundTasks = None
):
    """
    Endpoint per processare upload dalla pagina home
    Avvia riconciliazione e reindirizza alla pagina risultati
    
    Args:
        estratto_conto: File PDF estratto conto
        scheda_contabile: File PDF scheda contabile
        bank_type: Tipo di banca (default: "credit_agricole")
        accounting_type: Tipo di gestionale (default: "wolters_kluwer")
        matching_tolerance: Tolleranza per matching importi
    """
    job_id = str(uuid.uuid4())
    
    # Salva file temporaneamente
    estratto_path = os.path.join(settings.data_input_path, f"{job_id}_estratto_{estratto_conto.filename}")
    scheda_path = os.path.join(settings.data_input_path, f"{job_id}_scheda_{scheda_contabile.filename}")
    
    try:
        os.makedirs(settings.data_input_path, exist_ok=True)
        
        # Salva estratto conto
        with open(estratto_path, "wb") as f:
            content = await estratto_conto.read()
            f.write(content)
        
        # Salva scheda contabile
        with open(scheda_path, "wb") as f:
            content = await scheda_contabile.read()
            f.write(content)
        
        # Avvia processing in background
        if background_tasks:
            background_tasks.add_task(
                process_matching_async,
                job_id,
                estratto_path,
                scheda_path,
                matching_tolerance,
                bank_type,
                accounting_type
            )
        
        jobs_storage[job_id] = {
            "status": ProcessingStatus.PENDING,
            "created_at": datetime.now()
        }
        
        # Reindirizza alla pagina di attesa/risultati
        return RedirectResponse(url=f"/results/{job_id}", status_code=303)
        
    except Exception as e:
        logger.error(f"Error processing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

