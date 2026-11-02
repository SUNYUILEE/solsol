"""Advisory execution scale, separate from frozen scientific input/hash."""
def plan(problem,optimizer,run_root):
    import shutil
    from pathlib import Path
    import psutil
    count=optimizer['checkpoints'];nfe=count*optimizer['population']
    disk_path=Path(run_root).resolve()
    while not disk_path.exists():disk_path=disk_path.parent
    return dict(schema='SOLSOL_EXECUTION_RESOURCES_V1',search_evaluations=nfe,
        full_replay_evaluations=nfe,checkpoint_count=count,
        initialization_evaluation_limit=optimizer.get('initialization_evaluations',0),
        decision_values=nfe*problem.n_var,
        available_memory_bytes=psutil.virtual_memory().available,
        disk_free_bytes=shutil.disk_usage(disk_path).free,disk_path=str(disk_path),
        estimates_only=True,wall_time_estimate_seconds=None,
        note='초기 집단 포함 탐색 전체를 저장하고 종료 후 같은 행 전체를 재평가합니다. 모든 세대·누적 archive를 보존합니다. 소요 시간·최대 메모리는 배치와 archive 크기에 따라 달라집니다. 새 계산 시작 시 완료된 저장 결과의 메모리 캐시를 비우며 원본 파일은 유지합니다.')
