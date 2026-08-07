import unittest

from jd_parser.extractor import RuleBasedExtractor


class ExtractorTest(unittest.TestCase):
    def test_extracts_core_fields(self):
        raw = """岗位名称：NLP算法工程师
工作地点：南京
岗位职责：
负责RAG系统开发
任职要求：
熟练使用Python和PyTorch，具备2年以上自然语言处理相关经验
加分项：
有知识图谱经验者优先"""
        profile = RuleBasedExtractor().extract("JD_1", raw)
        self.assertEqual(profile.title, "NLP算法工程师")
        self.assertEqual(profile.constraints.location.value, "南京")
        self.assertEqual(profile.constraints.experience_years.value, 2)
        self.assertTrue(any(skill.name == "Python" and skill.level == "required" for skill in profile.skills))
        self.assertTrue(any(skill.name == "知识图谱" and skill.level == "preferred" for skill in profile.skills))


if __name__ == "__main__":
    unittest.main()

