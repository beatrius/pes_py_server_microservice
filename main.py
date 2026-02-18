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
    """Limpia el SVG, inyecta namespaces y genera IDs obligatorios para Inkstitch."""
    try:
        parser = ET.XMLParser(resolve_entities=False, no_network=True)
        tree = ET.parse(path, parser=parser)
        root = tree.getroot()
        
        # Namespaces necesarios
        NS_MAP = {
            'svg': 'http://www.w3.org/2000/svg',
            'inkstitch': 'http://inkstitch.org/namespace'
        }
        
        # Normalizar dimensiones para evitar errores de bastidor
        root.set('width', '100mm')
        root.set('height', '100mm')
        if not root.get('viewBox'):
            root.set('viewBox', '0 0 200 200')

        # Procesar trayectos
        for el in root.xpath('//svg:path', namespaces=NS_MAP):
            # 1. Generar ID si no existe (Vital para Inkstitch v3)
            if not el.get('id'):
                el.set('id', f'stitch_{uuid.uuid4().hex[:6]}')
            
            # 2. Configurar relleno automático
            fill = el.get('fill', '').lower()
            if fill and fill not in ['none', 'transparent', '']:
                el.set(f'{INK_NS}allow_auto_fill', 'true')
                el.set(f'{INK_NS}fill_spacing_mm', '0.4')
            
            # 3. Configurar trazo si existe
            stroke = el.get('stroke', '').lower()
            if stroke and stroke not in ['none', 'transparent', '']:
                el.set(f'{INK_NS}stitch_type', 'stroke')

        tree.write(path)
        return True
    except Exception as e:
        logger.error(f"Error preparando XML: {e}")
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
        
        if not await preparar_svg_async(svg_path):
            raise ValueError("Error preparando metadatos del SVG")
        
        env = os.environ.copy()
        
        # --- PLAN A: Exportación Directa ---
        logger.info(f"Intentando Plan A para {job_id}")
        proc = await asyncio.create_subprocess_exec(
            "inkscape", svg_path,
            "--export-type=pes",
            f"--export-filename={pes_path}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        await asyncio.wait_for(proc.communicate(), timeout=40.0)

        # --- PLAN B: Si el Plan A falló o generó archivo vacío ---
        if not os.path.exists(pes_path) or os.path.getsize(pes_path) == 0:
            logger.info(f"Plan B: Forzando motor de puntadas para {job_id}")
            actions = "select-all:all;object-to-path;org.inkstitch.stitch;export-do"
            proc = await asyncio.create_subprocess_exec(
                "inkscape", svg_path,
                f"--actions={actions}",
                f"--export-filename={pes_path}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            await asyncio.wait_for(proc.communicate(), timeout=60.0)

        # Verificación Final
        if os.path.exists(pes_path) and os.path.getsize(pes_path) > 0:
            background_tasks.add_task(cleanup, [svg_path, pes_path])
            return FileResponse(
                pes_path, 
                media_type="application/octet-stream", 
                filename=f"{file.filename.rsplit('.', 1)[0]}.pes"
            )
        
        raise ValueError("Inkstitch no pudo generar puntadas. Revisa que el diseño tenga áreas de color sólido.")

    except Exception as e:
        logger.error(f"Error crítico: {e}")
        cleanup([svg_path, pes_path])
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    try:
        env = os.environ.copy()
        ink = subprocess.run(["inkscape", "--version"], capture_output=True, text=True, env=env)
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
