"""Preserved generic tournament extracted from donor moea.py; no model import."""
import numpy as np
def seeded_cv_tournament(pop, pairs, random_state=None, **kwargs):
    """Avoid installed pymoo 0.6.1.6's unseeded infeasible-CV tie branch."""
    if random_state is None:
        raise ValueError("Tournament requires the optimizer RNG")
    winners=[]
    for a,b in pairs:
        av,bv=float(np.asarray(pop[a].CV).item()),float(np.asarray(pop[b].CV).item())
        if (av>0 or bv>0) and av!=bv:
            winners.append(a if av<bv else b)
        else:
            winners.append(int(random_state.choice([a,b])))
    return np.asarray(winners,dtype=int)[:,None]
