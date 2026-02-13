import sys
from unittest.mock import MagicMock

# Mock de wx para evitar instalar librerías gráficas pesadas
mock_wx = MagicMock()
sys.modules["wx"] = mock_wx
sys.modules["wx.lib"] = MagicMock()
sys.modules["wx.lib.newevent"] = MagicMock()

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import os
import uuid
import lxml.etree as ET

app = FastAPI()

# Configuración de CORS segura para producción
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", 
        "https://stitchcucumber.lovable.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ... (Aquí el resto de tus funciones como preparar_svg_para_inkstitch y el endpoint /convert) ...
