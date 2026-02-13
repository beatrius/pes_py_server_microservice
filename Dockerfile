FROM python:3.11-slim

# 1. Instalar dependencias del sistema e Inkscape
RUN apt-get update && apt-get install -y \
    inkscape \
    wget \
    libnss3 \
    && rm -rf /var/lib/apt/lists/*

# 2. Instalar Inkstitch CLI (URL UNIVERSAL v3.0.1)
RUN wget https://github.com/inkstitch/inkstitch/releases/download/v3.0.1/inkstitch-v3.0.1-linux.tar.gz \
    && tar -xzvf inkstitch-v3.0.1-linux.tar.gz \
    && cp inkstitch/inkstitch /usr/local/bin/inkstitch \
    && chmod +x /usr/local/bin/inkstitch \
    && rm -rf inkstitch inkstitch-v3.0.1-linux.tar.gz

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt

# Render usa la variable de entorno PORT
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
