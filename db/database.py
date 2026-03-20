"""Database connection and initialization."""

import sqlite3
from pathlib import Path
from typing import Optional
from config import settings


class Database:
    """SQLite database manager."""
    
    def __init__(self, db_path: str = "bokfoering.db"):
        self.db_path = db_path
        self.connection: Optional[sqlite3.Connection] = None
    
    def connect(self) -> sqlite3.Connection:
        """Connect to database."""
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        # Enable foreign keys
        self.connection.execute("PRAGMA foreign_keys = ON")
        return self.connection
    
    def disconnect(self) -> None:
        """Disconnect from database."""
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute SQL query."""
        if not self.connection:
            self.connect()
        return self.connection.execute(sql, params)
    
    def executemany(self, sql: str, params_list: list) -> sqlite3.Cursor:
        """Execute multiple SQL queries."""
        if not self.connection:
            self.connect()
        return self.connection.executemany(sql, params_list)
    
    def commit(self) -> None:
        """Commit transaction."""
        if self.connection:
            self.connection.commit()
    
    def rollback(self) -> None:
        """Rollback transaction."""
        if self.connection:
            self.connection.rollback()
    
    def init_db(self) -> None:
        """Initialize database schema from migration files."""
        self.connect()
        
        # Get current schema version
        try:
            cursor = self.connection.execute("SELECT MAX(version) as v FROM schema_version")
            row = cursor.fetchone()
            current_version = row["v"] if row["v"] else 0
        except:
            current_version = 0
        
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
                    self.connection.execute(statement)
                
                self.commit()
        
        print(f"✓ Database initialized: {self.db_path}")


# Global database instance
db = Database(settings.database_url.replace("sqlite:///", ""))
