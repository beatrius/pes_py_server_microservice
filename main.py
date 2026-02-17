import sys
from unittest.mock import MagicMock
import logging


# --- PARCHE PARA ENTORNOS SERVIDOR (RENDER/DOCKER) ---
mock_wx = MagicMock()
sys.modules["wx"] = mock_wx
for mod in ["wx.lib", "wx.lib.apa", "wx.lib.apa.floatspin", "wx.lib.intctrl", "wx.lib.scrolledpanel"]:
    sys.modules[mod] = MagicMock()


from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import asyncio
import os
import uuid
import lxml.etree as ET


# Configurar logging estructurado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

os.environ["QT_QPA_PLATFORM"] = "offscreen"

# CORRECCIÓN 3: Rate Limiting
limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://stitchcucumber.lovable.app", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["POST"],  # Restringido solo a POST
    allow_headers=["Content-Type"],  # Restringido a lo necesario
    expose_headers=["Content-Disposition"]
)

# CORRECCIÓN 4: Límite de tamaño de archivo (10 MB)
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB en bytes


def cleanup(paths):
    """Limpia archivos temporales de forma segura"""
    for p in paths:
        if os.path.exists(p):
            try:
                os.remove(p)
                logger.info(f"Cleaned up file: {p}")
            except Exception as e:
                logger.error(f"Failed to cleanup {p}: {e}")


async def procesar_svg_con_inkscape(input_path):
    """
    CORRECCIÓN 1: Usa asyncio para no bloquear el servidor.
    Convierte todas las formas (rect, circle, etc.) a paths puros.
    """
    try:
        logger.info(f"Starting Inkscape conversion for {input_path}")
        
        # CORRECCIÓN 1: subprocess asíncrono con timeout
        process = await asyncio.create_subprocess_exec(
            "inkscape",
            f"--actions=select-all:all;object-to-path;export-filename:{input_path};export-do",
            input_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Esperar con timeout de 30 segundos
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)
        except asyncio.TimeoutError:
            process.kill()
            logger.error(f"Inkscape conversion timed out for {input_path}")
            return False
        
        if process.returncode != 0:
            logger.error(f"Inkscape failed: {stderr.decode()}")
            return False
        
        logger.info(f"Inkscape conversion successful for {input_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error in Inkscape conversion: {e}", exc_info=True)
        return False


def inyectar_instrucciones_bordado(file_path):
    """
    Inyecta atributos de bordado una vez que todo son paths.
    """
    try:
        logger.info(f"Injecting embroidery instructions for {file_path}")
        
        # Parser seguro: no resuelve entidades externas ni usa red
        parser = ET.XMLParser(
            resolve_entities=False,
            no_network=True,
            huge_tree=False  # Previene Billion Laughs attack
        )
        tree = ET.parse(file_path, parser=parser)
        root = tree.getroot()
        
        NS = {'svg': 'http://www.w3.org/2000/svg', 'inkstitch': 'http://inkstitch.org/namespace'}
        ET.register_namespace('inkstitch', NS['inkstitch'])

        # Asegurar tamaño 100mm
        root.set('width', '100mm')
        root.set('height', '100mm')

        # Ahora que todo es path gracias a Inkscape, solo buscamos paths
        elementos = root.xpath('//svg:path', namespaces=NS)
        
        for el in elementos:
            el.set('{http://inkstitch.org/namespace}allow_auto_fill', 'true')
            el.set('{http://inkstitch.org/namespace}fill_spacing_mm', '0.4')
            
            # Herencia de color recursiva
            if not el.get('fill') or el.get('fill') == 'none':
                parent = el.getparent()
                while parent is not None:
                    p_fill = parent.get('fill')
                    if p_fill and p_fill != 'none':
                        el.set('fill', p_fill)
                        break
                    parent = parent.getparent()
                
                if not el.get('fill') or el.get('fill') == 'none':
                    el.set('fill', '#12925e')

        tree.write(file_path)
        logger.info(f"Successfully injected embroidery instructions for {file_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error injecting instructions: {e}", exc_info=True)
        return False


