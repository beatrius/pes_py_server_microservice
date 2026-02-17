FROM python:3.11-slim

# 1. Instalar dependencias del sistema y librerías gráficas/matemáticas
RUN apt-get update && apt-get install -y \
    inkscape \
    curl \
    xz-utils \
    libnss3 \
    libgomp1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Instalar Inkstitch CLI (URL corregida v3.0.1)
RUN curl -L -f "https://github.com/inkstitch/inkstitch/releases/download/v3.0.1/inkstitch-v3.0.1-linux.tar.xz" -o inkstitch.tar.xz \
    && mkdir -p /usr/local/bin/inkstitch_cli \
    && tar -xJf inkstitch.tar.xz -C /usr/local/bin/inkstitch_cli \
    && chmod +x /usr/local/bin/inkstitch_cli/inkstitch \
    && ln -s /usr/local/bin/inkstitch_cli/inkstitch /usr/local/bin/inkstitch \
    && rm inkstitch.tar.xz

# 3. Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV QT_QPA_PLATFORM=offscreen
ENV INKSCAPE_PROFILE_DIR=/tmp

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]