"""Human-readable discovery/export names; UUID remains the internal identity."""
from datetime import datetime
from math import isfinite

def _mapping(value):
    return value if isinstance(value,dict) else {}

def _recorded_integer(*values):
    return next((v for v in values if type(v) is int and v>=0),None)

def names(packet,folder):
    stamp=datetime.fromtimestamp(folder.stat().st_ctime).strftime('%Y-%m-%d_%H-%M-%S')
    cid=packet.get('experiment_contract_id',folder.parent.name)
    model={'HMSP-2D-V1':'Radar-RF-EOIR','RADAR_EOIR':'Radar-EOIR','RADAR_RF_SCANNER':'Radar-RF'}.get(cid,cid)
    opt=_mapping(packet.get('optimizer'));config=_mapping(packet.get('config'))
    checkpoints=_recorded_integer(opt.get('checkpoints'))
    # Historical EOIR records keep these values in config, not optimizer.
    # Absence is not an observed zero-generation or unlimited-budget run.
    generations=_recorded_integer(opt.get('generations'),
        checkpoints-1 if checkpoints is not None and checkpoints>0 else None,
        config.get('generations'),packet.get('actual_generation'),
        packet.get('latest_generation'),packet.get('generation'))
    seed=_recorded_integer(opt.get('seed'),config.get('seed'))
    budget=_mapping(_mapping(config.get('_resource_contract')).get('budget'))
    limit=budget.get('limit');b=None
    if budget.get('mode')=='OFF':b='OFF'
    elif budget.get('mode')=='MAX' and type(limit) in (int,float) and limit>=0 and (type(limit) is int or isfinite(limit)):b=str(limit)
    generation_label=f'{generations}세대' if generations is not None else '세대 미기록'
    label=f'{stamp.replace("_"," ")} · {model} · {generation_label} · 예산 {b if b is not None else "미기록"} · seed {seed if seed is not None else "미기록"}'
    file=f'{stamp}_{model}_{generations if generations is not None else "unknown"}gen_budget-{b if b is not None else "unknown"}_seed-{seed if seed is not None else "unknown"}_{packet.get("run_id",folder.name)[:8]}'
    return dict(display_name=label,export_name=file)
