"""Dimension-independent projection using saved metadata and raw row IDs."""
import copy

def physical_key(session,row):
    decisions=getattr(session,'_validated_decisions',None)
    # Only a fully verified store read supplies this map. Raw nested-list keys
    # remain the fallback for live and legacy sessions.
    return decisions[row['id']].tobytes() if decisions is not None else tuple(map(tuple,row['X']))


def history_count(session,checkpoint):
    if checkpoint is None:return 0
    # Checkpoints and raw X are immutable. Process each historical front once,
    # including equal-F/different-X placements, independently of current fronts.
    state=getattr(session,'_history_count_cache',None)
    if state is None:state=dict(counts=[],seen=set(),keys={});session._history_count_cache=state
    for cp in session.checkpoints[len(state['counts']):checkpoint['generation']+1]:
        for i in cp['archive_ids']:
            if i not in state['keys']:state['keys'][i]=physical_key(session,session.rows[i])
            state['seen'].add(state['keys'][i])
        state['counts'].append(len(state['seen']))
    return state['counts'][checkpoint['generation']]

def evaluation_summary(session, checkpoint, tolerance):
    """Read-only prefix accounting; infeasible examples never enter the archive."""
    stop=checkpoint['nfe'] if checkpoint else 0
    cache=getattr(session,'_evaluation_summaries',None)
    if cache is None:cache={};session._evaluation_summaries=cache
    key=(stop,tolerance)
    if key in cache:return copy.deepcopy(cache[key])
    # Live generations append rows. Accumulate each row once rather than
    # rescanning all prior X/G under the optimizer lock on every screen refresh.
    states=getattr(session,'_evaluation_prefixes',None)
    if states is None:states={};session._evaluation_prefixes=states
    state=states.get(tolerance)
    if state is None or stop<state['stop'] or (stop and not state['counts'] and session.rows[0]['G']):
        width=len(session.rows[0]['G']) if stop else 0
        state=dict(stop=0,counts=[0]*width,minimum=[None]*width,maximum=[None]*width,feasible=0,examples=[],seen=set(),unique=set())
    counts=state['counts'];minimum=state['minimum'];maximum=state['maximum']
    feasible=state['feasible'];examples=state['examples'];seen=state['seen'];unique=state['unique']
    rows=session.rows[state['stop']:stop]
    for row in rows:
        bad=False
        for j,g in enumerate(row['G']):
            minimum[j]=g if minimum[j] is None or g<minimum[j] else minimum[j]
            maximum[j]=g if maximum[j] is None or g>maximum[j] else maximum[j]
            if g>tolerance:counts[j]+=1;bad=True
        feasible+=not bad
        if not bad:unique.add(physical_key(session,row))
        if bad and len(examples)<12:
            identity=physical_key(session,row)
            if identity not in seen:examples.append(copy.deepcopy(row));seen.add(identity)
    state.update(stop=stop,feasible=feasible)
    if tolerance not in states or stop>=states[tolerance]['stop']:states[tolerance]=state
    value=dict(evaluated=stop,feasible=feasible,infeasible=stop-feasible,unique_feasible=len(unique),
               tolerance=tolerance,constraint_violations=counts,G_min=minimum,G_max=maximum,
               infeasible_examples=examples,example_policy='FIRST_12_UNIQUE_INFEASIBLE_RAW_PLACEMENTS_NOT_ARCHIVE')
    # Cache a prefix snapshot, never the accumulator's mutable lists.
    cache[key]=copy.deepcopy(value)
    if len(cache)>8:cache.pop(next(iter(cache)))
    return copy.deepcopy(value)

def view(session,generation=None,*,summary=False):
    if summary:
        from .workflow import metadata_packet
        p=metadata_packet(session)
        solver=session.data['solver'] if hasattr(session,'data') else session.solver_metadata
        p['solver']=copy.deepcopy({k:v for k,v in solver.items() if k not in ('auxiliary_evaluations','initial_X','initialization_formulation')})
        p['checkpoints']=[copy.deepcopy({k:v for k,v in c.items() if k not in ('population_X','population_ids','archive_ids','front_ids')}) for c in session.checkpoints]
    else:p=session.packet(include_rows=False,compact_checkpoints=True)
    checkpoints=session.checkpoints
    if generation is not None and not 0<=generation<len(checkpoints):raise ValueError('Invalid generation')
    cp=checkpoints[generation] if generation is not None else checkpoints[-1] if checkpoints else None
    ids=cp['archive_ids'] if cp else []
    initial=checkpoints[0]['archive_ids'] if checkpoints else []
    from .hard_constraints import valid_ids,decorated,reports
    original_count=len(ids);ids=valid_ids(session,ids);initial=valid_ids(session,initial)
    p['installation_audit_summary']=dict(excluded_archive_rows=original_count-len(ids),invalid_raw_rows=sum(not r['hard_pass'] for r in reports(session).values()),policy='CURRENT_HARD_CONSTRAINTS_RAW_UNCHANGED')
    research=p['config'].get('_research') or p['problem'].get('research_configuration')
    p['evaluation_summary']=evaluation_summary(session,cp,p['archive_policy']['tolerance'])
    if not research:raise ValueError('Run has no configurable snapshot; use historical view')
    p.update(view_schema='SOLSOL_CONFIGURABLE_VIEW_V1',metadata=research['metadata'],research_configuration=research,
        historical_nondominated_count=history_count(session,cp),
        generation_population=[decorated(session,i) for i in dict.fromkeys(cp.get('population_ids',[])) if i is not None and i>=0] if cp else [],
        **({} if summary else {'archive':[decorated(session,i) for i in ids]}),
        initial_archive=[decorated(session,i) for i in initial],
        generation=cp['generation'] if cp else 0,target_count=None if research['goals'] is None else sum(session.rows[i]['qualified'] is True for i in ids),
        target_status='NOT_CONFIGURED' if research['goals'] is None else 'REACHED' if any(session.rows[i]['qualified'] for i in ids) else 'NOT_REACHED',
        goal_explanation='설정된 영역 커버율과 설치 제약을 모두 통과한 누적 해만 표시합니다. 목표는 탐색 종료나 달성을 보장하지 않습니다.')
    if summary:
        p['view_schema']='SOLSOL_CONFIGURABLE_SUMMARY_V1'
        p['collections']=dict(archive=dict(count=len(ids),complete=False,endpoint=f'engine/runs/{session.id}/placements',selection='archive'),initial_archive=dict(count=len(initial),complete=True),generation_population=dict(count=len(p['generation_population']),complete=True))
    if getattr(session,'runtime_diagnostic',None):p['runtime_diagnostic']=copy.deepcopy(session.runtime_diagnostic)
    if session.cid in ('HMSP-EXEC-V1','HMSP-2D-V1'):
        p['spatial_loading']='ON_DEMAND_RAW_ROW'
    if session.cid=='HMSP-EXEC-V1':
        p['goal_explanation']='품질 목표는 0~1이며 전체 G<=0으로 탐색 제약에 반영됩니다. A는 합성 품질, C는 외부 cue 조건부 max 품질이며 확률이 아닙니다.'
    return p
