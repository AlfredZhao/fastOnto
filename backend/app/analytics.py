"""Controlled SH analytics: fixed, versioned metric templates; never user or LLM supplied SQL."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal
import re
from typing import Callable
import json

from .database import Database


class AnalyticsError(ValueError):
    pass


@dataclass(frozen=True)
class MetricTemplate:
    code: str
    title: str
    scenario: str
    measure: str
    allowed_dimensions: tuple[str, ...]
    definition: str


METRICS = {
    "sales_amount": MetricTemplate("sales_amount", "销售额", "sales_overview", "SUM(s.amount_sold)",
                                   ("month", "product", "category", "customer", "channel", "promotion"),
                                   "销售额（人民币） = SH.SALES.AMOUNT_SOLD 的求和；本 MVP 按人民币口径展示。"),
    "quantity_sold": MetricTemplate("quantity_sold", "销售数量", "sales_overview", "SUM(s.quantity_sold)",
                                     ("month", "product", "category", "customer", "channel", "promotion"),
                                     "销售数量 = SH.SALES.QUANTITY_SOLD 的求和。"),
}

SCENARIOS = (
    {"code": "sales_overview", "title": "销售总览", "description": "在受控时间范围内查看销售额与销售数量。", "metrics": ["sales_amount", "quantity_sold"],
     "questions": ["本月销售额和销量是多少？", "销售额是多少？"]},
    {"code": "sales_trend", "title": "销售趋势", "description": "按月查看销售额或销量变化。", "metrics": ["sales_amount", "quantity_sold"],
     "questions": ["每月销售额趋势怎样？"]},
    {"code": "product_performance", "title": "商品经营", "description": "按商品或品类查看销售表现与排名。", "metrics": ["sales_amount", "quantity_sold"],
     "questions": ["销售额最高的10个商品是什么？", "各品类销售额排名怎样？"]},
    {"code": "customer_contribution", "title": "客户贡献", "description": "按客户查看销售贡献与排名。", "metrics": ["sales_amount", "quantity_sold"],
     "questions": ["销售额最高的10个客户是什么？"]},
    {"code": "channel_promotion", "title": "渠道与促销", "description": "按渠道或促销活动查看销售表现。", "metrics": ["sales_amount", "quantity_sold"],
     "questions": ["各渠道销售额是多少？", "促销活动销售额排名怎样？"]},
)

DIMENSIONS = {
    "month": ("月份", "t.calendar_year || '-' || lpad(t.calendar_month_number, 2, '0')", "join SH.TIMES t on t.time_id=s.time_id", "t.calendar_year, t.calendar_month_number", "month"),
    "product": ("商品", "p.prod_name", "join SH.PRODUCTS p on p.prod_id=s.prod_id", "p.prod_name", "product"),
    "category": ("产品类别", "p.prod_category", "join SH.PRODUCTS p on p.prod_id=s.prod_id", "p.prod_category", "category"),
    "customer": ("客户", "c.cust_last_name || c.cust_first_name", "join SH.CUSTOMERS c on c.cust_id=s.cust_id", "c.cust_last_name, c.cust_first_name", "customer"),
    "channel": ("渠道", "ch.channel_desc", "join SH.CHANNELS ch on ch.channel_id=s.channel_id", "ch.channel_desc", "channel"),
    "promotion": ("促销活动", "pr.promo_name", "join SH.PROMOTIONS pr on pr.promo_id=s.promo_id", "pr.promo_name", "promotion"),
}

# The SH sample schema keeps dates in SALES.TIME_ID and joins to TIMES for calendar dimensions.
_YEAR = re.compile(r"^(19|20)\d{2}$")
PERIODS = {"CURRENT_WEEK", "CURRENT_MONTH", "CURRENT_QUARTER", "CURRENT_YEAR", "PREVIOUS_WEEK", "PREVIOUS_MONTH", "PREVIOUS_QUARTER", "PREVIOUS_YEAR"}


def default_presentations():
    return {"customer": {"order": "LAST_FIRST", "separator": ""}}


def _presentation(value):
    default = default_presentations()["customer"]
    if not isinstance(value, dict): return default
    order, separator = value.get("order"), value.get("separator")
    if order not in {"LAST_FIRST", "FIRST_LAST"} or not isinstance(separator, str) or len(separator) > 10 or any(ord(ch) < 32 for ch in separator):
        return default
    return {"order": order, "separator": separator}


def presentations(db: Database):
    values = default_presentations()
    with db.connection() as conn, conn.cursor() as cursor:
        cursor.execute("select dimension_code,definition_json from FO_ANALYTIC_PRESENTATIONS")
        for code, definition in cursor:
            if code == "customer":
                try: values["customer"] = _presentation(json.loads(definition.read() if hasattr(definition, "read") else definition))
                except (ValueError, TypeError): pass
    return values


def save_presentation(db: Database, dimension: str, definition: dict):
    if dimension != "customer": raise AnalyticsError("当前 MVP 仅支持配置客户名称展示规则。")
    value = _presentation(definition)
    if value == default_presentations()["customer"] and definition != value:
        raise AnalyticsError("展示规则不合法；姓名顺序仅支持姓-名或名-姓，分隔符最多 10 个可见字符。")
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    with db.connection(readonly=False) as conn, conn.cursor() as cursor:
        cursor.execute("merge into FO_ANALYTIC_PRESENTATIONS target using (select :dimension as dimension_code,:definition as definition_json from dual) source on (target.dimension_code=source.dimension_code) when matched then update set target.definition_json=source.definition_json,target.updated_at=systimestamp when not matched then insert(dimension_code,definition_json) values(source.dimension_code,source.definition_json)", {"dimension": dimension, "definition": payload})
        conn.commit()
    return {"dimension": dimension, **value}


def metric_catalog():
    return [{"code": item.code, "title": item.title, "scenario": item.scenario,
             "allowed_dimensions": list(item.allowed_dimensions), "definition": item.definition,
             "template_version": "sh_sales_v1"} for item in METRICS.values()]


def scenario_catalog():
    return list(SCENARIOS)


def _serialize(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def period_from_selector(selector: str | None, *, now: datetime | None = None):
    if selector is None: return None
    if selector not in PERIODS: raise AnalyticsError("不支持的时间范围。")
    today = (now or datetime.now(ZoneInfo("Asia/Shanghai"))).date()
    if selector.endswith("WEEK"):
        start = today - timedelta(days=today.weekday())
        if selector == "PREVIOUS_WEEK": start -= timedelta(days=7)
        end = start + timedelta(days=7)
    elif selector.endswith("MONTH"):
        start = today.replace(day=1)
        if selector == "PREVIOUS_MONTH": start = (start - timedelta(days=1)).replace(day=1)
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    elif selector.endswith("QUARTER"):
        month = ((today.month - 1) // 3) * 3 + 1
        start = today.replace(month=month, day=1)
        if selector == "PREVIOUS_QUARTER":
            start = (start - timedelta(days=1)).replace(day=1)
            start = start.replace(month=((start.month - 1) // 3) * 3 + 1)
        end = start.replace(year=start.year + 1, month=1) if start.month == 10 else start.replace(month=start.month + 3)
    else:
        start = today.replace(month=1, day=1)
        if selector == "PREVIOUS_YEAR": start = start.replace(year=start.year - 1)
        end = start.replace(year=start.year + 1)
    labels = {"CURRENT_WEEK": "本周", "CURRENT_MONTH": "本月", "CURRENT_QUARTER": "本季度", "CURRENT_YEAR": "本年", "PREVIOUS_WEEK": "上周", "PREVIOUS_MONTH": "上月", "PREVIOUS_QUARTER": "上季度", "PREVIOUS_YEAR": "上年"}
    return {"kind": selector, "label": labels[selector], "start": start.isoformat(), "end": end.isoformat(), "timezone": "Asia/Shanghai"}


def period_from_year(year: str):
    if not _YEAR.fullmatch(year): raise AnalyticsError("年份必须是 1900 至 2099 的四位数。")
    value = int(year)
    return {"kind": "CALENDAR_YEAR", "label": f"{value}年", "start": date(value, 1, 1).isoformat(), "end": date(value + 1, 1, 1).isoformat(), "timezone": "Asia/Shanghai"}


def _period_from_question(text: str, *, now: datetime | None = None):
    year_match = re.search(r"\b((?:19|20)\d{2})\s*年", text)
    if year_match: return period_from_year(year_match.group(1))
    if "本月" in text: return period_from_selector("CURRENT_MONTH", now=now)
    if "上月" in text: return period_from_selector("PREVIOUS_MONTH", now=now)
    if "本周" in text: return period_from_selector("CURRENT_WEEK", now=now)
    if "上周" in text: return period_from_selector("PREVIOUS_WEEK", now=now)
    if "本季度" in text: return period_from_selector("CURRENT_QUARTER", now=now)
    if "上季度" in text: return period_from_selector("PREVIOUS_QUARTER", now=now)
    if "本年" in text or "今年" in text: return period_from_selector("CURRENT_YEAR", now=now)
    if "上年" in text or "去年" in text: return period_from_selector("PREVIOUS_YEAR", now=now)
    return None


def _query_spec(metric_code: str, dimension: str | None, year: str | None, limit: int):
    metric = METRICS.get(metric_code)
    if metric is None:
        raise AnalyticsError("未配置该指标；不会执行查询。")
    if dimension is not None and dimension not in metric.allowed_dimensions:
        raise AnalyticsError("该指标不支持所选分析维度；不会执行查询。")
    if year is not None and not _YEAR.fullmatch(year):
        raise AnalyticsError("年份必须为四位数，且限定在 1900 至 2099。")
    if not 1 <= limit <= 100:
        raise AnalyticsError("返回条数必须在 1 至 100 之间。")
    return metric


def execute(db: Database, metric_code: str, *, dimension: str | None = None, year: str | None = None, period: dict | None = None, limit: int = 20, mode: str = "governed", presentations: dict | None = None):
    """Run one reviewed aggregate only. Identifiers originate only from local registries."""
    if mode not in {"governed", "explore"}: raise AnalyticsError("不支持的查询模式。")
    if period is not None and year is not None: raise AnalyticsError("年份和时间范围不能同时指定。")
    if year is not None: period = period_from_year(year)
    if period is not None and (not isinstance(period, dict) or set(period) != {"kind", "label", "start", "end", "timezone"}): raise AnalyticsError("时间范围格式无效。")
    metric = _query_spec(metric_code, dimension, None, limit)
    joins, select_dimension, group_by, order_by = "", "", "", "metric_value desc"
    columns: list[str] = []
    presentations = presentations or default_presentations()
    if dimension:
        label, select_expr, join, group_expr, field = DIMENSIONS[dimension]
        if dimension == "customer":
            rule = presentations["customer"]
            select_expr = ("c.cust_last_name || :customer_separator || c.cust_first_name"
                           if rule["order"] == "LAST_FIRST" else "c.cust_first_name || :customer_separator || c.cust_last_name")
        joins, select_dimension, group_by = f" {join}", f"{select_expr} as dimension_value, ", f" group by {group_expr}"
        columns.append(label)
        order_by = "dimension_value" if dimension == "month" else "metric_value desc, dimension_value"
    where = ""
    binds: dict[str, object] = {"row_limit": limit}
    if dimension == "customer": binds["customer_separator"] = presentations["customer"]["separator"]
    if period:
        where = " where s.time_id >= :period_start and s.time_id < :period_end"
        binds["period_start"] = date.fromisoformat(period["start"])
        binds["period_end"] = date.fromisoformat(period["end"])
    sql = (f"select {select_dimension}{metric.measure} as metric_value from SH.SALES s{joins}{where}{group_by} "
           f"order by {order_by} fetch first :row_limit rows only")
    with db.connection() as conn, conn.cursor() as cursor:
        cursor.execute(sql, binds)
        rows = cursor.fetchall()
    columns.append(metric.title)
    return {
        "scenario": _scenario_for(metric.code, dimension), "metric": {"code": metric.code, "title": metric.title,
        "definition": metric.definition, "template_id": "sh_sales_v1", "template_version": 1},
        "parameters": {"dimension": dimension, "period": period, "limit": limit}, "columns": columns,
        "rows": [[_serialize(value) for value in row] for row in rows],
        "lineage": {"source": "SH", "tables": _tables_for(dimension), "mode": "governed-metric" if mode == "governed" else "bounded-exploration",
                    "notice": "固定指标模板执行；未复制 SH 业务行。结果反映查询时源数据，不是历史快照。" if mode == "governed" else "探索模式只允许服务端审阅过的 SH 聚合模板；这不是已发布业务指标口径，不能替代正式报表。"},
    }


def _tables_for(dimension: str | None):
    tables = ["SH.SALES"]
    if dimension == "month": tables.append("SH.TIMES")
    elif dimension == "product" or dimension == "category": tables.append("SH.PRODUCTS")
    elif dimension == "customer": tables.append("SH.CUSTOMERS")
    elif dimension == "channel": tables.append("SH.CHANNELS")
    elif dimension == "promotion": tables.append("SH.PROMOTIONS")
    return tables


def _scenario_for(metric_code: str, dimension: str | None):
    if dimension == "month": return "sales_trend"
    if dimension in {"product", "category"}: return "product_performance"
    if dimension == "customer": return "customer_contribution"
    if dimension in {"channel", "promotion"}: return "channel_promotion"
    return "sales_overview"


def execute_many(db: Database, metric_codes: list[str], *, dimension=None, period=None, limit=20, mode="governed", presentations=None):
    if not isinstance(metric_codes, list) or not 1 <= len(metric_codes) <= 2 or len(set(metric_codes)) != len(metric_codes):
        raise AnalyticsError("一次最多执行两个不同的已发布指标。")
    return [execute(db, code, dimension=dimension, period=period, limit=limit, mode=mode, presentations=presentations) for code in metric_codes]


def fallback_answers(results: list[dict]):
    return {"answer": f"已按固定口径返回 {len(results)} 个指标结果；可分别查看下方口径与追溯信息。", "highlights": []}


def fallback_answer(result: dict):
    count = len(result.get("rows") or [])
    metric = result.get("metric", {}).get("title", "指标")
    if not count: return {"answer": f"未查询到符合当前条件的{metric}结果。", "highlights": []}
    return {"answer": f"已按固定口径返回 {count} 条{metric}聚合结果；可查看下方口径与追溯信息。", "highlights": []}


def resolve_with_llm(db, settings, question: str, *, mode: str, classifier):
    """Use an injected bounded classifier, falling back to deterministic routing on unavailable LLM."""
    if sum(token in question for token in ("销售额", "销售金额", "营业额", "金额")) and sum(token in question for token in ("销量", "销售量", "数量", "件数")):
        return resolve_question(question)
    try:
        value = classifier(db, settings, question, mode=mode, catalog={"metrics": metric_catalog(), "scenarios": scenario_catalog()})
        if "metric_codes" not in value and isinstance(value.get("metric_code"), str):
            value = {"metric_codes": [value["metric_code"]], "dimension": value.get("dimension"),
                     "period": period_from_year(value["year"]) if value.get("year") else None,
                     "limit": value.get("limit"), "resolution": value.get("resolution", "LLM 路由")}
        if not isinstance(value.get("metric_codes"), list) or not value.get("metric_codes"):
            raise AnalyticsError("LLM 路由未提供可执行指标。")
        return value
    except Exception:
        result = resolve_question(question)
        result["resolution"] = "规则路由兜底；LLM 未配置、不可用或未返回有效受限计划。"
        return result


def resolve_question(question: str):
    """Conservative non-LLM router for the initial MVP. Unknown requests never query SH."""
    if not isinstance(question, str) or not question.strip() or len(question) > 500:
        raise AnalyticsError("问题必须是 1 至 500 个字符。")
    text = question.strip()
    lowered = text.lower()
    has_amount = any(token in text for token in ("销售额", "销售金额", "营业额", "金额"))
    has_quantity = any(token in text for token in ("销量", "销售量", "数量", "件数"))
    if not has_amount and not has_quantity:
        raise AnalyticsError("未匹配到已发布指标。请明确询问销售额或销量，或选择“受限探索”。")
    metric_codes = (["sales_amount", "quantity_sold"] if has_amount and has_quantity
                    else ["quantity_sold"] if has_quantity else ["sales_amount"])
    candidates = (("month", ("月", "趋势")), ("product", ("商品", "产品")), ("category", ("品类", "类别")),
                  ("customer", ("客户",)), ("channel", ("渠道",)), ("promotion", ("促销", "活动")))
    matches = [name for name, keywords in candidates if any(keyword in text for keyword in keywords)]
    if len(matches) > 1:
        raise AnalyticsError("问题同时命中多个分析维度；请一次只选择商品、客户、渠道、促销、品类或月份之一。")
    period = _period_from_question(text)
    top_match = re.search(r"(?:top|TOP|前|最高的|最大的)\s*(\d{1,3})\s*个?", text)
    if "利润" in text or "毛利" in text or "成本" in text:
        raise AnalyticsError("当前已发布指标没有利润或成本口径；不会猜测或执行非受控查询。")
    return {"metric_codes": metric_codes, "dimension": matches[0] if matches else None,
            "period": period, "limit": int(top_match.group(1)) if top_match else 20,
            "resolution": "规则路由；未调用 LLM，也未生成 SQL。"}
