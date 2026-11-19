"""Minimal DB-API 2.0 style wrapper around the `psql` command line client.

Only used where psycopg2 is NOT installed (e.g. the sandbox this project was built in).
It exposes the same calls the notebook uses with psycopg2:
    conn = connect(dbname=...); cur = conn.cursor(); cur.execute(sql, params);
    cur.executemany(sql, rows); cur.fetchall(); cur.description; conn.commit(); conn.close()
Each execute() is its own transaction (autocommit); executemany() runs inside one BEGIN/COMMIT.
With psycopg2 installed the notebook never imports this file.
"""
import csv, io, os, shutil, subprocess


def _quote(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def _interpolate(sql, params):
    parts = sql.split("%s")
    if len(parts) - 1 != len(params):
        raise ValueError(f"{len(parts) - 1} placeholders but {len(params)} parameters")
    out = [parts[0]]
    for p, tail in zip(params, parts[1:]):
        out += [_quote(p), tail]
    return "".join(out)


class Cursor:
    def __init__(self, conn):
        self._conn, self._rows, self.description, self.rowcount = conn, [], None, -1

    def _load(self, stdout):
        rows = list(csv.reader(io.StringIO(stdout)))
        if rows:
            self.description = [(name, None, None, None, None, None, None) for name in rows[0]]
            self._rows = [tuple(None if x == "" else x for x in r) for r in rows[1:]]
        else:
            self.description, self._rows = None, []

    def execute(self, sql, params=None):
        if params is not None:
            sql = _interpolate(sql, params)
        self._load(self._conn._run(sql))
        return self

    def executemany(self, sql, seq_of_params):
        body = ";\n".join(_interpolate(sql, p) for p in seq_of_params)
        self._conn._run("BEGIN;\n" + body + ";\nCOMMIT;")
        self.description, self._rows = None, []

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self):
        pass


class Connection:
    def __init__(self, dbname):
        self.dbname = dbname
        psql = shutil.which("psql")
        self._cmd = ["psql", "-X", "-q", "--csv", "-v", "ON_ERROR_STOP=1", "-d", dbname, "-f", "-"]
        if os.geteuid() == 0:  # the sandbox runs as root; the Postgres role is `postgres`
            self._cmd = ["runuser", "-u", "postgres", "--"] + self._cmd
        assert psql, "psql not found"

    def _run(self, sql):
        p = subprocess.run(self._cmd, input=sql, capture_output=True, text=True, cwd="/")
        if p.returncode != 0:
            raise RuntimeError(p.stderr.strip())
        return p.stdout

    def cursor(self):
        return Cursor(self)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def connect(dbname, **_ignored):
    return Connection(dbname)