@app.post("/convert")
@limiter.limit("10/minute")  # CORRECCIÓN 3: Rate limiting
async def convert(request: Request, file: UploadFile = File(...)):
    """
    Endpoint principal de conversión SVG a PES.
    Incluye todas las correcciones de seguridad y rendimiento.
    """
    client_ip = request.client.host
    logger.info(f"Conversion request from {client_ip}")
    
    # VALIDACIÓN DE SEGURIDAD: Tipo de archivo
    if file.content_type not in ["image/svg+xml", "application/xml", "text/xml"]:
        logger.warning(f"Invalid file type from {client_ip}: {file.content_type}")
        raise HTTPException(400, "Only SVG files are allowed")

    s_id = str(uuid.uuid4())
    in_p = os.path.abspath(f"{s_id}.svg")
    out_p = os.path.abspath(f"{s_id}.pes")
    
    try:
        # CORRECCIÓN 4: Validar tamaño de archivo antes de leer
        content = await file.read(MAX_FILE_SIZE + 1)
        
        if len(content) > MAX_FILE_SIZE:
            logger.warning(f"File too large from {client_ip}: {len(content)} bytes")
            raise HTTPException(413, f"File size exceeds maximum of {MAX_FILE_SIZE // (1024*1024)}MB")
        
        logger.info(f"Processing file of size {len(content)} bytes")
        
        # 1. Guardar SVG original
        with open(in_p, "wb") as f:
            f.write(content)
        
        # 2. CORRECCIÓN 1: Convertir todo a PATHS con Inkscape (async)
        if not await procesar_svg_con_inkscape(in_p):
            raise Exception("Failed to process shapes with Inkscape")
        
        # 3. Inyectar órdenes de bordado
        if not inyectar_instrucciones_bordado(in_p):
            raise Exception("Failed to prepare embroidery instructions")
        
        # 4. CORRECCIÓN 1: Comando Inkstitch con subprocess asíncrono
        logger.info(f"Starting Inkstitch conversion for {in_p}")
        
        process = await asyncio.create_subprocess_exec(
            "inkstitch",
            "--extension=output",
            "--format-pes=True",
            f"--output={out_p}",
            in_p,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Esperar con timeout de 60 segundos (Inkstitch puede ser lento)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60.0)
        except asyncio.TimeoutError:
            process.kill()
            logger.error(f"Inkstitch conversion timed out for {client_ip}")
            cleanup([in_p, out_p])
            # CORRECCIÓN 2: Mensaje genérico, no exponer detalles
            raise HTTPException(500, "Conversion process timed out")
        
        if process.returncode != 0:
            logger.error(f"Inkstitch failed for {client_ip}: {stderr.decode()}")
            cleanup([in_p, out_p])
            # CORRECCIÓN 2: Mensaje genérico
            raise HTTPException(500, "Conversion failed")

        # Verificar que el archivo de salida existe y tiene contenido
        if os.path.exists(out_p) and os.path.getsize(out_p) > 0:
            logger.info(f"Conversion successful for {client_ip}, output size: {os.path.getsize(out_p)} bytes")
            
            # CORRECCIÓN: Leer archivo en memoria antes de limpiarlo (evita race condition)
            with open(out_p, "rb") as f:
                pes_content = f.read()
            
            # Limpiar archivos inmediatamente
            cleanup([in_p, out_p])
            
            # Retornar contenido desde memoria
            return Response(
                content=pes_content,
                media_type="application/octet-stream",
                headers={"Content-Disposition": "attachment; filename=bordado.pes"}
            )
        
        cleanup([in_p])
        logger.warning(f"Inkstitch produced no output for {client_ip}")
        # CORRECCIÓN 2: Mensaje genérico
        raise HTTPException(500, "Conversion produced no output")
        
    except HTTPException:
        # Re-lanzar HTTPExceptions (ya tienen mensajes apropiados)
        raise
    except Exception as e:
        # CORRECCIÓN 2: Loggear error completo pero retornar mensaje genérico
        logger.error(f"Unexpected error for {client_ip}: {e}", exc_info=True)
        cleanup([in_p, out_p])
        raise HTTPException(500, "An internal error occurred during conversion")


@app.get("/health")
async def health():
    """Health check endpoint para monitoring"""
    return {"status": "healthy", "service": "pes-converter"}


@app.get("/")
async def root():
    """Root endpoint con información del servicio"""
    return {
        "service": "PES Converter Microservice",
        "version": "2.0",
        "endpoints": {
            "convert": "POST /convert - Convert SVG to PES",
            "health": "GET /health - Health check"
        },
        "limits": {
            "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
            "rate_limit": "10 requests per minute"
        }
    }
