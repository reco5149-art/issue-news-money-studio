"""Short-lived local reuse of identical analysis inputs, never credentials."""
import hashlib
import json
import time
from . import storage as st

TTL=6*60*60

def key(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def get(identifier):
    try:
        data=json.loads((st.DATA/'analysis-cache'/(identifier+'.json')).read_text(encoding='utf-8'))
        if 0<=time.time()-data['at']<TTL:return data['result']
    except (OSError,ValueError,KeyError,TypeError):pass
    return None

def put(identifier,result):
    root=st.DATA/'analysis-cache'
    root.mkdir(parents=True,exist_ok=True)
    (root/(identifier+'.json')).write_text(json.dumps({'at':time.time(),'result':result},ensure_ascii=False),encoding='utf-8')
