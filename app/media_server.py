"""Optional media-only server. Never expose the editor API with a public tunnel."""
import re
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from .storage import MEDIA,init
init()
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)

@app.get('/{post_id}/{filename}')
def public_image(post_id: str, filename: str):
    if not re.fullmatch(r'[a-f0-9]{32}', post_id) or not re.fullmatch(r'(0[1-9]|10)\.(jpg|png)', filename):
        raise HTTPException(404)
    path = MEDIA / post_id / filename
    if not path.is_file() or path.resolve().parent.parent != MEDIA.resolve():
        raise HTTPException(404)
    return FileResponse(path)
