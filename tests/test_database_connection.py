"""
数据库连接模块单元测试。

对应阶段7测试中发现的真实问题：sqlite3.connect() 对不存在的路径会
自动创建空文件，导致"数据库未初始化"这个状态如果只检查"文件是否存在"
是查不出来的，必须显式检查业务表是否存在。
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from database.connection import get_connection, is_schema_initialized, check_connection


class TestIsSchemaInitialized(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_nonexistent_file_returns_false(self):
        path = Path(self._tmpdir.name) / "never_created.db"
        self.assertFalse(is_schema_initialized(path))

    def test_nonexistent_file_check_has_no_side_effect(self):
        """检查不存在的文件不应该把它创建出来
        （sqlite3.connect()的自动创建行为是本问题的根源，检查函数本身
        不能重复踩这个坑）。
        """
        path = Path(self._tmpdir.name) / "should_not_be_created.db"
        is_schema_initialized(path)
        self.assertFalse(path.exists())

    def test_empty_file_without_schema_returns_false(self):
        """文件存在但没有建表（例如被sqlite3.connect()意外自动创建的
        空文件）应返回False，不能被误判为"已初始化"。
        """
        path = Path(self._tmpdir.name) / "empty.db"
        conn = sqlite3.connect(str(path))
        conn.close()
        self.assertTrue(path.exists())
        self.assertFalse(is_schema_initialized(path))

    def test_file_with_schema_returns_true(self):
        path = Path(self._tmpdir.name) / "real.db"
        schema_path = Path(__file__).resolve().parent.parent / "database" / "schema.sql"
        conn = sqlite3.connect(str(path))
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.commit()
        conn.close()
        self.assertTrue(is_schema_initialized(path))

    def test_file_with_unrelated_tables_only_returns_false(self):
        """文件存在、有表，但不是业务schema（例如别的程序创建的无关
        sqlite文件）应返回False，不能只看"是否有任意表"。
        """
        path = Path(self._tmpdir.name) / "unrelated.db"
        conn = sqlite3.connect(str(path))
        conn.execute("CREATE TABLE unrelated_table (id INTEGER)")
        conn.commit()
        conn.close()
        self.assertFalse(is_schema_initialized(path))


class TestGetConnection(unittest.TestCase):
    def test_commit_on_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.db"
            with get_connection(path) as conn:
                conn.execute("CREATE TABLE t (id INTEGER)")
                conn.execute("INSERT INTO t VALUES (1)")
            with get_connection(path) as conn:
                row = conn.execute("SELECT id FROM t").fetchone()
            self.assertEqual(row["id"], 1)

    def test_rollback_on_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.db"
            with get_connection(path) as conn:
                conn.execute("CREATE TABLE t (id INTEGER)")
                conn.execute("INSERT INTO t VALUES (1)")

            with self.assertRaises(RuntimeError):
                with get_connection(path) as conn:
                    conn.execute("INSERT INTO t VALUES (2)")
                    raise RuntimeError("forced failure")

            with get_connection(path) as conn:
                count = conn.execute("SELECT COUNT(*) AS n FROM t").fetchone()["n"]
            self.assertEqual(count, 1, "rollback应撤销未commit的插入")


if __name__ == "__main__":
    unittest.main()
