"""Calculator-owned result I/O and historical two-bit placement encoding."""
import hashlib,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,allow_nan=False,indent=2)
def mask(x):return (np.asarray(x,dtype=np.uint8)*[1,2]).sum(axis=-1).astype(np.uint8)
def unmask(q):
    q=np.asarray(q)
    if np.any((q<0)|(q>3)|(q!=np.floor(q))):raise ValueError('invalid four-state gene')
    return ((q[...,None].astype(np.uint8)&np.array([1,2],np.uint8))>0).astype(np.uint8)
def load_model(name):
    from model_service_client import module_attribute
    data=read(ROOT/'results'/name/'problem.json')
    return module_attribute('model','Model')(data['sites_metres'],data['demand_metres'])
