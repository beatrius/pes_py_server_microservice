FROM python:3.11-slim

# Instalar Inkscape y dependencias necesarias
RUN apt-get update && apt-get install -y \
    inkscape \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Instalar Inkstitch CLI (Versión específica verificada)
RUN wget https://github.com/inkstitch/inkstitch/releases/download/v3.0.1/inkstitch-3.0.1-linux-en_US.tar.gz \
    && tar -xzvf inkstitch-3.0.1-linux-en_US.tar.gz \
    && mv inkstitch /usr/local/bin/inkstitch \
    && chmod +x /usr/local/bin/inkstitch

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt

# Render usa la variable de entorno PORT
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
