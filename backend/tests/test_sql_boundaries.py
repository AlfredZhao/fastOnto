import re
from app.config import ROOT


def test_migrations_do_not_mutate_sh():
    for file in (ROOT / 'db/migrations').glob('*.sql'):
        text = file.read_text().upper()
        assert "SESSION_USER" in text and "'FASTONTO'" in text
        assert not re.search(r'(INSERT\s+INTO|UPDATE|DELETE\s+FROM|ALTER\s+TABLE|CREATE\s+TABLE|DROP\s+TABLE|TRUNCATE\s+TABLE)\s+SH\.', text)
        assert 'CREATE MATERIALIZED VIEW' not in text


def test_network_explicitly_schema_private():
    text = (ROOT / 'db/migrations/002_virtual_rdf.sql').read_text()
    assert "network_owner=>'FASTONTO'" in text
    assert "network_name=>'FO_NET'" in text
    assert "CREATE_RDFVIEW_GRAPH" in text
    assert "CREATE_RDF_GRAPH(" not in text
