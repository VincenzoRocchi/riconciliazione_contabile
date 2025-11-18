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
    
    # Brute Force Matching Settings
    max_combinations: int = 5  # Massimo numero di voci da combinare per brute force
    max_brute_force_iterations: int = 50000  # Limite sicurezza per evitare loop infiniti nel brute force (aumentato per gestire più candidati)
    min_amount_for_brute_force: float = 100.0  # Importo minimo per attivare brute force (solo per importi grandi come assegni)
    
    # Paths
    data_input_path: str = "/code/data_input"
    data_output_path: str = "/code/data_output"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
