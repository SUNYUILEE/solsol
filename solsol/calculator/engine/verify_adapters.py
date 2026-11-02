"""Bounded HTTP adapter check; model oracles live in the model project."""
import numpy as np
from app.integrated.engine.registry import compile_problem, compile_toy

def main():
    checks = 0
    for s in (1, 2, 3):
        for m in (2, 3, 4):
            p = compile_toy(n_sensors=s, n_objectives=m)
            b = p.batch(np.zeros((0, p.n_var), np.uint8))
            assert b.F.shape == (0, m) and b.G.shape == (0, 0)
            b = p.batch(np.zeros((2, p.n_var), np.uint8))
            assert b.F.shape == (2, m) and b.G.shape == (2, 0)
            checks += 2
    from live_model import DEFAULT
    p = compile_problem('RADAR_EOIR', dict(DEFAULT))
    x = np.zeros((p.model.n, 2), np.uint8)
    rows = p.evaluate_physical(x)
    f, g, _ = p.model.evaluate(x)
    assert np.array_equal(rows[0]['F'], f) and np.array_equal(rows[0]['G'], g)
    checks += 1
    from rf_contract import fixture
    p = compile_problem('RADAR_RF_SCANNER', fixture())
    x = np.zeros((p.model.n, 2), np.uint8)
    row = p.evaluate_physical(x, spatial=True)[0]
    old = p.model.row(x)
    assert row['F'] == old['F'] and row['G'] == old['G'] and row['rf_status'] == old['rf_status']
    checks += 1
    print({'status': 'PASS', 'checks': checks, 'scope': 'developer dimensions and legacy delegated comparison'})

if __name__ == '__main__':
    main()
