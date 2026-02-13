from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import os
import uuid
import lxml.etree as ET

# Configuración para entornos sin pantalla
os.environ["QT_QPA_PLATFORM"] = "offscreen"

app = FastAPI()

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def preparar_svg_para_inkstitch(file_path):
    """
    Inyecta atributos de Inkstitch en el SVG para forzar que 
    cualquier trazado (path) sea tratado como un relleno de bordado.
    """
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        # Namespaces necesarios para Inkstitch
        ns = {
            'svg': 'http://www.w3.org/2000/svg',
            'inkstitch': 'http://inkstitch.org/namespace'
        }
        
        # Registramos el namespace para que no se pierda al guardar
        ET.register_namespace('inkstitch', ns['inkstitch'])

        # Buscamos formas comunes: path, circle, rect, ellipse
        formas = root.xpath('//svg:path | //svg:circle | //svg:rect | //svg:ellipse', namespaces=ns)
        
        for forma in formas:
            # Forzamos el relleno automático (Auto-fill)
            # Esto evita que el PES salga vacío si el SVG no tiene parámetros
            forma.set('{http://inkstitch.org/namespace}allow_auto_fill', 'true')
            # Establecemos una densidad de puntada estándar (0.4mm)
            forma.set('{http://inkstitch.org/namespace}fill_spacing_mm', '0.4')
            
        tree.write(file_path, encoding='utf-8', xml_declaration=True)
    except Exception as e:
        print(f"Error preparando SVG: {e}")
        # Si falla la preparación, intentamos seguir de todos modos

@app.get("/")
def read_root():
    return {"status": "servidor funcionando", "engine": "inkstitch", "mode": "auto-digitize"}

@app.post("/convert")
async def convert_svg_to_pes(file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())
    input_path = f"{session_id}.svg"
    output_path = f"{session_id}.pes"

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Archivo vacío")
            
        with open(input_path, "wb") as f:
            f.write(content)

        # 1. Preparar el SVG (El paso intermedio crítico)
        preparar_svg_para_inkstitch(input_path)

        # 2. Ejecución de Inkstitch con el flag --promiscuous
        # Este flag permite que Inkstitch procese elementos aunque no estén en capas específicas
        process = subprocess.run([
            "inkstitch", 
            "--extension=output",
            "--format=pes",
            "--promiscuous", 
            input_path,
            "-o", output_path
        ], capture_output=True, text=True)

        if process.returncode != 0:
            # Si hay error, enviamos el stderr para saber qué falló
            raise HTTPException(status_code=500, detail=f"Inkstitch Error: {process.stderr}")

        if not os.path.exists(output_path):
            raise HTTPException(status_code=500, detail="Inkstitch no generó el archivo de salida")

        with open(output_path, "rb") as f:
            pes_bytes = f.read()

        return Response(
            content=pes_bytes, 
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename=embroidery_{session_id}.pes"}
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server Error: {str(e)}")
    
    finally:
        # Limpieza rigurosa de archivos temporales
        if os.path.exists(input_path):
            try: os.remove(input_path)
            except: pass
        if os.path.exists(output_path):
            try: os.remove(output_path)
            except: pass
