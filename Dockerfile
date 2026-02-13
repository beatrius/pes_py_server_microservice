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

# PARCHE CRÍTICO: Evitar el error de lista (ValueError) en el arranque de Inkstitch
RUN sed -i 's/sys.path.remove(extensions_path)/pass # sys.path.remove(extensions_path)/g' /usr/local/bin/inkstitch_dir/inkstitch.py

# 3. Crear el ejecutable manual
RUN echo '#!/usr/bin/env python3\nimport sys\nimport os\nsys.path.append("/usr/local/bin/inkstitch_dir")\nfrom inkstitch import inkstitch\nif __name__ == "__main__":\n    sys.exit(inkstitch.main())' > /usr/local/bin/inkstitch \
    && chmod +x /usr/local/bin/inkstitch

COPY . .

# 4. Instalar dependencias de Python (Asegúrate de que requirements.txt incluya numpy)
RUN pip install --no-cache-dir -r requirements.txt

# Variables de entorno críticas
ENV DISPLAY=:0
ENV INKSCAPE_PROFILE_DIR=/tmp
# PYTHONPATH debe incluir las extensiones del sistema para que Inkstitch encuentre 'inkex' y 'numpy'
ENV PYTHONPATH="${PYTHONPATH}:/usr/share/inkscape/extensions:/usr/local/bin/inkstitch_dir"

# Render usa la variable $PORT automáticamente
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
