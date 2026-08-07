import unittest

from jd_parser.schemas import JDProfile, Skill
from jd_parser.validator import validate_profile


class ValidatorTest(unittest.TestCase):
    def test_validates_skill_evidence(self):
        raw = "岗位名称：NLP算法工程师\n熟练使用Python和PyTorch"
        profile = JDProfile(
            document_id="JD_1",
            title="NLP算法工程师",
            skills=[Skill(name="Python", level="required", evidence="熟练使用Python和PyTorch")],
            raw_text=raw,
        )
        result = validate_profile(profile)
        self.assertEqual(result.status, "valid")

    def test_invalid_when_evidence_missing(self):
        profile = JDProfile(
            document_id="JD_2",
            title="算法工程师",
            skills=[Skill(name="Python", level="required", evidence="不存在的证据")],
            raw_text="熟练使用Java",
        )
        result = validate_profile(profile)
        self.assertEqual(result.status, "invalid")

    def test_needs_review_when_title_missing(self):
        profile = JDProfile(document_id="JD_3", raw_text="熟练使用Python")
        result = validate_profile(profile)
        self.assertEqual(result.status, "needs_review")


if __name__ == "__main__":
    unittest.main()

