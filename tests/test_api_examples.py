"""
后端 API 测试脚本 - 启动后端后运行此脚本检测各接口是否正常
用法: python tests/test_api_examples.py
"""

import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("请先安装 requests: pip install requests")
    sys.exit(1)

BASE_URL = "http://127.0.0.1:8000"

# ==================== 测试样例数据 ====================

SAMPLE_JD = """岗位名称: 大模型算法工程师
岗位职责:
1. 负责企业知识库问答场景的大语言模型应用建设, 包括 RAG 检索增强生成、Prompt 优化和效果评估。
2. 设计并优化向量召回、排序模型和问答链路, 提升答案准确率、可解释性和稳定性。
3. 参与模型微调、模型部署和推理服务工程化, 与后端团队协作完成 API 接口开发。
任职要求:
1. 本科及以上学历, 计算机、人工智能、软件工程等相关专业, 3 年以上 NLP 或大模型相关经验。
2. 熟练掌握 Python, 熟悉 PyTorch、Transformer、BERT 或大语言模型训练与推理流程。
3. 熟悉 LangChain、LlamaIndex、Milvus、Elasticsearch 等 RAG 相关工具者优先。
4. 具备良好的工程化能力, 熟悉 Docker、FastAPI、Linux 和 Git。
加分项:
1. 有企业服务 ToB、知识库问答或智能客服项目落地经验。
2. 有 LoRA、SFT、模型微调、MLOps 或 Kubernetes 经验优先。"""

SAMPLE_RESUME = """候选人A
求职意向: 算法工程师 / 大模型方向

教育背景:
- XX大学 计算机科学与技术 本科 2018-2022

工作经历:
2022.06 - 至今 | XX科技有限公司 | 算法工程师
- 负责企业知识库问答系统的大语言模型应用开发，基于 LangChain 搭建 RAG 检索增强生成链路
- 使用 Milvus 构建向量数据库，实现文档切片、向量化存储和语义检索
- 参与 Prompt 工程和效果评估，将问答准确率从 75% 提升至 90%+
- 使用 PyTorch 进行 LoRA 微调实验，优化领域问答效果
- 基于 FastAPI 开发模型推理服务接口，使用 Docker 容器化部署

技能清单:
- 编程语言: Python (熟练)、SQL
- 框架/工具: PyTorch、LangChain、LlamaIndex、Milvus、Elasticsearch、FastAPI、Docker
- 领域知识: 大语言模型、RAG、向量检索、Prompt Engineering、NLP
- 其他: Git、Linux、Kubernetes 基础"""

# 更多测试样例
EXTRA_JD_SAMPLES = [
    {
        "title": "推荐算法工程师",
        "text": """岗位名称: 推荐算法工程师
岗位职责:
1. 负责电商推荐场景的召回模型、排序模型和特征工程建设。
2. 结合用户行为数据迭代推荐策略并推动 A/B测试。
任职要求:
1. 本科及以上学历, 2 年以上推荐算法或机器学习相关经验。
2. 熟练掌握 Python、SQL, 熟悉 Spark、TensorFlow 或 PyTorch。
3. 熟悉 Kafka、Redis、特征工程。"""
    },
    {
        "title": "后端开发工程师",
        "text": """岗位名称: 后端开发工程师
岗位职责:
1. 负责招聘业务平台的后端开发, 设计 RESTful API 和微服务架构。
任职要求:
1. 3 年以上 Java 或 Python 后端开发经验。
2. 熟练掌握 Spring Boot、MySQL、Redis、Kafka。
3. 熟悉 Docker、Linux、Git。"""
    },
]

EXTRA_RESUME_SAMPLES = [
    {
        "name": "候选人B - 推荐方向",
        "text": """候选人B
求职意向: 推荐算法工程师

工作经历:
2021.07 - 至今 | XX电商平台 | 推荐算法工程师
- 负责商品推荐召回和排序模型开发，使用 TensorFlow 构建深度学习排序模型
- 基于 Spark 进行大规模用户行为数据处理和特征工程
- 使用 Redis 缓存热门推荐结果，优化线上服务响应时间
- 主导 A/B 实验框架搭建，推动推荐策略迭代

技能: Python、SQL、Spark、TensorFlow、Kafka、Redis、机器学习、推荐系统"""
    },
    {
        "name": "候选人C - 后端方向",
        "text": """候选人C
求职意向: 后端开发工程师

工作经历:
2020.06 - 至今 | XX互联网公司 | Java后端开发工程师
- 负责 SaaS 平台核心模块的 Spring Boot 微服务开发
- 设计 MySQL 数据库表结构和索引优化，处理千万级数据查询
- 使用 Redis 做缓存加速，Kafka 处理异步消息
- 参与容器化部署和 CI/CD 流水线建设

技能: Java、Spring Boot、MySQL、Redis、Kafka、Docker、Linux、Git、微服务"""
    },
]


