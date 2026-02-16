import sys
from unittest.mock import MagicMock

# --- PARCHE CRÍTICO PARA ENTORNOS SERVERLESS/DOCKER ---
mock_wx = MagicMock()
sys.modules["wx"] = mock_wx
sys.modules["wx.lib"] = MagicMock()
sys.modules["wx.lib.apa"] = MagicMock()
sys.modules["wx.lib.apa.floatspin"] = MagicMock()
sys.modules["wx.lib.intctrl"] = MagicMock()
sys.modules["wx.lib.scrolledpanel"] = MagicMock()
# --------------------------------------------------------

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import os
import uuid
import lxml.etree as ET
import math
from shapely.geometry import LineString
import re

# Configuración para entornos sin pantalla
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

def parse_svg_path(path_data):
    """
    Parsea un path SVG y extrae puntos válidos
    """
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
    """
    Simplifica la geometría del SVG para evitar problemas con valores flotantes
    """
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        ns = {'svg': 'http://www.w3.org/2000/svg'}
        paths = root.xpath('//svg:path', namespaces=ns)
        
        for path in paths:
            d_attr = path.get('d')
            if not d_attr:
                continue
            
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
            except Exception as e:
                print(f"Error simplificando path individual: {e}")
                continue
        
        tree.write(file_path, encoding='utf-8', xml_declaration=True)
        return True
    except Exception as e:
        print(f"Error en simplificación de geometría: {e}")
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
        formats = root.xpath('//svg:path | //svg:circle | //svg:rect | //svg:ellipse', namespaces=ns)
        for forma in formats:
            forma.set('{http://inkstitch.org/namespace}allow_auto_fill', 'true')
            forma.set('{http://inkstitch.org/namespace}fill_spacing_mm', '1.0')
            forma.set('{http://inkstitch.org/namespace}max_stitch_length_mm', '4.0')
            forma.set('{http://inkstitch.org/namespace}running_stitch_length_mm', '2.0')
            forma.set('{http://inkstitch.org/namespace}auto_fill_underlay', 'false')
            forma.set('{http://inkstitch.org/namespace}fill_underlay', 'false')
            
        tree.write(file_path, encoding='utf-8', xml_declaration=True)
    except Exception as e:
        print(f"Error preparando SVG: {e}")

@app.get("/")
def read_root():
    return {"status": "servidor funcionando", "engine": "inkstitch", "version": "final-binary-fix"}

@app.post("/convert")
async def convert_svg_to_pes(file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())
    input_path = os.path.abspath(f"{session_id}.svg")
    output_path = os.path.abspath(f"{session_id}.pes")
    
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Archivo vacío")
        
        with open(input_path, "wb") as f:
            f.write(content)
        
        preparar_svg_para_inkstitch(input_path)
        
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
            raise HTTPException(status_code=500, detail="No se generó el archivo PES")
        
        # Enviamos el archivo usando FileResponse para evitar errores de codificación UTF-8
        return FileResponse(
            path=output_path,
            filename="embroidery.pes",
            media_type="application/octet-stream"
        )
    
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server Error: {str(e)}")
    finally:
        # La limpieza del archivo de salida se hará después de enviar la respuesta
        if os.path.exists(input_path):
            try: os.remove(input_path)
            except: pass
        # Nota: FileResponse se encarga de cerrar el archivo, pero el borrado del PES 
        # en 'finally' podría ser prematuro. Si falla la descarga, intenta borrarlo manualmente después.
