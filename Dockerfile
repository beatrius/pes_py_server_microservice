FROM python:3.11-slim

# 1. Instalar dependencias del sistema (Añadido unzip)
RUN apt-get update && apt-get install -y \
    inkscape \
    curl \
    unzip \
    libnss3 \
    libgomp1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Instalar Inkstitch CLI (Búsqueda dinámica del asset)
RUN URL=$(curl -s https://api.github.com/repos/inkstitch/inkstitch/releases/tags/v3.0.1 | grep "browser_download_url" | grep "linux-en_US.zip" | cut -d '"' -f 4) \
    && echo "Descargando desde: $URL" \
    && curl -L -f "$URL" -o inkstitch.zip \
    && mkdir -p /usr/local/bin/inkstitch_cli \
    && unzip inkstitch.zip -d /usr/local/bin/inkstitch_cli \
    && find /usr/local/bin/inkstitch_cli -name "inkstitch" -exec chmod +x {} \; \
    && find /usr/local/bin/inkstitch_cli -name "inkstitch" -exec ln -s {} /usr/local/bin/inkstitch \; \
    && rm inkstitch.zip

# 3. Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV QT_QPA_PLATFORM=offscreen
ENV INKSCAPE_PROFILE_DIR=/tmp

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