def print_section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def check_response(resp: requests.Response, endpoint: str) -> bool:
    """检查响应状态并打印结果"""
    status = "PASS" if resp.status_code == 200 else f"FAIL ({resp.status_code})"
    print(f"  [{status}] {endpoint}")
    if resp.status_code != 200:
        print(f"    响应: {resp.text[:300]}")
        return False
    return True


# ==================== 测试用例 ====================

def test_health():
    print_section("1. 健康检查")
    resp = requests.get(f"{BASE_URL}/health", timeout=5)
    ok = check_response(resp, "GET /health")
    if ok:
        print(f"    返回: {resp.json()}")
    return ok


def test_samples():
    print_section("2. 样例数据接口")
    resp = requests.get(f"{BASE_URL}/samples", timeout=5)
    ok = check_response(resp, "GET /samples")
    if ok:
        data = resp.json()
        print(f"    JD样例数: {len(data.get('jds', []))}")
        print(f"    简历样例数: {len(data.get('resumes', []))}")
    return ok


def test_parse_jd():
    print_section("3. JD 解析接口")
    payload = {"jd_text": SAMPLE_JD, "use_llm": False}
    resp = requests.post(f"{BASE_URL}/parse/jd", json=payload, timeout=30)
    ok = check_response(resp, "POST /parse/jd")
    if ok:
        data = resp.json()
        jd_parse = data.get("jd_parse", {})
        job_profile = data.get("job_profile", {})
        print(f"    岗位标题: {jd_parse.get('job_title', 'N/A')}")
        print(f"    提取技能数: {len(job_profile.get('skills', []))}")
        skills = [s['name'] for s in job_profile.get('skills', [])]
        print(f"    技能列表: {skills[:10]}...")
    return ok


def test_parse_resume():
    print_section("4. 简历解析接口")
    payload = {"resume_text": SAMPLE_RESUME, "use_llm": False}
    resp = requests.post(f"{BASE_URL}/parse/resume", json=payload, timeout=30)
    ok = check_response(resp, "POST /parse/resume")
    if ok:
        data = resp.json()
        resume_parse = data.get("resume_parse", {})
        resume_profile = data.get("resume_profile", {})
        print(f"    候选人ID: {resume_parse.get('candidate_id', 'N/A')}")
        print(f"    提取技能数: {len(resume_profile.get('skills', []))}")
        skills = [s['name'] for s in resume_profile.get('skills', [])]
        print(f"    技能列表: {skills[:10]}...")
    return ok


def test_match():
    print_section("5. 人岗匹配接口 (核心)")
    payload = {
        "jd_text": SAMPLE_JD,
        "resume_text": SAMPLE_RESUME,
        "use_llm": False,
    }
    resp = requests.post(f"{BASE_URL}/match", json=payload, timeout=60)
    ok = check_response(resp, "POST /match")
    if ok:
        data = resp.json()
        print(f"    匹配分数: {data.get('final_score', 'N/A')}")
        print(f"    匹配决策: {data.get('decision', 'N/A')}")
        print(f"    匹配技能数: {len(data.get('matched_skills', []))}")
        print(f"    缺失技能数: {len(data.get('missing_skills', []))}")
        print(f"    部分匹配数: {len(data.get('partial_skills', []))}")
        explanation = data.get('explanation', '')
        print(f"    说明: {explanation[:100]}..." if len(explanation) > 100 else f"    说明: {explanation}")

        # 图谱信息
        graph = data.get("graph", {})
        print(f"    图谱节点数: {len(graph.get('nodes', []))}")
        print(f"    图谱边数: {len(graph.get('edges', []))}")
    return ok


