from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pyembroidery
import io
from typing import Dict, Any
from svgpathtools import parse_path
from xml.etree import ElementTree as ET
import re

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
    # This endpoint returns the user-configurable options
    return {
        "options": [
            {
                "key": "stitch_density",
                "label": "Densidad de Puntada (mm)",
                "type": "number",
                "default": 2.5,
                "description": "Distancia entre puntadas a lo largo de un trazo. Menor valor = más denso."
            },
            {
                "key": "width_mm",
                "label": "Ancho del Diseño (mm)",
                "type": "number",
                "default": 100,
                "description": "Ancho final del bordado en milímetros."
            },
            {
                "key": "height_mm",
                "label": "Alto del Diseño (mm)",
                "type": "number",
                "default": 100,
                "description": "Alto final del bordado en milímetros."
            }
        ]
    }

# Helper function to extract color from SVG element
def get_color(elem):
    fill = elem.get("fill", "") or ""
    stroke = elem.get("stroke", "") or ""
    style = elem.get("style", "") or ""
    
    color_hex = None
    for attr in [fill, stroke]:
        if attr and attr != "none" and attr.startswith("#"):
            color_hex = attr
            break
    
    if not color_hex and style:
        match = re.search(r"(?:fill|stroke)\s*:\s*(#[0-9a-fA-F]{3,6})", style)
        if match:
            color_hex = match.group(1)
    
    if color_hex:
        hex_val = color_hex.lstrip("#")
        if len(hex_val) == 3:
            hex_val = "".join(c*2 for c in hex_val)
        r, g, b = int(hex_val[0:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16)
        return pyembroidery.EmbThread({"color": (r, g, b)})
    
    return pyembroidery.EmbThread({"color": (0, 0, 0)}) # Default to black

@app.post("/convert")
async def convert_svg(request: ConvertRequest):
    try:
        svg_content = request.svg
        options = request.options
        
        root = ET.fromstring(svg_content)
        ns = {"svg": "http://www.w3.org/2000/svg"}
        
        pattern = pyembroidery.EmbPattern()
        
        width_mm = float(options.get("width_mm", 100))
        height_mm = float(options.get("height_mm", 100))
        
        viewbox = root.get("viewBox", f"0 0 {width_mm} {height_mm}")
        vb = [float(x) for x in viewbox.split()]
        vb_w, vb_h = vb[2] - vb[0], vb[3] - vb[1]
        
        scale_x = (width_mm * 10) / vb_w  # mm to 0.1mm units
        scale_y = (height_mm * 10) / vb_h
        
        paths = root.findall(".//svg:path", ns) + root.findall(".//path")
        
        stitch_density = float(options.get("stitch_density", 2.5))
        density_units = stitch_density * 10  # to 0.1mm
        
        for path_elem in paths:
            d = path_elem.get("d", "")
            if not d:
                continue
            
            thread = get_color(path_elem)
            pattern.add_thread(thread)
            
            try:
                parsed = parse_path(d)
            except Exception:
                continue
            
            first = True
            for segment in parsed:
                if segment.length() == 0:
                    continue
                num_points = max(2, int(segment.length() / density_units))
                
                for i in range(num_points + 1):
                    t = i / num_points
                    point = segment.point(t)
                    
                    x = (point.real - vb[0]) * scale_x
                    y = (point.imag - vb[1]) * scale_y
                    
                    if first:
                        pattern.add_command(pyembroidery.MOVE, x, y)
                        first = False
                    else:
                        pattern.add_command(pyembroidery.STITCH, x, y)
            
            pattern.add_command(pyembroidery.COLOR_BREAK)
        
        pattern.add_command(pyembroidery.END)
        
        if not pattern.stitches:
            raise HTTPException(status_code=422, detail="El SVG no contiene trazados válidos para bordar.")

        output = io.BytesIO()
        pyembroidery.write(pattern, output, {"format": "pes"})
        output.seek(0)
        
        return Response(
            content=output.getvalue(), 
            media_type="application/octet-stream", 
            headers={"Content-Disposition": "attachment; filename=embroidery.pes"}
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al procesar el archivo: {str(e)}")

@app.get("/")
async def read_root():
    return {"message": "Servicio de conversión de bordados para Lovable. Endpoints: /analyze, /convert"}