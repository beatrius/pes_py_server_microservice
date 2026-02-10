from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pyembroidery
import io
from typing import Dict, Any
from svgelements import SVG, Path, Shape, Color

app = FastAPI()

# Configuración de CORS
origins = [
    "https://stitchcucumber.lovable.app",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)

class AnalyzeRequest(BaseModel):
    svg: str

class ConvertRequest(BaseModel):
    svg: str
    options: Dict[str, Any]

@app.post("/analyze")
async def analyze_svg(request: AnalyzeRequest):
    return {
        "options": [
            {
                "key": "stitch_spacing",
                "label": "Espaciado de Puntada (mm)",
                "type": "number",
                "default": 2.0,
                "description": "Distancia entre puntadas a lo largo de un trazo. Menor valor = más denso."
            },
            {
                "key": "max_stitch_length",
                "label": "Longitud Máxima de Puntada (mm)",
                "type": "number",
                "default": 3.0,
                "description": "Divide puntadas largas en más pequeñas. Afecta la densidad."
            },
            {
                "key": "tie_on",
                "label": "Activar Nudo de Inicio",
                "type": "boolean",
                "default": True,
            },
            {
                "key": "tie_off",
                "label": "Activar Nudo de Fin",
                "type": "boolean",
                "default": True,
            }
        ]
    }

@app.post("/convert")
async def convert_svg(request: ConvertRequest):
    try:
        svg_stream = io.StringIO(request.svg)
        # El factor de escala convierte píxeles (asumiendo 96 DPI) a unidades de 1/10 mm
        scale_factor = 254.0 / 96.0
        svg = SVG.parse(svg_stream, transform=f"scale({scale_factor})")
        pattern = pyembroidery.EmbPattern()

        opts = request.options
        # Convertir mm a unidades de 1/10 mm
        stitch_spacing = float(opts.get("stitch_spacing", 2.0)) * 10.0

        for element in svg.elements():
            if isinstance(element, Shape):
                element = Path(element)
            
            if isinstance(element, Path):
                for subpath in element.as_subpaths():
                    subpath = Path(subpath)
                    if subpath.length() == 0:
                        continue

                    segments = int(subpath.length() / stitch_spacing)
                    if segments < 1:
                        continue

                    points = [subpath.point(i / float(segments)) for i in range(segments + 1)]
                    points = [(p.x, p.y) for p in points]
                    
                    color = "black"
                    if element.stroke and element.stroke.value is not None:
                        color = element.stroke.hex
                    
                    pattern.add_block(points, color)

        if not pattern.stitches:
            raise HTTPException(status_code=422, detail="El SVG no contiene trazados de línea (strokes) válidos para bordar.")

        settings = {
            "max_stitch_length": float(opts.get("max_stitch_length", 3.0)) * 10.0,
            "tie_on": pyembroidery.CONTINGENCY_TIE_ON_THREE_SMALL if opts.get("tie_on", True) else pyembroidery.CONTINGENCY_TIE_ON_NONE,
            "tie_off": pyembroidery.CONTINGENCY_TIE_OFF_THREE_SMALL if opts.get("tie_off", True) else pyembroidery.CONTINGENCY_TIE_OFF_NONE,
        }

        normalized_pattern = pattern.get_normalized_pattern(settings)

        pes_stream = io.BytesIO()
        pyembroidery.write_pes(normalized_pattern, pes_stream)
        pes_stream.seek(0)

        return Response(
            content=pes_stream.getvalue(),
            media_type="application/octet-stream",
            headers={"Content-Disposition": "attachment; filename=output.pes"}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al procesar el archivo: {str(e)}")

@app.get("/")
async def read_root():
    return {"message": "Servicio de conversión de bordados para Lovable. Endpoints: /analyze, /convert"}
