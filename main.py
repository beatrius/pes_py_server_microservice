import sys
from unittest.mock import MagicMock

# --- PARCHE PARA ENTORNOS SIN INTERFAZ (RENDER/DOCKER) ---
mock_wx = MagicMock()
sys.modules["wx"] = mock_wx
sys.modules["wx.lib"] = MagicMock()
sys.modules["wx.lib.apa"] = MagicMock()
sys.modules["wx.lib.apa.floatspin"] = MagicMock()
sys.modules["wx.lib.intctrl"] = MagicMock()
sys.modules["wx.lib.scrolledpanel"] = MagicMock()

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import os
import uuid
import lxml.etree as ET

os.environ["QT_QPA_PLATFORM"] = "offscreen"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def cleanup(in_f, out_f):
    for f in [in_f, out_f]:
        if os.path.exists(f):
            try: os.remove(f)
            except: pass

def procesar_geometria_universal(file_path):
    """
    Analiza el SVG y prepara CUALQUIER forma para ser bordada.
    """
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        ns = {
            'svg': 'http://www.w3.org/2000/svg',
            'inkstitch': 'http://inkstitch.org/namespace'
        }
        ET.register_namespace('inkstitch', ns['inkstitch'])
        
        # 1. Normalización de unidades: Forzamos que el diseño tenga un tamaño físico real.
        # Si el SVG no tiene unidades, Inkstitch puede ignorarlo.
        if 'width' in root.attrib:
            w = root.get('width').replace('px', '')
            root.set('width', f"{w}mm")
        if 'height' in root.attrib:
            h = root.get('height').replace('px', '')
            root.set('height', f"{h}mm")

        # 2. Selector Universal de Formas: Captura paths, rects, circles, ellipses y polygons.
        elementos = root.xpath('//svg:path | //svg:rect | //svg:circle | //svg:ellipse | //svg:polygon', namespaces=ns)
        
        for el in elementos:
            # Forzamos el autocompletado de puntadas (Relleno)
            el.set('{http://inkstitch.org/namespace}allow_auto_fill', 'true')
            # Densidad estándar (0.4mm es el equilibrio entre calidad y velocidad)
            el.set('{http://inkstitch.org/namespace}fill_spacing_mm', '0.4')
            
            # Si el elemento no tiene color de relleno, le asignamos uno por defecto (negro)
            # para asegurar que Inkstitch genere puntadas.
            style = el.get('style', '')
            fill = el.get('fill')
            if (not fill or fill == 'none') and 'fill' not in style:
                el.set('fill', '#000000')

        tree.write(file_path)
        return True
    except Exception as e:
        print(f"Error procesando SVG: {e}")
        return False

@app.post("/convert")
async def convert(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())
    in_p = os.path.abspath(f"{session_id}.svg")
    out_p = os.path.abspath(f"{session_id}.pes")
    
    try:
        # Guardar archivo recibido
        with open(in_p, "wb") as f:
            f.write(await file.read())
        
        # Preparar todas las formas del diseño
        procesar_geometria_universal(in_p)
        
        # Comando de conversión
        cmd = ["inkstitch", "--extension=output", "--format=pes", f"--output={out_p}", in_p]
        res = subprocess.run(cmd, capture_output=True, text=True)
        
        if not os.path.exists(out_p):
            # Error crítico: devolvemos JSON para que el cliente sepa qué pasó
            return {"error": "Inkstitch no generó puntadas. Revisa la geometría.", "log": res.stderr}

        background_tasks.add_task(cleanup, in_p, out_p)
        
        # Respuesta binaria limpia
        return FileResponse(
            path=out_p,
            media_type="application/octet-stream",
            filename="diseno_bordado.pes"
        )
        
    except Exception as e:
        cleanup(in_p, out_p)
        return {"error": str(e)}
