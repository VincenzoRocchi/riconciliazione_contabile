"""
Processing endpoints per upload e processamento documenti
Verifica di coerenza tra estratto conto e scheda contabile
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Optional
import os
import uuid
from datetime import datetime, timedelta
import logging
from pathlib import Path

from app.core.config import settings
from app.core.models import (
    ProcessingResponse, ProcessingStatus,
    FinalReport, ValidationIssue, ValidationFlag, MatchingStatus
)
from app.services.ocr_service import OCRService
from app.services.reconciliation_logic import riconcilia_saldi

router = APIRouter()
logger = logging.getLogger(__name__)

# Storage per job (in produzione usare Redis/DB)
jobs_storage = {}


def cleanup_old_files(directory: str, max_files: int = 10):
    """
    Mantiene solo i max_files più recenti in una directory, elimina i più vecchi.
    
    Args:
        directory: Percorso della directory da pulire
        max_files: Numero massimo di file da mantenere (default: 10)
    """
    try:
        dir_path = Path(directory)
        if not dir_path.exists():
            return
        
        # Ottieni tutti i file (escludi directory e file nascosti)
        files = [f for f in dir_path.iterdir() if f.is_file() and not f.name.startswith('.')]
        
        if len(files) <= max_files:
            return
        
        # Ordina per data di modifica (più recente prima)
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        
        # Elimina i file più vecchi
        files_to_delete = files[max_files:]
        for file_to_delete in files_to_delete:
            try:
                file_to_delete.unlink()
                logger.info(f"Eliminato file vecchio: {file_to_delete.name}")
            except Exception as e:
                logger.warning(f"Errore nell'eliminazione di {file_to_delete.name}: {e}")
        
        logger.info(f"Pulizia completata: mantenuti {max_files} file più recenti in {directory}")
        
    except Exception as e:
        logger.error(f"Errore durante la pulizia di {directory}: {e}")


@router.post("/process", response_model=ProcessingResponse)
async def process_document(
    estratto_conto: UploadFile = File(..., description="Estratto conto bancario"),
    scheda_contabile: UploadFile = File(..., description="Scheda contabile da verificare"),
    matching_tolerance: float = 0.01,
    bank_type: str = "credit_agricole",
    accounting_type: str = "wolters_kluwer",
    background_tasks: BackgroundTasks = None
):
    """
    Endpoint API per processare riconciliazione tra estratto conto e scheda contabile
    
    - **estratto_conto**: Estratto conto bancario
    - **scheda_contabile**: Scheda contabile da verificare
    - **matching_tolerance**: Tolleranza per confronto importi (default 0.01 = 1 centesimo)
    - **bank_type**: Tipo di banca (default: "credit_agricole")
    - **accounting_type**: Tipo di gestionale (default: "wolters_kluwer")
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
        
        # Pulisci file vecchi da data_input (mantieni solo 10 più recenti)
        cleanup_old_files(settings.data_input_path, max_files=10)
        
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
        
        return ProcessingResponse(
            job_id=job_id,
            status=ProcessingStatus.PENDING,
            message="Matching process started"
        )
        
    except Exception as e:
        logger.error(f"Error processing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/process/{job_id}", response_model=FinalReport)
async def get_processing_result(job_id: str):
    """
    Recupera il risultato del processing
    """
    if job_id not in jobs_storage:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs_storage[job_id]
    
    if job["status"] != ProcessingStatus.COMPLETED:
        return JSONResponse({
            "job_id": job_id,
            "status": job["status"],
            "message": "Processing still in progress"
        })
    
    return job.get("result")


