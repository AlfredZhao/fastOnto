"""Single reviewed SPARQL template; not an arbitrary query endpoint."""
from .database import Database

PRODUCT_QUERY = """
select product, product$rdfterm, label, label$rdfterm
from table(SEM_MATCH(
  'SELECT ?product ?label WHERE {
     ?product a <https://fastonto.example/vocab/Product>;
       <https://fastonto.example/vocab/label> ?label
   } ORDER BY ?product LIMIT 10',
  SEM_MODELS('FO_SH_V1'), null,null,null,null,'PLUS_RDFT=T',null,null,'FASTONTO','FO_NET'))
"""


def products(db: Database):
    with db.connection() as conn, conn.cursor() as cursor:
        cursor.execute(PRODUCT_QUERY)
        rows = cursor.fetchall()
        def text(value):
            return value.read() if hasattr(value, "read") else value
        return {"graph": "FO_SH_V1", "mode": "virtual-rdf", "network": "FO_NET",
                "items": [dict(zip(("uri", "uri_term", "label", "label_term"), map(text, row))) for row in rows],
                "notice": "实时虚拟 RDF 查询；仅允许预设模板。term 字段保留 RDF 节点表示。"}
