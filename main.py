from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import pyembroidery
import io
from typing import Optional

app = FastAPI()

# Configuración de CORS (ajusta los orígenes según sea necesario)
origins = [
    "https://stitchcucumber.lovable.app",  # Dominio de tu app Lovable en producción
    "http://localhost:3000",  # Para desarrollo local de Lovable
    "*",  # Permite todos los orígenes durante el desarrollo, ¡elimina esto en producción!
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/convert-svg-to-pes/")
async def convert_svg_to_pes(
    file: UploadFile = File(...),
    max_stitch_length: Optional[float] = Form(30.0, description="Longitud máxima de puntada (en 1/10 mm)"),
    max_jump_length: Optional[float] = Form(121.0, description="Longitud máxima de salto (en 1/10 mm)"),
    tie_on: Optional[bool] = Form(True, description="Activar nudo de inicio (tie-on)"),
    tie_off: Optional[bool] = Form(True, description="Activar nudo de fin (tie-off)"),
    long_stitch_contingency: Optional[str] = Form("SEW_TO", description="Qué hacer con puntadas largas: SEW_TO o JUMP_NEEDLE")
):
    if not file.filename.lower().endswith(".svg"):
        raise HTTPException(status_code=400, detail="Tipo de archivo inválido. Solo se aceptan archivos .svg.")

    try:
        contents = await file.read()
        svg_stream = io.BytesIO(contents)
        
        # Leer el SVG y convertirlo a un patrón de bordado
        pattern = pyembroidery.read_svg(svg_stream)

        if not pattern.stitches:
            raise HTTPException(status_code=422, detail="El SVG no pudo ser convertido a un patrón de bordado. Asegúrate de que contenga rutas vectoriales válidas.")

        # Aplicar configuraciones de bordado desde los parámetros
        settings = {
            "max_stitch_length": max_stitch_length,
            "max_jump_length": max_jump_length,
            "tie_on": pyembroidery.CONTINGENCY_TIE_ON_THREE_SMALL if tie_on else pyembroidery.CONTINGENCY_TIE_ON_NONE,
            "tie_off": pyembroidery.CONTINGENCY_TIE_OFF_THREE_SMALL if tie_off else pyembroidery.CONTINGENCY_TIE_OFF_NONE,
            "long_stitch_contingency": pyembroidery.CONTINGENCY_LONG_STITCH_SEW_TO if long_stitch_contingency == "SEW_TO" else pyembroidery.CONTINGENCY_LONG_STITCH_JUMP_NEEDLE
        }

        # Normalizar el patrón con las configuraciones
        normalized_pattern = pattern.get_normalized_pattern(settings)

        # Crear un archivo PES en memoria
        pes_stream = io.BytesIO()
        pyembroidery.write_pes(normalized_pattern, pes_stream)
        pes_stream.seek(0)

        # Devolver el archivo PES para descarga
        return StreamingResponse(
            pes_stream,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={file.filename.rsplit('.', 1)[0]}.pes"}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando el archivo SVG: {str(e)}")

@app.get("/")
async def read_root():
    return {"message": "Bienvenido al servicio de conversión de SVG a PES con pyembroidery."}
