# --- CIRUGÍA DE ESTRUCTURA TOTAL DE WX ---
# Creamos una estructura genérica de carpetas para que NADA falle al importar desde wx.lib
RUN mkdir -p /usr/local/lib/python3.11/site-packages/wx/lib/agw/floatspin \
    && mkdir -p /usr/local/lib/python3.11/site-packages/wx/lib/intctrl \
    && mkdir -p /usr/local/lib/python3.11/site-packages/wx/lib/scrolledpanel

# Creamos todos los __init__.py necesarios
RUN find /usr/local/lib/python3.11/site-packages/wx -type d -exec touch {}/__init__.py \;

# Inyectamos el Mocking global que intercepta cualquier llamada a wx
RUN echo 'import sys\n\
from unittest.mock import MagicMock\n\
m = MagicMock()\n\
# Interceptamos el nivel base y subniveles comunes\n\
sys.modules["wx"] = m\n\
sys.modules["wx.lib"] = m\n\
sys.modules["wx.adv"] = m\n\
sys.modules["wx.core"] = m\n\
# Interceptamos dinámicamente cualquier sub-módulo que pida Inkstitch\n\
class MockPackage(MagicMock):\n\
    def __getattr__(self, name):\n\
        return MagicMock()\n\
sys.modules["wx.lib.agw"] = MockPackage()\n\
sys.modules["wx.lib.agw.floatspin"] = MockPackage()\n\
sys.modules["wx.lib.intctrl"] = MockPackage()\n\
sys.modules["wx.lib.scrolledpanel"] = MockPackage()' > /usr/local/lib/python3.11/site-packages/wx/__init__.py

# Parche de ruta de Inkstitch
RUN sed -i 's/sys.path.remove(extensions_path)/pass # sys.path.remove(extensions_path)/g' /usr/local/bin/inkstitch_dir/inkstitch.py
# -----------------------------------------
