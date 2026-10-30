import pytest

from app import analytics


class Cursor:
    def __init__(self): self.sql = ''; self.binds = {}
    def execute(self, sql, binds): self.sql, self.binds = sql, binds
    def fetchall(self): return [('Road Bike', 1250)]
    def __enter__(self): return self
    def __exit__(self, *args): pass

class Connection:
    def __init__(self, cursor): self.value = cursor
    def cursor(self): return self.value
    def __enter__(self): return self
    def __exit__(self, *args): pass

class Database:
    def __init__(self): self.cursor_value = Cursor()
    def connection(self): return Connection(self.cursor_value)


def test_metric_execution_only_uses_reviewed_identifiers():
    db = Database()
    result = analytics.execute(db, 'sales_amount', dimension='product', year='2020', limit=10)
    assert result['columns'] == ['商品', '销售额']
    assert result['lineage']['tables'] == ['SH.SALES', 'SH.PRODUCTS']
    assert 'SH.SALES s join SH.PRODUCTS p' in db.cursor_value.sql
    assert db.cursor_value.binds == {'row_limit': 10, 'period_start': __import__('datetime').date(2020, 1, 1), 'period_end': __import__('datetime').date(2021, 1, 1)}
    assert '2020' not in db.cursor_value.sql

@pytest.mark.parametrize('question,dimension', [
    ('销售额最高的10个商品是什么？', 'product'),
    ('各渠道销量是多少？', 'channel'),
    ('2020年每月销售额趋势怎样？', 'month'),
])
def test_question_router_is_conservative(question, dimension):
    assert analytics.resolve_question(question)['dimension'] == dimension

@pytest.mark.parametrize('question', ['利润最高的产品是什么？', '按商品和客户分别看销售额'])
def test_question_router_refuses_undefined_or_ambiguous_questions(question):
    with pytest.raises(analytics.AnalyticsError): analytics.resolve_question(question)

@pytest.mark.parametrize('dimension', ['x; delete', 'cost'])
def test_query_rejects_unknown_dimensions(dimension):
    with pytest.raises(analytics.AnalyticsError): analytics.execute(Database(), 'sales_amount', dimension=dimension)


def test_chinese_top_count_and_customer_name_order():
    resolved = analytics.resolve_question('销售额最高的10个客户是什么？')
    assert resolved['dimension'] == 'customer'
    assert resolved['limit'] == 10
    db = Database()
    analytics.execute(db, 'sales_amount', dimension='customer')
    assert "c.cust_last_name || :customer_separator || c.cust_first_name" in db.cursor_value.sql
    assert db.cursor_value.binds["customer_separator"] == ""


def test_llm_resolution_is_bounded_and_falls_back_when_classifier_fails():
    def classifier(*args, **kwargs):
        assert kwargs['mode'] == 'governed'
        assert kwargs['catalog']['metrics'][0]['code'] == 'sales_amount'
        return {'metric_codes': ['quantity_sold'], 'dimension': 'channel', 'period': None, 'limit': 8, 'resolution': 'LLM'}
    value = analytics.resolve_with_llm(None, None, '各渠道销量前8名', mode='governed', classifier=classifier)
    assert value['metric_codes'] == ['quantity_sold'] and value['limit'] == 8
    def unavailable(*args, **kwargs): raise RuntimeError('offline')
    fallback = analytics.resolve_with_llm(None, None, '销售额最高的10个客户', mode='governed', classifier=unavailable)
    assert fallback['dimension'] == 'customer' and fallback['limit'] == 10


def test_exploration_is_visibly_not_a_governed_metric():
    db = Database()
    result = analytics.execute(db, 'sales_amount', dimension='product', mode='explore')
    assert result['lineage']['mode'] == 'bounded-exploration'
    assert '不是已发布业务指标' in result['lineage']['notice']


def test_customer_presentation_is_safely_bound_and_configurable():
    db = Database()
    result = analytics.execute(db, 'sales_amount', dimension='customer', presentations={'customer': {'order': 'FIRST_LAST', 'separator': ' '}})
    assert result['columns'][0] == '客户'
    assert 'c.cust_first_name || :customer_separator || c.cust_last_name' in db.cursor_value.sql
    assert db.cursor_value.binds['customer_separator'] == ' '
    with pytest.raises(analytics.AnalyticsError):
        analytics.save_presentation(None, 'product', {'order': 'LAST_FIRST', 'separator': ''})


def test_relative_period_is_normalized_to_absolute_dates():
    from datetime import datetime, date
    from zoneinfo import ZoneInfo
    value = analytics._period_from_question('本月销售额是多少？', now=datetime(2026, 10, 30, 9, 0, tzinfo=ZoneInfo('Asia/Shanghai')))
    assert value == {'kind': 'CURRENT_MONTH', 'label': '本月', 'start': '2026-10-01', 'end': '2026-11-01', 'timezone': 'Asia/Shanghai'}
    db = Database()
    analytics.execute(db, 'sales_amount', period=value)
    assert db.cursor_value.binds['period_start'] == date(2026, 10, 1)
    assert db.cursor_value.binds['period_end'] == date(2026, 11, 1)


def test_unknown_metric_question_refuses_instead_of_defaulting_to_sales_amount():
    with pytest.raises(analytics.AnalyticsError, match='未匹配到已发布指标'):
        analytics.resolve_question('表现最好的商品是什么？')


def test_two_metrics_share_one_resolved_period_without_widening_the_query():
    resolved = analytics.resolve_question('本月销售额和销量是多少？')
    assert resolved['metric_codes'] == ['sales_amount', 'quantity_sold']
    db = Database()
    values = analytics.execute_many(db, resolved['metric_codes'], period=resolved['period'])
    assert [item['metric']['code'] for item in values] == ['sales_amount', 'quantity_sold']
    assert values[0]['parameters']['period']['start'] == values[1]['parameters']['period']['start']


def test_month_trend_orders_chronologically_for_line_chart():
    db = Database()
    analytics.execute(db, 'sales_amount', dimension='month')
    assert 'order by dimension_value fetch first' in db.cursor_value.sql
