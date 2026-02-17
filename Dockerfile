FROM python:3.11-slim

# 1. Instalamos las dependencias con los nombres de paquetes actuales
RUN apt-get update && apt-get install -y \
    inkscape \
    curl \
    xz-utils \
    libnss3 \
    libgomp1 \
    libgl1 \
    libglx0 \
    libxml2 \
    libgtk-3-0 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Instalación de Inkstitch
RUN curl -L -f "https://github.com/inkstitch/inkstitch/releases/download/v3.0.1/inkstitch-3.0.1-linux.tar.xz" -o inkstitch.tar.xz \
    && mkdir -p /opt/inkstitch \
    && tar -xJf inkstitch.tar.xz -C /opt/inkstitch --strip-components=1 \
    && chmod -R 755 /opt/inkstitch \
    && rm inkstitch.tar.xz

# 3. Acceso directo global
RUN ln -sf /opt/inkstitch/bin/inkstitch /usr/local/bin/inkstitch

# 4. Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# 5. Entorno
ENV PATH="/opt/inkstitch/bin:${PATH}"
ENV LD_LIBRARY_PATH="/opt/inkstitch/lib:${LD_LIBRARY_PATH}"
ENV HOME=/tmp
ENV INKSCAPE_PROFILE_DIR=/tmp
ENV QT_QPA_PLATFORM=offscreen

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]