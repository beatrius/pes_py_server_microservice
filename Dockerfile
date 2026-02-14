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

# --- PARCHE DE NIVEL DIOS V2: ESTRUCTURA MULTINIVEL DE WX ---
# Creamos la jerarquía completa de carpetas
RUN mkdir -p /usr/local/lib/python3.11/site-packages/wx/lib/agw

# Creamos los archivos __init__.py en cada nivel para que Python los vea como paquetes
RUN echo 'import sys\nfrom unittest.mock import MagicMock\nm = MagicMock()\nsys.modules["wx"] = m' > /usr/local/lib/python3.11/site-packages/wx/__init__.py

RUN echo 'import sys\nfrom unittest.mock import MagicMock\nm = MagicMock()\nsys.modules["wx.lib"] = m' > /usr/local/lib/python3.11/site-packages/wx/lib/__init__.py

RUN echo 'import sys\nfrom unittest.mock import MagicMock\nm = MagicMock()\nsys.modules["wx.lib.agw"] = m\nsys.modules["wx.lib.agw.floatspin"] = m' > /usr/local/lib/python3.11/site-packages/wx/lib/agw/__init__.py

# Inyectamos el resto de submódulos comunes en el nivel raíz por si acaso
RUN echo 'import sys\nfrom unittest.mock import MagicMock\nm = MagicMock()\nfor mod in ["wx.adv", "wx.grid", "wx.aui", "wx.dataview", "wx.html", "wx.stc", "wx.xml"]:\n    sys.modules[mod] = m' >> /usr/local/lib/python3.11/site-packages/wx/__init__.py

# PARCHE DE RUTA: Corregimos el error de sys.path.remove
RUN sed -i 's/sys.path.remove(extensions_path)/pass # sys.path.remove(extensions_path)/g' /usr/local/bin/inkstitch_dir/inkstitch.py
# -----------------------------------------------------------

# Creamos el __init__.py que inyecta todos los submódulos que Inkstitch busca
RUN echo 'import sys\n\
from unittest.mock import MagicMock\n\
m = MagicMock()\n\
sys.modules["wx"] = m\n\
sys.modules["wx.adv"] = m\n\
sys.modules["wx.lib"] = m\n\
sys.modules["wx.lib.newevent"] = m\n\
sys.modules["wx.grid"] = m\n\
sys.modules["wx.aui"] = m\n\
sys.modules["wx.dataview"] = m' > /usr/local/lib/python3.11/site-packages/wx/__init__.py

# PARCHE DE RUTA: Corregimos el error de sys.path.remove que bloquea el arranque
RUN sed -i 's/sys.path.remove(extensions_path)/pass # sys.path.remove(extensions_path)/g' /usr/local/bin/inkstitch_dir/inkstitch.py
# -----------------------------------------------

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

# 4. Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Variables de entorno críticas
ENV QT_QPA_PLATFORM=offscreen
ENV INKSCAPE_PROFILE_DIR=/tmp
ENV PYTHONPATH="${PYTHONPATH}:/usr/share/inkscape/extensions:/usr/local/bin/inkstitch_dir"

# Render usa la variable $PORT automáticamente
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
