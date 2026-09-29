"""Optional media-only server. Never expose the editor API with a public tunnel."""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .storage import MEDIA,init
init()
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
app.mount('/',StaticFiles(directory=MEDIA),name='public-images')
