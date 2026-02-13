FROM python:3.11-slim

# Instalar Inkscape y dependencias necesarias
RUN apt-get update && apt-get install -y \
    inkscape \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Instalar Inkstitch CLI (Versión universal)
RUN wget https://github.com/inkstitch/inkstitch/releases/latest/download/inkstitch-linux-amd64.tar.gz \
    && tar -xzvf inkstitch-linux-amd64.tar.gz \
    && mv inkstitch /usr/local/bin/inkstitch \
    && chmod +x /usr/local/bin/inkstitch

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt

# Render usa la variable de entorno PORT
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
