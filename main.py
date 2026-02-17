import os
import subprocess
import uuid
import lxml.etree as ET
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://stitchcucumber.lovable.app", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"]
)

INK_NS = "{http://inkstitch.org/namespace}"

def cleanup(files):
    for f in files:
        if os.path.exists(f):
            os.remove(f)

def preparar_svg_profesional(path):
    try:
        # A. Convertir todo a PATHS con Inkscape
        subprocess.run([
            "inkscape", path,
            "--actions=select-all:all;object-to-path;export-filename=" + path + ";export-do"
        ], check=True, capture_output=True)

        # B. Inyectar Namespaces Absolutos
        parser = ET.XMLParser(resolve_entities=False, no_network=True)
        tree = ET.parse(path, parser=parser)
        root = tree.getroot()
        
        namespaces = {'svg': 'http://www.w3.org/2000/svg'}
        
        # Sincronizar tamaño a 100mm
        root.set('width', '100mm')
        root.set('height', '100mm')

        for el in root.xpath('//svg:path', namespaces=namespaces):
            # Usamos el formato {url}atributo para máxima compatibilidad
            el.set(f'{INK_NS}allow_auto_fill', 'true')
            el.set(f'{INK_NS}fill_spacing_mm', '0.4')
            
            # Asegurar que tenga color de relleno
            if not el.get('fill') or el.get('fill') == 'none':
                el.set('fill', '#12925e')

        tree.write(path)
        return True
    except Exception as e:
        print(f"Error en preparación: {e}")
        return False

@app.post("/convert")
async def convert(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename.endswith('.svg'):
        raise HTTPException(400, "Solo archivos SVG")

    job_id = str(uuid.uuid4())
    svg_path = f"{job_id}.svg"
    pes_path = f"{job_id}.pes"

    try:
        with open(svg_path, "wb") as f:
            f.write(await file.read())

        if not preparar_svg_profesional(svg_path):
            raise Exception("No se pudo procesar la geometría del SVG")

        # Ejecución de Inkstitch CLI corregida
        result = subprocess.run([
            "inkstitch", 
            "--extension=output", 
            "--format-pes=True", 
            f"--output={pes_path}", 
            svg_path
        ], capture_output=True, text=True)

        if os.path.exists(pes_path) and os.path.getsize(pes_path) > 0:
            background_tasks.add_task(cleanup, [svg_path, pes_path])
            return FileResponse(pes_path, media_type="application/octet-stream", filename="bordado.pes")
        
        print(f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}")
        raise Exception("Inkstitch no generó puntadas.")

    except Exception as e:
        cleanup([svg_path, pes_path])
        return {"error": str(e)}
    
@app.get("/health")
def health_check():
    try:
        # Verifica si Inkscape responde
        inkscape = subprocess.run(["inkscape", "--version"], capture_output=True, text=True)
        # Verifica si Inkstitch responde
        inkstitch = subprocess.run(["inkstitch", "--version"], capture_output=True, text=True)
        
        return {
            "status": "ready",
            "inkscape": inkscape.stdout.strip() if inkscape.returncode == 0 else "Error",
            "inkstitch": inkstitch.stdout.strip() if inkstitch.returncode == 0 else "Error"
        }
    except Exception as e:
        return {"status": "error", "details": str(e)}