def test_graph_full():
    print_section("6. 全量图谱接口")
    resp = requests.get(f"{BASE_URL}/graph/full", timeout=15)
    ok = check_response(resp, "GET /graph/full")
    if ok:
        data = resp.json()
        print(f"    节点数: {len(data.get('nodes', []))}")
        print(f"    边数: {len(data.get('edges', []))}")
    return ok


def test_graph_view():
    print_section("7. 图谱视图接口")
    view_types = ["position", "tech_stack", "level"]
    results = []
    for vt in view_types:
        resp = requests.get(f"{BASE_URL}/graph/view", params={"view_type": vt}, timeout=15)
        ok = check_response(resp, f"GET /graph/view?view_type={vt}")
        results.append(ok)
        if ok:
            data = resp.json()
            print(f"      视图类型: {data.get('view_type')}, 节点: {len(data.get('nodes', []))}")
    return all(results)


def test_match_multiple_cases():
    print_section("8. 多组人岗匹配测试")
    cases = [
        ("大模型JD + 大模型简历(高匹配)", SAMPLE_JD, SAMPLE_RESUME),
        ("推荐JD + 推荐简历(高匹配)", EXTRA_JD_SAMPLES[0]["text"], EXTRA_RESUME_SAMPLES[0]["text"]),
        ("后端JD + 后端简历(高匹配)", EXTRA_JD_SAMPLES[1]["text"], EXTRA_RESUME_SAMPLES[1]["text"]),
        ("大模型JD + 后端简历(低匹配)", SAMPLE_JD, EXTRA_RESUME_SAMPLES[1]["text"]),
    ]

    for name, jd_text, resume_text in cases:
        payload = {"jd_text": jd_text, "resume_text": resume_text, "use_llm": False}
        try:
            resp = requests.post(f"{BASE_URL}/match", json=payload, timeout=60)
            ok = check_response(resp, f"匹配: {name}")
            if ok:
                data = resp.json()
                score = data.get('final_score', 0)
                decision = data.get('decision', 'N/A')
                matched = len(data.get('matched_skills', []))
                missing = len(data.get('missing_skills', []))
                print(f"      分数={score:.1f} | 决策={decision} | 匹配={matched} | 缺失={missing}")
        except Exception as e:
            print(f"  [ERROR] {name}: {e}")
    return True


def test_panorama_graph():
    print_section("9. 全景图谱接口")
    payload = {
        "job_documents": [
            {"id": "test_001", "text": EXTRA_JD_SAMPLES[0]["text"]},
            {"id": "test_002", "text": EXTRA_JD_SAMPLES[1]["text"]},
        ]
    }
    resp = requests.post(f"{BASE_URL}/graph/panorama", json=payload, timeout=30)
    ok = check_response(resp, "POST /graph/panorama")
    if ok:
        data = resp.json()
        result_data = data.get("data", data)
        nodes = result_data.get("nodes", [])
        views = result_data.get("views", {})
        print(f"    节点数: {len(nodes)}")
        print(f"    视图: {list(views.keys()) if views else '无'}")
    return ok


# ==================== 主流程 ====================

def main():
    print("=" * 60)
    print("  Job Ability Graph - 后端 API 测试脚本")
    print(f"  目标地址: {BASE_URL}")
    print("=" * 60)

    # 先检查服务是否可用
    try:
        requests.get(f"{BASE_URL}/health", timeout=3)
    except requests.ConnectionError:
        print("\n[ERROR] 无法连接到后端服务!")
        print("请先启动后端: python backend/app/main.py")
        sys.exit(1)

    results = []

    # 执行所有测试
    results.append(("健康检查", test_health()))
    results.append(("样例数据", test_samples()))
    results.append(("JD解析", test_parse_jd()))
    results.append(("简历解析", test_parse_resume()))
    results.append(("人岗匹配", test_match()))
    results.append(("全量图谱", test_graph_full()))
    results.append(("图谱视图", test_graph_view()))
    results.append(("多组匹配", test_match_multiple_cases()))
    results.append(("全景图谱", test_panorama_graph()))

    # 汇总结果
    print("\n" + "=" * 60)
    print("  测试结果汇总")
    print("=" * 60)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
    print(f"\n  总计: {passed}/{total} 通过")

    if passed == total:
        print("\n  所有接口测试通过!")
    else:
        print(f"\n  有 {total - passed} 个接口存在问题，请检查上方日志")


if __name__ == "__main__":
    main()
