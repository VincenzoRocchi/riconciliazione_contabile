# Usa un'immagine leggera di Python
FROM python:3.11-slim

# Variabili d'ambiente per non scrivere .pyc e per l'output immediato
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Directory di lavoro nel container
WORKDIR /code

# Installa dipendenze di sistema per pdfplumber
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copia e installa i requirements
COPY requirements.txt /code/
RUN pip install --no-cache-dir -r requirements.txt

# Copia i file di documentazione
COPY ./docs /code/docs

# Copia il resto del codice
COPY ./app /code/app

# Espone la porta 8000
EXPOSE 8000

# Comando di avvio (Hot reload attivo per lo sviluppo)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

