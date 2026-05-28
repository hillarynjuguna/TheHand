import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH = DATA_DIR / "thehand.db"
JOB_ARTIFACTS_DIR = DATA_DIR / "jobs"
JOB_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

DB_LOCK = threading.Lock()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    with DB_LOCK, get_connection() as conn:
        yield conn
        conn.commit()


def row_to_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition};")
    except sqlite3.OperationalError:
        pass


def init_schema() -> bool:
    fts_enabled = False
    with transaction() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                source_type TEXT,
                source TEXT,
                filename TEXT,
                status TEXT,
                step TEXT,
                step_status TEXT,
                progress INTEGER,
                model TEXT,
                language TEXT,
                created_at TEXT,
                updated_at TEXT,
                transcript_text TEXT,
                transcript_srt TEXT,
                transcript_vtt TEXT,
                transcript_json TEXT,
                error TEXT,
                duration REAL
            );
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                chunk_index INTEGER,
                start_ts REAL,
                end_ts REAL,
                text TEXT,
                embedding_json TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(job_id) REFERENCES jobs(job_id)
            );
            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id TEXT PRIMARY KEY,
                job_id TEXT,
                artifact_type TEXT,
                title TEXT,
                content TEXT,
                metadata_json TEXT,
                embedding_json TEXT,
                generation_model TEXT,
                generation_status TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(job_id) REFERENCES jobs(job_id)
            );
            CREATE TABLE IF NOT EXISTS artifact_versions (
                version_id INTEGER PRIMARY KEY AUTOINCREMENT,
                artifact_id TEXT,
                version_number INTEGER,
                content TEXT,
                metadata_json TEXT,
                created_at TEXT,
                FOREIGN KEY(artifact_id) REFERENCES artifacts(artifact_id)
            );
            CREATE TABLE IF NOT EXISTS artifact_events (
                event_id TEXT PRIMARY KEY,
                artifact_id TEXT,
                job_id TEXT,
                event_type TEXT,
                status TEXT,
                detail_json TEXT,
                created_at TEXT,
                FOREIGN KEY(artifact_id) REFERENCES artifacts(artifact_id)
            );
            CREATE TABLE IF NOT EXISTS executions (
                execution_id TEXT PRIMARY KEY,
                work_type TEXT,
                entity_id TEXT,
                status TEXT,
                attempts INTEGER,
                max_attempts INTEGER,
                lease_id TEXT,
                heartbeat_at TEXT,
                queued_at TEXT,
                started_at TEXT,
                completed_at TEXT,
                updated_at TEXT,
                error TEXT,
                correlation_id TEXT,
                causation_id TEXT,
                payload_json TEXT
            );
            CREATE TABLE IF NOT EXISTS leases (
                lease_id TEXT PRIMARY KEY,
                execution_id TEXT,
                owner TEXT,
                acquired_at TEXT,
                heartbeat_at TEXT,
                expires_at TEXT,
                released_at TEXT,
                status TEXT
            );
            CREATE TABLE IF NOT EXISTS artifact_lineage (
                artifact_id TEXT PRIMARY KEY,
                job_id TEXT,
                artifact_type TEXT,
                upstream_type TEXT,
                upstream_id TEXT,
                upstream_hash TEXT,
                status TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS runtime_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                entity_id TEXT,
                entity_type TEXT,
                state_json TEXT,
                high_watermark_event_id TEXT,
                high_watermark_timestamp TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS job_registry (
                id TEXT PRIMARY KEY,
                status TEXT,
                created_at TEXT,
                updated_at TEXT,
                record_json TEXT,
                snapshot_json TEXT,
                terminal INTEGER
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_job_registry_status ON job_registry(status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_job_registry_updated_at ON job_registry(updated_at);")
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts USING fts5(job_id UNINDEXED, source, filename, status, model, language, transcript_text);"
            )
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(chunk_id UNINDEXED, job_id UNINDEXED, source, filename, text);"
            )
            fts_enabled = True
        except sqlite3.OperationalError:
            fts_enabled = False

        for column, definition in [
            ("depends_on", "TEXT"),
            ("input_hash", "TEXT"),
            ("generation_attempts", "INTEGER DEFAULT 0"),
            ("generation_error", "TEXT"),
            ("generation_started_at", "TEXT"),
            ("generation_completed_at", "TEXT"),
        ]:
            ensure_column(conn, "artifacts", column, definition)
    return fts_enabled
