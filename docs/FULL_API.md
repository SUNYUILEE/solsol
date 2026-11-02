# 같은 계산기를 앱·AI에서 호출하기

서버를 시작하고 등록 계약을 사용합니다.

```python
from solsol.calculator.client import EngineClient
import json, uuid

c = EngineClient('ABC_COVERAGE_RESOURCE_V1', 'http://127.0.0.1:8877')
registry = c.registry()
request = json.load(open('request.json', encoding='utf-8'))
confirmed = c.validate_configuration(request)
key = str(uuid.uuid4())
posted = c.submit_configuration(request, key, confirmed['execution_sha256'])
saved = c.wait(posted['run_id'], seconds=30)  # bounded; poll again if active
print(saved['state'], posted['ui_url'])
# c.cancel(posted['run_id'])
# c.request_status(key)  # recover uncertain submission without a new POST
```

`config`, `registry`, `list_runs`, `status(generation=...)`, `copy_configuration`, `compare_runs`, `configuration_diff`, `result_contract`, `diagnose`, `diagnostics`, `quality_overview`, `quality_start/status/cancel/resume`, `quality_research`, `preview_validation/submit_validation`, `validation/cancel_validation/retry_validation`, `export_validation`, `empirical_reference`는 동일 서버의 서비스입니다. 정확한 인자·응답은 `solsol/calculator/engine_client.py`를 참조합니다.

HTTP 접두사는 `/contracts/{cid}/api/`입니다. GET `config`에서 세션 token, GET `engine/registry`에서 모델·폼·metric·capability를 조회합니다. POST에는 JSON, `X-Experiment-Contract`, `X-Run-Token`이 필요합니다. 실행 POST에는 `X-Request-ID`, `X-Execution-SHA256`을 추가합니다. `engine/validations`에는 preview의 plan SHA를 사용합니다. 토큰은 실행 시 발급되며 저장소에 넣지 않습니다.

원시 내보내기는 서버 산출물을 그대로 보존합니다. 검산·reference는 별도 증거이며 optimizer 원시 X/F/G와 출처를 바꾸지 않습니다. 과거 전용 `runs/.../quality-set`, `multi-seed-quality`, `robust-cost-proof`는 원본에서도 공통 API에 구현되지 않았습니다. 현재 `quality-research`, `quality-workflow`, `quality-jobs`, 반복 검증·reference 서비스로 접근하며 이 전용 경로의 복구를 주장하지 않습니다.
