"""Explain observed saved sets; never infer global feasibility or human understanding."""

def explain(cell, scope):
    if cell['state'] != 'completed':
        return dict(status='NOT_COMPLETE', answer='아직 이 실험의 계산·재평가·저장이 완료되지 않았습니다.',
                    numbers='현재 상태: '+cell['state'], meaning='미완료를 절충 없음이나 목표 불가능으로 판단하지 않습니다.',
                    next_action='진행 상태를 확인하고 완료 후 결과를 여세요.', human_understanding='NOT_MEASURED')
    target = cell['b_target_count']
    configured = cell['goals_configured']
    witness = cell['a_target_witness']
    if scope == 'targets' and not configured:
        status, answer = 'TARGETS_UNCONFIGURED', '저장 조건에 목표가 설정되지 않아 목표 통과 해를 비교할 수 없습니다.'
    elif not cell['b_archive_count']:
        status, answer = 'EMPTY_SCOPE', '이번 B 탐색에서 선택한 집합에 해당하는 배치를 찾지 못했습니다.'
    elif cell['b_conflict']:
        status, answer = 'OBSERVED_CONFLICT', '이 예산 안에서 한 성능을 높이면 다른 성능이 낮아지는 배치 쌍을 관측했습니다.'
    else:
        status, answer = 'NO_CONFLICT_OBSERVED', '이번에 찾은 배치에서는 판정 허용오차를 넘는 성능 간 절충을 관측하지 못했습니다.'
    numbers = (f"예산 {cell['budget']:g} · seed {cell['seed']} · B 전체 누적 비지배 {cell['b_all_archive_count']}개"
               + (f" · 목표 통과 {target}개" if configured else ' · 목표 미설정')
               + f" · 현재 표시 {cell['b_archive_count']}개 · 서로 다른 성능 최선값 {cell['b_performance_front']}개")
    if witness and target == 0:
        meaning = (f"같은 예산 이하에서 A seed {witness.get('seed', '미기록')}의 원시 행 {witness['raw_id']}가 이미 목표를 통과했습니다(비용 {witness['cost']:g}). "
                   '따라서 B의 목표 0개는 이번 탐색의 미발견이며, 목표 달성 불가능이 아닙니다.')
    elif not cell['b_conflict']:
        meaning = '탐색 부족, 성능 포화 또는 여러 성능이 함께 좋아지는 구조일 수 있습니다. 이 결과만으로 원인을 확정할 수 없습니다.'
    else:
        pair = cell['b_conflict']
        meaning = f"B 원시 행 {pair['A']['id']}와 {pair['B']['id']}의 실제 성능을 아래에서 비교할 수 있습니다. 이는 저장된 관측 배치 사이의 절충입니다."
    slack = cell['min_budget_slack']
    limit = ('비교 집합에서 최소 잔여 예산 '+(f'{slack:g}' if slack is not None else '미관측')
             +'입니다. 잔여 예산 0만으로 자원 부족의 인과 효과를 증명하지 않습니다. '
             'A→B는 비용 목적 제거와 예산 제한이 함께 바뀝니다. 전역 최적·수렴·필요 최소 예산의 증명이 아닙니다.')
    action = ('전체 누적 집합을 확인하거나 목표를 설정한 새 실험을 구성하세요.' if status == 'TARGETS_UNCONFIGURED'
              else 'A의 목표 통과 근거를 확인하고 동일 조건의 탐색량·반복 결과를 비교하세요.' if witness and target == 0
              else '예산·seed별 성능 범위를 비교한 뒤 아래 A·B 두 배치를 검산하세요.' if cell['a_example'] and cell['b_example']
              else '비교할 배치가 있는 집합·예산을 선택하세요. 빈 결과를 검산 완료로 처리하지 않습니다.')
    return dict(status=status,answer=answer,numbers=numbers,meaning=meaning,scope=limit,next_action=action,
                human_understanding='NOT_MEASURED')
