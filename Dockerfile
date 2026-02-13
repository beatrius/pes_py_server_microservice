FROM python:3.11-slim

# 1. Instalar dependencias esenciales
RUN apt-get update && apt-get install -y \
    inkscape \
    curl \
    libnss3 \
    && rm -rf /var/lib/apt/lists/*

# 2. Descargar e instalar Inkstitch (Usando la versión v3.0.1 verificada)
# Cambiamos a la versión 'linux' genérica que es más estable en sus nombres
RUN curl -L "https://github.com/inkstitch/inkstitch/releases/download/v3.0.1/inkstitch-v3.0.1-linux.tar.gz" -o inkstitch.tar.gz \
    && tar -xzf inkstitch.tar.gz \
    && mv inkstitch /usr/local/bin/inkstitch_dir \
    && ln -s /usr/local/bin/inkstitch_dir/inkstitch /usr/local/bin/inkstitch \
    && chmod +x /usr/local/bin/inkstitch \
    && rm inkstitch.tar.gz

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt

# Variable de entorno para que Inkscape funcione sin interfaz gráfica
ENV DISPLAY=:0

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
