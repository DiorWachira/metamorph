from __future__ import annotations

from pathlib import Path

import pytest

from metamorph.config import Config, load_config
from metamorph.errors import ConfigError
from metamorph.relations import resolve_relations
from metamorph.seeds import load_seeds
from metamorph.types import Mode

BASE = {"target": {"type": "python", "callable": "m:f"}, "seeds": "seeds.jsonl"}


def config(**overrides: object) -> Config:
    return Config.model_validate({**BASE, **overrides})


def test_load_config_expands_env_but_snapshots_raw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_TOKEN", "s3cret")
    path = tmp_path / "metamorph.yaml"
    path.write_text(
        "target: {type: http, url: 'http://x', headers: {Authorization: 'Bearer ${APP_TOKEN}'}}\n"
        "seeds: seeds.jsonl\nrelations: [typo-robustness]\n",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.target.headers["Authorization"] == "Bearer s3cret"  # type: ignore[union-attr]
    assert "s3cret" not in str(cfg.snapshot)
    assert cfg.resolve(cfg.seeds) == tmp_path / "seeds.jsonl"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (
            "target: {type: python, callable: m:f}\nseeds: s.jsonl\nrelations: [x]\nbogus: 1\n",
            "bogus",
        ),
        ("target: {type: ftp}\nseeds: s.jsonl\nrelations: [x]\n", "invalid config"),
        ("- just a list\n", "mapping"),
        (
            "target: {type: http, url: '${NOPE_NOT_SET}'}\nseeds: s\nrelations: [x]\n",
            "NOPE_NOT_SET",
        ),
    ],
)
def test_invalid_configs(tmp_path: Path, content: str, message: str) -> None:
    path = tmp_path / "metamorph.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError, match=message):
        load_config(path)


def test_missing_config_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="metamorph init"):
        load_config(tmp_path / "missing.yaml")


class TestResolveRelations:
    def test_builtin_by_id_and_overrides(self) -> None:
        cfg = config(
            relations=[
                "doc-order-invariance",
                {
                    "id": "typo-robustness",
                    "mode": "blocking",
                    "transform": {"params": {"rate": 0.3}},
                },
            ]
        )
        doc, typo = resolve_relations(cfg)
        assert doc.mode is Mode.WARNING and doc.threshold == 0.8
        assert typo.mode is Mode.BLOCKING
        assert typo.transform.rate == 0.3  # type: ignore[attr-defined]

    def test_switching_comparator_drops_old_params(self) -> None:
        cfg = config(relations=[{"id": "typo-robustness", "comparator": {"name": "exact"}}])
        (rel,) = resolve_relations(cfg)
        assert rel.comparator.name == "exact" and rel.threshold == 1.0

    def test_custom_relation(self) -> None:
        custom = {
            "id": "my-rel",
            "description": "custom",
            "transform": {"name": "typos"},
            "comparator": {"name": "set_equal", "threshold": 0.9},
        }
        (rel,) = resolve_relations(config(relations=[custom]))
        assert rel.id == "my-rel" and rel.threshold == 0.9

    def test_errors(self) -> None:
        with pytest.raises(ConfigError, match="unknown relation"):
            resolve_relations(config(relations=["nope"]))
        with pytest.raises(ConfigError, match="more than once"):
            resolve_relations(config(relations=["typo-robustness", "typo-robustness"]))
        with pytest.raises(ConfigError, match="invalid relation"):
            resolve_relations(config(relations=[{"id": "half-defined"}]))
        with pytest.raises(ConfigError, match="not enabled"):
            resolve_relations(config(relations=["typo-robustness"]), only=["distractor-invariance"])

    def test_only_filter(self) -> None:
        cfg = config(relations=["typo-robustness", "distractor-invariance"])
        assert [r.id for r in resolve_relations(cfg, only=["typo-robustness"])] == [
            "typo-robustness"
        ]


class TestSeeds:
    def test_load_with_defaults_and_limit(self, tmp_path: Path) -> None:
        path = tmp_path / "s.jsonl"
        path.write_text(
            '{"input": {"q": 1}}\n\n'
            '{"id": "b", "input": {"q": 2}, "tags": ["rag"]}\n'
            '{"input": {}}\n',
            encoding="utf-8",
        )
        seeds = load_seeds(path)
        assert [s.id for s in seeds] == ["line-1", "b", "line-4"]
        assert seeds[1].tags == {"rag"}
        assert len(load_seeds(path, limit=2)) == 2

    @pytest.mark.parametrize(
        ("content", "message"),
        [
            ("not json\n", "invalid JSON"),
            ('{"question": "no input wrapper"}\n', '"input"'),
            ('{"id": "a", "input": {}}\n{"id": "a", "input": {}}\n', "duplicate"),
            ('{"input": {}, "tags": "rag"}\n', "tags"),
            ("\n", "empty"),
        ],
    )
    def test_invalid(self, tmp_path: Path, content: str, message: str) -> None:
        path = tmp_path / "s.jsonl"
        path.write_text(content, encoding="utf-8")
        with pytest.raises(ConfigError, match=message):
            load_seeds(path)
