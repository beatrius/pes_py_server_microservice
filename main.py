import sys
from unittest.mock import MagicMock

# --- PARCHE CRÍTICO PARA ENTORNOS SERVERLESS/DOCKER ---
# Engañamos a Inkstitch para que no intente cargar la interfaz gráfica (wxPython)
# Creamos la estructura completa de mocks para evitar AttributeError y ModuleNotFoundError
mock_wx = MagicMock()
sys.modules["wx"] = mock_wx
sys.modules["wx.lib"] = MagicMock()
sys.modules["wx.lib.agw"] = MagicMock()
sys.modules["wx.lib.agw.floatspin"] = MagicMock()
sys.modules["wx.lib.intctrl"] = MagicMock()
sys.modules["wx.lib.scrolledpanel"] = MagicMock()
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

# Configuración de CORS
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
    Inyecta atributos de Inkstitch en el SVG para asegurar la generación de puntadas.
    """
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        ns = {
            'svg': 'http://www.w3.org/2000/svg',
            'inkstitch': 'http://inkstitch.org/namespace'
        }
        
        ET.register_namespace('inkstitch', ns['inkstitch'])

        # Buscamos formas comunes
        formas = root.xpath('//svg:path | //svg:circle | //svg:rect | //svg:ellipse', namespaces=ns)
        
        for forma in formas:
            # Forzamos parámetros básicos para que Inkstitch sepa qué bordar
            forma.set('{http://inkstitch.org/namespace}allow_auto_fill', 'true')
            forma.set('{http://inkstitch.org/namespace}fill_spacing_mm', '0.4')
            
        tree.write(file_path, encoding='utf-8', xml_declaration=True)
    except Exception as e:
        print(f"Error preparando SVG: {e}")

@app.get("/")
def read_root():
    return {
        "status": "servidor funcionando", 
        "engine": "inkstitch", 
        "mode": "headless-ready"
    }

@app.post("/convert")
async def convert_svg_to_pes(file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())
    # Usamos rutas absolutas para evitar confusiones en el contenedor
    input_path = os.path.abspath(f"{session_id}.svg")
    output_path = os.path.abspath(f"{session_id}.pes")

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Archivo vacío")
            
        with open(input_path, "wb") as f:
            f.write(content)

        # 1. Preparar el SVG
        preparar_svg_para_inkstitch(input_path)

        # 2. Ejecución de Inkstitch
        # NOTA: Es vital usar '=' en los argumentos para que inkex no falle al parsear.
        # Añadimos --extension y --format para evitar que el motor reciba valores None.
        command = [
            "inkstitch",
            "--extension=output",
            "--format=pes",
            f"--output={output_path}",
            input_path
        ]

        process = subprocess.run(
            command, 
            capture_output=True, 
            text=True
        )

        # Si el comando falla, devolvemos el error específico de Inkstitch
        if process.returncode != 0:
            raise HTTPException(
                status_code=500, 
                detail=f"Inkstitch Error: {process.stderr or process.stdout}"
            )

        if not os.path.exists(output_path):
            raise HTTPException(
                status_code=500, 
                detail="Inkstitch terminó pero no generó el archivo .pes"
            )

        # Leemos el archivo generado
        with open(output_path, "rb") as f:
            pes_bytes = f.read()

        #
