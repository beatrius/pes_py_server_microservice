FROM python:3.11-slim

# 1. Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    inkscape \
    curl \
    unzip \
    libnss3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Descargar el código fuente que ya comprobamos que Render SÍ baja (33MB)
RUN curl -L "https://github.com/inkstitch/inkstitch/archive/refs/tags/v3.0.1.zip" -o inkstitch.zip \
    && unzip inkstitch.zip \
    && mv inkstitch-3.0.1 /usr/local/bin/inkstitch_dir \
    && rm inkstitch.zip

# PARCHE CRÍTICO: Comentamos la línea que causa el ValueError en Render
RUN sed -i 's/sys.path.remove(extensions_path)/pass # sys.path.remove(extensions_path)/g' /usr/local/bin/inkstitch_dir/inkstitch.py

# 3. Crear el ejecutable manual
# Inkstitch en su código fuente se ejecuta llamando a su script principal
RUN echo '#!/usr/bin/env python3\nimport sys\nimport os\nsys.path.append("/usr/local/bin/inkstitch_dir")\nfrom inkstitch import inkstitch\nif __name__ == "__main__":\n    sys.exit(inkstitch.main())' > /usr/local/bin/inkstitch \
    && chmod +x /usr/local/bin/inkstitch

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

# Variables para que Inkscape funcione sin pantalla
ENV DISPLAY=:0
ENV INKSCAPE_PROFILE_DIR=/tmp
ENV PYTHONPATH="${PYTHONPATH}:/usr/local/bin/inkstitch_dir"

# Render usa la variable $PORT
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
