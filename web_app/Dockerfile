FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Configurar pip con timeout largo y reintentos para redes lentas
RUN pip config set global.timeout 600 && \
    pip config set global.retries 10

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 600 --retries 10 -r requirements.txt

COPY entrypoint.sh .
RUN chmod +x /app/entrypoint.sh

COPY . .
RUN groupadd --system appuser && useradd --system --gid appuser appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

CMD ["bash", "/app/entrypoint.sh"]