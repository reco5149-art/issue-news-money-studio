"""Exit nonzero when first-run dependency installation is required."""
import importlib.util
import sys

modules = ('fastapi', 'uvicorn', 'httpx', 'bs4', 'PIL', 'multipart', 'dotenv')
sys.exit(0 if all(importlib.util.find_spec(name) for name in modules) else 1)
