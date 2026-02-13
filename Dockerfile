FROM python:3.11-slim

# 1. Instalar dependencias del sistema (Inkscape es obligatorio)
RUN apt-get update && apt-get install -y \
    inkscape \
    libnss3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Copiar archivos del proyecto
COPY . .

# 3. Instalar dependencias de Python + Inkstitch via pip
# Instalamos inkstitch directamente desde su repositorio de código
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "https://github.com/inkstitch/inkstitch/archive/refs/tags/v3.0.1.zip"

# Variable de entorno para que Inkscape no busque una pantalla
ENV DISPLAY=:0
ENV INKSCAPE_PROFILE_DIR=/tmp

# Render usa la variable $PORT
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
