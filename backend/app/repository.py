import uuid
import oracledb

from .database import Database


class RevisionConflict(Exception):
    pass


def list_models(db: Database):
    with db.connection() as conn, conn.cursor() as c:
        c.execute("select model_id, title, revision, updated_at from FO_MODELS order by updated_at desc fetch first 100 rows only")
        return [{"id": r[0], "title": r[1], "revision": r[2], "updated_at": r[3].isoformat()} for r in c]


def get_model(db: Database, model_id: str):
    with db.connection() as conn, conn.cursor() as c:
        c.execute("select title, revision, source_yaml, updated_at from FO_MODELS where model_id=:id", {"id": model_id})
        row = c.fetchone()
        if row is None:
            return None
        source = row[2].read() if hasattr(row[2], "read") else row[2]
        return {"id": model_id, "title": row[0], "revision": row[1], "source": source, "updated_at": row[3].isoformat()}


def save_model(db: Database, source: str, title: str, digest: str, model_id: str | None, expected_revision: int):
    creating = model_id is None
    model_id = model_id or str(uuid.uuid4())
    with db.connection(readonly=False) as conn:
        with conn.cursor() as c:
            if creating:
                if expected_revision != 0:
                    raise RevisionConflict()
                revision = 1
            else:
                c.execute("select revision from FO_MODELS where model_id=:id for update wait 3", {"id": model_id})
                row = c.fetchone()
                if row is None or row[0] != expected_revision:
                    raise RevisionConflict()
                revision = row[0] + 1
        # Separate cursor: CLOB input sizing must not leak into the preceding SELECT.
        with conn.cursor() as c:
            c.setinputsizes(source=oracledb.DB_TYPE_CLOB)
            binds = {"id": model_id, "title": title, "revision": revision, "source": source, "digest": digest}
            if creating:
                c.execute("insert into FO_MODELS(model_id,title,revision,source_yaml,source_sha256) "
                          "values(:id,:title,:revision,:source,:digest)", binds)
            else:
                c.execute("update FO_MODELS set title=:title, revision=:revision, source_yaml=:source, "
                          "source_sha256=:digest, updated_at=systimestamp where model_id=:id", binds)
        with conn.cursor() as c:
            c.setinputsizes(source=oracledb.DB_TYPE_CLOB)
            c.execute("insert into FO_MODEL_VERSIONS(model_id,revision,source_yaml,source_sha256) "
                      "values(:id,:revision,:source,:digest)",
                      {"id": model_id, "revision": revision, "source": source, "digest": digest})
        conn.commit()
    return {"id": model_id, "title": title, "revision": revision, "sha256": digest}
