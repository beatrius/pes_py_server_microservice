# 1. IMAGEN BASE (Fundamental para que no dé el error 'no build stage')
FROM python:3.11-slim

# 2. Instalar dependencias del sistema e Inkscape
RUN apt-get update && apt-get install -y \
    inkscape \
    curl \
    unzip \
    libnss3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 3. Descargar el código fuente de Inkstitch
RUN curl -L "https://github.com/inkstitch/inkstitch/archive/refs/tags/v3.0.1.zip" -o inkstitch.zip \
    && unzip inkstitch.zip \
    && mv inkstitch-3.0.1 /usr/local/bin/inkstitch_dir \
    && rm inkstitch.zip

# --- CIRUGÍA DE ESTRUCTURA TOTAL DE WX (Corregida) ---
# Creamos físicamente las carpetas que Python exige como paquetes
RUN mkdir -p /usr/local/lib/python3.11/site-packages/wx/lib/agw/floatspin \
    && mkdir -p /usr/local/lib/python3.11/site-packages/wx/lib/intctrl \
    && mkdir -p /usr/local/lib/python3.11/site-packages/wx/lib/scrolledpanel

# Creamos los archivos __init__.py en cada carpeta para que sean "paquetes legales"
RUN find /usr/local/lib/python3.11/site-packages/wx -type d -exec touch {}/__init__.py \;

# Inyectamos el Mocking global que intercepta cualquier llamada a wx
RUN echo 'import sys\n\
from unittest.mock import MagicMock\n\
m = MagicMock()\n\
sys.modules["wx"] = m\n\
sys.modules["wx.lib"] = m\n\
sys.modules["wx.adv"] = m\n\
sys.modules["wx.core"] = m\n\
class MockPackage(MagicMock):\n\
    def __getattr__(self, name):\n\
        return MagicMock()\n\
sys.modules["wx.lib.agw"] = MockPackage()\n\
sys.modules["wx.lib.agw.floatspin"] = MockPackage()\n\
sys.modules["wx.lib.intctrl"] = MockPackage()\n\
sys.modules["wx.lib.scrolledpanel"] = MockPackage()' > /usr/local/lib/python3.11/site-packages/wx/__init__.py

# Parche de ruta interna de Inkstitch
RUN sed -i 's/sys.path.remove(extensions_path)/pass # sys.path.remove(extensions_path)/g' /usr/local/bin/inkstitch_dir/inkstitch.py
# -----------------------------------------------------

# 4. Crear el ejecutable manual
RUN echo '#!/usr/bin/env python3\n\
import sys\n\
import os\n\
sys.path.append("/usr/local/bin/inkstitch_dir")\n\
from inkstitch import inkstitch\n\
if __name__ == "__main__":\n\
    sys.exit(inkstitch.main())' > /usr/local/bin/inkstitch \
    && chmod +x /usr/local/bin/inkstitch

COPY . .

# 5. Instalar dependencias de Python del proyecto
RUN pip install --no-cache-dir -r requirements.txt

# Variables de entorno críticas
ENV QT_QPA_PLATFORM=offscreen
ENV INKSCAPE_PROFILE_DIR=/tmp
ENV PYTHONPATH="${PYTHONPATH}:/usr/share/inkscape/extensions:/usr/local/bin/inkstitch_dir"
ENV INKSTITCH_NO_API_SERVER=1

# Render usa la variable $PORT automáticamente
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
