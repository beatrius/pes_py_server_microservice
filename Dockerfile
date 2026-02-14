FROM python:3.11-slim

# 1. Instalar dependencias del sistema e Inkscape
RUN apt-get update && apt-get install -y \
    inkscape \
    curl \
    unzip \
    libnss3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Descargar el código fuente de Inkstitch
RUN curl -L "https://github.com/inkstitch/inkstitch/archive/refs/tags/v3.0.1.zip" -o inkstitch.zip \
    && unzip inkstitch.zip \
    && mv inkstitch-3.0.1 /usr/local/bin/inkstitch_dir \
    && rm inkstitch.zip

# --- EL PARCHE DE ESTRUCTURA FÍSICA ---
# Creamos cada carpeta del camino para que 'wx.lib.agw.floatspin' sea una ruta real
RUN mkdir -p /usr/local/lib/python3.11/site-packages/wx/lib/agw/floatspin

# Creamos los archivos __init__.py en cada nivel. 
# Esto es lo que convierte una carpeta en un "paquete" para Python.
RUN touch /usr/local/lib/python3.11/site-packages/wx/__init__.py && \
    touch /usr/local/lib/python3.11/site-packages/wx/lib/__init__.py && \
    touch /usr/local/lib/python3.11/site-packages/wx/lib/agw/__init__.py && \
    touch /usr/local/lib/python3.11/site-packages/wx/lib/agw/floatspin/__init__.py

# Inyectamos el código de engaño en el primer __init__.py que Python leerá
RUN echo 'import sys\n\
from unittest.mock import MagicMock\n\
m = MagicMock()\n\
modules = [\n\
    "wx", "wx.adv", "wx.lib", "wx.lib.agw", \n\
    "wx.lib.agw.floatspin", "wx.grid", "wx.aui", \n\
    "wx.dataview", "wx.html", "wx.stc", "wx.xml"\n\
]\n\
for mod in modules:\n\
    sys.modules[mod] = m' > /usr/local/lib/python3.11/site-packages/wx/__init__.py

# Corregimos el error interno de Inkstitch con las rutas
RUN sed -i 's/sys.path.remove(extensions_path)/pass # sys.path.remove(extensions_path)/g' /usr/local/bin/inkstitch_dir/inkstitch.py
# --------------------------------------

# 3. Crear el ejecutable manual de Inkstitch
RUN echo '#!/usr/bin/env python3\n\
import sys\n\
import os\n\
sys.path.append("/usr/local/bin/inkstitch_dir")\n\
from inkstitch import inkstitch\n\
if __name__ == "__main__":\n\
    sys.exit(inkstitch.main())' > /usr/local/bin/inkstitch \
    && chmod +x /usr/local/bin/inkstitch

COPY . .

# 4. Instalar dependencias de Python (Asegúrate de que requirements.txt esté actualizado)
RUN pip install --no-cache-dir -r requirements.txt

# Variables de entorno
ENV QT_QPA_PLATFORM=offscreen
ENV INKSCAPE_PROFILE_DIR=/tmp
ENV PYTHONPATH="${PYTHONPATH}:/usr/share/inkscape/extensions:/usr/local/bin/inkstitch_dir"

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
