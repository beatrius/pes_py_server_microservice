from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pyembroidery
import io
from typing import Dict, Any, List

app = FastAPI()

# Configuración de CORS
origins = [
    "https://stitchcucumber.lovable.app",  # Dominio de tu app Lovable en producción
    "http://localhost:3000",              # Para desarrollo local de Lovable
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)

# --- Modelos de Datos para las Peticiones ---
class AnalyzeRequest(BaseModel):
    svg: str

class ConvertRequest(BaseModel):
    svg: str
    options: Dict[str, Any]

# --- Endpoint /analyze ---
@app.post("/analyze")
async def analyze_svg(request: AnalyzeRequest):
    """
    Recibe un SVG y devuelve una lista de opciones de bordado configurables.
    """
    # Aquí podrías analizar el SVG para proponer valores por defecto dinámicos.
    # Por ahora, devolvemos una estructura estática de opciones.
    embroidery_options = [
        {
            "key": "max_stitch_length",
            "label": "Longitud Máxima de Puntada",
            "type": "number",
            "default": 30.0,
            "description": "Controla la densidad (en 1/10 mm). Menor valor = más denso."
        },
        {
            "key": "max_jump_length",
            "label": "Longitud Máxima de Salto",
            "type": "number",
            "default": 121.0,
            "description": "Distancia máxima de los saltos entre áreas (en 1/10 mm)."
        },
        {
            "key": "tie_on",
            "label": "Activar Nudo de Inicio",
            "type": "boolean",
            "default": True,
            "description": "Asegura el hilo al comenzar cada bloque de color."
        },
        {
            "key": "tie_off",
            "label": "Activar Nudo de Fin",
            "type": "boolean",
            "default": True,
            "description": "Remata el hilo al finalizar cada bloque de color."
        },
        {
            "key": "long_stitch_contingency",
            "label": "Gestión de Puntadas Largas",
            "type": "select",
            "default": "SEW_TO",
            "options": [
                {"key": "SEW_TO", "label": "Rellenar con puntadas"},
                {"key": "JUMP_NEEDLE", "label": "Saltar la aguja"}
            ],
            "description": "Cómo manejar puntadas que exceden la longitud máxima."
        }
    ]
    return {"options": embroidery_options}

# --- Endpoint /convert ---
@app.post("/convert")
async def convert_svg(request: ConvertRequest):
    """
    Recibe un SVG y las opciones de bordado, y devuelve el archivo PES binario.
    """
    try:
        # Usar io.StringIO para tratar el string del SVG como un archivo
        svg_stream = io.StringIO(request.svg)
        pattern = pyembroidery.read_svg(svg_stream)

        if not pattern.stitches:
            raise HTTPException(status_code=422, detail="El SVG no contiene rutas vectoriales válidas para bordar.")

        # Mapear opciones recibidas a la configuración de pyembroidery
        opts = request.options
        settings = {
            "max_stitch_length": float(opts.get("max_stitch_length", 30.0)),
            "max_jump_length": float(opts.get("max_jump_length", 121.0)),
            "tie_on": pyembroidery.CONTINGENCY_TIE_ON_THREE_SMALL if opts.get("tie_on", True) else pyembroidery.CONTINGENCY_TIE_ON_NONE,
            "tie_off": pyembroidery.CONTINGENCY_TIE_OFF_THREE_SMALL if opts.get("tie_off", True) else pyembroidery.CONTINGENCY_TIE_OFF_NONE,
            "long_stitch_contingency": pyembroidery.CONTINGENCY_LONG_STITCH_SEW_TO if opts.get("long_stitch_contingency") == "SEW_TO" else pyembroidery.CONTINGENCY_LONG_STITCH_JUMP_NEEDLE
        }

        normalized_pattern = pattern.get_normalized_pattern(settings)

        # Crear el archivo PES en memoria
        pes_stream = io.BytesIO()
        pyembroidery.write_pes(normalized_pattern, pes_stream)
        pes_stream.seek(0)

        # Devolver la respuesta binaria
        return Response(
            content=pes_stream.getvalue(),
            media_type="application/octet-stream",
            headers={"Content-Disposition": "attachment; filename=output.pes"}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al procesar el archivo: {str(e)}")

# --- Endpoint Raíz ---
@app.get("/")
async def read_root():
    return {"message": "Servicio de conversión de bordados para Lovable. Endpoints disponibles: /analyze y /convert."}