async def process_matching_async(
    job_id: str,
    estratto_path: str,
    scheda_path: str,
    matching_tolerance: float,
    bank_type: str = "credit_agricole",
    accounting_type: str = "wolters_kluwer"
):
    """
    Funzione asincrona per processare la riconciliazione tra estratto conto e scheda contabile
    Usa solo parser locali (pdfplumber)
    
    Args:
        job_id: ID del job
        estratto_path: Percorso estratto conto PDF
        scheda_path: Percorso scheda contabile PDF
        matching_tolerance: Tolleranza per matching importi
        bank_type: Tipo di banca (default: "credit_agricole")
        accounting_type: Tipo di gestionale (default: "wolters_kluwer")
    """
    try:
        jobs_storage[job_id]["status"] = ProcessingStatus.PROCESSING
        
        # 1. Parsing - Estratto conto
        logger.info(f"Parsing estratto conto: {estratto_path} (bank_type: {bank_type})")
        ocr_service = OCRService()
        estratto_data = ocr_service.extract_from_bank_statement(estratto_path, bank_type=bank_type)
        df_banca = estratto_data.get("dataframe")
        
        if df_banca is None or df_banca.empty:
            raise ValueError("No data extracted from estratto conto")
        
        # 2. Parsing - Scheda contabile
        logger.info(f"Parsing scheda contabile: {scheda_path} (accounting_type: {accounting_type})")
        scheda_data = ocr_service.extract_from_accounting_sheet(scheda_path, accounting_type=accounting_type)
        df_contabilita = scheda_data.get("dataframe")
        
        if df_contabilita is None or df_contabilita.empty:
            raise ValueError("No data extracted from scheda contabile")
        
        # 3. Riconciliazione
        jobs_storage[job_id]["status"] = ProcessingStatus.VALIDATING
        logger.info("Starting reconciliation process")
        
        # Usa tolleranza custom se fornita, altrimenti da settings
        tolerance = matching_tolerance if matching_tolerance > 0 else settings.amount_tolerance
        
        risultati_df, summary = riconcilia_saldi(
            df_banca,
            df_contabilita,
            amount_tolerance=tolerance,
            date_tolerance_days=settings.date_tolerance_days,
            max_combinations=getattr(settings, 'max_combinations', 5),
            max_brute_force_iterations=getattr(settings, 'max_brute_force_iterations', 50000),
            min_amount_for_brute_force=getattr(settings, 'min_amount_for_brute_force', 100.0)
        )
        
        # 4. Genera flags dalle voci mancanti/orfani
        flags = []
        
        # Voci mancanti in contabilità
        missing = risultati_df[risultati_df['Stato'] == 'MANCANTE']
        for _, row in missing.iterrows():
            flags.append(ValidationIssue(
                flag_type=ValidationFlag.MISSING_DATA,
                severity="error",
                message=f"Voce mancante nella scheda contabile",
                field="reconciliation",
                value={
                    "data": str(row.get('Data Banca', '')),
                    "importo": row.get('Importo Banca', 0),
                    "descrizione": row.get('Descrizione Banca', '')
                }
            ))
        
        # Voci orfane in contabilità (non presenti in banca)
        orfani = risultati_df[risultati_df['Stato'].str.contains('NON TROVATO', na=False)]
        for _, row in orfani.iterrows():
            flags.append(ValidationIssue(
                flag_type=ValidationFlag.INCONSISTENCY,
                severity="warning",
                message=f"Voce in contabilità non presente in estratto conto",
                field="reconciliation",
                value={
                    "data": str(row.get('Data Contabilità', '')),
                    "importo": row.get('Importo Contabilità', 0),
                    "descrizione": row.get('Descrizione Contabilità', '')
                }
            ))
        
        # 5. Determina overall verdict
        if summary["missing_in_contabilita"] == 0 and summary["orfani_in_contabilita"] == 0:
            overall_verdict = "valid"
        elif summary["missing_in_contabilita"] > 0:
            overall_verdict = "invalid"
        else:
            overall_verdict = "needs_review"
        
        # 6. Build Final Report (formato compatibile)
        from app.core.models import MatchingResult, VoiceMatch
        
        voice_matches = []
        for _, row in risultati_df.iterrows():
            if row['Stato'] == 'OK':
                voice_matches.append(VoiceMatch(
                    estratto_voice_id="",
                    estratto_voice={
                        "data": str(row.get('Data Banca', '')),
                        "importo": row.get('Importo Banca', 0),
                        "descrizione": row.get('Descrizione Banca', '')
                    },
                    match_status=MatchingStatus.MATCHED,
                    matched_scheda_voice={
                        "data": str(row.get('Data Contabilità', '')),
                        "importo": row.get('Importo Contabilità', 0),
                        "descrizione": row.get('Descrizione Contabilità', '')
                    },
                    confidence=1.0
                ))
            elif row['Stato'] == 'MANCANTE':
                voice_matches.append(VoiceMatch(
                    estratto_voice_id="",
                    estratto_voice={
                        "data": str(row.get('Data Banca', '')),
                        "importo": row.get('Importo Banca', 0),
                        "descrizione": row.get('Descrizione Banca', '')
                    },
                    match_status=MatchingStatus.MISSING,
                    confidence=0.0
                ))
        
        matching_result = MatchingResult(
            total_estratto_voices=summary["total_banca"],
            matched_voices=summary["matched"],
            missing_voices=summary["missing_in_contabilita"],
            partial_matches=0,
            duplicate_voices=summary["orfani_in_contabilita"],
            voice_matches=voice_matches,
            is_complete=(summary["missing_in_contabilita"] == 0),
            summary={
                **summary,
                "risultati_df": risultati_df.to_dict('records')
            }
        )
        
        final_report = FinalReport(
            job_id=job_id,
            processing_status=ProcessingStatus.COMPLETED,
            matching_result=matching_result,
            estratto_conto_data={
                "transactions": df_banca.to_dict('records'),
                "summary": {
                    "total": len(df_banca),
                    "saldo": float(df_banca['importo'].sum())
                }
            },
            scheda_contabile_data={
                "transactions": df_contabilita.to_dict('records'),
                "summary": {
                    "total": len(df_contabilita),
                    "saldo": float(df_contabilita['importo'].sum())
                }
            },
            flags=flags,
            overall_verdict=overall_verdict
        )
        
        jobs_storage[job_id]["status"] = ProcessingStatus.COMPLETED
        jobs_storage[job_id]["result"] = final_report
        
        # Salva report
        output_path = os.path.join(settings.data_output_path, f"{job_id}_report.json")
        os.makedirs(settings.data_output_path, exist_ok=True)
        with open(output_path, "w") as f:
            import json
            json.dump(final_report.dict(), f, indent=2, default=str)
        
        # Salva anche CSV per analisi
        csv_path = os.path.join(settings.data_output_path, f"{job_id}_risultati.csv")
        risultati_df.to_csv(csv_path, index=False)
        
        # Pulisci file vecchi da data_output (mantieni solo 10 più recenti)
        cleanup_old_files(settings.data_output_path, max_files=10)
        
        logger.info(f"Reconciliation completed for job {job_id}: {summary['matched']}/{summary['total_banca']} matched, "
                   f"saldo banca: {summary['saldo_banca']:.2f}, saldo contabilità: {summary['saldo_contabilita']:.2f}")
        
    except Exception as e:
        logger.error(f"Error in async reconciliation: {e}")
        jobs_storage[job_id]["status"] = ProcessingStatus.FAILED
        jobs_storage[job_id]["error"] = str(e)


def cleanup_old_jobs(max_age_hours: int = 24) -> int:
    """
    Cancella i job più vecchi della finestra specificata (default 24h).
    Restituisce il numero di job eliminati.
    """
    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    to_delete = []
    
    for job_id, job in list(jobs_storage.items()):
        created_at = job.get("created_at")
        if created_at is None or created_at < cutoff:
            to_delete.append(job_id)
    
    for job_id in to_delete:
        jobs_storage.pop(job_id, None)
    
    if to_delete:
        logger.info(f"Removed {len(to_delete)} expired reconciliation job(s)")
    
    return len(to_delete)
