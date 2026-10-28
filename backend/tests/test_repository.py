from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal

import pytest

from app.repository import RevisionConflict, save_model
from app.sources import SOURCES, preview, preview_sql, serialize
from app.graph import products


class Cursor:
    def __init__(self, db):
        self.db = db
        self.sizes = {}
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def setinputsizes(self, **sizes): self.sizes = sizes
    def execute(self, sql, binds=None):
        self.db.calls.append((sql, binds or {}, dict(self.sizes)))
    def fetchone(self): return (self.db.revision,) if self.db.revision is not None else None
    def fetchall(self): return self.db.rows


class DB:
    def __init__(self, revision=1):
        self.revision = revision
        self.calls = []
        self.rows = []
        self.committed = False
        self.readonly = None
    @contextmanager
    def connection(self, *, readonly=True):
        self.readonly = readonly
        yield self
    def cursor(self): return Cursor(self)
    def commit(self): self.committed = True


def test_update_binds_and_clob_sizes_isolated():
    db = DB()
    result = save_model(db, 'source', 'title', '0' * 64, 'id', 1)
    lock, update, version = db.calls
    assert lock[1] == {'id': 'id'} and lock[2] == {}
    assert set(update[1]) == {'id', 'title', 'revision', 'source', 'digest'}
    assert set(version[1]) == {'id', 'revision', 'source', 'digest'}
    assert result['revision'] == 2 and db.committed
    assert db.readonly is False


def test_revision_conflict_no_writes():
    db = DB(revision=3)
    with pytest.raises(RevisionConflict):
        save_model(db, 'source', 'title', '0' * 64, 'id', 1)
    assert len(db.calls) == 1 and not db.committed


def test_create_revision_one():
    db = DB()
    result = save_model(db, 'source', 'title', '0' * 64, None, 0)
    assert len(result['id']) == 36 and result['revision'] == 1
    assert len(db.calls) == 2 and db.committed


def test_source_preview_bound_exact_binds():
    db = DB()
    db.rows = [(Decimal('13'), '足球', '类别', '子类', Decimal('899.99'))] * 3
    result = preview(db, 'PRODUCTS', 0, 2)
    assert db.readonly is True
    assert db.calls[0][1] == {'row_offset': 0, 'row_limit': 3}
    assert result['has_more'] and len(result['rows']) == 2
    assert result['rows'][0][4] == '899.99'


def test_no_user_sql_or_dedup():
    for name in SOURCES:
        sql = preview_sql(name).upper()
        assert sql.startswith('SELECT ') and ' FROM SH.' in sql
        assert 'DISTINCT' not in sql and 'GROUP BY' not in sql
    with pytest.raises(KeyError): preview_sql('SALES; DELETE FROM SH.SALES')


def test_serialization_preserves_edges():
    assert serialize(Decimal('123456789.01')) == '123456789.01'
    assert serialize(datetime(1, 1, 1)).startswith('0001-01-01')
    assert serialize(datetime(9999, 12, 31)).startswith('9999-12-31')


def test_graph_template_keeps_rdf_terms():
    db = DB()
    db.rows = [('https://example.test/1', '<https://example.test/1>', '产品', '"产品"')]
    result = products(db)
    assert result['mode'] == 'virtual-rdf'
    assert result['items'][0]['label_term'] == '"产品"'
    assert db.readonly is True
    assert 'PLUS_RDFT=T' in db.calls[0][0]
    assert 'LIMIT 10' in db.calls[0][0]
