"""
Modelli per riconciliazione contabile
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ProcessingStatus(str, Enum):
    """Stati del processing"""
    PENDING = "pending"
    PROCESSING = "processing"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingResponse(BaseModel):
    """Risposta iniziale quando viene avviato un job di processing"""
    job_id: str
    status: ProcessingStatus
    message: str


class ValidationFlag(str, Enum):
    """Tipi di flag di validazione"""
    MISSING_DATA = "missing_data"
    INCONSISTENCY = "inconsistency"


class MatchingStatus(str, Enum):
    """Stati di matching delle voci"""
    MATCHED = "matched"
    MISSING = "missing"  # Voce nell'estratto conto non trovata nella scheda


class ValidationIssue(BaseModel):
    """Singolo problema di validazione"""
    flag_type: ValidationFlag
    severity: str  # "error", "warning"
    message: str
    field: Optional[str] = None
    value: Optional[Any] = None


class VoiceMatch(BaseModel):
    """Risultato matching di una singola voce"""
    estratto_voice_id: str
    estratto_voice: Dict[str, Any]
    match_status: MatchingStatus
    matched_scheda_voice_id: Optional[str] = None
    matched_scheda_voice: Optional[Dict[str, Any]] = None
    confidence: float = 0.0


class MatchingResult(BaseModel):
    """Risultato del matching tra estratto conto e scheda contabile"""
    total_estratto_voices: int
    matched_voices: int
    missing_voices: int
    partial_matches: int
    duplicate_voices: int
    voice_matches: List[VoiceMatch] = []
    is_complete: bool
    summary: Dict[str, Any] = {}


class FinalReport(BaseModel):
    """Report finale completo"""
    job_id: str
    processing_status: ProcessingStatus
    matching_result: MatchingResult
    estratto_conto_data: Dict[str, Any] = {}
    scheda_contabile_data: Dict[str, Any] = {}
    flags: List[ValidationIssue] = []
    overall_verdict: str  # "valid", "needs_review", "invalid"
    generated_at: datetime = Field(default_factory=datetime.now)
