from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import os
import uuid

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
            raise HTTPException(status_code=400, detail="Archivo vacío")
            
        with open(input_path, "wb") as f:
            f.write(content)

        # Ejecución de Inkstitch (Indentación corregida aquí)
        process = subprocess.run([
            "inkstitch", 
            "--extension=output",
            "--format=pes",
            input_path,
            "-o", output_path
        ], capture_output=True, text=True)

        if process.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Error en Inkstitch: {process.stderr}")

        if not os.path.exists(output_path):
            raise HTTPException(status_code=500, detail="No se generó el archivo PES")

        with open(output_path, "rb") as f:
            pes_bytes = f.read()

        return Response(
            content=pes_bytes, 
            media_type="application/octet-stream"
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        # Limpieza de archivos temporales
        if os.path.exists(input_path): os.remove(input_path)
        if os.path.exists(output_path): os.remove(output_path)
