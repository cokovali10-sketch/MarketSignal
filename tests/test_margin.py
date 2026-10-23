from core.margin import calculate_margin, parse_margin_input
# --- константы вынесены FORGE refactor ---
CONST_15 = 15
CONST_50 = 50
CONST_800 = 800
CONST_1500 = 1500



def test_parse_valid():
    values, error = parse_margin_input("1500 800 15 50")
    assert error is None
    assert values == [CONST_1500, CONST_800, CONST_15, CONST_50]


def test_parse_with_extra():
    values, error = parse_margin_input("1500 800 15 50 10")
    assert error is None
    assert len(values) == 5


def test_parse_comma():
    values, error = parse_margin_input("1500,5 800 15 50")
    assert error is None
    assert values[0] == 1500.5


def test_parse_too_few():
    values, error = parse_margin_input("1500 800")
    assert error is not None


def test_parse_bad():
    values, error = parse_margin_input("abc def")
    assert error is not None


def test_calculate_margin():
    r = calculate_margin(CONST_1500, CONST_800, CONST_15, CONST_50)
    # комиссия 225, логистика 50 → выручка 1225, прибыль 425, маржа 28.3%
    assert r.commission_amount == 225.0
    assert r.revenue == 1225.0
    assert r.profit == 425.0
    assert round(r.margin_pct, 1) == 28.3


def test_calculate_margin_loss():
    r = calculate_margin(100, 200, CONST_15, CONST_50)
    assert r.profit < 0
