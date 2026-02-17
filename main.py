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

# Configuración de Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración de Rate Limit
limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
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
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

def cleanup(files):
    for f in files:
        if os.path.exists(f):
            try: os.remove(f)
            except: pass

async def preparar_svg_async(path):
    try:
        # A. Inkscape asíncrono con Timeout
        proc = await asyncio.create_subprocess_exec(
            "inkscape", path,
            "--actions=select-all:all;object-to-path;export-filename=" + path + ";export-do",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=20.0)
        except asyncio.TimeoutError:
            proc.kill()
            logger.error("Timeout en Inkscape")
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
        logger.error(f"Error en preparación: {e}", exc_info=True)
        return False

@app.post("/convert")
@limiter.limit("10/minute")
async def convert(request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename.endswith('.svg'):
        raise HTTPException(status_code=400, detail="Solo archivos SVG")

    # Validación de tamaño
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande (máx 10MB)")
    
    job_id = str(uuid.uuid4())
    svg_path = f"{job_id}.svg"
    pes_path = f"{job_id}.pes"

    try:
        with open(svg_path, "wb") as f:
            f.write(content)

        if not await preparar_svg_async(svg_path):
            raise ValueError("Error procesando geometría")

        # C. Inkstitch asíncrono
        proc = await asyncio.create_subprocess_exec(
            "inkstitch", "--extension=output", "--format-pes=True",
            f"--output={pes_path}", svg_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=40.0)
            if proc.returncode != 0:
                logger.error(f"Inkstitch Error: {stderr.decode()}")
                raise ValueError("Inkstitch falló al generar puntadas")
        except asyncio.TimeoutError:
            proc.kill()
            raise HTTPException(status_code=504, detail="Inkstitch tomó demasiado tiempo")

        if os.path.exists(pes_path) and os.path.getsize(pes_path) > 0:
            background_tasks.add_task(cleanup, [svg_path, pes_path])
            return FileResponse(pes_path, media_type="application/octet-stream", filename="bordado.pes")
        
        raise ValueError("No se generó el archivo PES")

    except Exception as e:
        logger.error(f"Error conversión: {e}", exc_info=True)
        cleanup([svg_path, pes_path])
        raise HTTPException(status_code=500, detail="Error interno en la conversión")

@app.get("/health")
async def health_check():
    try:
        ink = await asyncio.create_subprocess_exec("inkscape", "--version", stdout=asyncio.subprocess.PIPE)
        st = await asyncio.create_subprocess_exec("inkstitch", "--version", stdout=asyncio.subprocess.PIPE)
        out_i, _ = await ink.communicate()
        out_s, _ = await st.communicate()
        return {
            "status": "ready",
            "inkscape": out_i.decode().strip(),
            "inkstitch": out_s.decode().strip()
        }
    except Exception as e:
        return {"status": "error", "details": str(e)}