FROM python:3.11-slim

# 1. Dependencias de sistema necesarias para Inkscape y lxml
RUN apt-get update && apt-get install -y \
    inkscape \
    curl \
    xz-utils \
    libnss3 \
    libgomp1 \
    libgl1 \
    libxml2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Instalación de Inkstitch - MÉTODO ROBUSTO
# Descargamos, creamos carpeta, extraemos ignorando la carpeta raíz del zip y damos permisos
RUN curl -L -f "https://github.com/inkstitch/inkstitch/releases/download/v3.0.1/inkstitch-3.0.1-linux.tar.xz" -o inkstitch.tar.xz \
    && mkdir -p /opt/inkstitch \
    && tar -xJf inkstitch.tar.xz -C /opt/inkstitch --strip-components=1 \
    && chmod -R +x /opt/inkstitch/bin/inkstitch \
    && rm inkstitch.tar.xz

# 3. Crear un enlace simbólico REAL en la ruta de sistema
RUN ln -s /opt/inkstitch/bin/inkstitch /usr/bin/inkstitch

# 4. Configurar Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# 5. Variables de entorno - Aquí está el secreto para Render
ENV PATH="/opt/inkstitch/bin:${PATH}"
ENV HOME=/tmp
ENV INKSCAPE_PROFILE_DIR=/tmp
ENV QT_QPA_PLATFORM=offscreen

# Render usa la variable $PORT
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
