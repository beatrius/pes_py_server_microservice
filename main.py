import sys
from unittest.mock import MagicMock

# --- PARCHE CRÍTICO PARA ENTORNOS SERVERLESS/DOCKER ---
# Engañamos a Inkstitch para que no intente cargar la interfaz gráfica
mock_wx = MagicMock()
sys.modules["wx"] = mock_wx
sys.modules["wx.lib"] = MagicMock()
sys.modules["wx.lib.apa"] = MagicMock()
sys.modules["wx.lib.apa.floatspin"] = MagicMock()
sys.modules["wx.lib.intctrl"] = MagicMock()
sys.modules["wx.lib.scrolledpanel"] = MagicMock()
# --------------------------------------------------------

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import os
import uuid
import lxml.etree as ET
import math
from shapely.geometry import LineString
import re

# Configuración para entornos sin pantalla (Inkscape/Qt)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

app = FastAPI()

# Configuración de CORS para Lovable
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

def cleanup_files(*files):
    """Elimina los archivos temporales después de enviar la respuesta"""
    for file in files:
        if os.path.exists(file):
            try:
                os.remove(file)
            except Exception as e:
                print(f"Error borrando archivo temporal: {e}")

def parse_svg_path(path_data):
    points = []
    try:
        numbers = re.findall(r'-?\d+\.?\d*', path_data)
        for i in range(0, len(numbers) - 1, 2):
            try:
                x = float(numbers[i])
                y = float(numbers[i + 1])
                if not (math.isnan(x) or math.isnan(y) or math.isinf(x) or math.isinf(y)):
                    points.append((x, y))
            except (ValueError, IndexError):
                continue
    except Exception as e:
        print(f"Error parseando path: {e}")
    return points

def simplificar_geometria_svg(file_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        ns = {'svg': 'http://www.w3.org/2000/svg'}
        paths = root.xpath('//svg:path', namespaces=ns)
        
        for path in paths:
            d_attr = path.get('d')
            if not d_attr: continue
            
            try:
                points = parse_svg_path(d_attr)
                if len(points) >= 3:
                    line = LineString(points)
                    simplified = line.simplify(tolerance=0.5, preserve_topology=True)
                    coords = list(simplified.coords)
                    if len(coords) >= 2:
                        new_path = f"M {coords[0][0]},{coords[0][1]}"
                        for coord in coords[1:]:
                            new_path += f" L {coord[0]},{coord[1]}"
                        new_path += " Z"
                        path.set('d', new_path)
            except Exception:
                continue
        
        tree.write(file_path, encoding='utf-8', xml_declaration=True)
        return True
    except Exception as e:
        print(f"Error en simplificación: {e}")
        return False

def preparar_svg_para_inkstitch(file_path):
    try:
        simplificar_geometria_svg(file_path)
        tree = ET.parse(file_path)
        root = tree.getroot()
        ns = {
            'svg': 'http://www.w3.org/2000/svg',
            'inkstitch': 'http://inkstitch.org/namespace'
        }
        ET.register_namespace('inkstitch', ns['inkstitch'])
        elements = root.xpath('//svg:path | //svg:circle | //svg:rect | //svg:ellipse', namespaces=ns)
        for el in elements:
            el.set('{http://inkstitch.org/namespace}allow_auto_fill', 'true')
            el.set('{http://inkstitch.org/namespace}fill_spacing_mm', '1.0')
            el.set('{http://inkstitch.org/namespace}auto_fill_underlay', 'false')
            
        tree.write(file_path, encoding='utf-8', xml_declaration=True)
    except Exception as e:
        print(f"Error preparando SVG: {e}")

@app.get("/")
def read_root():
    return {"status": "online", "engine": "inkstitch", "fix": "FileResponse-binary"}

@app.post("/convert")
async def convert_svg_to_pes(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())
    input_path = os.path.abspath(f"{session_id}.svg")
    output_path = os.path.abspath(f"{session_id}.pes")
    
    try:
        content = await file.read()
        with open(input_path, "wb") as f:
            f.write(content)
        
        preparar_svg_para_inkstitch(input_path)
        
        # Ejecutamos Inkstitch
        command = [
            "inkstitch",
            "--extension=output",
            "--format=pes",
            f"--output={output_path}",
            input_path
        ]
        
        process = subprocess.run(command, capture_output=True, text=True)
        
        if process.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Inkstitch Error: {process.stderr}")
        
        if not os.path.exists(output_path):
            raise HTTPException(status_code=500, detail="Error: El archivo PES no se creó.")

        # Programamos la limpieza de archivos para después de enviar la respuesta
        background_tasks.add_task(cleanup_files, input_path, output_path)

        # FileResponse envía el archivo como binario puro (soluciona el error utf-8)
        return FileResponse(
            path=output_path,
            filename="diseno_bordado.pes",
            media_type="application/octet-stream"
        )
    
    except Exception as e:
        cleanup_files(input_path, output_path)
        raise HTTPException(status_code=500, detail=f"Server Error: {str(e)}")
