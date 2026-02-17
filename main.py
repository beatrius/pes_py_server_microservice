import sys
from unittest.mock import MagicMock

# --- PARCHE PARA ENTORNOS SERVIDOR (RENDER/DOCKER) ---
# Inkstitch requiere librerías gráficas que no existen en servidores. 
# Estos mocks engañan al sistema para que ignore la falta de interfaz.
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

# Indica a Qt que no intente abrir ninguna ventana
os.environ["QT_QPA_PLATFORM"] = "offscreen"

app = FastAPI()

# --- CONFIGURACIÓN DE CORS ---
# Permite que Lovable reciba el archivo binario y lea el nombre del mismo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://stitchcucumber.lovable.app", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"]
)

def cleanup(paths):
    """Elimina archivos temporales de forma segura"""
    for p in paths:
        if os.path.exists(p):
            try: os.remove(p)
            except: pass

def forzar_geometria_bordado(file_path):
    """
    Inyecta atributos de Inkstitch en cada elemento del SVG.
    Optimizado para la jerarquía de grupos (color) de Vectorizer.
    """
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        NS = {
            'svg': 'http://www.w3.org/2000/svg', 
            'inkstitch': 'http://inkstitch.org/namespace'
        }
        ET.register_namespace('inkstitch', NS['inkstitch'])

        # 1. Normalizar tamaño a 100mm (según tu config de Vectorizer)
        root.set('width', '100mm')
        root.set('height', '100mm')

        # 2. Selección Recursiva de Formas
        # Buscamos en todo el árbol (//) ignorando la profundidad de los grupos <g>
        elementos = root.xpath('//*[local-name()="path" or local-name()="rect" or local-name()="circle" or local-name()="ellipse" or local-name()="polygon"]', namespaces=NS)
        
        for el in elementos:
            # Configuración de Relleno Tatami
            el.set('{http://inkstitch.org/namespace}allow_auto_fill', 'true')
            el.set('{http://inkstitch.org/namespace}fill_spacing_mm', '0.4')
            
            # 3. Lógica de Herencia de Color (Soluciona el problema de Vectorizer)
            # Si el elemento no tiene color (fill="none" o vacío), sube por el árbol
            # hasta encontrar el color del grupo <g> asignado por Vectorizer.
            current_fill = el.get('fill')
            if not current_fill or current_fill == 'none':
                parent = el.getparent()
                while parent is not None:
                    p_fill = parent.get('fill')
                    if p_fill and p_fill != 'none':
                        el.set('fill', p_fill)
                        break
                    parent = parent.getparent()
                
                # Si sigue sin color tras buscar en los padres, ponemos el verde por defecto
                if not el.get('fill') or el.get('fill') == 'none':
                    el.set('fill', '#12925e')

        tree.write(file_path)
        return True
    except Exception as e:
        print(f"Error procesando XML/SVG: {e}")
        return False

@app.post("/convert")
async def convert(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    s_id = str(uuid.uuid4())
    in_p = os.path.abspath(f"{s_id}.svg")
    out_p = os.path.abspath(f"{s_id}.pes")
    
    try:
        # 1. Guardar SVG recibido
        with open(in_p, "wb") as f:
            f.write(await file.read())
        
        # 2. Preparar geometría para Inkstitch
        if not forzar_geometria_bordado(in_p):
            raise Exception("Fallo al inyectar comandos de bordado")
        
        # 3. Ejecutar Conversión
        # capture_output=False evita errores de decodificación 'utf-8' con bytes binarios
        subprocess.run(
            ["inkstitch", "--extension=output", "--format=pes", f"--output={out_p}", in_p],
            capture_output=False
        )

        # 4. Verificar resultado y retornar
        if os.path.exists(out_p) and os.path.getsize(out_p) > 0:
            # Programamos borrado de archivos para después del envío
            background_tasks.add_task(cleanup, [in_p, out_p])
            
            return FileResponse(
                path=out_p, 
                media_type="application/octet-stream", 
                filename="diseño_bordado.pes"
            )
        
        # Si llegamos aquí es que el archivo PES no se generó o está vacío
        cleanup([in_p, out_p])
        return {"error": "No se generaron puntadas. Verifique que el SVG contenga formas sólidas."}
        
    except Exception as e:
        cleanup([in_p, out_p])
        return {"error": f"Error en el servidor: {str(e)}"}
