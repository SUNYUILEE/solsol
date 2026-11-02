"""Isolated, user-cancellable solver of an already validated public matrix."""
import json,sys,os,threading,time
from pathlib import Path
import numpy as np
from scipy.optimize import Bounds,LinearConstraint,milp
from scipy.sparse import coo_matrix

def main():
    source,output,phase,parent=sys.argv[1:]
    def parent_watch():
        if os.name=='nt':
            import ctypes
            from ctypes import wintypes
            api=ctypes.WinDLL('kernel32',use_last_error=True)
            api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];api.OpenProcess.restype=wintypes.HANDLE
            api.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
            handle=api.OpenProcess(0x00100000,False,int(parent))
            if not handle:os._exit(3)
            api.WaitForSingleObject(handle,0xFFFFFFFF);os._exit(3)
        else:
            while os.getppid()==int(parent):time.sleep(.2)
            os._exit(3)
    threading.Thread(target=parent_watch,daemon=True).start()
    p=json.loads(Path(source).read_text(encoding='utf-8'))['payload']
    c=np.asarray(p['objective']['c'],float);m=p['constraints'];a=m['matrix']
    matrix=coo_matrix((a['data'],(a['row'],a['col'])),shape=tuple(a['shape'])).tocsc()
    low=[-np.inf if x is None else x for x in m['lower']]
    high=[np.inf if x is None else x for x in m['upper']]
    result=milp(c,integrality=np.ones(len(c)) if phase=='integer' else np.zeros(len(c)),
        bounds=Bounds(0,1),constraints=LinearConstraint(matrix,low,high),options={'mip_rel_gap':0.})
    value=dict(status=int(result.status),message=str(result.message),x=None if result.x is None else result.x.tolist())
    for key in ('fun','mip_dual_bound','mip_gap','mip_node_count'):
        v=getattr(result,key,None);value[key]=float(v) if v is not None and np.isfinite(v) else None
    destination=Path(output);temp=destination.with_suffix('.pending')
    temp.write_text(json.dumps(value,allow_nan=False),encoding='utf-8');temp.replace(destination)

if __name__=='__main__':main()
