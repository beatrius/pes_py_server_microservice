FROM python:3.11-slim

# 1. Instalar dependencias del sistema, Inkscape y librerías matemáticas
RUN apt-get update && apt-get install -y \
    inkscape \
    curl \
    unzip \
    libnss3 \
    libgomp1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Instalar Inkstitch CLI (Versión ejecutable para Linux)
# Esto es mucho más estable que el código fuente
RUN curl -L "https://github.com/inkstitch/inkstitch/releases/download/v3.0.1/inkstitch-v3.0.1-linux-en_US.zip" -o inkstitch.zip \
    && unzip inkstitch.zip -d /usr/local/bin/inkstitch_cli \
    && chmod +x /usr/local/bin/inkstitch_cli/inkstitch \
    && ln -s /usr/local/bin/inkstitch_cli/inkstitch /usr/local/bin/inkstitch \
    && rm inkstitch.zip

# 3. Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Variables de entorno para ejecución sin pantalla
ENV QT_QPA_PLATFORM=offscreen
ENV INKSCAPE_PROFILE_DIR=/tmp

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]