"""Deterministic Cartesian segment/solid-prism line of sight."""
import numpy as np


def visible(start, end, obstacles):
    """Closed prisms block touches and endpoints; no diffraction or inference."""
    a=np.asarray(start,dtype=float);b=np.asarray(end,dtype=float)
    if a.shape!=(3,) or b.shape!=(3,) or not np.isfinite([a,b]).all():
        raise ValueError('LOS requires finite XYZ endpoints')
    direction=b-a
    for box in obstacles:
        lower=np.array([box['xmin'],box['ymin'],box['zmin']],float)
        upper=np.array([box['xmax'],box['ymax'],box['zmax']],float)
        if not np.isfinite([lower,upper]).all() or np.any(lower>=upper):
            raise ValueError('Invalid solid prism')
        enter=0.;leave=1.
        for j in range(3):
            if direction[j]==0:
                if a[j]<lower[j] or a[j]>upper[j]:
                    enter=2.;break
            else:
                t0=(lower[j]-a[j])/direction[j];t1=(upper[j]-a[j])/direction[j]
                enter=max(enter,min(t0,t1));leave=min(leave,max(t0,t1))
                if enter>leave:break
        if enter<=leave:return False
    return True
