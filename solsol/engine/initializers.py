"""Model-oracle preparation. MILP proposes a local linear approximation only."""
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from .inventory import assign, resource_bounds, randomized_resource_repair
from .contracts import digest


def prepare(model,opt,cancel):
    space=model.space;lower,upper=resource_bounds(space,model.inventory_rule)
    rng=np.random.default_rng(np.random.SeedSequence([opt['seed'],91401]))
    population=[]
    for _ in range(opt['population']):
        counts=np.array([rng.integers(lo,hi+1) for lo,hi in zip(lower,upper)])
        orders=[rng.permutation(np.flatnonzero(space.allowed[:,j])) for j in range(space.shape[1])]
        population.append(assign(space,counts,orders,exact=bool(np.all(lower==upper)),minimum=lower))
    ledger=[];trace=[];method=opt['initializer'];budget=opt['preparation_budget']
    def evaluate(x,purpose):
        if cancel.is_set() or len(ledger)>=budget:return None
        row=model.evaluate(x)
        ledger.append(dict(auxiliary_id=len(ledger),phase='preparation',purpose=purpose,row=row))
        return row
    if method!='random' and budget:
        base=assign(space,lower,[np.flatnonzero(space.allowed[:,j]) for j in range(space.shape[1])],minimum=lower)
        r0=evaluate(base,'baseline')
        slots=np.argwhere(space.allowed & (base==0))
        proposals=[];deltas=[];gdelta=[];score=[]
        for i,j in slots:
            if len(ledger)>=budget-1 or cancel.is_set():break
            x=base.copy();x[i,j]=1
            # Single-bit probes are evaluated, not assumed feasible.
            try:r=evaluate(x,'single-add')
            except ValueError:continue
            if r is None:break
            proposals.append((int(i),int(j)));deltas.append(np.array(r['F'])-r0['F']);gdelta.append(np.array(r['G'])-r0['G'])
            gain=sum(max(0,r['named_metrics'].get(k,0)-r0['named_metrics'].get(k,0)) for k in ['coverage','joint_coverage'])
            score.append(gain/max(r['cost']-r0['cost'],1e-12))
        candidate=base.copy()
        if method=='milp' and proposals:
            n=len(proposals)
            # Normalize objective slopes; original F/G are never replaced.
            d=np.asarray(deltas);scale=np.maximum(np.abs(d).max(0),1.)
            objective=(d/scale).sum(1)
            result=milp(objective,integrality=np.ones(n),bounds=Bounds(np.zeros(n),np.ones(n)),
                constraints=LinearConstraint(np.asarray(gdelta).T,-np.inf,-np.asarray(r0['G'])),
                options=dict(time_limit=5.0))
            trace.append(dict(kind='LOCAL_LINEAR_PROPOSAL',status=int(result.status),
                message=result.message,scientific_optimum_certified=False))
            if result.x is not None:
                for (i,j),v in zip(proposals,result.x):
                    if v>.5:candidate[i,j]=1
        elif proposals:
            # Greedy recomputes actual marginal gain at every accepted step.
            current=r0
            for _,(i,j) in sorted(zip(score,proposals),key=lambda pair:-pair[0]):
                if len(ledger)>=budget-1:break
                x=candidate.copy();x[i,j]=1
                try:r=evaluate(x,'greedy-add')
                except ValueError:continue
                performance_axes=[i for i,k in enumerate(model.objective_ids) if k!='cost']
                if r is not None and all(g<=0 for g in r['G']) and any(r['F'][i]<current['F'][i] for i in performance_axes):
                    candidate=x;current=r
        candidate=randomized_resource_repair(space,model.inventory_rule,candidate,rng)
        final=evaluate(candidate,'proposal-recheck')
        if final is not None and all(g<=0 for g in final['G']):population[0]=candidate
        trace.append(dict(proposal_feasible=bool(final and all(g<=0 for g in final['G'])),
                          injected=bool(final and all(g<=0 for g in final['G']))))
    physical=np.asarray(population)
    info=dict(method=method,version='neutral-common-initialization-v1',preparation_budget=budget,
        preparation_evaluations=len(ledger),initial_X_sha256=digest(physical.astype(int).tolist()),
        trace=trace,scientific_optimum_certified=False,
        approximation='LOCAL_LINEAR_F_G_PROPOSAL' if method=='milp' else None)
    return physical,ledger,info
