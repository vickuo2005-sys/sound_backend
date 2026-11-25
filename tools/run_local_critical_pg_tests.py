"""Run PostgreSQL-specific correctness tests on a disposable loopback cluster.
Uses an existing official PostgreSQL 17 installation; never accesses cloud DSNs.
"""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
BIN=Path("C:/Program Files/PostgreSQL/17/bin")


def main():
    if not (BIN/"initdb.exe").exists():
        print("Existing PostgreSQL 17 binaries unavailable")
        return 2
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0)); port=sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="critical-pg-") as directory:
        base=Path(directory).resolve()
        assert base.is_relative_to(Path(tempfile.gettempdir()).resolve())
        data=base/"data"; pw=base/"password.txt"
        password=secrets.token_urlsafe(32)
        pw.write_text(password,encoding="utf-8")
        flags=getattr(subprocess,"CREATE_NO_WINDOW",0)
        initialized=subprocess.run([str(BIN/"initdb.exe"),"-D",str(data),"-U","critical_test",
            "--pwfile",str(pw),"--auth-host=scram-sha-256","--auth-local=scram-sha-256",
            "--encoding=UTF8","--no-locale"],capture_output=True,creationflags=flags)
        if initialized.returncode:
            print("Local PostgreSQL init failed; cloud environments were not used")
            return 2
        started=False
        try:
            start=subprocess.run([str(BIN/"pg_ctl.exe"),"-D",str(data),"-l",str(base/"server.log"),
                "-o",f"-h 127.0.0.1 -p {port}","-w","start"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
            if start.returncode:
                print("Local PostgreSQL start failed; cloud environments were not used")
                return 2
            started=True
            env=os.environ.copy()
            env.pop("DATABASE_URL",None)
            env['CRITICAL_PATH_TEST_PG_DSN']=f"host=127.0.0.1 port={port} dbname=postgres user=critical_test password={password} sslmode=disable"
            result=subprocess.run([sys.executable,"-m","pytest","-q","tests/test_critical_path_optimization.py","--junitxml",str(base/"results.xml")],
                cwd=ROOT,env=env,creationflags=flags)
            suites=list(ET.parse(base/'results.xml').getroot().iter('testsuite'))
            counts={k:sum(int(suite.attrib.get(k,0)) for suite in suites) for k in ('tests','failures','errors','skipped')}
            counts['passed']=counts['tests']-counts['failures']-counts['errors']-counts['skipped']
            print(json.dumps(counts),flush=True)
            (ROOT/'outputs/critical_path_postgres_tests.json').write_text(json.dumps({
                "environment":"DISPOSABLE_LOCAL_POSTGRESQL_17_LOOPBACK",
                "exit_code":result.returncode,"counts":counts,"cloud_database_accessed":False,
                "command":"python -m pytest -q tests/test_critical_path_optimization.py"},indent=2),encoding='utf-8')
            return result.returncode
        finally:
            if started:
                stop=subprocess.run([str(BIN/"pg_ctl.exe"),"-D",str(data),"-m","fast","-w","stop"],
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
                if stop.returncode: raise RuntimeError("Disposable PostgreSQL stop failed; preserve data directory")


if __name__=="__main__":
    raise SystemExit(main())
