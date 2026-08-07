import unittest

from jd_parser.cleaner import clean_text


class CleanerTest(unittest.TestCase):
    def test_removes_navigation_and_duplicate_blocks(self):
        raw = "首页\n岗位职责：\n负责RAG系统开发\n\n负责RAG系统开发\n立即申请"
        self.assertEqual(clean_text(raw), "岗位职责：\n负责RAG系统开发")


if __name__ == "__main__":
    unittest.main()

