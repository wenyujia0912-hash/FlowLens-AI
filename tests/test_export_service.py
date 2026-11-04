"""
导出服务单元测试。

验证生成的 .xlsx 内容是结构合法的 OOXML 包（用标准库 zipfile/xml 解析
回读，不依赖 openpyxl——当前环境没有openpyxl，这也顺便验证了"不借助
第三方库也能确认生成文件结构正确"）。
"""

from __future__ import annotations

import unittest
import zipfile
import io
import xml.etree.ElementTree as ET

from services import export_service


class TestBuildXlsx(unittest.TestCase):
    def test_produces_valid_zip(self):
        """生成的内容必须是合法的ZIP包（.xlsx的底层格式）。"""
        content = export_service.build_xlsx(["列A", "列B"], [["值1", 100], ["值2", 200]])
        buf = io.BytesIO(content)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            self.assertIn("[Content_Types].xml", names)
            self.assertIn("xl/workbook.xml", names)
            self.assertIn("xl/worksheets/worksheet1.xml", names)

    def test_header_and_rows_present_in_xml(self):
        """表头和数据行都应出现在生成的worksheet XML里。"""
        content = export_service.build_xlsx(
            ["订单编号", "金额"], [["ORD-001", 1000], ["ORD-002", 2000]]
        )
        buf = io.BytesIO(content)
        with zipfile.ZipFile(buf) as zf:
            sheet_xml = zf.read("xl/worksheets/worksheet1.xml").decode("utf-8")

        # XML本身应能被标准库解析（不是格式错误的字符串拼接）。
        root = ET.fromstring(sheet_xml)
        self.assertIsNotNone(root)

        self.assertIn("订单编号", sheet_xml)
        self.assertIn("ORD-001", sheet_xml)
        self.assertIn("1000", sheet_xml)

    def test_row_count_matches_header_plus_data(self):
        headers = ["A", "B", "C"]
        rows = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
        content = export_service.build_xlsx(headers, rows)
        buf = io.BytesIO(content)
        with zipfile.ZipFile(buf) as zf:
            sheet_xml = zf.read("xl/worksheets/worksheet1.xml").decode("utf-8")
        root = ET.fromstring(sheet_xml)
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        row_elements = root.findall(".//m:row", ns)
        self.assertEqual(len(row_elements), 4)  # 1表头 + 3数据行

    def test_special_characters_escaped(self):
        """特殊字符（& < > "）必须被正确转义，否则生成的XML会损坏。"""
        content = export_service.build_xlsx(
            ["字段"], [["包含 & < > \" 特殊字符"]]
        )
        buf = io.BytesIO(content)
        with zipfile.ZipFile(buf) as zf:
            sheet_xml = zf.read("xl/worksheets/worksheet1.xml").decode("utf-8")
        # 解析不报错即说明转义正确。
        root = ET.fromstring(sheet_xml)
        self.assertIsNotNone(root)

    def test_none_values_produce_empty_cell(self):
        content = export_service.build_xlsx(["A", "B"], [[1, None], [None, 2]])
        buf = io.BytesIO(content)
        with zipfile.ZipFile(buf) as zf:
            sheet_xml = zf.read("xl/worksheets/worksheet1.xml").decode("utf-8")
        root = ET.fromstring(sheet_xml)  # 应能正常解析，不因None值损坏XML
        self.assertIsNotNone(root)

    def test_boolean_values_handled_distinctly_from_numbers(self):
        """bool是int的子类，必须验证没有被错误地当成数字1/0处理
        （True应显示为"TRUE"文本，而不是数字1）。
        """
        content = export_service.build_xlsx(["状态"], [[True], [False]])
        buf = io.BytesIO(content)
        with zipfile.ZipFile(buf) as zf:
            sheet_xml = zf.read("xl/worksheets/worksheet1.xml").decode("utf-8")
        self.assertIn("TRUE", sheet_xml)
        self.assertIn("FALSE", sheet_xml)

    def test_empty_headers_rejected(self):
        with self.assertRaises(ValueError):
            export_service.export_rows_to_xlsx([], [])


class TestColumnLetter(unittest.TestCase):
    def test_basic_mapping(self):
        self.assertEqual(export_service._column_letter(0), "A")
        self.assertEqual(export_service._column_letter(25), "Z")
        self.assertEqual(export_service._column_letter(26), "AA")
        self.assertEqual(export_service._column_letter(27), "AB")


class TestBuildExportFilename(unittest.TestCase):
    def test_filename_has_xlsx_extension(self):
        name = export_service.build_export_filename("test_export")
        self.assertTrue(name.endswith(".xlsx"))
        self.assertTrue(name.startswith("test_export_"))


if __name__ == "__main__":
    unittest.main()
