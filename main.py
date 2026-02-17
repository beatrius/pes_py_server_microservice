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
    """Ejecuta Inkscape para convertir objetos a trazos e inyectar atributos de InkStitch."""
    proc = None
    try:
        # A. Inkscape asíncrono
        proc = await asyncio.create_subprocess_exec(
            "inkscape", path,
            "--actions=select-all:all;object-to-path;export-filename=" + path + ";export-do",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=25.0)
        except asyncio.TimeoutError:
            logger.error(f"Timeout de Inkscape en archivo: {path}")
            return False

        # B. Inyectar Namespaces y Atributos de bordado
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

    # Validación de tamaño
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande (máx 10MB)")
    
    job_id = str(uuid.uuid4())
    svg_path = f"{job_id}.svg"
    pes_path = f"{job_id}.pes"
    proc = None

    try:
        # Guardar archivo original
        with open(svg_path, "wb") as f:
            f.write(content)

        # 1. Preparar geometría
        if not await preparar_svg_async(svg_path):
            raise ValueError("No se pudo procesar la geometría del SVG")

        # 2. Inkstitch asíncrono
        proc = await asyncio.create_subprocess_exec(
            "inkstitch", "--extension=output", "--format-pes=True",
            f"--output={pes_path}", svg_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=45.0)
            if proc.returncode != 0:
                logger.error(f"Inkstitch Error: {stderr.decode()}")
                raise ValueError("Inkstitch falló al generar puntadas")
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Inkstitch tomó demasiado tiempo")

        # 3. Responder con el archivo generado
        if os.path.exists(pes_path) and os.path.getsize(pes_path) > 0:
            background_tasks.add_task(cleanup, [svg_path, pes_path])
            return FileResponse(
                pes_path, 
                media_type="application/octet-stream", 
                filename=f"{file.filename.rsplit('.', 1)[0]}.pes"
            )
        
        raise ValueError("El archivo PES no se generó o está vacío")

    except HTTPException as http_e:
        cleanup([svg_path, pes_path])
        raise http_e
    except Exception as e:
        logger.error(f"Error crítico en conversión: {e}", exc_info=True)
        cleanup([svg_path, pes_path])
        raise HTTPException(status_code=500, detail="Error interno en el servidor")
    finally:
        # Cierre total: Asegurar que el proceso del sistema se cierre pase lo que pase
        if proc and proc.returncode is None:
            try:
                proc.kill()
                await proc.wait()
                logger.info("Proceso Inkstitch forzado a cerrar en finally")
            except: pass

@app.get("/health")
async def health_check():
    """Verifica si Inkscape e InkStitch están disponibles en el sistema."""
    try:
        # Ejecutar comandos de versión
        ink = await asyncio.create_subprocess_exec("inkscape", "--version", stdout=asyncio.subprocess.PIPE)
        st = await asyncio.create_subprocess_exec("inkstitch", "--version", stdout=asyncio.subprocess.PIPE)
        
        out_i, _ = await ink.communicate()
        out_s, _ = await st.communicate()
        
        return {
            "status": "ready",
            "inkscape": out_i.decode().strip() if out_i else "Not found",
            "inkstitch": out_s.decode().strip() if out_s else "Not found"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "error",
            "detail": str(e)
        }