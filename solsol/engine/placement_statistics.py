"""Exact decision-space statistics without repeated layout conversion."""
import numpy as np


def hamming_summary(layouts):
    n=len(layouts);count=n*(n-1)//2
    low=high=None;total=0
    if count:
        xs=np.asarray(layouts).reshape(n,-1)
        for i in range(1,n):
            distances=np.count_nonzero(xs[:i]!=xs[i],axis=1)
            total+=int(distances.sum())
            a=int(distances.min());b=int(distances.max())
            low=a if low is None else min(low,a)
            high=b if high is None else max(high,b)
    return dict(pair_count=count,minimum=low,maximum=high,mean=total/count if count else None)
