FROM python:3.11-slim

# 1. Instalamos las dependencias necesarias
# Inkscape v1.2+ es necesario para las acciones CLI
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
    xvfb \
    dbus-x11 \
    at-spi2-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Instalación de Inkstitch como extensión de Inkscape
# Lo instalamos en la ruta de extensiones del sistema para que esté disponible para todos
RUN curl -L -f "https://github.com/inkstitch/inkstitch/releases/download/v3.0.1/inkstitch-3.0.1-linux.tar.xz" -o inkstitch.tar.xz \
    && mkdir -p /usr/share/inkscape/extensions/inkstitch \
    && tar -xJf inkstitch.tar.xz -C /usr/share/inkscape/extensions/inkstitch \
    && chmod -R 755 /usr/share/inkscape/extensions/inkstitch \
    && rm inkstitch.tar.xz

# 3. Acceso directo al binario de Inkstitch (opcional pero útil para debugging)
RUN ln -sf /usr/share/inkscape/extensions/inkstitch/bin/inkstitch /usr/local/bin/inkstitch

# 4. Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# 5. Configuración de Entorno
# IMPORTANTE: HOME debe ser /tmp para que Inkscape pueda escribir su caché en Render
ENV HOME=/tmp
ENV INKSCAPE_PROFILE_DIR=/tmp
ENV DISPLAY=:99
# Aseguramos que el binario esté en el PATH
ENV PATH="/usr/share/inkscape/extensions/inkstitch/bin:${PATH}"

# 6. Script de inicio para manejar Xvfb
RUN echo '#!/bin/bash\n\
# Limpiar posibles locks previos\n\
rm -f /tmp/.X99-lock\n\
# Iniciar Xvfb\n\
Xvfb :99 -screen 0 1024x768x16 & \n\
sleep 2 \n\
# Iniciar la aplicación\n\
exec uvicorn main:app --host 0.0.0.0 --port ${PORT}' > /app/entrypoint.sh \
    && chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
