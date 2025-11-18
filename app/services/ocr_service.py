"""
OCR Service per estrazione dati da documenti contabili
Usa solo pdfplumber locale (PDF nativi, nessun OCR/AI necessario)
"""
from typing import Dict, Any
import logging
import pandas as pd
from app.services.parsers import parse_scheda_contabile, parse_estratto_conto

logger = logging.getLogger(__name__)


class OCRService:
    """Servizio per estrazione dati da PDF nativi (solo pdfplumber, locale)"""
    
    def extract_from_accounting_sheet(self, pdf_path: str) -> Dict[str, Any]:
        """
        Estrae dati da scheda contabile usando parser locale (pdfplumber)
        PDF nativo, estrazione deterministica e veloce
        """
        logger.info(f"Extracting data from accounting sheet: {pdf_path}")
        
        try:
            df = parse_scheda_contabile(pdf_path)
            
            # Converti DataFrame in formato dict compatibile
            return {
                "document_type": "accounting_sheet",
                "raw_text": "",
                "structured_data": {
                    "transactions": df.to_dict('records')
                },
                "metadata": {
                    "total_transactions": len(df),
                    "parser": "pdfplumber_local"
                },
                "dataframe": df  # Mantieni anche il DataFrame per uso diretto
            }
        except Exception as e:
            logger.error(f"Error parsing accounting sheet: {e}")
            raise
    
    def extract_from_bank_statement(self, pdf_path: str, bank_type: str = "credit_agricole") -> Dict[str, Any]:
        """
        Estrae dati da estratto conto usando parser locale (pdfplumber)
        PDF nativo, estrazione deterministica e veloce
        
        Args:
            pdf_path: Percorso del PDF
            bank_type: Tipo di banca (default: "credit_agricole")
        """
        logger.info(f"Extracting data from bank statement: {pdf_path} (bank_type: {bank_type})")
        
        try:
            df = parse_estratto_conto(pdf_path, bank_type=bank_type)
            
            # Converti DataFrame in formato dict compatibile
            return {
                "document_type": "bank_statement",
                "raw_text": "",
                "structured_data": {
                    "transactions": df.to_dict('records')
                },
                "metadata": {
                    "total_transactions": len(df),
                    "parser": "pdfplumber_local",
                    "bank_type": bank_type
                },
                "dataframe": df  # Mantieni anche il DataFrame per uso diretto
            }
        except Exception as e:
            logger.error(f"Error parsing bank statement: {e}")
            raise
