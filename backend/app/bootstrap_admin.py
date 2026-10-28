"""Explicit one-time bootstrap; never reset an existing account or print passwords."""
import os
import secrets
import uuid

from .auth import HASHER
from .config import ROOT, Settings
from .database import Database


def main():
    db = Database(Settings())
    created_file = False
    secret_file = ROOT / ".runtime" / "initial-admin.txt"
    try:
        with db.connection(readonly=False) as conn, conn.cursor() as c:
            c.execute("select count(*) from FO_USERS where username=:username",{"username":"admin"})
            if c.fetchone()[0]:
                print("admin already exists; password unchanged.")
                return
            secret_file.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            os.chmod(secret_file.parent,0o700)
            password = secrets.token_urlsafe(24)
            password_hash = HASHER.hash(password)
            user_id = str(uuid.uuid4())
            fd = os.open(secret_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            created_file = True
            with os.fdopen(fd,"w",encoding="utf-8") as f:
                f.write(f"Username: admin\nTemporary password: {password}\nFirst login must change password. Do not reuse it elsewhere.\n")
                f.flush()
                os.fsync(f.fileno())
            c.execute("insert into FO_USERS(user_id,username,password_hash,must_change_password) "
                      "values(:id,:username,:hash,1)",{"id":user_id,"username":"admin","hash":password_hash})
            conn.commit()
        print("admin initialized with Argon2id hash and forced password change.")
        print("Temporary credential file: .runtime/initial-admin.txt (mode 600). Password not printed.")
    except Exception:
        if created_file:
            # Keep the file on ambiguous commit failure so a committed account is recoverable.
            print("Bootstrap incomplete or commit status unknown; credential file retained locally. Recheck account before retry.")
        else:
            print("Bootstrap failed; check migration/configuration or an existing credential file. Details suppressed.")
        raise SystemExit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
