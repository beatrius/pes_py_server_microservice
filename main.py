from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import pyembroidery
import xml.etree.ElementTree as ET
import tempfile
import os
import re
import traceback

print(">>> V8 - add_thread dict, no EmbThread <<<")

app = FastAPI()

class AnalyzeRequest(BaseModel):
    svg: str

class ConvertRequest(BaseModel):
    svg: str
    options: Optional[Dict[str, Any]] = None

def parse_color(color_str: str) -> int:
    """Convert CSS color to int 0xRRGGBB."""
    if not color_str:
        return 0x000000
    color_str = color_str.strip().lower()
    if color_str.startswith('#'):
        hex_val = color_str[1:]
        if len(hex_val) == 3:
            hex_val = ''.join(c * 2 for c in hex_val)
        try:
            return int(hex_val[:6], 16)
        except ValueError:
            return 0x000000
    color_map = {
        'black': 0x000000, 'white': 0xFFFFFF, 'red': 0xFF0000,
        'green': 0x008000, 'blue': 0x0000FF, 'yellow': 0xFFFF00,
        'none': 0x000000
    }
    return color_map.get(color_str, 0x000000)

def extract_paths_from_svg(svg_content: str):
    """Extract path data and colors from SVG."""
    paths = []
    try:
        root = ET.fromstring(svg_content)
    except ET.ParseError:
        return paths

    ns = {'svg': 'http://www.w3.org/2000/svg'}
    
    for elem in root.iter():
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        
        if tag == 'path':
            d = elem.get('d', '')
            stroke = elem.get('stroke', '')
            fill = elem.get('fill', '')
            style = elem.get('style', '')
            
            if style:
                s_match = re.search(r'stroke:\s*([^;]+)', style)
                f_match = re.search(r'fill:\s*([^;]+)', style)
                if s_match:
                    stroke = s_match.group(1)
                if f_match:
                    fill = f_match.group(1)
            
            color = stroke if stroke and stroke != 'none' else fill
            if d:
                paths.append({'d': d, 'color': color or '#000000'})
        
        elif tag in ('rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon'):
            stroke = elem.get('stroke', '')
            fill = elem.get('fill', '')
            color = stroke if stroke and stroke != 'none' else fill
            paths.append({'tag': tag, 'elem': elem, 'color': color or '#000000'})
    
    return paths

def parse_path_d(d_string: str):
    """Parse SVG path d attribute into coordinates."""
    coords = []
    numbers = re.findall(r'[-+]?[0-9]*\.?[0-9]+', d_string)
    for i in range(0, len(numbers) - 1, 2):
        try:
            x = float(numbers[i])
            y = float(numbers[i + 1])
            coords.append((x, y))
        except (ValueError, IndexError):
            continue
    return coords

def get_viewbox(svg_content: str):
    """Get SVG viewBox dimensions."""
    try:
        root = ET.fromstring(svg_content)
    except ET.ParseError:
        return 0, 0, 100, 100
    
    vb = root.get('viewBox', '')
    if vb:
        parts = vb.split()
        if len(parts) == 4:
            try:
                return float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])
            except ValueError:
                pass
    
    w = root.get('width', '100')
    h = root.get('height', '100')
    try:
        w_val = float(re.sub(r'[^0-9.]', '', w))
        h_val = float(re.sub(r'[^0-9.]', '', h))
    except ValueError:
        w_val, h_val = 100, 100
    
    return 0, 0, w_val, h_val

@app.post("/analyze")
async def analyze(request: AnalyzeRequest):
    try:
        options = [
            {"key": "stitch_density", "label": "Densidad de Puntada (mm)", "type": "number", "default": 2.5, "description": "Distancia entre puntadas. Menor valor = más denso."},
            {"key": "width_mm", "label": "Ancho del Diseño (mm)", "type": "number", "default": 100, "description": "Ancho final del bordado en milímetros."},
            {"key": "height_mm", "label": "Alto del Diseño (mm)", "type": "number", "default": 100, "description": "Alto final del bordado en milímetros."},
        ]
        return {"options": options}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error en análisis: {str(e)}")

@app.post("/convert")
async def convert(request: ConvertRequest):
    try:
        options = request.options or {}
        width_mm = float(options.get("width_mm", 100))
        height_mm = float(options.get("height_mm", 100))
        stitch_density = float(options.get("stitch_density", 2.5))

        vb_x, vb_y, vb_w, vb_h = get_viewbox(request.svg)
        
        # Scale: SVG units -> 0.1mm (pyembroidery native unit)
        scale_x = (width_mm * 10) / vb_w if vb_w > 0 else 10
        scale_y = (height_mm * 10) / vb_h if vb_h > 0 else 10
        
        # Stitch length in 0.1mm
        stitch_len = stitch_density * 10

        pattern = pyembroidery.EmbPattern()
        paths = extract_paths_from_svg(request.svg)

        if not paths:
            # Create a simple cross pattern as fallback
            pattern.add_thread({"color": 0x000000, "name": "Black"})
            cx = width_mm * 5  # center in 0.1mm
            cy = height_mm * 5
            size = min(width_mm, height_mm) * 3
            pattern.add_stitch_absolute(pyembroidery.JUMP, cx - size, cy - size)
            pattern.add_stitch_absolute(pyembroidery.STITCH, cx + size, cy + size)
            pattern.add_stitch_absolute(pyembroidery.JUMP, cx + size, cy - size)
            pattern.add_stitch_absolute(pyembroidery.STITCH, cx - size, cy + size)
            pattern.add_stitch_absolute(pyembroidery.END, 0, 0)
        else:
            for path_info in paths:
                color_int = parse_color(path_info.get('color', '#000000'))
                pattern.add_thread({"color": color_int})
                
                if 'd' in path_info:
                    coords = parse_path_d(path_info['d'])
                    if coords:
                        first = coords[0]
                        x = (first[0] - vb_x) * scale_x
                        y = (first[1] - vb_y) * scale_y
                        pattern.add_stitch_absolute(pyembroidery.JUMP, x, y)
                        
                        for coord in coords[1:]:
                            x = (coord[0] - vb_x) * scale_x
                            y = (coord[1] - vb_y) * scale_y
                            pattern.add_stitch_absolute(pyembroidery.STITCH, x, y)
                        
                        pattern.add_stitch_absolute(pyembroidery.COLOR_BREAK, 0, 0)
            
            pattern.add_stitch_absolute(pyembroidery.END, 0, 0)

        tmp_path = os.path.join(tempfile.gettempdir(), "output.pes")
        pyembroidery.write_pes(pattern, tmp_path)

        with open(tmp_path, "rb") as f:
            pes_bytes = f.read()

        os.remove(tmp_path)
        print(f"V8 PES OK, size: {len(pes_bytes)} bytes")

        from fastapi.responses import Response
        return Response(content=pes_bytes, media_type="application/octet-stream")

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al procesar el archivo: {str(e)}")
