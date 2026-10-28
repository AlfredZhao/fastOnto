"""Keep the documented tutorial compatible with the shipped modeling subset."""
import json

import pytest
import yaml
from rdflib import Graph

from app.config import ROOT
from app.modeling import InvalidModel, parse_model


@pytest.fixture
def tutorial():
    return (ROOT / "models/standards-tutorial.yaml").read_text(encoding="utf-8")


def test_tutorial_structure(tutorial):
    _, report = parse_model(tutorial)
    classes = {c["name"]: c for c in report["classes"]}
    assert set(classes) == {"Standard", "Organization"}
    assert len(classes["Standard"]["slots"]) == 7
    assert len(classes["Organization"]["slots"]) == 2
    assert report["enum_count"] == 1
    assert report["relationships"] == [
        {"source": "Standard", "target": "Organization", "label": "发布机构", "kind": "reference"}
    ]
    assert len({c["uri"] for c in classes.values()}) == 2


def test_tutorial_unknown_range(tutorial):
    data = yaml.safe_load(tutorial)
    data["classes"]["Standard"]["attributes"]["issuedBy"]["range"] = "MissingOrganization"
    with pytest.raises(InvalidModel, match="未知类型"):
        parse_model(yaml.safe_dump(data, allow_unicode=True))


def test_tutorial_string_is_not_relationship(tutorial):
    data = yaml.safe_load(tutorial)
    data["classes"]["Standard"]["attributes"]["issuedBy"]["range"] = "string"
    _, report = parse_model(yaml.safe_dump(data, allow_unicode=True))
    assert report["valid"]
    assert report["relationships"] == []


@pytest.mark.parametrize("format", ["jsonschema", "owl", "shacl"])
def test_tutorial_exports(client, tutorial, format):
    response = client.post(f"/api/models/export/{format}", json={"source": tutorial})
    assert response.status_code == 200
    content = response.json()["content"]
    if format == "jsonschema":
        assert "Standard" in json.loads(content)["$defs"]
    else:
        assert len(Graph().parse(data=content, format="turtle")) > 0
