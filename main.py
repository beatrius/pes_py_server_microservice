import sys
from unittest.mock import MagicMock

# --- PARCHE PARA EVITAR ERRORES DE INTERFAZ GRÁFICA ---
mock_wx = MagicMock()
sys.modules["wx"] = mock_wx
sys.modules["wx.lib"] = MagicMock()
sys.modules["wx.lib.apa"] = MagicMock()
sys.modules["wx.lib.apa.floatspin"] = MagicMock()
sys.modules["wx.lib.intctrl"] = MagicMock()
sys.modules["wx.lib.scrolledpanel"] = MagicMock()
# -----------------------------------------------------

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

os.environ["QT_QPA_PLATFORM"] = "offscreen"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Permitimos todo temporalmente para descartar bloqueos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def cleanup_files(*files):
    for f in files:
        if os.path.exists(f):
            try: os.remove(f)
            except: pass

def preparar_svg(file_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        ns = {'svg': 'http://www.w3.org/2000/svg', 'inkstitch': 'http://inkstitch.org/namespace'}
        ET.register_namespace('inkstitch', ns['inkstitch'])
        for el in root.xpath('//svg:path | //svg:circle | //svg:rect', namespaces=ns):
            el.set('{http://inkstitch.org/namespace}allow_auto_fill', 'true')
            el.set('{http://inkstitch.org/namespace}fill_spacing_mm', '1.0')
        tree.write(file_path)
    except: pass

@app.get("/")
def health():
    return {"status": "ok"}

@app.post("/convert")
async def convert(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())
    in_p = os.path.abspath(f"{session_id}.svg")
    out_p = os.path.abspath(f"{session_id}.pes")
    
    try:
        # 1. Guardar SVG
        with open(in_p, "wb") as f:
            f.write(await file.read())
        
        # 2. Preparar
        preparar_svg(in_p)
        
        # 3. Convertir
        cmd = ["inkstitch", "--extension=output", "--format=pes", f"--output={out_p}", in_p]
        res = subprocess.run(cmd, capture_output=True, text=True)
        
        if res.returncode != 0 or not os.path.exists(out_p):
            raise Exception(f"Inkstitch falló: {res.stderr}")

        # 4. RETORNO BINARIO PURO
        # Programamos el borrado para después de que se complete la descarga
        background_tasks.add_task(cleanup_files, in_p, out_p)
        
        return FileResponse(
            path=out_p,
            filename="bordado.pes",
            media_type="application/octet-stream"
        )
    
    except Exception as e:
        cleanup_files(in_p, out_p)
        return {"detail": f"Server Error: {str(e)}"}
