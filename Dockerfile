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

# 2. Instalar Inkstitch CLI desde la URL oficial (evita subir el archivo a GitHub)
RUN curl -L -f "https://github.com/inkstitch/inkstitch/releases/download/v3.0.1/inkstitch-3.0.1-linux.tar.xz" -o inkstitch.tar.xz \
    && mkdir -p /usr/local/bin/inkstitch_cli \
    && tar -xJf inkstitch.tar.xz -C /usr/local/bin/inkstitch_cli \
    && find /usr/local/bin/inkstitch_cli -name "inkstitch" -exec chmod +x {} \; \
    && ln -sf $(find /usr/local/bin/inkstitch_cli -name "inkstitch") /usr/local/bin/inkstitch \
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