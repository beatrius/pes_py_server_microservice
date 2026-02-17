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
        # A. Inkscape asíncrono - LÍNEA CORREGIDA ABAJO
        proc = await asyncio.create_subprocess_exec(
            "inkscape", path,
            "--actions=select-all:all;object-to-path;export-filename=" + path + ";export-do",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=25.0)
        except asyncio.TimeoutError:
            logger.error(f"Timeout de Inkscape en: {path}")
            return False

        # B. Inyectar Namespaces
        parser = ET.XMLParser(resolve_entities=False, no_network=True)
        tree = ET.parse(path, parser=parser)
        root = tree.getroot()
        namespaces = {'svg': 'http://www.w3.org/2000/svg'}
        
        root.set('width', '100mm')
        root.set('height', '100mm')

        for el in root.xpath('//svg:path', namespaces=namespaces):
            el.set(f'{INK_NS}allow_auto_fill', 'true')
            el.set(f'{INK_NS}fill_spacing_mm', '0.4')
            if not el.get('fill') or el.get('fill') == 'none':
                el.set('fill', '#12925e')

        tree.write(path)
        return True
    except Exception as e:
        logger.error(f"Error en preparación de SVG: {e}", exc_info=True)
        return False
    finally:
        if proc and proc.returncode is None:
            try:
                proc.kill()
                await proc.wait()
            except: pass

@app.post("/convert")
@limiter.limit("10/minute")
async def convert(request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.svg'):
        raise HTTPException(status_code=400, detail="Solo archivos SVG")

    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande")
    
    job_id = str(uuid.uuid4())
    svg_path = f"/tmp/{job_id}.svg"
    pes_path = f"/tmp/{job_id}.pes"
    proc = None

    try:
        with open(svg_path, "wb") as f:
            f.write(content)

        if not await preparar_svg_async(svg_path):
            raise ValueError("No se pudo procesar la geometría del SVG")

        # 2. Inkstitch asíncrono
        proc = await asyncio.create_subprocess_exec(
            "inkstitch", svg_path,
            f"--output
