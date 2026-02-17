import sys
from unittest.mock import MagicMock

# --- PARCHE PARA ENTORNOS SERVIDOR (RENDER/DOCKER) ---
mock_wx = MagicMock()
sys.modules["wx"] = mock_wx
for mod in ["wx.lib", "wx.lib.apa", "wx.lib.apa.floatspin", "wx.lib.intctrl", "wx.lib.scrolledpanel"]:
    sys.modules[mod] = MagicMock()

from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
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
    allow_origins=["https://stitchcucumber.lovable.app", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"]
)

def cleanup(paths):
    for p in paths:
        if os.path.exists(p):
            try: os.remove(p)
            except: pass

def procesar_svg_con_inkscape(input_path):
    """
    Convierte todas las formas (rect, circle, etc.) a paths puros.
    Esto es lo que permite que Inkstitch no ignore ningun elemento.
    """
    try:
        # Sobrescribimos el archivo original con la versión convertida a paths
        subprocess.run([
            "inkscape",
            "--actions=select-all:all;object-to-path;export-filename:" + input_path + ";export-do",
            input_path
        ], check=True)
        return True
    except Exception as e:
        print(f"Error en Inkscape: {e}")
        return False

def inyectar_instrucciones_bordado(file_path):
    """
    Inyecta atributos de bordado una vez que todo son paths.
    """
    try:
        # Parser seguro: no resuelve entidades externas ni usa red
        parser = ET.XMLParser(resolve_entities=False, no_network=True)
        tree = ET.parse(file_path, parser=parser)
        root = tree.getroot()
        
        NS = {'svg': 'http://www.w3.org/2000/svg', 'inkstitch': 'http://inkstitch.org/namespace'}
        ET.register_namespace('inkstitch', NS['inkstitch'])

        # Asegurar tamaño 100mm
        root.set('width', '100mm')
        root.set('height', '100mm')

        # Ahora que todo es path gracias a Inkscape, solo buscamos paths
        elementos = root.xpath('//svg:path', namespaces=NS)
        
        for el in elementos:
            el.set('{http://inkstitch.org/namespace}allow_auto_fill', 'true')
            el.set('{http://inkstitch.org/namespace}fill_spacing_mm', '0.4')
            
            # Herencia de color recursiva
            if not el.get('fill') or el.get('fill') == 'none':
                parent = el.getparent()
                while parent is not None:
                    p_fill = parent.get('fill')
                    if p_fill and p_fill != 'none':
                        el.set('fill', p_fill)
                        break
                    parent = parent.getparent()
                
                if not el.get('fill') or el.get('fill') == 'none':
                    el.set('fill', '#12925e')

        tree.write(file_path)
        return True
    except Exception as e:
        print(f"Error inyectando: {e}")
        return False

@app.post("/convert")
async def convert(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    # VALIDACIÓN DE SEGURIDAD
    if file.content_type not in ["image/svg+xml", "application/xml", "text/xml"]:
        raise HTTPException(400, "Solo se permiten archivos SVG válidos")

    s_id = str(uuid.uuid4())
    in_p = os.path.abspath(f"{s_id}.svg")
    out_p = os.path.abspath(f"{s_id}.pes")
    
    try:
        # 1. Guardar SVG original
        content = await file.read()
        with open(in_p, "wb") as f:
            f.write(content)
        
        # 2. MEJORA: Convertir todo a PATHS con Inkscape
        if not procesar_svg_con_inkscape(in_p):
            raise Exception("Error al procesar formas con Inkscape")
        
        # 3. Inyectar órdenes de bordado
        if not inyectar_instrucciones_bordado(in_p):
            raise Exception("Fallo al preparar el bordado")
        
        # 4. MEJORA: Comando Inkstitch corregido
        # --extension=output y --format-pes=True son la sintaxis correcta
        subprocess.run([
            "inkstitch", 
            "--extension=output", 
            "--format-pes=True", 
            f"--output={out_p}", 
            in_p
        ], capture_output=False)

        if os.path.exists(out_p) and os.path.getsize(out_p) > 0:
            background_tasks.add_task(cleanup, [in_p, out_p])
            return FileResponse(
                path=out_p, 
                media_type="application/octet-stream", 
                filename="bordado.pes"
            )
        
        cleanup([in_p])
        return {"error": "Inkstitch no pudo generar puntadas"}
        
    except Exception as e:
        cleanup([in_p, out_p])
        return {"error": str(e)}
