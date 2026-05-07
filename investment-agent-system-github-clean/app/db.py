import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import settings


def _sqlite_path_from_url(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///") or database_url == "sqlite:///:memory:":
        return None
    raw_path = database_url.replace("sqlite:///", "", 1)
    return Path(raw_path)


def _sqlite_url_for_path(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _probe_sqlite_path(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=PERSIST;")
        cursor.fetchone()
        cursor.execute("PRAGMA user_version;")
        cursor.fetchone()
    finally:
        connection.close()


def _resolve_database_url(database_url: str) -> str:
    sqlite_path = _sqlite_path_from_url(database_url)
    if sqlite_path is None:
        return database_url

    try:
        _probe_sqlite_path(sqlite_path)
        return database_url
    except sqlite3.Error:
        fallback_path = sqlite_path.with_name(
            f"{sqlite_path.stem}_runtime{sqlite_path.suffix or '.db'}"
        )
        _probe_sqlite_path(fallback_path)
        print(
            f"[WARN] Primary SQLite database is unavailable; "
            f"using fallback database at {fallback_path}"
        )
        return _sqlite_url_for_path(fallback_path)


resolved_database_url = _resolve_database_url(settings.database_url)
engine = create_engine(
    resolved_database_url,
    connect_args={"check_same_thread": False} if resolved_database_url.startswith("sqlite") else {},
)


@event.listens_for(engine, "connect")
def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    if not resolved_database_url.startswith("sqlite"):
        return

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=PERSIST;")
        cursor.fetchone()
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA temp_store=MEMORY;")
    finally:
        cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)
Base = declarative_base()


def get_session() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
