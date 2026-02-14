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


# --- PARCHE DEFINITIVO: ESTRUCTURA FÍSICA DE PAQUETES WX ---
# 1. Creamos la jerarquía completa de carpetas
RUN mkdir -p /usr/local/lib/python3.11/site-packages/wx/lib/agw

# 2. Creamos los archivos __init__.py en cada nivel para que Python los reconozca como paquetes
# Nivel raíz: wx
RUN echo 'import sys\nfrom unittest.mock import MagicMock\nm = MagicMock()\nsys.modules["wx"] = m' > /usr/local/lib/python3.11/site-packages/wx/__init__.py

# Nivel 2: wx.lib
RUN echo 'import sys\nfrom unittest.mock import MagicMock\nm = MagicMock()\nsys.modules["wx.lib"] = m' > /usr/local/lib/python3.11/site-packages/wx/lib/__init__.py

# Nivel 3: wx.lib.agw
RUN echo 'import sys\nfrom unittest.mock import MagicMock\nm = MagicMock()\nsys.modules["wx.lib.agw"] = m\nsys.modules["wx.lib.agw.floatspin"] = m' > /usr/local/lib/python3.11/site-packages/wx/lib/agw/__init__.py

# 3. Inyectamos submódulos adicionales comunes para blindar el arranque total
RUN echo 'import sys\nfrom unittest.mock import MagicMock\nm = MagicMock()\nfor mod in ["wx.adv", "wx.grid", "wx.aui", "wx.dataview", "wx.html", "wx.stc", "wx.xml"]:\n    sys.modules[mod] = m' >> /usr/local/lib/python3.11/site-packages/wx/__init__.py

# 4. PARCHE DE RUTA: Corregimos el error de sys.path.remove original de Inkstitch
RUN sed -i 's/sys.path.remove(extensions_path)/pass # sys.path.remove(extensions_path)/g' /usr/local/bin/inkstitch_dir/inkstitch.py
# -----------------------------------------------------------


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

# 4. Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Variables de entorno críticas
ENV QT_QPA_PLATFORM=offscreen
ENV INKSCAPE_PROFILE_DIR=/tmp
ENV PYTHONPATH="${PYTHONPATH}:/usr/share/inkscape/extensions:/usr/local/bin/inkstitch_dir"

# Render usa la variable $PORT
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
