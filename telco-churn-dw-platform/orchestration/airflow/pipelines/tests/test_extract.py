from datetime import UTC, datetime

from pipelines.extract_ops import _convert


def test_mysql_tinyint_boolean_becomes_bool():
    assert _convert("churned", 1) is True
    assert _convert("churned", 0) is False
    assert _convert("churned", None) is None


def test_naive_mysql_datetime_is_utc():
    v = _convert("updated_at", datetime(2026, 10, 21, 12, 0))
    assert v == datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def test_other_values_untouched():
    assert _convert("tenure_months", 5) == 5
