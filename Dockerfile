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

# --- CIRUGÍA DE ESTRUCTURA DE PAQUETES ---
# Creamos todas las carpetas que Inkstitch ha pedido y las que suele pedir
RUN mkdir -p /usr/local/lib/python3.11/site-packages/wx/lib/agw/floatspin \
    && mkdir -p /usr/local/lib/python3.11/site-packages/wx/lib/intctrl

# Creamos los __init__.py en cada nivel para que Python los reconozca como paquetes legales
RUN touch /usr/local/lib/python3.11/site-packages/wx/__init__.py \
    && touch /usr/local/lib/python3.11/site-packages/wx/lib/__init__.py \
    && touch /usr/local/lib/python3.11/site-packages/wx/lib/agw/__init__.py \
    && touch /usr/local/lib/python3.11/site-packages/wx/lib/agw/floatspin/__init__.py \
    && touch /usr/local/lib/python3.11/site-packages/wx/lib/intctrl/__init__.py

# Inyectamos el Mocking global en el raíz de wx
RUN echo 'import sys\n\
from unittest.mock import MagicMock\n\
m = MagicMock()\n\
# Lista extendida para cubrir los nuevos errores\n\
modules = [\n\
    "wx", "wx.adv", "wx.lib", "wx.lib.agw", "wx.lib.agw.floatspin", \n\
    "wx.lib.intctrl", "wx.grid", "wx.aui", "wx.dataview", "wx.html", \n\
    "wx.stc", "wx.xml", "wx.core"\n\
]\n\
for mod in modules:\n\
    sys.modules[mod] = m' > /usr/local/lib/python3.11/site-packages/wx/__init__.py

# Corregimos el error de ruta interno de Inkstitch
RUN sed -i 's/sys.path.remove(extensions_path)/pass # sys.path.remove(extensions_path)/g' /usr/local/bin/inkstitch_dir/inkstitch.py
# --------------------------------------

# 3. Crear el ejecutable manual
RUN echo '#!/usr/bin/env python3\n\
import sys\n\
import os\n\
sys.path.append("/usr/local/bin/inkstitch_dir")\n\
from inkstitch import inkstitch\n\
if __name__ == "__main__":\n\
    sys.exit(inkstitch.main())' > /usr/local/bin/inkstitch \
    && chmod +x /usr/local/bin/inkstitch

COPY . .

# 4. Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Variables de entorno
ENV QT_QPA_PLATFORM=offscreen
ENV INKSCAPE_PROFILE_DIR=/tmp
ENV PYTHONPATH="${PYTHONPATH}:/usr/share/inkscape/extensions:/usr/local/bin/inkstitch_dir"

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
