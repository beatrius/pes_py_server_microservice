import sys
from unittest.mock import MagicMock

# --- PARCHE CRÍTICO PARA ENTORNOS SERVERLESS/DOCKER ---
# Engañamos a Inkstitch para que no intente cargar la interfaz gráfica (wxPython)
# Esto evita el error "ModuleNotFoundError: No module named 'wx'"
mock_wx = MagicMock()
sys.modules["wx"] = mock_wx
sys.modules["wx.lib"] = MagicMock()
sys.modules["wx.lib.newevent"] = MagicMock()
# -----------------------------------------------------

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import os
import uuid
import lxml.etree as ET

# Configuración para entornos sin pantalla (para librerías Qt/Inkscape)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

app = FastAPI()

# Configuración de CORS actualizada
# Solo permitimos tu dominio de Lovable y localhost para desarrollo
origins = [
    "http://localhost:5173",
    "https://stitchcucumber.lovable.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def preparar_svg_para_inkstitch(file_path):
    """
    Inyecta atributos de Inkstitch en el SVG para forzar que 
    cualquier trazado (path) sea tratado como un relleno de bordado.
    """
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        # Namespaces necesarios para Inkstitch
        ns = {
            'svg': 'http://www.w3.org/2000/svg',
            'inkstitch': 'http://inkstitch.org/namespace'
        }
        
        # Registramos el namespace para que no se pierda al guardar el archivo XML
        ET.register_namespace('inkstitch', ns['inkstitch'])

        # Buscamos formas comunes dentro del SVG: path, circle, rect, ellipse
        formas = root.xpath('//svg:path | //svg:circle | //svg:rect | //svg:ellipse', namespaces=ns)
        
        for forma in formas:
            # Forzamos el relleno automático (Auto-fill) 
            # Esto asegura que aunque el usuario no sepa de bordado, se genere una superficie
            forma.set('{http://inkstitch.org/namespace}allow_auto_fill', 'true')
            # Establecemos una densidad de puntada estándar (0.4mm entre líneas)
            forma.set('{http://inkstitch.org/namespace}fill_spacing_mm', '0.4')
            
        tree.write(file_path, encoding='utf-8', xml_declaration=True)
    except Exception as e:
        print(f"Error preparando SVG: {e}")

@app.get("/")
def read_root():
    return {
        "status": "servidor funcionando", 
        "engine": "inkstitch", 
        "mode": "headless-mock-gui"
    }

@app.post("/convert")
async def convert_svg_to_pes(file: UploadFile = File(...)):
    # Creamos un ID único para esta sesión para evitar colisiones entre usuarios
    session_id = str(uuid.uuid4())
    input_path = f"{session_id}.svg"
    output_path = f"{session_id}.pes"

    try:
        # Leemos el archivo enviado desde Lovable
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Archivo vacío")
            
        with open(input_path, "wb") as f:
            f.write(content)

        # 1. Preparar el SVG (Inyección de metadatos de bordado)
        preparar_svg_para_inkstitch(input_path)

        # 2. Ejecución de Inkstitch vía comando de consola
        # --promiscuous es vital: permite procesar archivos que no tienen "capas" de Inkscape
        process = subprocess.run([
            "inkstitch", 
            "--extension=output",
            "--format=pes",
            "--promiscuous", 
            input_path,
            "-o", output_path
        ], capture_output=True, text=True)

        # Si el comando falla, devolvemos el error específico de Inkstitch
        if process.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Inkstitch Error: {process.stderr}")

        if not os.path.exists(output_path):
            raise HTTPException(status_code=500, detail="Inkstitch no generó el archivo de salida")

        # Leemos el archivo .pes generado (binario)
        with open(output_path, "rb") as f:
            pes_bytes = f.read()

        # Devolvemos el archivo al navegador
        return Response(
            content=pes_bytes, 
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename=embroidery_{session_id}.pes"}
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        # Captura de errores genéricos del servidor
        raise HTTPException(status_code=500, detail=f"Server Error: {str(e)}")
    
    finally:
        # LIMPIEZA: Eliminamos los archivos para no llenar el disco del servidor
        for path in [input_path, output_path]:
            if os.path.exists(path):
                try: os.remove(path)
                except: pass
