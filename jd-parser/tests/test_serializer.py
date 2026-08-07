import unittest

from jd_parser.schemas import JDProfile, JDConstraints, Skill, TextConstraint, IntConstraint
from jd_parser.serializer import serialize_profile


class SerializerTest(unittest.TestCase):
    def test_serialization_is_deterministic(self):
        profile = JDProfile(
            document_id="JD_1",
            title="NLP算法工程师",
            responsibilities=["负责信息抽取模型研发", "参与RAG系统建设"],
            requirements=["熟练使用Python和PyTorch"],
            preferred=["有知识图谱经验者优先"],
            skills=[
                Skill(name="Python", level="required", evidence="熟练使用Python和PyTorch"),
                Skill(name="PyTorch", level="required", evidence="熟练使用Python和PyTorch"),
                Skill(name="RAG", level="mentioned", evidence="参与RAG系统建设"),
                Skill(name="知识图谱", level="preferred", evidence="有知识图谱经验者优先"),
            ],
            constraints=JDConstraints(
                education=TextConstraint(value="硕士及以上", evidence="计算机相关专业硕士及以上学历"),
                experience_years=IntConstraint(value=2, evidence="具备2年以上自然语言处理相关经验"),
                location=TextConstraint(value="南京", evidence="工作地点：南京"),
            ),
            raw_text="raw",
        )
        first = serialize_profile(profile)
        second = serialize_profile(profile)
        self.assertEqual(first, second)
        self.assertIn("[必需技能]\nPython；PyTorch", first)
        self.assertNotIn("schema_version", first)


if __name__ == "__main__":
    unittest.main()

