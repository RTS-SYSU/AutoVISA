"""Ephemeral PostgreSQL server for acceptance; the caller persists a portable dump."""

from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory


@contextmanager
def database():
    """Start a temporary PostgreSQL cluster accessible through a private Unix socket.

    @yield Pair of connection string and utility runner valid until the context exits.
    @raise RuntimeError If initialization, startup or shutdown reports a nonzero exit.
    @raise subprocess.TimeoutExpired If a database utility exceeds its time limit.
    """
    # bin_dir is selected by the launcher so clients and server come from the same installation.
    bin_dir = Path(os.environ["AUTORTA_PGBIN"])
    with TemporaryDirectory(prefix="autorta-pg-") as temp:
        # root owns the private socket and server log; data contains the disposable cluster files.
        root = Path(temp)
        data = root / "data"
        def run(name, *args):
            """Execute a utility from the same PostgreSQL installation as this cluster.

            @param name Utility basename, such as initdb, pg_ctl, pg_dump or pg_restore.
            @param args Positional command arguments, converted to strings for subprocess execution.
            @return Raw standard output bytes from the successful command.
            @raise RuntimeError If the utility fails, with the end of its output and available server log.
            @raise subprocess.TimeoutExpired If the command exceeds 90 seconds.
            """
            result = subprocess.run([str(bin_dir / name), *map(str, args)], capture_output=True, timeout=90)
            if result.returncode:
                # extra is the diagnostic tail of the server log, which may not exist during initialization.
                log = (root / "server.log")
                extra = log.read_text(errors="replace")[-1200:] if log.is_file() else ""
                raise RuntimeError((result.stderr + result.stdout).decode(errors="replace")[-1500:] + extra)
            return result.stdout

        run("initdb", "-D", data, "-L", os.environ["AUTORTA_PGSHARE"], "-A", "trust",
            "--no-locale", "-E", "UTF8")
        # Only this user's private Unix socket is reachable. No TCP port is opened.
        run("pg_ctl", "-D", data, "-l", root / "server.log", "-w", "start", "-o",
            f"-k {root} -c listen_addresses='' -c unix_socket_permissions=0700")
        # The host field points libpq to the private socket directory for this cluster.
        dsn = f"host={root} dbname=postgres"
        try:
            yield dsn, run
        finally:
            run("pg_ctl", "-D", data, "-m", "fast", "-w", "stop")

