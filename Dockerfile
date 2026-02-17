FROM python:3.11-slim

# 1. Instalar dependencias del sistema indispensables
RUN apt-get update && apt-get install -y \
    inkscape \
    curl \
    xz-utils \
    libnss3 \
    libgomp1 \
    libgl1 \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Instalar Inkstitch CLI (Versión 3.0.1 con estructura bin/inkstitch)
RUN curl -L -f "https://github.com/inkstitch/inkstitch/releases/download/v3.0.1/inkstitch-3.0.1-linux.tar.xz" -o inkstitch.tar.xz \
    && mkdir -p /usr/local/bin/inkstitch_cli \
    && tar -xJf inkstitch.tar.xz -C /usr/local/bin/inkstitch_cli --strip-components=1 \
    # Damos permisos de ejecución a todo el paquete extraído
    && chmod -R +x /usr/local/bin/inkstitch_cli \
    # Creamos el enlace simbólico para que el comando 'inkstitch' sea global
    && ln -sf /usr/local/bin/inkstitch_cli/bin/inkstitch /usr/local/bin/inkstitch \
    && rm inkstitch.tar.xz

# 3. Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copiar el código del proyecto
COPY . .

# Variables de entorno críticas para servidores sin pantalla
ENV QT_QPA_PLATFORM=offscreen
ENV INKSCAPE_PROFILE_DIR=/tmp
ENV HOME=/tmp

# Comando para arrancar la API (Render asigna el PORT automáticamente)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
