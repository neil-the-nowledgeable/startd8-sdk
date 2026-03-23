"""Basic CRUD query templates with parameterized queries.

Single-table SELECT/INSERT/UPDATE/DELETE with proper parameter binding
per database+language combination. Focus is on the parameterization
pattern (the security-critical part), not business logic.
"""

from __future__ import annotations

from ..models import DatabaseType, OperationType, QueryWorkItem
from . import register_template


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _table_name(wi: QueryWorkItem) -> str:
    """Get the primary table name from a work item."""
    return wi.tables[0] if wi.tables else "items"


def _param_names(wi: QueryWorkItem) -> list[str]:
    """Get parameter names from a work item."""
    return [p.name for p in wi.parameters] if wi.parameters else ["id"]


# ---------------------------------------------------------------------------
# PostgreSQL — C# (Npgsql)
# ---------------------------------------------------------------------------

def _pg_select_csharp(wi: QueryWorkItem) -> str:
    table = _table_name(wi)
    params = _param_names(wi)
    param = params[0]
    return f'''\
public async Task<NpgsqlDataReader> Get{table.capitalize()}Async(
    NpgsqlDataSource dataSource, string {param})
{{
    await using var conn = await dataSource.OpenConnectionAsync();
    await using var cmd = new NpgsqlCommand(
        "SELECT * FROM {table} WHERE {param} = @{param}", conn);
    cmd.Parameters.AddWithValue("@{param}", {param});
    return await cmd.ExecuteReaderAsync();
}}'''

def _pg_insert_csharp(wi: QueryWorkItem) -> str:
    table = _table_name(wi)
    params = _param_names(wi)
    cols = ", ".join(params)
    at_params = ", ".join(f"@{p}" for p in params)
    add_lines = "\n    ".join(
        f'cmd.Parameters.AddWithValue("@{p}", {p});' for p in params
    )
    method_params = ", ".join(f"string {p}" for p in params)
    return f'''\
public async Task Insert{table.capitalize()}Async(
    NpgsqlDataSource dataSource, {method_params})
{{
    await using var conn = await dataSource.OpenConnectionAsync();
    await using var cmd = new NpgsqlCommand(
        "INSERT INTO {table} ({cols}) VALUES ({at_params})", conn);
    {add_lines}
    await cmd.ExecuteNonQueryAsync();
}}'''

def _pg_update_csharp(wi: QueryWorkItem) -> str:
    table = _table_name(wi)
    params = _param_names(wi)
    key = params[0]
    set_cols = ", ".join(f"{p} = @{p}" for p in params[1:]) if len(params) > 1 else f"{key} = @{key}"
    add_lines = "\n    ".join(
        f'cmd.Parameters.AddWithValue("@{p}", {p});' for p in params
    )
    method_params = ", ".join(f"string {p}" for p in params)
    return f'''\
public async Task Update{table.capitalize()}Async(
    NpgsqlDataSource dataSource, {method_params})
{{
    await using var conn = await dataSource.OpenConnectionAsync();
    await using var cmd = new NpgsqlCommand(
        "UPDATE {table} SET {set_cols} WHERE {key} = @{key}", conn);
    {add_lines}
    await cmd.ExecuteNonQueryAsync();
}}'''

def _pg_delete_csharp(wi: QueryWorkItem) -> str:
    table = _table_name(wi)
    params = _param_names(wi)
    param = params[0]
    return f'''\
public async Task Delete{table.capitalize()}Async(
    NpgsqlDataSource dataSource, string {param})
{{
    await using var conn = await dataSource.OpenConnectionAsync();
    await using var cmd = new NpgsqlCommand(
        "DELETE FROM {table} WHERE {param} = @{param}", conn);
    cmd.Parameters.AddWithValue("@{param}", {param});
    await cmd.ExecuteNonQueryAsync();
}}'''

