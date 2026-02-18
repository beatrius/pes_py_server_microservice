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

# --- CONFIGURACIÓN CRÍTICA PARA SERVIDORES (RENDER) ---
# Forzamos a que todas las apps busquen sus configuraciones en /tmp
os.environ["HOME"] = "/tmp"
os.environ["XDG_CONFIG_HOME"] = "/tmp"
os.environ["XDG_CACHE_HOME"] = "/tmp"
os.environ["INKSCAPE_PROFILE_DIR"] = "/tmp"
os.environ["DISPLAY"] = os.environ.get("DISPLAY", ":99")

# Aseguramos que el PATH incluya la ubicación de la extensión instalada por Manus
INKSTITCH_BIN_DIR = "/usr/share/inkscape/extensions/inkstitch/bin"
os.environ["PATH"] = f"{INKSTITCH_BIN_DIR}:{os.environ.get('PATH', '')}"

# 1. Configuración de Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
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
MAX_FILE_SIZE = 10 * 1024 * 1024

def cleanup(files):
    for f in files:
        if f and os.path.exists(f):
            try:
                os.remove(f)
                logger.info(f"Cleanup: {f} eliminado")
            except Exception as e:
                logger.error(f"Error en cleanup de {f}: {e}")

async def preparar_svg_async(path):
    """Usa Inkscape para normalizar el SVG convirtiendo todo a trazos."""
    proc = None
    try:
        env = os.environ.copy()
        # Comando para convertir objetos a trayectos y guardar el resultado
        proc = await asyncio.create_subprocess_exec(
            "inkscape", path,
            "--actions=select-all:all;object-to-path;export-filename=" + path + ";export-do",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            if proc.returncode != 0:
                logger.error(f"Inkscape Prep Error: {stderr.decode()}")
                return False
        except asyncio.TimeoutError:
            logger.error("Timeout en preparación de Inkscape")
            return False

        # Inyectar parámetros de bordado básicos con LXML
        parser = ET.XMLParser(resolve_entities=False, no_network=True)
        tree = ET.parse(path, parser=parser)
        root = tree.getroot()
        namespaces = {'svg': 'http://www.w3.org/2000/svg'}
        
        # Forzar tamaño estándar si no tiene
        root.set('width', '100mm')
        root.set('height', '100mm')
        
        for el in root.xpath('//svg:path', namespaces=namespaces):
            el.set(f'{INK_NS}allow_auto_fill', 'true')
            el.set(f'{INK_NS}fill_spacing_mm', '0.4')
            # Asegurar que los elementos tengan color para que sean visibles al bordar
            if not el.get('fill') or el.get('fill') == 'none':
                el.set('fill', '#12925e')
        
        tree.write(path)
        return True
    except Exception as e:
        logger.error(f"Error en preparación de SVG: {e}")
        return False
    finally:
        if proc and proc.returncode is None:
            try: proc.kill()
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
        
        # 1. Normalizar geometría
        if not await preparar_svg_async(svg_path):
            raise ValueError("No se pudo procesar la geometría del SVG")
        
        # 2. Exportar a PES (Inkscape llamará internamente a la extensión de Inkstitch)
        env = os.environ.copy()
        proc = await asyncio.create_subprocess_exec(
            "inkscape", svg_path,
            f"--actions=export-filename={pes_path};export-do",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)
            if proc.returncode != 0:
                err_msg = stderr.decode()
                logger.error(f"Inkstitch Export Error: {err_msg}")
                raise ValueError(f"Fallo en conversión: {err_msg}")
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="El proceso tardó demasiado")

        if os.path.exists(pes_path) and os.path.getsize(pes_path) > 0:
            background_tasks.add_task(cleanup, [svg_path, pes_path])
            return FileResponse(
                pes_path, 
                media_type="application/octet-stream", 
                filename=f"{file.filename.rsplit('.', 1)[0]}.pes"
            )
        
        raise ValueError("El archivo PES no se generó")

    except Exception as e:
        logger.error(f"Error crítico en conversión: {e}")
        cleanup([svg_path, pes_path])
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if proc and proc.returncode is None:
            try: proc.kill()
            except: pass

@app.get("/health")
async def health_check():
    """Verifica la salud del sistema y la presencia de Inkscape e Inkstitch."""
    try:
        env = os.environ.copy()
        # 1. Versión de Inkscape
        ink = subprocess.run(["inkscape", "--version"], capture_output=True, text=True, env=env)
        
        # 2. Verificar si la extensión de Inkstitch es reconocida por Inkscape
        actions = subprocess.run(["inkscape", "--action-list"], capture_output=True, text=True, env=env)
        has_inkstitch = "org.inkstitch" in actions.stdout or "inkstitch" in actions.stdout.lower()
        
        # 3. Verificar binario directo (opcional)
        bin_exists = os.path.exists(os.path.join(INKSTITCH_BIN_DIR, "inkstitch"))
        
        return {
            "status": "ready" if (ink.returncode == 0 and has_inkstitch) else "degraded",
            "inkscape": ink.stdout.strip() if ink.returncode == 0 else "Error",
            "inkstitch_extension": "Detected" if has_inkstitch else "Not Found in Actions",
            "bin_exists": bin_exists,
            "display": os.environ.get("DISPLAY"),
            "xdg_config": os.environ.get("XDG_CONFIG_HOME")
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)