import sys
from unittest.mock import MagicMock

# PARCHE PARA RENDER (Necesario para Inkstitch)
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

# REINSTALACIÓN DE CORS (La llave para Lovable)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://stitchcucumber.lovable.app", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"] # Importante para que el navegador vea el nombre del archivo
)

def cleanup(paths):
    for p in paths:
        if os.path.exists(p):
            try: os.remove(p)
            except: pass

def forzar_geometria_bordado(file_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        NS = {'svg': 'http://www.w3.org/2000/svg', 'inkstitch': 'http://inkstitch.org/namespace'}
        ET.register_namespace('inkstitch', NS['inkstitch'])

        # 1. Ajustar el tamaño (Ya lo hacíamos, pero es vital)
        root.set('width', '100mm')
        root.set('height', '100mm')

        # 2. SELECCIÓN AGRESIVA: Buscamos todos los elementos que REPRESENTAN formas, sin importar si están dentro de un <g> o no.
        elementos = root.xpath('//*[local-name()="path" or local-name()="rect" or local-name()="circle" or local-name()="ellipse"]', namespaces=NS)
        
        for el in elementos:
            # Forzamos los parámetros de bordado en cada pieza individual
            el.set('{http://inkstitch.org/namespace}allow_auto_fill', 'true')
            el.set('{http://inkstitch.org/namespace}fill_spacing_mm', '0.4')
            
            # Si el elemento no tiene color propio (porque lo heredaba del grupo),
            # le asignamos el color verde que vimos en tu SVG para que no sea invisible.
            if not el.get('fill') or el.get('fill') == 'none':
                # Buscamos si el padre tiene un color
                padre = el.getparent()
                color_padre = padre.get('fill') if padre is not None else None
                el.set('fill', color_padre if color_padre else '#12925e')

        tree.write(file_path)
        return True
    except Exception as e:
        print(f"Error inyectando: {e}")
        return False

@app.post("/convert")
async def convert(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    s_id = str(uuid.uuid4())
    in_p = os.path.abspath(f"{s_id}.svg")
    out_p = os.path.abspath(f"{s_id}.pes")
    
    try:
        # Guardar SVG
        with open(in_p, "wb") as f:
            f.write(await file.read())
        
        # Preparar para bordado
        forzar_geometria_bordado(in_p)
        
        # Ejecutar Inkstitch (Modo silencioso para evitar errores de codec)
        subprocess.run(
            ["inkstitch", "--extension=output", "--format=pes", f"--output={out_p}", in_p],
            capture_output=False # No capturamos para máxima estabilidad
        )

        if os.path.exists(out_p):
            # Limpiamos los archivos DESPUÉS de enviar la respuesta
            background_tasks.add_task(cleanup, [in_p, out_p])
            
            return FileResponse(
                path=out_p, 
                media_type="application/octet-stream", 
                filename="bordado_profesional.pes"
            )
        
        cleanup([in_p])
        return {"error": "No se generaron puntadas"}
        
    except Exception as e:
        cleanup([in_p, out_p])
        return {"error": str(e)}
