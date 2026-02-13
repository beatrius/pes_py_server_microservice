FROM python:3.11-slim

# 1. Instalar dependencias (añadimos curl)
RUN apt-get update && apt-get install -y \
    inkscape \
    curl \
    wget \
    libnss3 \
    && rm -rf /var/lib/apt/lists/*

# 2. Instalar Inkstitch usando curl -L (Método Blindado)
# Esta URL es la oficial para la v3.0.1
RUN curl -L -o inkstitch.tar.gz https://github.com/inkstitch/inkstitch/releases/download/v3.0.1/inkstitch-v3.0.1-linux-en_US.tar.gz \
    && tar -xzvf inkstitch.tar.gz \
    && mv inkstitch /usr/local/bin/inkstitch \
    && chmod +x /usr/local/bin/inkstitch \
    && rm inkstitch.tar.gz

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt

# Render usa la variable de entorno PORT
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
