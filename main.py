from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import os
import uuid

# Configuración necesaria para entornos sin pantalla (como Render)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

app = FastAPI()

# Configuración de CORS específica para tu app
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://stitchcucumber.lovable.app",
        "http://localhost:5173" # Útil si pruebas la app localmente
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/convert")
async def convert_svg_to_pes(file: UploadFile = File(...)):
    # 1. Crear nombres de archivo temporales únicos
    session_id = str(uuid.uuid4())
    input_path = f"{session_id}.svg"
    output_path = f"{session_id}.pes"

    try:
        # 2. Guardar el SVG que viene de Lovable
        content = await file.read()
        if not content:
            raise Exception("El archivo SVG está vacío")
            
        with open(input_path, "wb") as f:
            f.write(content)

        # 3. Llamar a Inkstitch CLI
        # Inkstitch intentará digitalizar automáticamente el SVG.
        # Agregamos parámetros de seguridad para que funcione en Docker.
        process = subprocess.run([
            "inkstitch",
            "--extension=output",
            "--format=pes",
            input_path,
            "-o", output_path
        ], capture_output=True, text=True)

        if process.returncode != 0:
            # Si Inkstitch falla, devolvemos el error detallado
            return {"error": "Error en la digitalización", "detail": process.stderr}, 500

        # 4. Verificar si el archivo PES se creó realmente
        if not os.path.exists(output_path):
            return {"error": "Inkstitch no generó el archivo de salida"}, 500

        # 5. Leer el archivo PES generado
        with open(output_path, "rb") as f:
            pes_bytes = f.read()

        return Response(
            content=pes_bytes, 
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename=embroidery_{session_id}.pes"}
        )

    except Exception as e:
        return {"error": str(e)}, 500
    
    finally:
        # Limpieza rigurosa de archivos temporales
        if os.path.exists(input_path):
            try: os.remove(input_path)
            except: pass
        if os.path.exists(output_path):
            try: os.remove(output_path)
            except: pass
