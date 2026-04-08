"""Database connection and initialization.

Thread-safe SQLite database manager using thread-local connections.
Each thread gets its own connection, which is required for SQLite
with FastAPI/uvicorn (which may use multiple threads).
"""

import sqlite3
import os
import threading
from pathlib import Path
from contextlib import contextmanager
from config import settings


class Database:
    """Thread-safe SQLite database manager.

    Uses thread-local storage so each thread gets its own connection.
    This is required because SQLite connections cannot be shared across threads.
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = settings.database_url.replace("sqlite:///", "")
        self.db_path = db_path
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._local = threading.local()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        conn = getattr(self._local, 'connection', None)
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")  # Better concurrent read performance
            self._local.connection = conn
        return conn

    def connect(self) -> sqlite3.Connection:
        """Connect to database (returns thread-local connection)."""
        return self._get_connection()

    def disconnect(self) -> None:
        """Disconnect current thread's connection."""
        conn = getattr(self._local, 'connection', None)
        if conn is not None:
            conn.close()
            self._local.connection = None

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute SQL query."""
        return self._get_connection().execute(sql, params)

    def executemany(self, sql: str, params_list: list) -> sqlite3.Cursor:
        """Execute SQL for multiple parameter sets."""
        return self._get_connection().executemany(sql, params_list)

    def commit(self) -> None:
        """Commit current thread's transaction."""
        conn = getattr(self._local, 'connection', None)
        if conn is not None:
            conn.commit()

    def rollback(self) -> None:
        """Rollback current thread's transaction."""
        conn = getattr(self._local, 'connection', None)
        if conn is not None:
            conn.rollback()

    @contextmanager
    def transaction(self):
        """Context manager for database transactions.

        Usage:
            with db.transaction():
                db.execute("INSERT ...")
                db.execute("INSERT ...")
            # auto-commits on success, rolls back on exception
        """
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def init_db(self) -> None:
        """Initialize database schema from migration files."""
        conn = self._get_connection()

        # Create schema_version table if not exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # Get current schema version
        cursor = conn.execute("SELECT MAX(version) as v FROM schema_version")
        row = cursor.fetchone()
        current_version = row["v"] if row["v"] else 0

        # Apply migrations
        migrations_dir = Path(__file__).parent / "migrations"
        migration_files = sorted(migrations_dir.glob("*.sql"))

        for migration_file in migration_files:
            # Extract version from filename (e.g., 001_initial_schema.sql → 1)
            version = int(migration_file.name.split("_")[0])

            if version > current_version:
                print(f"  📝 Applying migration {version}: {migration_file.name}")
                with open(migration_file, "r") as f:
                    sql_script = f.read()

                # Split by semicolon and execute each statement
                statements = [s.strip() for s in sql_script.split(";") if s.strip()]
                for statement in statements:
                    conn.execute(statement)

                # Record migration version (migration file may have already inserted it)
                conn.execute(
                    "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
                    (version,)
                )
                conn.commit()

        print(f"✓ Database initialized: {self.db_path}")


# Global database instance
db = Database()


def get_db():
    """Get database connection for dependency injection.
    
    Usage:
        from db.database import get_db
        
        @router.get("/items")
        def list_items(db = Depends(get_db)):
            cursor = db.execute("SELECT * FROM items")
            return cursor.fetchall()
    """
    return db
