"""
任务服务单元测试。

对应技术方案 §9："为任务状态流转编写测试，确保完成任务必须有结果。"
使用真实的临时 SQLite 数据库（应用 schema.sql），不是纯 mock，以验证
service 层 + repository 层 + 数据库 CHECK 约束三层协同工作正常。
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from services import task_service
from database.connection import get_connection


class TaskServiceTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        schema_path = Path(__file__).resolve().parent.parent / "database" / "schema.sql"
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()


class TestCreateTask(TaskServiceTestBase):
    def test_create_minimal_task(self):
        with get_connection(self.db_path) as conn:
            task = task_service.create_task(
                conn, title="测试任务", assignee="张三", due_at="2024-04-01T10:00:00"
            )
            self.assertEqual(task.status, "待处理")
            self.assertEqual(task.priority, "P2")  # 默认优先级

        # 任务创建应附带一条日志
        with get_connection(self.db_path) as conn:
            from repositories import task_repository

            logs = task_repository.list_logs_for_task(conn, task.task_id)
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].action, "创建任务")

    def test_create_task_rejects_empty_title(self):
        with get_connection(self.db_path) as conn:
            with self.assertRaises(task_service.TaskValidationError):
                task_service.create_task(conn, title="  ", assignee="张三", due_at="2024-04-01T10:00:00")

    def test_create_task_rejects_empty_assignee(self):
        with get_connection(self.db_path) as conn:
            with self.assertRaises(task_service.TaskValidationError):
                task_service.create_task(conn, title="测试任务", assignee="", due_at="2024-04-01T10:00:00")

    def test_create_task_rejects_invalid_priority(self):
        with get_connection(self.db_path) as conn:
            with self.assertRaises(task_service.TaskValidationError):
                task_service.create_task(
                    conn, title="测试任务", assignee="张三", due_at="2024-04-01T10:00:00", priority="P9"
                )


class TestCompleteTask(TaskServiceTestBase):
    def test_complete_requires_result(self):
        """核心验收点：完成任务必须有处理结果（技术方案 §4、§9 明确要求）。"""
        with get_connection(self.db_path) as conn:
            task = task_service.create_task(
                conn, title="测试任务", assignee="张三", due_at="2024-04-01T10:00:00"
            )
            with self.assertRaises(task_service.TaskValidationError):
                task_service.update_status(conn, task.task_id, "已完成", actor="张三", result=None)

    def test_complete_with_empty_result_rejected(self):
        with get_connection(self.db_path) as conn:
            task = task_service.create_task(
                conn, title="测试任务", assignee="张三", due_at="2024-04-01T10:00:00"
            )
            with self.assertRaises(task_service.TaskValidationError):
                task_service.update_status(conn, task.task_id, "已完成", actor="张三", result="   ")

    def test_complete_with_result_succeeds(self):
        with get_connection(self.db_path) as conn:
            task = task_service.create_task(
                conn, title="测试任务", assignee="张三", due_at="2024-04-01T10:00:00"
            )
            task_service.update_status(
                conn, task.task_id, "已完成", actor="张三", result="已联系客户并补发货"
            )

        with get_connection(self.db_path) as conn:
            from repositories import task_repository

            updated = task_repository.get_by_id(conn, task.task_id)
            self.assertEqual(updated.status, "已完成")
            self.assertEqual(updated.result, "已联系客户并补发货")
            self.assertIsNotNone(updated.completed_at)

    def test_db_constraint_also_rejects_completed_without_result(self):
        """即使绕过 service 层直接写库，数据库 CHECK 约束也应拒绝
        "已完成但无结果"的数据（技术方案 §4 的最后一道防线）。
        """
        with get_connection(self.db_path) as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """INSERT INTO operation_tasks
                       (task_id, anomaly_id, order_id, title, description, priority,
                        assignee, due_at, status, result, created_at, completed_at)
                       VALUES ('TASK-X', NULL, NULL, '标题', NULL, 'P2', '张三',
                               '2024-04-01T10:00:00', '已完成', NULL, '2024-03-01T10:00:00', '2024-03-02T10:00:00')"""
                )


class TestCancelTask(TaskServiceTestBase):
    def test_cancel_with_reason(self):
        with get_connection(self.db_path) as conn:
            task = task_service.create_task(
                conn, title="测试任务", assignee="张三", due_at="2024-04-01T10:00:00"
            )
            task_service.update_status(
                conn, task.task_id, "已取消", actor="张三", cancel_reason="客户已自行解决"
            )

        with get_connection(self.db_path) as conn:
            from repositories import task_repository

            updated = task_repository.get_by_id(conn, task.task_id)
            self.assertEqual(updated.status, "已取消")
            logs = task_repository.list_logs_for_task(conn, task.task_id)
            cancel_logs = [l for l in logs if l.action == "取消任务"]
            self.assertEqual(len(cancel_logs), 1)
            self.assertIn("客户已自行解决", cancel_logs[0].content)


class TestTaskLogAppendOnly(TaskServiceTestBase):
    def test_progress_notes_accumulate(self):
        """任务日志追加式记录，不覆盖历史（页面交互设计 §3.6）。"""
        with get_connection(self.db_path) as conn:
            task = task_service.create_task(
                conn, title="测试任务", assignee="张三", due_at="2024-04-01T10:00:00"
            )
            task_service.add_progress_note(conn, task.task_id, "已联系供应商确认", actor="张三")
            task_service.add_progress_note(conn, task.task_id, "供应商回复预计明天发货", actor="李四")

        with get_connection(self.db_path) as conn:
            from repositories import task_repository

            logs = task_repository.list_logs_for_task(conn, task.task_id)
            # 创建任务(1) + 两条处理记录(2) = 3 条日志，历史记录均保留
            self.assertEqual(len(logs), 3)
            self.assertEqual(logs[0].action, "创建任务")
            self.assertEqual(logs[1].content, "已联系供应商确认")
            self.assertEqual(logs[2].content, "供应商回复预计明天发货")


if __name__ == "__main__":
    unittest.main()
