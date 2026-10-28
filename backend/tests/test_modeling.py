import json

import pytest
import yaml
from rdflib import Graph

from app.modeling import InvalidModel, parse_model


def test_reference_model(source):
    _, r = parse_model(source)
    assert r["valid"]
    assert len(r["classes"]) == 6
    assert len(r["relationships"]) == 5
    product = next(c for c in r["classes"] if c["name"] == "Product")
    assert product["uri"] == "https://fastonto.example/vocab/Product"
    assert next(f for f in product["slots"] if f["name"] == "id")["identifier"]


@pytest.mark.parametrize("change", [
    lambda d: d.update(imports=["https://example.invalid/evil"]),
    lambda d: d.update(imports=["/etc/passwd"]),
    lambda d: d["prefixes"].update(linkml="https://example.invalid/"),
    lambda d: d["classes"]["Product"].update(is_a="Product"),
    lambda d: d["classes"]["Product"].update(is_a="Missing"),
    lambda d: d["classes"]["Product"].update(slots=["undefined"]),
    lambda d: d["classes"]["Product"].update(slot_usage={"undefined": {"required": True}}),
    lambda d: d["slots"]["label"].update(range="Undefined"),
    lambda d: d["slots"]["label"].update(required="not a boolean"),
    lambda d: d["slots"]["label"].update(ifabsent="python:malicious"),
    lambda d: d.update(default_prefix="missing"),
    lambda d: d.update(title="x" * 501),
    lambda d: d.update(classes=[]),
])
def test_invalid_profile(source, change):
    data = yaml.safe_load(source)
    change(data)
    with pytest.raises(InvalidModel):
        parse_model(yaml.safe_dump(data, allow_unicode=True))


@pytest.mark.parametrize("source", ["name: a\nname: b", "a: &a [*a]", "!!python/object/apply:os.system [echo nope]", "[]", "a: [", "x" * 65537, "a: " + "[" * 25 + "0" + "]" * 25])
def test_malformed_yaml(source):
    with pytest.raises(InvalidModel):
        parse_model(source)


def test_inheritance(source):
    d = yaml.safe_load(source)
    d["classes"]["SpecialProduct"] = {"is_a": "Product", "title": "特殊产品"}
    _, report = parse_model(yaml.safe_dump(d, allow_unicode=True))
    cls = next(c for c in report["classes"] if c["name"] == "SpecialProduct")
    assert {s["name"] for s in cls["slots"]} == {"id", "label", "category", "list_price"}


@pytest.mark.parametrize("format", ["jsonschema", "owl", "shacl"])
def test_exports_parse(client, source, format):
    response = client.post(f"/api/models/export/{format}", json={"source": source})
    assert response.status_code == 200
    content = response.json()["content"]
    if format == "jsonschema":
        assert "$defs" in json.loads(content)
    else:
        assert len(Graph().parse(data=content, format="turtle")) > 0
