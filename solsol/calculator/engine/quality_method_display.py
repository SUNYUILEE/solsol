"""Current API guidance, separate from the frozen diagnostic computation identity."""
import copy

def describe(payload):
    from .quality_jobs import METHODS
    return dict(payload,methods={key:value['label'] for key,value in METHODS.items()},
        method_registry=copy.deepcopy(METHODS),
        execution=dict(endpoint='quality-jobs',evaluation_budget=None,time_budget=None,cancel_resume=True,
            meaning='선택한 범위 전체를 검사합니다. 중지·미완료는 전체 검사를 끝낸 결과와 구분합니다.'),
        legacy_execution=dict(endpoint='quality-workflow',meaning='과거 동기 검산 API: 요청별 평가 수 제한과 작은 문제 전체 조합만 지원합니다. 새 검산은 quality-jobs를 사용합니다.'))
