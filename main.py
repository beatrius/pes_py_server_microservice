from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import os
import uuid

# Configuración para entornos sin pantalla
os.environ["QT_QPA_PLATFORM"] = "offscreen"

app = FastAPI()

# Configuración de CORS ultra-permisiva para pruebas
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite cualquier origen
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos los métodos (incluyendo OPTIONS y POST)
    allow_headers=["*"],  # Permite todos los encabezados
)

@app.get("/")
def read_root():
    return {"status": "servidor funcionando", "engine": "inkstitch"}

@app.post("/convert")
async def convert_svg_to_pes(file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())
    input_path = f"{session_id}.svg"
    output_path = f"{session_id}.pes"

    try:
        content = await file.read()
        if not content:
            return {"error": "Archivo vacío"}, 400
            
        with open(input_path, "wb") as f:
            f.write(content)

        # Ejecución de Inkstitch
       process = subprocess.run([
            "inkstitch", # El sistema ya sabe que está en /usr/local/bin
            "--extension=output",
            "--format=pes",
            input_path,
            "-o", output_path
        ], capture_output=True, text=True)

        if process.returncode != 0:
            return {"error": "Error en Inkstitch", "detail": process.stderr}, 500

        if not os.path.exists(output_path):
            return {"error": "No se generó el archivo PES"}, 500

        with open(output_path, "rb") as f:
            pes_bytes = f.read()

        return Response(
            content=pes_bytes, 
            media_type="application/octet-stream"
        )

    except Exception as e:
        return {"error": str(e)}, 500
    
    finally:
        if os.path.exists(input_path): os.remove(input_path)
        if os.path.exists(output_path): os.remove(output_path)
