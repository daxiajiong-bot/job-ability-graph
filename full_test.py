"""
前后端接口完整验证测试
使用真实示例数据测试所有核心API
"""

import json
import requests
from datetime import datetime

# API基础地址
BASE_URL = "http://localhost:8000"

print("=" * 80)
print("🔍 前后端接口完整验证测试")
print(f"📅 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"🌐 后端地址: {BASE_URL}")
print("=" * 80)

# ============================================
# 1. 加载示例数据
# ============================================
print("\n📂 [步骤1] 加载示例数据...")

with open('data/samples/jd_samples.json', 'r', encoding='utf-8') as f:
    jd_samples = json.load(f)
    print(f"   ✅ 加载 {len(jd_samples)} 个JD样本")

with open('data/samples/resume_samples.json', 'r', encoding='utf-8') as f:
    resume_samples = json.load(f)
    print(f"   ✅ 加载 {len(resume_samples)} 个简历样本")

# 选择第一组数据进行测试（大模型算法工程师 + 候选人A）
test_jd = jd_samples[0]  # 大模型算法工程师
test_resume = resume_samples[0]  # 候选人A（目标岗位匹配）

print(f"\n   📋 测试数据:")
print(f"      JD: {test_jd['title']} ({test_jd['category']})")
print(f"      简历: {test_resume['name']} (目标: {test_resume['target_position']})")


# ============================================
# 2. 测试JD解析接口
# ============================================
print("\n" + "=" * 80)
print("🧪 [测试1] JD解析接口 - POST /parse/jd")
print("=" * 80)

try:
    jd_response = requests.post(
        f"{BASE_URL}/parse/jd",
        json={
            "text": test_jd["text"],
            "use_llm": False
        }
    )

    print(f"\n📊 状态码: {jd_response.status_code}")

    if jd_response.status_code == 200:
        jd_result = jd_response.json()
        print("✅ JD解析成功!")

        # 提取关键信息
        jd_parse = jd_result.get("jd_parse", {})
        job_profile = jd_result.get("job_profile", {})

        print(f"\n📝 解析结果:")
        print(f"   岗位名称: {jd_parse.get('job_title', '未识别')}")
        print(f"   岗位类别: {job_profile.get('metadata', {}).get('job_category', '未识别')}")
        print(f"   学历要求: {job_profile.get('metadata', {}).get('education_requirement', '未识别')}")
        print(f"   经验要求: {job_profile.get('metadata', {}).get('experience_requirement', '未识别')} 年")

        skills = job_profile.get("skills", [])
        print(f"\n🎯 提取技能 ({len(skills)}个):")
        for i, skill in enumerate(skills[:8], 1):  # 显示前8个技能
            print(f"   {i}. {skill.get('name', '未知')} "
                  f"[{skill.get('skill_type', '未知')}] "
                  f"权重:{skill.get('weight', 0)} "
                  f"置信度:{skill.get('confidence', 0):.0%}")

        # 保存JD解析结果
        with open('test_output/jd_parse_result.json', 'w', encoding='utf-8') as f:
            json.dump(jd_result, f, ensure_ascii=False, indent=2)
        print(f"\n💾 结果已保存到: test_output/jd_parse_result.json")

    else:
        print(f"❌ JD解析失败: {jd_response.text}")

except Exception as e:
    print(f"❌ JD解析异常: {e}")


# ============================================
# 3. 测试简历解析接口
# ============================================
print("\n" + "=" * 80)
print("🧪 [测试2] 简历解析接口 - POST /parse/resume")
print("=" * 80)

try:
    resume_response = requests.post(
        f"{BASE_URL}/parse/resume",
        json={
            "text": test_resume["text"],
            "use_llm": False
        }
    )

    print(f"\n📊 状态码: {resume_response.status_code}")

    if resume_response.status_code == 200:
        resume_result = resume_response.json()
        print("✅ 简历解析成功!")

        # 提取关键信息
        resume_parse = resume_result.get("resume_parse", {})
        resume_profile = result.get("resume_profile", {})

        print(f"\n👤 解析结果:")
        print(f"   候选人ID: {resume_parse.get('candidate_id', '未识别')}")
        print(f"   学历: {resume_parse.get('education', '未识别')}")
        print(f"   工作经验: {resume_parse.get('experience_years', '未知')} 年")

        skills = resume_profile.get("skills", [])
        print(f"\n🎯 提取技能 ({len(skills)}个):")
        for i, skill in enumerate(skills[:8], 1):
            proficiency = skill.get("proficiency", 0)
            level = "专家" if proficiency >= 0.9 else ("高级" if proficiency >= 0.7 else ("中级" if proficiency >= 0.5 else "初级"))
            print(f"   {i}. {skill.get('name', '未知')} "
                  f"[{level}] "
                  f"熟练度:{proficiency:.0%}")

        # 保存简历解析结果
        with open('test_output/resume_parse_result.json', 'w', encoding='utf-8') as f:
            json.dump(resume_result, f, ensure_ascii=False, indent=2)
        print(f"\n💾 结果已保存到: test_output/resume_parse_result.json")

    else:
        print(f"❌ 简历解析失败: {resume_response.text}")

except Exception as e:
    print(f"❌ 简历解析异常: {e}")


# ============================================
# 4. 测试匹配接口（核心功能）
# ============================================
print("\n" + "=" * 80)
print("🧪 [测试3] 人岗匹配接口 - POST /match (核心功能)")
print("=" * 80)

try:
    match_response = requests.post(
        f"{BASE_URL}/match",
        json={
            "jd_text": test_jd["text"],
            "resume_text": test_resume["text"],
            "use_llm": False
        }
    )

    print(f"\n📊 状态码: {match_response.status_code}")

    if match_response.status_code == 200:
        match_result = match_response.json()
        print("✅ 匹配计算成功!")

        # 核心指标
        final_score = match_result.get("final_score", 0)
        decision = match_result.get("decision", "未知")
        matched_skills = match_result.get("matched_skills", [])
        missing_skills = match_result.get("missing_skills", [])
        partial_skills = match_result.get("partial_skills", [])
        score_detail = match_result.get("score_detail", {})

        print(f"\n{'='*60}")
        print(f"🎯 核心匹配结果")
        print(f"{'='*60}")
        print(f"   综合分数: {final_score:.1f} / 100")
        print(f"   匹配决策: {decision}")
        print(f"   命中技能: {len(matched_skills)} 个")
        print(f"   缺失技能: {len(missing_skills)} 个")
        print(f"   部分匹配: {len(partial_skills)} 个")

        # 多维度分数分析
        print(f"\n{'='*60}")
        print(f"📈 多维度评分详情")
        print(f"{'='*60}")

        dimensions = [
            ("skill_coverage", "技能覆盖率"),
            ("distribution_similarity", "分布相似度"),
            ("experience_fit", "经验匹配度"),
            ("education_fit", "学历匹配度"),
            ("domain_fit", "领域相关性"),
            ("semantic_fit", "语义相似度")
        ]

        for key, label in dimensions:
            score = score_detail.get(key)
            if score is not None:
                status = "✅" if score >= 0.7 else ("⚠️" if score >= 0.5 else "❌")
                bar_length = int(score * 30)
                bar = "█" * bar_length + "░" * (30 - bar_length)
                print(f"   {status} {label:12s}: [{bar}] {score:.1%}")

        # 技能匹配详情
        print(f"\n{'='*60}")
        print(f"🎯 技能匹配详情")
        print(f"{'='*60}")

        if matched_skills:
            print(f"\n✨ 命中技能 (前10个):")
            for i, skill in enumerate(matched_skills[:10], 1):
                name = skill.get("name", "未知")
                match_type = skill.get("match_type", "未知")
                contribution = skill.get("contribution", 0)
                jd_weight = skill.get("jd_weight", 0)
                resume_level = skill.get("resume_proficiency", 0)

                print(f"   {i:2d}. {name:20s} | 类型:{match_type:8s} | 贡献度:{contribution:.2f} | JD权重:{jd_weight:.1f} | 简历水平:{resume_level:.0%}")

        if missing_skills:
            print(f"\n⚠️ 缺失技能:")
            for i, skill in enumerate(missing_skills[:5], 1):
                name = skill.get("name", "未知")
                priority = skill.get("priority", "未知")
                gap_priority = skill.get("gap_priority", 0)
                print(f"   {i}. {name:20s} | 优先级:{priority:10s} | 差距值:{gap_priority:.1f}")

        if partial_skills:
            print(f"\n⚠️ 部分匹配技能 (不足):")
            for i, skill in enumerate(partial_skills[:5], 1):
                name = skill.get("name", "未知")
                required = skill.get("required_level", 0)
                actual = skill.get("resume_level", 0)
                gap_type = skill.get("gap_type", "未知")
                print(f"   {i}. {name:20s} | 需要:{required:.0%} | 实际:{actual:.0%} | 差距类型:{gap_type}")

        # AI分析说明
        explanation = match_result.get("explanation", "")
        if explanation:
            print(f"\n{'='*60}")
            print(f"💡 AI智能分析说明")
            print(f"{'='*60}")
            print(f"   {explanation}")

        # 保存完整匹配结果
        with open('test_output/match_result_full.json', 'w', encoding='utf-8') as f:
            json.dump(match_result, f, ensure_ascii=False, indent=2)
        print(f"\n💾 完整结果已保存到: test_output/match_result_full.json")

    else:
        print(f"❌ 匹配失败: {match_response.text}")

except Exception as e:
    print(f"❌ 匹配异常: {e}")


# ============================================
# 5. 生成测试报告
# ============================================
print("\n" + "=" * 80)
print("📋 测试总结报告")
print("=" * 80)

report = {
    "测试时间": datetime.now().isoformat(),
    "后端状态": "运行中",
    "测试数据": {
        "JD": test_jd["title"],
        "简历": test_resume["name"],
        "预期匹配": "高度匹配（候选人与目标岗位一致）"
    },
    "测试结果": {
        "JD解析": "✅ 成功" if jd_response.status_code == 200 else "❌ 失败",
        "简历解析": "✅ 成功" if resume_response.status_code == 200 else "❌ 失败",
        "人岗匹配": "✅ 成功" if match_response.status_code == 200 else "❌ 失败"
    },
    "核心指标": {
        "综合分数": f"{final_score:.1f}/100",
        "匹配决策": decision,
        "命中技能数": len(matched_skills),
        "缺失技能数": len(missing_skills)
    } if match_response.status_code == 200 else {},
    "结论": "前后端接口对接完成，系统正常运行！" if all([
        jd_response.status_code == 200,
        resume_response.status_code == 200,
        match_response.status_code == 200
    ]) else "存在接口问题，需要排查"
}

for key, value in report.items():
    if isinstance(value, dict):
        print(f"\n{key}:")
        for k, v in value.items():
            print(f"   {k}: {v}")
    else:
        print(f"{key}: {value}")

# 保存报告
with open('test_output/test_report.json', 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(f"\n💾 测试报告已保存到: test_output/test_report.json")

print("\n" + "=" * 80)
print("✅ 测试完成!")
print("=" * 80)
