import pytest

from app.governance import GovernanceError, _code, _definition


def test_governance_code_is_bounded_identifier():
    assert _code('sales_core') == 'sales_core'
    with pytest.raises(GovernanceError): _code('sales-core')


@pytest.mark.parametrize('definition', [
    {'logical_source': 'PRODUCTS'},
    {'constraint': {'kind': 'required'}},
    {'dimensions': ['month', 'channel']},
])
def test_declarative_definitions_are_accepted(definition):
    assert _definition(definition)


@pytest.mark.parametrize('definition', [
    {'sql': 'select * from SH.PRODUCTS'},
    {'nested': {'sparql': 'SELECT * WHERE {?s ?p ?o}'}},
    {'steps': [{'script': 'rm -rf /'}]},
])
def test_executable_definition_fields_are_rejected(definition):
    with pytest.raises(GovernanceError): _definition(definition)
