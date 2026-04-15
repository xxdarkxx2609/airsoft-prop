"""PyInstaller runtime hook — forces mock mode for standalone builds."""

import sys

if "--mock" not in sys.argv:
    sys.argv.append("--mock")
