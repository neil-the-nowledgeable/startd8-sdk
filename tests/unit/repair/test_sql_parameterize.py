"""Tests for SQL parameterization repair step (REQ-KZ-CS-400)."""

from pathlib import Path

from startd8.repair.steps.sql_parameterize import SqlParameterizeStep, _parameterize_sql
from startd8.repair.models import RepairContext


class TestParameterizeSql:
    """Unit tests for the _parameterize_sql rewriting engine."""

    def test_single_line_select_with_quoted_vars(self):
        code = (
            '    selectCmd.CommandText =\n'
            '        $"SELECT quantity FROM {_tableName} '
            "WHERE userId='{userId}' AND productId='{productId}'\";\n"
        )
        result, count = _parameterize_sql(code)
        assert count == 1
        assert "@userId" in result
        assert "@productId" in result
        assert "'{userId}'" not in result
        assert "AddWithValue" in result

    def test_insert_with_mixed_vars(self):
        code = (
            '    upsertCmd.CommandText =\n'
            '        $"INSERT INTO {_tableName} (userId, productId, quantity) '
            "VALUES ('{userId}', '{productId}', {newQty}) "
            "ON CONFLICT (userId, productId) DO UPDATE SET quantity = {newQty}\";\n"
        )
        result, count = _parameterize_sql(code)
        assert count == 1
        assert "@userId" in result
        assert "@productId" in result
        assert "@newQty" in result
        assert "$\"" not in result  # interpolation removed

    def test_delete_with_single_var(self):
        code = '    cmd.CommandText = $"DELETE FROM {_tableName} WHERE userId=\'{userId}\'\";\n'
        result, count = _parameterize_sql(code)
        assert count == 1
        assert "@userId" in result
        assert "cmd.Parameters.AddWithValue" in result

    def test_skips_non_sql_interpolation(self):
        code = '    var msg = $"Hello {name}";\n'
        result, count = _parameterize_sql(code)
        assert count == 0
        assert result == code

    def test_skips_table_name_variable(self):
        """_tableName should NOT be parameterized (it's a table, not user input)."""
        code = '    cmd.CommandText = $"SELECT * FROM {_tableName}";\n'
        result, count = _parameterize_sql(code)
        # _tableName starts with _ so it should be skipped
        assert count == 0

    def test_preserves_non_cs_files(self):
        step = SqlParameterizeStep()
        result = step(
            code='$"SELECT * FROM t WHERE id=\'{id}\'"',
            context=RepairContext(diagnostics=[]),
            file_path=Path("main.py"),
        )
        assert result.modified is False

    def test_fires_on_cs_files(self):
        step = SqlParameterizeStep()
        code = '    cmd.CommandText = $"SELECT x FROM t WHERE userId=\'{userId}\'\";\n'
        result = step(
            code=code,
            context=RepairContext(diagnostics=[]),
            file_path=Path("Store.cs"),
        )
        assert result.modified is True
        assert result.metrics["queries_parameterized"] == 1


class TestOnRealAlloyDBCode:
    """Test against the actual AlloyDB pattern from run-095."""

    ALLOYDB_ADDITEM = '''\
        public async Task AddItemAsync(string userId, string productId, int quantity)
        {
            try
            {
                await using var conn = _dataSource.CreateConnection();
                await conn.OpenAsync();

                int currentQty = 0;
                await using (var selectCmd = conn.CreateCommand())
                {
                    selectCmd.CommandText =
                        $"SELECT quantity FROM {_tableName} " +
                        $"WHERE userId=\'{userId}\' AND productId=\'{productId}\'";

                    await using var reader = await selectCmd.ExecuteReaderAsync();
                    if (await reader.ReadAsync())
                    {
                        currentQty = reader.GetInt32(0);
                    }
                }
            }
        }
'''

    def test_additem_parameterized(self):
        result, count = _parameterize_sql(self.ALLOYDB_ADDITEM)
        assert count >= 1
        assert "@userId" in result
        assert "@productId" in result
        assert "'{userId}'" not in result
