import pytest

from app.governance import GovernanceError, validate_mapping_definition
from app.modeling import parse_model


@pytest.fixture
def report(source):
    return parse_model(source)[1]


def valid():
    return {"version": 1, "class": "Product", "subject": {"column": "PROD_ID", "iri_template": "https://example.test/product/{PROD_ID}"},
            "properties": [{"property": "label", "column": "PROD_NAME"}, {"property": "category", "column": "PROD_CATEGORY"}, {"property": "list_price", "column": "PROD_LIST_PRICE"}]}


def test_column_mapping_definition_is_accepted(report):
    result = validate_mapping_definition(valid(), 'PRODUCTS', report)
    assert result['class'] == 'Product'


@pytest.mark.parametrize('mutate', [
    lambda d: d.update(version=2),
    lambda d: d['subject'].update(column='NOPE'),
    lambda d: d['subject'].update(iri_template='https://example.test/product/id'),
    lambda d: d['properties'].append({'property': 'label', 'column': 'PROD_CATEGORY'}),
    lambda d: d['properties'].__setitem__(0, {'property': 'missing', 'column': 'PROD_NAME'}),
])
def test_mapping_definition_rejects_invalid_columns_or_terms(report, mutate):
    definition = valid(); mutate(definition)
    with pytest.raises(GovernanceError): validate_mapping_definition(definition, 'PRODUCTS', report)


def test_external_source_columns_can_be_validated_without_sh_catalog(report):
    result = validate_mapping_definition(valid(), None, report, source_columns=['PROD_ID', 'PROD_NAME', 'PROD_CATEGORY', 'PROD_LIST_PRICE'])
    assert result['source_columns'] == ['PROD_CATEGORY', 'PROD_ID', 'PROD_LIST_PRICE', 'PROD_NAME']
