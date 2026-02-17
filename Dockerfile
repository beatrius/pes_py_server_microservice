FROM python:3.11-slim

# 1. Instalar dependencias del sistema (Incluye xz-utils para el nuevo formato)
RUN apt-get update && apt-get install -y \
    inkscape \
    curl \
    xz-utils \
    libnss3 \
    libgomp1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Instalar Inkstitch CLI (Detección dinámica de la URL)
# Esto busca el archivo .tar.xz de Linux en la release v3.0.1
RUN export DOWNLOAD_URL=$(curl -s https://api.github.com/repos/inkstitch/inkstitch/releases/tags/v3.0.1 \
    | grep "browser_download_url" | grep "linux-en_US.tar.xz" | cut -d '"' -f 4) \
    && echo "Descargando desde: $DOWNLOAD_URL" \
    && curl -L -f "$DOWNLOAD_URL" -o inkstitch.tar.xz \
    && mkdir -p /usr/local/bin/inkstitch_cli \
    && tar -xJf inkstitch.tar.xz -C /usr/local/bin/inkstitch_cli \
    && find /usr/local/bin/inkstitch_cli -name "inkstitch" -exec chmod +x {} \; \
    && find /usr/local/bin/inkstitch_cli -name "inkstitch" -exec ln -s {} /usr/local/bin/inkstitch \; \
    && rm inkstitch.tar.xz

# 3. Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copiar el código del proyecto
COPY . .

# Variables de entorno para evitar que Inkscape intente abrir ventanas gráficas
ENV QT_QPA_PLATFORM=offscreen
ENV INKSCAPE_PROFILE_DIR=/tmp

# Comando para arrancar la API
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