def _pg_upsert_csharp(wi: QueryWorkItem) -> str:
    """INSERT...ON CONFLICT DO UPDATE (REQ-QPI-003)."""
    table = _table_name(wi)
    params = _param_names(wi)
    key = params[0]
    value_cols = params[1:] if len(params) > 1 else params
    col_list = ", ".join(params)
    val_list = ", ".join(f"@{p}" for p in params)
    set_clause = ", ".join(f"{p} = @{p}" for p in value_cols)
    add_lines = "\n    ".join(
        f'cmd.Parameters.AddWithValue("@{p}", {p});' for p in params
    )
    method_params = ", ".join(f"string {p}" for p in params)
    return f'''\
public async Task Upsert{table.capitalize()}Async(
    NpgsqlDataSource dataSource, {method_params})
{{
    await using var conn = await dataSource.OpenConnectionAsync();
    await using var cmd = new NpgsqlCommand(
        "INSERT INTO {table} ({col_list}) VALUES ({val_list}) "
        + "ON CONFLICT ({key}) DO UPDATE SET {set_clause}", conn);
    {add_lines}
    await cmd.ExecuteNonQueryAsync();
}}'''

register_template(DatabaseType.POSTGRESQL, "csharp", OperationType.SELECT, _pg_select_csharp)
register_template(DatabaseType.POSTGRESQL, "csharp", OperationType.INSERT, _pg_insert_csharp)
register_template(DatabaseType.POSTGRESQL, "csharp", OperationType.UPDATE, _pg_update_csharp)
register_template(DatabaseType.POSTGRESQL, "csharp", OperationType.DELETE, _pg_delete_csharp)
register_template(DatabaseType.POSTGRESQL, "csharp", OperationType.UPSERT, _pg_upsert_csharp)

# ---------------------------------------------------------------------------
# PostgreSQL — Python (psycopg2)
# ---------------------------------------------------------------------------

def _pg_select_python(wi: QueryWorkItem) -> str:
    table = _table_name(wi)
    params = _param_names(wi)
    param = params[0]
    return f'''\
def get_{table}(conn, {param}):
    """Fetch {table} by {param}."""
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM {table} WHERE {param} = %s", ({param},))
        return cur.fetchone()'''

def _pg_insert_python(wi: QueryWorkItem) -> str:
    table = _table_name(wi)
    params = _param_names(wi)
    placeholders = ", ".join(["%s"] * len(params))
    cols = ", ".join(params)
    args = ", ".join(params)
    method_params = ", ".join(params)
    return f'''\
def insert_{table}(conn, {method_params}):
    """Insert a row into {table}."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO {table} ({cols}) VALUES ({placeholders})",
            ({args},),
        )
    conn.commit()'''

def _pg_delete_python(wi: QueryWorkItem) -> str:
    table = _table_name(wi)
    params = _param_names(wi)
    param = params[0]
    return f'''\
def delete_{table}(conn, {param}):
    """Delete from {table} by {param}."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM {table} WHERE {param} = %s", ({param},))
    conn.commit()'''

register_template(DatabaseType.POSTGRESQL, "python", OperationType.SELECT, _pg_select_python)
register_template(DatabaseType.POSTGRESQL, "python", OperationType.INSERT, _pg_insert_python)
register_template(DatabaseType.POSTGRESQL, "python", OperationType.DELETE, _pg_delete_python)

# ---------------------------------------------------------------------------
# PostgreSQL — Node.js (pg)
# ---------------------------------------------------------------------------

def _pg_select_nodejs(wi: QueryWorkItem) -> str:
    table = _table_name(wi)
    params = _param_names(wi)
    param = params[0]
    return f'''\
async function get{table.capitalize()}(pool, {param}) {{
    const result = await pool.query(
        "SELECT * FROM {table} WHERE {param} = $1",
        [{param}]
    );
    return result.rows[0];
}}'''

def _pg_insert_nodejs(wi: QueryWorkItem) -> str:
    table = _table_name(wi)
    params = _param_names(wi)
    cols = ", ".join(params)
    placeholders = ", ".join(f"${i+1}" for i in range(len(params)))
    args = ", ".join(params)
    return f'''\
async function insert{table.capitalize()}(pool, {args}) {{
    await pool.query(
        "INSERT INTO {table} ({cols}) VALUES ({placeholders})",
        [{args}]
    );
}}'''

register_template(DatabaseType.POSTGRESQL, "nodejs", OperationType.SELECT, _pg_select_nodejs)
register_template(DatabaseType.POSTGRESQL, "nodejs", OperationType.INSERT, _pg_insert_nodejs)
