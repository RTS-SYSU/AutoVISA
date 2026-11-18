"""PostgreSQL holds immutable history; the object directory holds verified bytes."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from uuid import uuid4

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from .terms import Rejected, form


def encoded(value):
    """Serialize a value deterministically before hashing or publishing it.

    @param value JSON-serializable revision or manifest content.
    @return UTF-8 JSON bytes with sorted keys and compact separators.
    @raise TypeError If the value cannot be serialized as JSON.
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha(data):
    """Compute a content address from the exact bytes supplied.

    @param data Bytes to identify.
    @return Lowercase hexadecimal SHA-256 digest.
    """
    return hashlib.sha256(data).hexdigest()


class Objects:
    """Publish and retrieve immutable bytes by their SHA-256 content address.

    @ivar root Directory in which each published filename is its content digest.
    """
    def __init__(self, directory):
        """Open or create the directory holding content-addressed objects.

        @param directory Filesystem directory shared by writers and readers of the same ledger.
        """
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, data):
        """Publish bytes durably and verify an existing object at the same address.

        @param data Exact bytes to persist.
        @return SHA-256 address of the published object.
        @raise Rejected If an existing object has disappeared or its content differs.
        @raise OSError If the object or its directory entry cannot be written or flushed.
        """
        # key is both the digest and final filename; path is its durable directory entry.
        key = sha(data)
        path = self.root / key
        if path.exists():
            self.get(key)
            return key
        # tmp stays on the same filesystem so a hard link can atomically publish the flushed bytes.
        with NamedTemporaryFile(dir=self.root, delete=False) as tmp:
            try:
                tmp.write(data)
                tmp.flush()
                os.fsync(tmp.fileno())
                # A concurrent writer can publish only the same digest. Never overwrite it.
                try:
                    os.link(tmp.name, path)
                except FileExistsError:
                    self.get(key)
                # fd refers to the directory; flushing it makes the new filename durable after a crash.
                fd = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            finally:
                Path(tmp.name).unlink(missing_ok=True)
        return key

    def get(self, key):
        """Read and verify an object before returning its contents.

        @param key Expected lowercase 64-character SHA-256 address.
        @return Object bytes whose digest matches the requested address.
        @raise Rejected If the address is malformed or the object is missing or damaged.
        """
        if not isinstance(key, str) or not re.fullmatch("[0-9a-f]{64}", key):
            raise Rejected("artifact_mismatch", f"Invalid object address: {key!r}")
        try:
            data = (self.root / key).read_bytes()
        except FileNotFoundError:
            raise Rejected("missing_artifact", key) from None
        if sha(data) != key:
            raise Rejected("artifact_mismatch", key)
        return data


