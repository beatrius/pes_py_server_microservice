import traceback
import tempfile
import os
from io import BytesIO
from xml.etree import ElementTree as ET

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional, Dict, Any

import pyembroidery

print(">>> V7 minimal pyembroidery - write_pes direct <<<")

app = FastAPI()


class AnalyzeRequest(BaseModel):
    svg: str


class ConvertRequest(BaseModel):
    svg: str
    options: Optional[Dict[str, Any]] = None


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    return {
        "options": [
            {
                "key": "stitch_density",
                "label": "Densidad de Puntada (mm)",
                "type": "number",
                "default": 2.5,
                "description": "Distancia entre puntadas. Menor valor = más denso.",
            },
            {
                "key": "width_mm",
                "label": "Ancho del Diseño (mm)",
                "type": "number",
                "default": 100,
                "description": "Ancho final del bordado en milímetros.",
            },
            {
                "key": "height_mm",
                "label": "Alto del Diseño (mm)",
                "type": "number",
                "default": 100,
                "description": "Alto final del bordado en milímetros.",
            },
        ]
    }


def parse_svg_paths(svg_string: str):
    """Extract basic line segments from SVG paths and polylines."""
    try:
        root = ET.fromstring(svg_string)
    except ET.ParseError as e:
        raise HTTPException(status_code=400, detail=f"SVG inválido: {e}")

    ns = {"svg": "http://www.w3.org/2000/svg"}
    segments = []

    # Get viewBox for coordinate scaling
    viewbox = root.get("viewBox", "0 0 100 100")
    parts = viewbox.split()
    vb_w = float(parts[2]) if len(parts) >= 3 else 100
    vb_h = float(parts[3]) if len(parts) >= 4 else 100

    # Extract polyline/polygon points
    for tag in ["polyline", "polygon"]:
        for el in root.iter(f"{{{ns['svg']}}}{tag}") if ns else root.iter(tag):
            pts_str = el.get("points", "")
            if pts_str:
                coords = []
                for pair in pts_str.strip().split():
                    xy = pair.split(",")
                    if len(xy) == 2:
                        coords.append((float(xy[0]), float(xy[1])))
                if coords:
                    segments.append(coords)

    # Also try without namespace
    for tag in ["polyline", "polygon"]:
        for el in root.iter(tag):
            pts_str = el.get("points", "")
            if pts_str:
                coords = []
                for pair in pts_str.strip().split():
                    xy = pair.split(",")
                    if len(xy) == 2:
                        coords.append((float(xy[0]), float(xy[1])))
                if coords:
                    segments.append(coords)

    # Extract lines
    for el in list(root.iter(f"{{{ns['svg']}}}line")) + list(root.iter("line")):
        x1 = float(el.get("x1", 0))
        y1 = float(el.get("y1", 0))
        x2 = float(el.get("x2", 0))
        y2 = float(el.get("y2", 0))
        segments.append([(x1, y1), (x2, y2)])

    # Extract rects as 4-point polygons
    for el in list(root.iter(f"{{{ns['svg']}}}rect")) + list(root.iter("rect")):
        x = float(el.get("x", 0))
        y = float(el.get("y", 0))
        w = float(el.get("width", 0))
        h = float(el.get("height", 0))
        if w > 0 and h > 0:
            segments.append([(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)])

    # If no geometry found, create a simple cross pattern as fallback
    if not segments:
        cx, cy = vb_w / 2, vb_h / 2
        segments.append([(0, 0), (vb_w, vb_h)])
        segments.append([(vb_w, 0), (0, vb_h)])

    return segments, vb_w, vb_h


@app.post("/convert")
def convert(req: ConvertRequest):
    try:
        options = req.options or {}
        width_mm = float(options.get("width_mm", 100))
        height_mm = float(options.get("height_mm", 100))
        density = float(options.get("stitch_density", 2.5))

        segments, vb_w, vb_h = parse_svg_paths(req.svg)

        # Scale factors: SVG coords -> 0.1mm units (pyembroidery standard)
        scale_x = (width_mm * 10) / vb_w if vb_w > 0 else 10
        scale_y = (height_mm * 10) / vb_h if vb_h > 0 else 10

        # Build pattern using documented API
        pattern = pyembroidery.EmbPattern()

        # Add a default black thread
        thread = pyembroidery.EmbThread()
        thread.set("name", "Black")
        thread.set("color", 0x000000)
        pattern.add_thread(thread)

        first_segment = True
        for seg in segments:
            for i, (x, y) in enumerate(seg):
                px = x * scale_x
                py = y * scale_y
                if i == 0 and first_segment:
                    pattern.add_stitch_absolute(pyembroidery.STITCH, px, py)
                    first_segment = False
                elif i == 0:
                    pattern.add_stitch_absolute(pyembroidery.JUMP, px, py)
                else:
                    pattern.add_stitch_absolute(pyembroidery.STITCH, px, py)

        pattern.add_stitch_absolute(pyembroidery.END, 0, 0)

        # Write to temp file using write_pes (format-specific, avoids any dispatch issues)
        tmp_path = os.path.join(tempfile.gettempdir(), "output.pes")
        pyembroidery.write_pes(pattern, tmp_path)

        with open(tmp_path, "rb") as f:
            pes_bytes = f.read()

        print(f"PES generado: {len(pes_bytes)} bytes")

        return Response(
            content=pes_bytes,
            media_type="application/octet-stream",
            headers={"Content-Disposition": "attachment; filename=embroidery.pes"},
        )

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al procesar el archivo: {e}")
