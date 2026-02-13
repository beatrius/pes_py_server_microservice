FROM python:3.11-slim

# 1. Instalar dependencias del sistema e Inkscape
RUN apt-get update && apt-get install -y \
    inkscape \
    wget \
    libnss3 \
    && rm -rf /var/lib/apt/lists/*

# 2. Instalar Inkstitch usando el paquete .deb (Más fiable)
RUN wget https://github.com/inkstitch/inkstitch/releases/download/v3.0.1/inkstitch_3.0.1_amd64.deb \
    && apt-get update \
    && apt-get install -y ./inkstitch_3.0.1_amd64.deb \
    && rm inkstitch_3.0.1_amd64.deb

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt

# Render usa la variable de entorno PORT
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
