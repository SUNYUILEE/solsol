"""Optional compiler preparation before HTTP readiness; no saved data is read."""
def prepare_archive_runtime():
    import time
    started=time.perf_counter()
    try:
        import numpy as np
        from .archive_lifetimes import _compiled_deaths
        if _compiled_deaths is None:
            return dict(state='UNAVAILABLE',seconds=time.perf_counter()-started)
        f=np.empty((0,4),dtype=np.float64)
        i=np.empty(0,dtype=np.int64)
        result=_compiled_deaths(f,i,1,f,f,i,i,i,i,i,i)
        if result.shape!=(0,) or result.dtype!=np.int64:raise ValueError('Empty archive preparation result')
        return dict(state='READY',seconds=time.perf_counter()-started)
    except Exception as exc:
        return dict(state='FALLBACK',reason=type(exc).__name__,seconds=time.perf_counter()-started)