class Ledger:
    """Persist revision and attempt history on a PostgreSQL connection.

    @ivar objects Store for the large artifacts referenced by receipt manifests.
    @ivar db Connection returning dictionary-like rows in the W02 schema.
    @ivar reading True while rows() must reuse the active read snapshot.
    """
    def __init__(self, dsn, objects):
        """Open the artifact store and a dedicated database connection.

        @param dsn PostgreSQL connection string for the W02 database.
        @param objects Directory containing the ledger's content-addressed objects.
        @raise psycopg2.OperationalError If a database connection cannot be established.
        """
        self.objects = Objects(objects)
        self.reading = False
        self.db = psycopg2.connect(dsn, cursor_factory=RealDictCursor,
                                   options="-c search_path=autorta_w02,pg_catalog")

    def install(self):
        """Install the revision tables, indices and append-only triggers in one transaction.

        @raise psycopg2.Error If schema installation fails.
        """
        with self.db, self.db.cursor() as cur:
            cur.execute(Path(__file__).with_name("schema.sql").read_text())

    def close(self):
        """Release the PostgreSQL connection owned by this ledger."""
        self.db.close()

    @contextmanager
    def snapshot(self):
        """Keep all reads of one history response in a repeatable, read-only transaction.

        @yield None while queries on this ledger share the same database snapshot.
        """
        # One history response must not mix heads observed before and after a concurrent edit.
        with self.db, self.db.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            self.reading = True
            try:
                yield
            finally:
                self.reading = False

    def rows(self, sql, args=()):
        """Execute a parameterized query using the current snapshot or a fresh transaction.

        @param sql SQL statement producing rows, with psycopg2 parameter placeholders.
        @param args Bound SQL parameter values in placeholder order.
        @return List of plain dictionaries keyed by result column name.
        @raise psycopg2.Error If the query or its transaction fails.
        """
        def fetch():
            """Fetch the enclosing query's rows on this connection using a short-lived cursor.

            @return List of column-to-value mappings before the cursor closes.
            """
            with self.db.cursor() as cur:
                cur.execute(sql, args)
                return [dict(row) for row in cur.fetchall()]
        if self.reading:
            return fetch()
        with self.db:
            return fetch()

    def revise(self, kind, name, body, parent=None, context=None):
        """Append a revision only if the supplied parent still owns the head.

        @param kind Revision family, either context or goal.
        @param name Logical name whose generation sequence will advance.
        @param body JSON payload containing the hypotheses or target proposition.
        @param parent Expected current revision ID, or None to create the first generation.
        @param context Frozen context revision ID for a goal, or None for a context.
        @return Content-derived revision ID covering kind, name, lineage, context and body.
        @raise Rejected If the body, context or expected parent fails validation.
        @raise ValueError If kind is outside the supported revision families.
        """
        if kind == "goal":
            form(body["proposition"])
            if self.revision(context)["kind"] != "context":
                raise Rejected("context_mismatch", str(context))
        elif kind == "context":
            if context is not None or not isinstance(body["hypotheses"], list):
                raise Rejected("invalid_context", name)
            for prop in body["hypotheses"]:
                form(prop)
        else:
            raise ValueError(kind)
        # Serialize edits of a logical name, including the first edit (there is no row to lock).
        with self.db, self.db.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s),hashtext(%s))", (kind, name))
            cur.execute("SELECT id,generation FROM revisions WHERE kind=%s AND name=%s "
                        "ORDER BY generation DESC LIMIT 1", (kind, name))
            # old is the head observed under the per-name lock; None is valid only for a first revision.
            old = cur.fetchone()
            if (old["id"] if old else None) != parent:
                raise Rejected("revision_conflict", f"Head of {kind} {name} has changed")
            # generation orders edits of one name; key also incorporates the parent and semantic body.
            generation = old["generation"] + 1 if old else 1
            key = sha(encoded([kind, name, parent, context, body]))
            cur.execute("INSERT INTO revisions VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (key, kind, name, generation, parent, context, Json(body)))
        return key

    def revision(self, key):
        """Look up an immutable context or goal revision by identity.

        @param key Exact revision ID.
        @return Revision row including its logical name, generation, parent, context and body.
        @raise Rejected If the revision does not exist.
        """
        rows = self.rows("SELECT * FROM revisions WHERE id=%s", (key,))
        if not rows:
            raise Rejected("unknown_revision", str(key))
        return rows[0]

    def current(self, key):
        """Resolve the latest head in the same revision family as the supplied revision.

        @param key Revision ID identifying the family by its kind and logical name.
        @return ID of the revision with the highest generation in that family.
        @raise Rejected If the supplied revision does not exist.
        """
        rev = self.revision(key)
        return self.rows("SELECT id FROM revisions WHERE kind=%s AND name=%s "
                         "ORDER BY generation DESC LIMIT 1", (rev["kind"], rev["name"]))[0]["id"]

    def start(self, target, request):
        """Record a proof request before its checker starts.

        @param target Exact goal revision ID.
        @param request Structured proof submission or application, including its inputs.
        @return Fresh hexadecimal attempt ID.
        @raise Rejected If the target is missing or is not a goal revision.
        """
        if self.revision(target)["kind"] != "goal":
            raise Rejected("invalid_target", target)
        # Each submission gets a new attempt ID, even if its inputs exactly match an earlier attempt.
        attempt = uuid4().hex
        with self.db, self.db.cursor() as cur:
            cur.execute("INSERT INTO attempts(id,target,request) VALUES (%s,%s,%s)",
                        (attempt, target, Json(request)))
        return attempt

    def finish(self, attempt, code, detail, manifest, dependencies=()):
        """Commit the outcome and its ordered dependency edges in one transaction.

        @param attempt Previously registered attempt ID.
        @param code Accepted outcome or machine-readable rejection code.
        @param detail Human-readable explanation of the result.
        @param manifest Artifact and diagnostic manifest published before the database commit.
        @param dependencies Ordered input attempt IDs, starting with the conditional rule for applications.
        @raise Rejected If an existing manifest object fails integrity checks.
        @raise psycopg2.Error If the outcome or a referenced dependency violates a database constraint.
        """
        # Files are durable before the transaction makes a receipt and its ordered inputs visible.
        # key is the manifest address stored with this outcome; pos preserves each input's argument slot.
        key = self.objects.put(encoded(manifest))
        with self.db, self.db.cursor() as cur:
            cur.execute("INSERT INTO outcomes(attempt,code,detail,manifest) VALUES (%s,%s,%s,%s)",
                        (attempt, code, detail, key))
            for pos, dep in enumerate(dependencies):
                cur.execute("INSERT INTO receipt_inputs VALUES (%s,%s,%s)", (attempt, pos, dep))

    def attempt(self, key):
        """Fetch a registered attempt together with any outcome recorded so far.

        @param key Attempt ID from start(), prove() or compose().
        @return Joined row whose outcome fields are null while the attempt has no result.
        @raise Rejected If no attempt exists under this ID.
        """
        rows = self.rows("SELECT a.*,o.code,o.detail,o.manifest FROM attempts a "
                         "LEFT JOIN outcomes o ON o.attempt=a.id WHERE a.id=%s", (key,))
        if not rows:
            raise Rejected("unknown_attempt", str(key))
        return rows[0]

    def manifest(self, attempt, verify=False):
        """Read the receipt manifest and optionally verify all its artifact references.

        @param attempt Row with an outcome and a manifest object address.
        @param verify When true, read and hash every distinct object in the files mapping.
        @return Decoded manifest, including artifacts and recorded commands.
        @raise Rejected If the manifest or an object selected for verification fails integrity checks.
        """
        # m maps logical filenames to object digests, so shared objects need only one integrity read.
        m = json.loads(self.objects.get(attempt["manifest"]))
        if verify:
            # Logs, generated sources and compiled dependencies are all part of this receipt.
            for key in set(m["files"].values()):
                self.objects.get(key)
        return m

