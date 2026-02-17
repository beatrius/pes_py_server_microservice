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

# 2. Instalar Inkstitch CLI (URL Directa verificada v3.0.1)
RUN curl -L -f "https://github.com/inkstitch/inkstitch/releases/download/v3.0.1/inkstitch-v3.0.1-linux-en_US.zip" -o inkstitch.zip \
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
