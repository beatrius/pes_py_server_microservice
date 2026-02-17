FROM python:3.11-slim

# 1. Dependencias base + utilidades
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

# 2. Instalación Forzada de Inkstitch
# Usamos /opt/ para que sea una ruta absoluta y limpia
RUN curl -L -f "https://github.com/inkstitch/inkstitch/releases/download/v3.0.1/inkstitch-3.0.1-linux.tar.xz" -o inkstitch.tar.xz \
    && mkdir -p /opt/inkstitch \
    && tar -xJf inkstitch.tar.xz -C /opt/inkstitch --strip-components=1 \
    && chmod -R 755 /opt/inkstitch \
    && ln -sf /opt/inkstitch/bin/inkstitch /usr/local/bin/inkstitch \
    && rm inkstitch.tar.xz

# 3. Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Variables de entorno para que el sistema encuentre Inkstitch sí o sí
ENV PATH="/opt/inkstitch/bin:${PATH}"
ENV QT_QPA_PLATFORM=offscreen
ENV INKSCAPE_PROFILE_DIR=/tmp
ENV HOME=/tmp

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
