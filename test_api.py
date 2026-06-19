"""快速测试后端API"""
import requests
import json

print("=" * 60)
print("测试1: JD解析接口")
print("=" * 60)

jd_response = requests.post('http://localhost:8000/parse/jd', json={
    'text': '岗位名称: 大模型算法工程师\n任职要求:\n1. 本科及以上学历, 3年以上NLP经验\n2. 熟练掌握Python、PyTorch',
    'use_llm': False
})

print(f"状态码: {jd_response.status_code}")
if jd_response.status_code == 200:
    data = jd_response.json()
    print(f"✅ 解析成功!")
    print(f"   岗位名称: {data.get('jd_parse', {}).get('job_title', '未知')}")
    print(f"   技能数量: {len(data.get('job_profile', {}).get('skills', []))}")
else:
    print(f"❌ 错误: {jd_response.text}")

print("\n" + "=" * 60)
print("测试2: 匹配接口 (核心功能)")
print("=" * 60)

match_response = requests.post('http://localhost:8000/match', json={
    'jd_text': '''岗位名称: 大模型算法工程师
任职要求:
1. 本科及以上学历, 3年以上NLP或大模型相关经验
2. 熟练掌握Python, PyTorch, RAG, LangChain
3. 熟悉知识库问答系统建设''',
    'resume_text': '''姓名: 候选人A
教育经历: 硕士 计算机科学
工作经历:
2022-至今 算法工程师
1. 负责RAG检索增强生成链路, 使用LangChain、Milvus搭建混合检索
2. 基于PyTorch完成意图识别和排序模型优化
专业技能: Python、PyTorch、NLP、RAG、LangChain、Milvus、FastAPI''',
    'use_llm': False
})

print(f"状态码: {match_response.status_code}")
if match_response.status_code == 200:
    result = match_response.json()
    print(f"\n✅ 匹配成功!")
    print(f"\n📊 核心指标:")
    print(f"   综合分数: {result.get('final_score', 0):.1f}/100")
    print(f"   匹配决策: {result.get('decision', '未知')}")
    print(f"   命中技能: {len(result.get('matched_skills', []))} 个")
    print(f"   缺失技能: {len(result.get('missing_skills', []))} 个")
    print(f"   部分匹配: {len(result.get('partial_skills', []))} 个")

    if result.get('score_detail'):
        print(f"\n📈 多维度分数:")
        for dim, score in result['score_detail'].items():
            if score is not None:
                status = "✅" if score >= 0.7 else ("⚠️" if score >= 0.5 else "❌")
                print(f"   {status} {dim}: {score:.1%}")

    if result.get('matched_skills'):
        print(f"\n🎯 前5个命中技能:")
        for i, skill in enumerate(result['matched_skills'][:5], 1):
            print(f"   {i}. {skill.get('name', '未知')} ({skill.get('match_type', '未知')}) - 贡献度: {skill.get('contribution', 0):.1f}")

    if result.get('missing_skills'):
        print(f"\n⚠️ 缺失技能:")
        for skill in result['missing_skills'][:3]:
            print(f"   ❌ {skill.get('name', '未知')} (优先级: {skill.get('priority', '未知')})")

    if result.get('explanation'):
        print(f"\n💡 AI分析说明:\n   {result['explanation'][:200]}...")

    # 保存完整结果到文件
    with open('test_match_result.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n💾 完整结果已保存到: test_match_result.json")

else:
    print(f"❌ 匹配失败: {match_response.text}")

print("\n" + "=" * 60)
print("✅ 测试完成")
print("=" * 60)
