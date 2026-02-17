import os
import uuid
import asyncio
import logging
import lxml.etree as ET
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# --- CONFIGURACIÓN PARA RENDER ---
# Forzamos a que los programas usen /tmp (única carpeta con escritura permitida)
os.environ["HOME"] = "/tmp"
os.environ["INKSCAPE_PROFILE_DIR"] = "/tmp"
# Aseguramos que Python encuentre el ejecutable de Inkstitch
os.environ["PATH"] = "/usr/local/bin/inkstitch_cli/bin:" + os.environ.get("PATH", "")

# 1. Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# 2. Configuración de Rate Limit
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="InkStitch API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 3. Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://stitchcucumber.lovable.app", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"]
)

INK_NS = "{http://inkstitch.org/namespace}"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

def cleanup(files):
    """Elimina archivos temporales de forma segura."""
    for f in files:
        if f and os.path.exists(f):
            try:
                os.remove(f)
                logger.info(f"Cleanup: {f} eliminado")
            except Exception as e:
                logger.error(f"Error en cleanup de {f}: {e}")

async def preparar_svg_async(path):
    """Ejecuta Inkscape para convertir objetos a trazos e inyectar atributos."""
    proc = None
    try:
        # A. Inkscape asíncrono
        proc = await asyncio.create_subprocess_exec(
            "inkscape", path,
            "--actions=select-all:all;
