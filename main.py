import sys
from unittest.mock import MagicMock

# PARCHE PARA RENDER
mock_wx = MagicMock()
sys.modules["wx"] = mock_wx
for mod in ["wx.lib", "wx.lib.apa", "wx.lib.apa.floatspin", "wx.lib.intctrl", "wx.lib.scrolledpanel"]:
    sys.modules[mod] = MagicMock()

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
import subprocess
import os
import uuid
import lxml.etree as ET

os.environ["QT_QPA_PLATFORM"] = "offscreen"

app = FastAPI()

def forzar_geometria_bordado(file_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        # Definimos los namespaces correctamente
        NS = {
            'svg': 'http://www.w3.org/2000/svg',
            'inkstitch': 'http://inkstitch.org/namespace'
        }
        ET.register_namespace('inkstitch', NS['inkstitch'])

        # 1. Forzar tamaño físico (10cm x 10cm)
        root.set('width', '100mm')
        root.set('height', '100mm')

        # 2. Buscar formas y convertirlas en algo que Inkstitch entienda
        # Buscamos cualquier elemento y le inyectamos las propiedades
        for el in root.xpath('//*[local-name()="rect" or local-name()="path" or local-name()="circle"]'):
            # Propiedades de bordado
            el.set('{http://inkstitch.org/namespace}allow_auto_fill', 'true')
            el.set('{http://inkstitch.org/namespace}fill_spacing_mm', '0.4')
            # Asegurar color
            if not el.get('fill') or el.get('fill') == 'none':
                el.set('fill', '#FF0000')

        tree.write(file_path)
        return True
    except Exception as e:
        print(f"Error XML: {e}")
        return False

@app.post("/convert")
async def convert(file: UploadFile = File(...)):
    s_id = str(uuid.uuid4())
    in_p = os.path.abspath(f"{s_id}.svg")
    out_p = os.path.abspath(f"{s_id}.pes")
    
    # Guardar
    with open(in_p, "wb") as f:
        f.write(await file.read())
    
    # Modificar SVG para que Inkstitch "lo vea"
    forzar_geometria_bordado(in_p)
    
    # Ejecutar Inkstitch
    # Importante: No capturamos el texto para que no explote el codec
    subprocess.run(["inkstitch", "--extension=output", "--format=pes", f"--output={out_p}", in_p])

    if os.path.exists(out_p):
        return FileResponse(
            path=out_p, 
            media_type="application/octet-stream", 
            filename="bordado_final.pes"
        )
    
    # Si llegamos aquí, es que Inkstitch no generó nada
    return {"error": "Inkstitch no encontro formas validas para bordar en el SVG"}
