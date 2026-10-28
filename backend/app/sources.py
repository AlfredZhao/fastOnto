from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from .database import Database


@dataclass(frozen=True)
class Source:
    title: str
    columns: tuple[str, ...]
    order_by: str
    identity: str


SOURCES = {
    "CUSTOMERS": Source("客户", ("CUST_ID", "CUST_FIRST_NAME", "CUST_LAST_NAME", "CUST_CITY", "COUNTRY_ID"), "CUST_ID", "CUST_ID"),
    "PRODUCTS": Source("产品", ("PROD_ID", "PROD_NAME", "PROD_CATEGORY", "PROD_SUBCATEGORY", "PROD_LIST_PRICE"), "PROD_ID", "PROD_ID"),
    "COUNTRIES": Source("国家", ("COUNTRY_ID", "COUNTRY_NAME", "COUNTRY_REGION"), "COUNTRY_ID", "COUNTRY_ID"),
    "CHANNELS": Source("渠道", ("CHANNEL_ID", "CHANNEL_DESC", "CHANNEL_CLASS"), "CHANNEL_ID", "CHANNEL_ID"),
    "PROMOTIONS": Source("促销", ("PROMO_ID", "PROMO_NAME", "PROMO_BEGIN_DATE", "PROMO_END_DATE"), "PROMO_ID", "PROMO_ID"),
    "TIMES": Source("时间", ("TIME_ID", "CALENDAR_YEAR", "CALENDAR_MONTH_DESC"), "TIME_ID", "TIME_ID"),
    "SALES": Source("销售记录", ("PROD_ID", "CUST_ID", "TIME_ID", "CHANNEL_ID", "PROMO_ID", "QUANTITY_SOLD", "AMOUNT_SOLD"), "TIME_ID, PROD_ID, CUST_ID, CHANNEL_ID, PROMO_ID, ROWID", "未定义永久身份；ROWID 仅用于当前页排序"),
    "COSTS": Source("成本", ("PROD_ID", "TIME_ID", "PROMO_ID", "CHANNEL_ID", "UNIT_COST", "UNIT_PRICE"), "TIME_ID, PROD_ID, PROMO_ID, CHANNEL_ID, ROWID", "业务组合键，未物化为 RDF"),
}


def source_catalog():
    return [{"name": name, "title": item.title, "owner": "SH", "readonly": True,
             "columns": list(item.columns), "identity": item.identity} for name, item in SOURCES.items()]


def serialize(value):
    if isinstance(value, Decimal):
        return str(value)  # Never lose currency precision in JSON floating point.
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def preview_sql(name: str):
    item = SOURCES[name]  # Names and columns MUST come from this fixed allowlist.
    return (f"select {', '.join(item.columns)} from SH.{name} order by {item.order_by} "
            "offset :row_offset rows fetch next :row_limit rows only")


def preview(db: Database, name: str, offset: int, limit: int):
    item = SOURCES[name]
    with db.connection() as conn, conn.cursor() as cursor:
        # Per-statement bind set; fetching one extra gives has_more without a full count.
        cursor.execute(preview_sql(name), {"row_offset": offset, "row_limit": limit + 1})
        rows = cursor.fetchall()
        return {"source": name, "columns": list(item.columns),
                "rows": [[serialize(v) for v in row] for row in rows[:limit]],
                "offset": offset, "limit": limit, "has_more": len(rows) > limit,
                "mode": "live-readonly", "notice": "直接查询 SH；不保存副本。跨页结果不保证同一业务快照。"}
