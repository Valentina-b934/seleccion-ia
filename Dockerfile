# Imagen para desplegar el sistema completo (API, panel, motor de flujos y módulo de visión).
# Incluye Tesseract con español para que el OCR corra dentro del servidor.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN mkdir -p data/imagenes

EXPOSE 8000
# Render y Railway entregan el puerto en la variable PORT.
CMD ["sh", "-c", "uvicorn app.servidor:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
