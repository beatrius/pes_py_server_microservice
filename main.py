from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import Response
import subprocess
import os
import uuid

app = FastAPI()

@app.post("/convert")
async def convert_svg_to_pes(file: UploadFile = File(...)):
    # 1. Crear nombres de archivo temporales únicos
    session_id = str(uuid.uuid4())
    input_path = f"{session_id}.svg"
    output_path = f"{session_id}.pes"

    try:
        # 2. Guardar el SVG que viene de Lovable
        content = await file.read()
        with open(input_path, "wb") as f:
            f.write(content)

        # 3. Llamar a Inkstitch CLI
        # Inkstitch intentará digitalizar automáticamente el SVG
        process = subprocess.run([
            "inkstitch",
            "--extension=output",
            "--format=pes",
            input_path,
            "-o", output_path
        ], capture_output=True, text=True)

        if process.returncode != 0:
            raise Exception(f"Error en Inkstitch: {process.stderr}")

        # 4. Leer el archivo PES generado
        with open(output_path, "rb") as f:
            pes_bytes = f.read()

        return Response(content=pes_bytes, media_type="application/octet-stream")

    except Exception as e:
        return {"error": str(e)}
    
    finally:
        # Limpieza de archivos temporales
        if os.path.exists(input_path): os.remove(input_path)
        if os.path.exists(output_path): os.remove(output_path)