from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import pyembroidery
import io

app = FastAPI()

# Configuración de CORS (ajusta los orígenes según sea necesario)
origins = [
    "https://stitchcucumber.lovable.app/", # Reemplaza con el dominio de tu app Lovable
    "http://localhost:3000", # Para desarrollo local de Lovable
    "*", # Permite todos los orígenes durante el desarrollo, ¡ajusta para producción!
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/process-svg/")
async def process_svg_file(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".svg"):
        raise HTTPException(status_code=400, detail="Invalid file type. Only .svg files are accepted.")

    try:
        contents = await file.read()
        # pyembroidery.read_svg() espera un archivo-like object o path
        f = io.BytesIO(contents)
        
        # Leer el SVG y convertirlo a un patrón de bordado
        # pyembroidery puede leer SVG y generar un patrón de puntadas
        pattern = pyembroidery.read_svg(f)

        # Si el SVG no contiene información de bordado directamente, pyembroidery intentará vectorizarlo
        # y generar puntadas. Esto puede ser complejo y requerir configuración adicional
        # o un SVG específicamente formateado para bordado.
        
        # Para este ejemplo, asumimos que pyembroidery puede procesar el SVG en un patrón.
        # Si el SVG es puramente gráfico sin instrucciones de bordado, pyembroidery puede
        # generar un patrón vacío o un error si no puede interpretarlo como bordado.

        if not pattern.stitches: # Si no se generaron puntadas, puede que el SVG no fuera interpretable como bordado
             raise HTTPException(status_code=422, detail="SVG could not be converted to an embroidery pattern. Ensure it contains valid vector paths for embroidery.")

        # Extraer información básica del patrón de bordado resultante
        stitch_count = len(pattern.stitches)
        color_changes = len(pattern.thread_set)
        
        # Calcular el tamaño del diseño. pattern.bounds() devuelve (min_x, min_y, max_x, max_y)
        min_x, min_y, max_x, max_y = pattern.bounds()
        design_width = max_x - min_x
        design_height = max_y - min_y

        return JSONResponse({
            "filename": file.filename,
            "stitch_count": stitch_count,
            "color_changes": color_changes,
            "design_width_mm": design_width, # pyembroidery trabaja en mm por defecto
            "design_height_mm": design_height,
            "message": "SVG file processed and converted to embroidery pattern successfully."
        })
    except Exception as e:
        # Captura errores específicos de pyembroidery o de procesamiento de SVG
        raise HTTPException(status_code=500, detail=f"Error processing SVG file: {str(e)}")

@app.get("/")
async def read_root():
    return {"message": "Welcome to the pyembroidery SVG service!"}
