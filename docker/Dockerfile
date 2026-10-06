FROM python:3.11-slim

WORKDIR /app

# Instalar Ollama
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://ollama.ai/install.sh | sh

# Copiar requirements
COPY docker/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY src/ src/

EXPOSE 8000

CMD ["python", "src/main.py"]
