import sys
from unittest.mock import MagicMock

# --- PARCHE DE INTERFAZ (WX) ---
mock_wx = MagicMock()
sys.modules["wx"] = mock_wx
for mod in ["wx.lib", "wx.lib.apa", "wx.lib.apa.floatspin", "wx.lib.intctrl", "wx.lib.scrolledpanel"]:
    sys.modules[mod] = MagicMock()

from fastapi import FastAPI, UploadFile, File, BackgroundTasks
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

def cleanup(paths):
    for p in paths:
        if os.path.exists(p):
            try: os.remove(p)
            except: pass

def inyectar_instrucciones_bordado(file_path):
    """Asegura que cualquier forma tenga parámetros de bordado válidos"""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        ns = {'svg': 'http://www.w3.org/2000/svg', 'inkstitch': 'http://inkstitch.org/namespace'}
        ET.register_namespace('inkstitch', ns['inkstitch'])
        
        # Escalar a dimensiones físicas reales (mm)
        root.set('width', '150mm')
        root.set('height', '150mm')

        # Buscar todas las formas posibles
        for el in root.xpath('//*[local-name()="path" or local-name()="rect" or local-name()="circle" or local-name()="ellipse" or local-name()="polygon"]'):
            # Forzar Relleno Tatami
            el.set('{http://inkstitch.org/namespace}allow_auto_fill', 'true')
            el.set('{http://inkstitch.org/namespace}fill_spacing_mm', '0.4')
            # Garantizar que el color no sea 'none'
            if not el.get('fill') or el.get('fill') == 'none':
                el.set('fill', '#000000')
        
        tree.write(file_path)
    except:
        pass

@app.post("/convert")
async def convert(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    s_id = str(uuid.uuid4())
    in_p = os.path.abspath(f"{s_id}.svg")
    out_p = os.path.abspath(f"{s_id}.pes")
    
    try:
        # 1. Guardar el archivo recibido
        data = await file.read()
        with open(in_p, "wb") as f:
            f.write(data)
        
        # 2. Preparar geometría universal
        inyectar_instrucciones_bordado(in_p)
        
        # 3. Conversión mediante Inkstitch
        # Usamos stdout/stderr como PIPE para no interferir con la respuesta principal
        subprocess.run(
            ["inkstitch", "--extension=output", "--format=pes", f"--output={out_p}", in_p],
            capture_output=True
        )
        
        if not os.path.exists(out_p):
            return {"error": "No se pudo generar el archivo de bordado"}

        # 4. Limpieza posterior a la descarga
        background_tasks.add_task(cleanup, [in_p, out_p])
        
        # 5. RETORNO DIRECTO DE ARCHIVO (Sin procesar como texto)
        return FileResponse(
            path=out_p,
            media_type="application/octet-stream",
            filename="profesional_embroidery.pes"
        )
        
    except Exception as e:
        cleanup([in_p, out_p])
        # Solo en caso de error crítico enviamos un JSON plano
        return {"error": "Ocurrió un fallo en el servidor durante la conversión"}
