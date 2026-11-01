from __future__ import annotations

import pytest

from metamorph.comparators import build_comparator
from metamorph.errors import ConfigError, NotComparable


def score(name: str, a: str, b: str, **params: object) -> float:
    return build_comparator(name, params).compare(a, b).score


def test_registry_errors() -> None:
    with pytest.raises(ConfigError, match="unknown comparator"):
        build_comparator("nope", {})
    with pytest.raises(ConfigError, match="bad params"):
        build_comparator("json_fields_equal", {"paths": []})
    with pytest.raises(ConfigError, match="invalid JSONPath"):
        build_comparator("json_fields_equal", {"paths": ["$[[["]})


class TestExact:
    def test_normalises_case_and_whitespace_by_default(self) -> None:
        assert score("exact", "Nairobi  is\nbig", "nairobi is big") == 1.0
        assert score("exact", "Nairobi", "nairobi", case_sensitive=True) == 0.0
        assert score("exact", "yes", "no") == 0.0


class TestTokenF1:
    def test_scores(self) -> None:
        assert score("token_f1", "M-Pesa launched in 2007", "m-pesa LAUNCHED in 2007!") == 1.0
        assert score("token_f1", "a b c d", "a b x y") == pytest.approx(0.5)
        assert score("token_f1", "alpha", "beta") == 0.0
        assert score("token_f1", "", "") == 1.0


class TestNumericWithin:
    def test_text_numbers(self) -> None:
        assert score("numeric_within", "It is 5,199 m", "Height: 5199 metres") == 1.0
        assert score("numeric_within", "47 counties", "48 counties") == 0.0
        assert score("numeric_within", "47 counties", "48 counties", tol=1) == 1.0
        assert score("numeric_within", "100", "104", tol=0.05, relative=True) == 1.0
        assert score("numeric_within", "1 and 2", "1 only") == 0.0

    def test_json_path(self) -> None:
        a, b = '{"total": 1000}', '```json\n{"total": 1000.0}\n```'
        assert score("numeric_within", a, b, path="$.total") == 1.0

    def test_not_comparable_without_numbers(self) -> None:
        with pytest.raises(NotComparable):
            score("numeric_within", "no numbers", "none here")


class TestJsonFieldsEqual:
    def test_share_of_equal_fields(self) -> None:
        a = '{"name": "Wanjiru", "skills": ["python", "sql"], "years": 3}'
        b = '{"name": "Wanjiru", "skills": ["python", "sql"], "years": 4}'
        assert score("json_fields_equal", a, b, paths=["$.name", "$.skills"]) == 1.0
        assert score("json_fields_equal", a, b, paths=["$.name", "$.years"]) == 0.5

    def test_invalid_source_json(self) -> None:
        with pytest.raises(NotComparable):
            score("json_fields_equal", "not json", "{}", paths=["$.a"])


class TestSetEqual:
    def test_json_list_and_plain_text(self) -> None:
        assert score("set_equal", '["Python", "SQL"]', '["sql", "python"]') == 1.0
        assert score("set_equal", "- Python\n- SQL", "python, sql") == 1.0
        assert score("set_equal", '["a", "b"]', '["a", "c"]') == pytest.approx(1 / 3)

    def test_path(self) -> None:
        a, b = '{"skills": ["a", "b"]}', '{"skills": ["b", "a"]}'
        assert score("set_equal", a, b, path="$.skills") == 1.0


class TestJsonSchemaEqual:
    def test_same_shape_different_values(self) -> None:
        a = '{"skills": ["python"], "years": 3, "remote": true}'
        b = '{"skills": ["go", "rust"], "years": 10, "remote": false}'
        assert score("json_schema_equal", a, b) == 1.0

    def test_shape_changes(self) -> None:
        a = '{"skills": ["python"], "years": 3}'
        assert score("json_schema_equal", a, '{"skills": "python", "years": 3}') < 1.0
        assert score("json_schema_equal", a, "Sorry, I cannot help.") == 0.0

    def test_source_must_be_json(self) -> None:
        with pytest.raises(NotComparable):
            score("json_schema_equal", "plain", "{}")
