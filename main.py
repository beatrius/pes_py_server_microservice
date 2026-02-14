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
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import os
import uuid
import lxml.etree as ET
import math
from shapely.geometry import Polygon, MultiPolygon, LineString, Point
from shapely.ops import unary_union
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
        # Expresión regular simple para extraer números
        numbers = re.findall(r'-?\d+\.?\d*', path_data)
        
        # Convertir a pares de coordenadas
        for i in range(0, len(numbers) - 1, 2):
            try:
                x = float(numbers[i])
                y = float(numbers[i + 1])
                
                # Validar que no sean NaN o Inf
                if not (math.isnan(x) or math.isnan(y) or 
                       math.isinf(x) or math.isinf(y)):
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
        
        # Namespace SVG
        ns = {'svg': 'http://www.w3.org/2000/svg'}
        
        # Buscar todos los paths
        paths = root.xpath('//svg:path', namespaces=ns)
        
        for path in paths:
            d_attr = path.get('d')
            if not d_attr:
                continue
            
            try:
                # Extraer puntos del path
                points = parse_svg_path(d_attr)
                
                if len(points) >= 3:
                    # Crear geometría con shapely
                    line = LineString(points)
                    
                    # Simplificar con tolerancia
                    simplified = line.simplify(tolerance=0.5, preserve_topology=True)
                    
                    # Convertir de vuelta a path SVG simplificado
                    coords = list(simplified.coords)
                    if len(coords) >= 2:
                        # Crear nuevo path data
                        new_path = f"M {coords[0][0]},{coords[0][1]}"
                        for coord in coords[1:]:
                            new_path += f" L {coord[0]},{coord[1]}"
                        new_path += " Z"
                        
                        # Actualizar el path
                        path.set('d', new_path)
            except Exception as e:
                print(f"Error simplificando path individual: {e}")
                continue
        
        # Guardar el SVG simplificado
        tree.write(file_path, encoding='utf-8', xml_declaration=True)
        return True
    except Exception as e:
        print(f"Error en simplificación de geometría: {e}")
        return False

def preparar_svg_para_inkstitch(file_path):
    try:
        # Primero simplificar la geometría
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
            # Configuración básica
            forma.set('{http://inkstitch.org/namespace}allow_auto_fill', 'true')
            
            # Parámetros más tolerantes para evitar errores de geometría
            forma.set('{http://inkstitch.org/namespace}fill_spacing_mm', '1.0')
            forma.set('{http://inkstitch.org/namespace}max_stitch_length_mm', '4.0')
            forma.set('{http://inkstitch.org/namespace}running_stitch_length_mm', '2.0')
            
            # CRÍTICO: Desactivar underlay para evitar FloatingPointError
            # El error ocurre en do_underlay() cuando intenta proyectar puntos
            forma.set('{http://inkstitch.org/namespace}auto_fill_underlay', 'false')
            forma.set('{http://inkstitch.org/namespace}fill_underlay', 'false')
            
        tree.write(file_path, encoding='utf-8', xml_declaration=True)
    except Exception as e:
        print(f"Error preparando SVG: {e}")

@app.get("/")
def read_root():
    return {"status": "servidor funcionando", "engine": "inkstitch", "version": "2.0-geometry-fix"}

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
        
        # Comando corregido con '=' para evitar ValueError y NoneType
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
        
        with open(output_path, "rb") as f:
            pes_bytes = f.read()
        
        return Response(
            content=pes_bytes,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename=embroidery.pes"}
        )
    
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server Error: {str(e)}")
    finally:
        # Limpieza de archivos
        for path in [input_path, output_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass
