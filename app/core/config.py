"""
Configuration management per l'applicazione
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Impostazioni dell'applicazione caricate da .env"""
    
    # Application Settings
    debug: bool = True
    log_level: str = "INFO"
    max_file_size_mb: int = 50
    
    # Reconciliation Settings
    amount_tolerance: float = 0.01  # Tolleranza per confronto importi (default 1 centesimo)
    date_tolerance_days: int = 5  # Finestra di tolleranza per date (default ±5 giorni)
    
    # Paths
    data_input_path: str = "/code/data_input"
    data_output_path: str = "/code/data_output"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
