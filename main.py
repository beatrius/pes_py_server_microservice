import os
import uuid
import asyncio
import logging
import lxml.etree as ET
import subprocess
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# --- CONFIGURACIÓN DE ENTORNO ---
os.environ["HOME"] = "/tmp"
os.environ["XDG_CONFIG_HOME"] = "/tmp"
os.environ["XDG_CACHE_HOME"] = "/tmp"
os.environ["INKSCAPE_PROFILE_DIR"] = "/tmp"
os.environ["DISPLAY"] = os.environ.get("DISPLAY", ":99")

# Ruta donde Manus instaló la extensión
INKSTITCH_EXT_DIR = "/usr/share/inkscape/extensions/inkstitch"
os.environ["PATH"] = f"{INKSTITCH_EXT_DIR}/bin:{os.environ.get('PATH', '')}"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="InkStitch API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://stitchcucumber.lovable.app", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"]
)

INK_NS = "{http://inkstitch.org/namespace}"
MAX_FILE_SIZE = 10 * 1024 * 1024

def cleanup(files):
    for f in files:
        if f and os.path.exists(f):
            try:
                os.remove(f)
            except Exception as e:
                logger.error(f"Error cleanup {f}: {e}")

async def preparar_svg_async(path):
    """Limpia el SVG y asegura que tenga los atributos de bordado."""
    try:
        parser = ET.XMLParser(resolve_entities=False, no_network=True)
        tree = ET.parse(path, parser=parser)
        root = tree.getroot()
        
        # Namespaces
        namespaces = {
            'svg': 'http://www.w3.org/2000/svg',
            'inkstitch': 'http://inkstitch.org/namespace'
        }
        
        # Forzar tamaño si no viene en mm
        root.set('width', '100mm')
        root.set('height', '100mm')

        # Procesar trayectos
        for el in root.xpath('//svg:path', namespaces=namespaces):
            # Si tiene relleno y no es transparente, activar auto-fill
            fill = el.get('fill', '').lower()
            if fill and fill != 'none' and fill != 'transparent':
                el.set(f'{INK_NS}allow_auto_fill', 'true')
                el.set(f'{INK_NS}fill_spacing_mm', '0.4')
            
            # Si tiene borde, asegurar parámetros de puntada de trazo
            stroke = el.get('stroke', '').lower()
            if stroke and stroke != 'none':
                el.set(f'{INK_NS}stitch_type', 'stroke')

        tree.write(path)
        return True
    except Exception as e:
        logger.error(f"Error parseando XML: {e}")
        return False

@app.post("/convert")
@limiter.limit("5/minute")
async def convert(request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.svg'):
        raise HTTPException(status_code=400, detail="Solo archivos SVG")
    
    content = await file.read(MAX_FILE_SIZE + 1)
    job_id = str(uuid.uuid4())
    svg_path = f"/tmp/{job_id}.svg"
    pes_path = f"/tmp/{job_id}.pes"
    
    try:
        with open(svg_path, "wb") as f:
            f.write(content)
        
        # 1. Limpieza y preparación de atributos
        if not await preparar_svg_async(svg_path):
            raise ValueError("Error preparando metadatos del SVG")
        
        # 2. Conversión mediante Inkscape
        # Ejecutamos select-all y convertimos objetos a trazos por si acaso,
        # luego llamamos a la acción de bordado de inkstitch explícitamente.
        env = os.environ.copy()
        
        # COMANDO MAESTRO: Seleccionar todo -> Convertir a trazo -> Generar puntadas -> Exportar
        actions = (
            "select-all:all;"
            "object-to-path;"
            "org.inkstitch.stitch;"
            f"export-filename={pes_path};"
            "export-do"
        )
        
        proc = await asyncio.create_subprocess_exec(
            "inkscape", svg_path,
            f"--actions={actions}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=80.0)
            if proc.returncode != 0:
                err = stderr.decode()
                logger.error(f"Inkscape Error: {err}")
                raise ValueError(f"Inkscape falló: {err}")
        except asyncio.TimeoutError:
            if proc: proc.kill()
            raise HTTPException(status_code=504, detail="Tiempo de espera agotado")

        if os.path.exists(pes_path) and os.path.getsize(pes_path) > 0:
            background_tasks.add_task(cleanup, [svg_path, pes_path])
            return FileResponse(
                pes_path, 
                media_type="application/octet-stream", 
                filename=f"{file.filename.rsplit('.', 1)[0]}.pes"
            )
        
        raise ValueError("Inkstitch no generó ninguna puntada (archivo vacío)")

    except Exception as e:
        logger.error(f"Error en conversión: {e}")
        cleanup([svg_path, pes_path])
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    try:
        env = os.environ.copy()
        ink = subprocess.run(["inkscape", "--version"], capture_output=True, text=True, env=env)
        # Listar acciones para verificar que org.inkstitch está cargado
        actions = subprocess.run(["inkscape", "--action-list"], capture_output=True, text=True, env=env)
        has_inkstitch = "org.inkstitch" in actions.stdout
        
        return {
            "status": "ready" if has_inkstitch else "degraded",
            "inkscape": ink.stdout.strip(),
            "inkstitch": "Detected" if has_inkstitch else "Missing",
            "display": os.environ.get("DISPLAY")
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}