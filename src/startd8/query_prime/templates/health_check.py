"""Health check query templates — REQ-QP-202.

Templates for all 5 databases x 3 primary languages.
Each includes proper error handling, bool return, no credential logging.
"""

from __future__ import annotations

from ..models import DatabaseType, OperationType, QueryWorkItem
from . import register_template


# ---------------------------------------------------------------------------
# PostgreSQL / AlloyDB
# ---------------------------------------------------------------------------

def _pg_health_csharp(wi: QueryWorkItem) -> str:
    return '''\
public async Task<bool> CheckHealthAsync(NpgsqlDataSource dataSource)
{
    try
    {
        await using var conn = await dataSource.OpenConnectionAsync();
        await using var cmd = new NpgsqlCommand("SELECT 1", conn);
        await cmd.ExecuteScalarAsync();
        return true;
    }
    catch (Exception)
    {
        return false;
    }
}'''

def _pg_health_python(wi: QueryWorkItem) -> str:
    return '''\
def check_health(conn) -> bool:
    """Check database connectivity."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:
        return False'''

def _pg_health_nodejs(wi: QueryWorkItem) -> str:
    return '''\
async function checkHealth(pool) {
    try {
        await pool.query("SELECT 1");
        return true;
    } catch (error) {
        return false;
    }
}'''

register_template(DatabaseType.POSTGRESQL, "csharp", OperationType.HEALTH_CHECK, _pg_health_csharp)
register_template(DatabaseType.POSTGRESQL, "python", OperationType.HEALTH_CHECK, _pg_health_python)
register_template(DatabaseType.POSTGRESQL, "nodejs", OperationType.HEALTH_CHECK, _pg_health_nodejs)

# ---------------------------------------------------------------------------
# Cloud Spanner
# ---------------------------------------------------------------------------

def _spanner_health_csharp(wi: QueryWorkItem) -> str:
    return '''\
public async Task<bool> CheckHealthAsync(string connectionString)
{
    try
    {
        await using var conn = new SpannerConnection(connectionString);
        await conn.OpenAsync();
        return true;
    }
    catch (Exception)
    {
        return false;
    }
}'''

def _spanner_health_python(wi: QueryWorkItem) -> str:
    return '''\
def check_health(client, instance_id: str, database_id: str) -> bool:
    """Check Spanner database connectivity."""
    try:
        database = client.instance(instance_id).database(database_id)
        with database.snapshot() as snapshot:
            snapshot.execute_sql("SELECT 1")
        return True
    except Exception:
        return False'''

def _spanner_health_nodejs(wi: QueryWorkItem) -> str:
    return '''\
async function checkHealth(database) {
    try {
        const [rows] = await database.run("SELECT 1");
        return true;
    } catch (error) {
        return false;
    }
}'''

register_template(DatabaseType.SPANNER, "csharp", OperationType.HEALTH_CHECK, _spanner_health_csharp)
register_template(DatabaseType.SPANNER, "python", OperationType.HEALTH_CHECK, _spanner_health_python)
register_template(DatabaseType.SPANNER, "nodejs", OperationType.HEALTH_CHECK, _spanner_health_nodejs)

# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------

def _redis_health_csharp(wi: QueryWorkItem) -> str:
    return '''\
public bool CheckHealth(IConnectionMultiplexer redis)
{
    try
    {
        var db = redis.GetDatabase();
        var pong = db.Ping();
        return pong.TotalMilliseconds < 5000;
    }
    catch (Exception)
    {
        return false;
    }
}'''

def _redis_health_python(wi: QueryWorkItem) -> str:
    return '''\
def check_health(redis_client) -> bool:
    """Check Redis connectivity."""
    try:
        return redis_client.ping()
    except Exception:
        return False'''

def _redis_health_nodejs(wi: QueryWorkItem) -> str:
    return '''\
async function checkHealth(redis) {
    try {
        const result = await redis.ping();
        return result === "PONG";
    } catch (error) {
        return false;
    }
}'''

register_template(DatabaseType.REDIS, "csharp", OperationType.HEALTH_CHECK, _redis_health_csharp)
register_template(DatabaseType.REDIS, "python", OperationType.HEALTH_CHECK, _redis_health_python)
register_template(DatabaseType.REDIS, "nodejs", OperationType.HEALTH_CHECK, _redis_health_nodejs)

# ---------------------------------------------------------------------------
# MySQL
# ---------------------------------------------------------------------------

def _mysql_health_csharp(wi: QueryWorkItem) -> str:
    return '''\
public async Task<bool> CheckHealthAsync(string connectionString)
{
    try
    {
        await using var conn = new MySqlConnection(connectionString);
        await conn.OpenAsync();
        await using var cmd = new MySqlCommand("SELECT 1", conn);
        await cmd.ExecuteScalarAsync();
        return true;
    }
    catch (Exception)
    {
        return false;
    }
}'''

def _mysql_health_python(wi: QueryWorkItem) -> str:
    return '''\
def check_health(conn) -> bool:
    """Check MySQL connectivity."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        return True
    except Exception:
        return False'''

def _mysql_health_nodejs(wi: QueryWorkItem) -> str:
    return '''\
async function checkHealth(pool) {
    try {
        await pool.query("SELECT 1");
        return true;
    } catch (error) {
        return false;
    }
}'''

register_template(DatabaseType.MYSQL, "csharp", OperationType.HEALTH_CHECK, _mysql_health_csharp)
register_template(DatabaseType.MYSQL, "python", OperationType.HEALTH_CHECK, _mysql_health_python)
register_template(DatabaseType.MYSQL, "nodejs", OperationType.HEALTH_CHECK, _mysql_health_nodejs)

# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------

def _sqlite_health_csharp(wi: QueryWorkItem) -> str:
    return '''\
public bool CheckHealth(string connectionString)
{
    try
    {
        using var conn = new SqliteConnection(connectionString);
        conn.Open();
        using var cmd = new SqliteCommand("SELECT 1", conn);
        cmd.ExecuteScalar();
        return true;
    }
    catch (Exception)
    {
        return false;
    }
}'''

def _sqlite_health_python(wi: QueryWorkItem) -> str:
    return '''\
def check_health(db_path: str) -> bool:
    """Check SQLite database connectivity."""
    import sqlite3
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False'''

def _sqlite_health_nodejs(wi: QueryWorkItem) -> str:
    return '''\
function checkHealth(dbPath) {
    try {
        const Database = require("better-sqlite3");
        const db = new Database(dbPath, { readonly: true });
        db.prepare("SELECT 1").get();
        db.close();
        return true;
    } catch (error) {
        return false;
    }
}'''

register_template(DatabaseType.SQLITE, "csharp", OperationType.HEALTH_CHECK, _sqlite_health_csharp)
register_template(DatabaseType.SQLITE, "python", OperationType.HEALTH_CHECK, _sqlite_health_python)
register_template(DatabaseType.SQLITE, "nodejs", OperationType.HEALTH_CHECK, _sqlite_health_nodejs)
