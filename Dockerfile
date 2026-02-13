FROM python:3.11-slim

# 1. Instalar dependencias esenciales
RUN apt-get update && apt-get install -y \
    inkscape \
    curl \
    libnss3 \
    && rm -rf /var/lib/apt/lists/*

# 2. Instalar Inkstitch v2.2.0 (URL ULTRA-ESTABLE)
# Usamos esta versión porque el enlace de GitHub es directo y no falla
RUN curl -L "https://github.com/inkstitch/inkstitch/releases/download/v2.2.0/inkstitch-v2.2.0-linux-en_US.tar.gz" -o inkstitch.tar.gz \
    && tar -xzf inkstitch.tar.gz \
    && mv inkstitch /usr/local/bin/inkstitch_dir \
    && ln -s /usr/local/bin/inkstitch_dir/inkstitch /usr/local/bin/inkstitch \
    && chmod +x /usr/local/bin/inkstitch \
    && rm inkstitch.tar.gz

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt

# Configuración necesaria para servidores
ENV DISPLAY=:0
ENV INKSCAPE_PROFILE_DIR=/tmp

# Render usa la variable $PORT automáticamente
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
