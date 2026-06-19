"""
===========================================
  测试样例数据 - 用于手动验证人岗匹配功能
  复制对应内容到页面的 JD / 简历输入框中即可测试
===========================================

共 6 组测试场景:
  场景1: 高度匹配 (大模型JD + 大模型简历)   → 预期: 分数高, 缺失少
  场景2: 高度匹配 (推荐JD + 推荐简历)       → 预期: 分数高, 缺失少
  场景3: 中等匹配 (后端JD + 后端简历)       → 预期: 分数中等, 有部分缺失
  场景4: 低匹配 (大模型JD + 后端简历)        → 预期: 分数低, 大量缺失
  场景5: 跨领域不匹配 (数据JD + 前端简历)    → 预期: 分数很低, 几乎全缺失
  场景6: 简历信息不足                       → 预期: 匹配项少, 缺失多

使用方式:
  在页面选择「手动输入」模式, 将下方 JD 和 Resume 文本分别粘贴到对应输入框,
  点击「运行匹配诊断」查看结果。
"""

# ================================================================
# 场景1: 高度匹配 - 大模型算法工程师
# ================================================================

SCENARIO_1_JD = """岗位名称: 大模型算法工程师
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

SCENARIO_1_RESUME = """姓名: 张三
求职意向: 大模型算法工程师 / NLP算法工程师
教育背景:
- XX大学 计算机科学与技术 硕士 2020-2023
- XX大学 软件工程 本科 2016-2020

工作经历:
2023.07 - 至今 | XX科技有限公司 | 算法工程师
- 负责企业知识库问答产品的 RAG 检索增强生成链路开发
- 使用 LangChain 搭建检索增强流程, Milvus 构建向量数据库实现语义检索
- 基于 PyTorch 进行 BERT 和大语言模型的微调实验(LoRA/SFT)
- 使用 FastAPI 开发模型推理服务接口, Docker 容器化部署上线
- 将问答系统准确率从 72% 提升至 91%

技能清单:
编程语言: Python(熟练)、SQL
框架/工具: PyTorch、LangChain、LlamaIndex、Milvus、Elasticsearch、FastAPI、Docker
领域知识: NLP、大语言模型(LLM)、RAG、向量检索、Prompt Engineering、Transformer
其他: Git、Linux、Kubernetes基础"""


# ================================================================
# 场景2: 高度匹配 - 推荐算法工程师
# ================================================================

SCENARIO_2_JD = """岗位名称: 推荐算法工程师
岗位职责:
1. 负责电商和内容推荐场景的召回模型、排序模型和特征工程建设。
2. 结合用户行为、商品画像和实时反馈数据, 迭代推荐策略并推动 A/B测试。
3. 与数据开发和后端团队协作, 完成推荐链路的模型训练、离线评估、在线部署和性能优化。
任职要求:
1. 本科及以上学历, 2 年以上推荐算法、搜索算法或机器学习相关经验。
2. 熟练掌握 Python、SQL, 熟悉机器学习、深度学习、召回模型、排序模型。
3. 熟悉 Spark、Kafka、Redis、TensorFlow 或 PyTorch 中至少两项。
4. 具备数据分析、特征工程和实验分析能力。
加分项:
1. 有电商、信息流、广告或内容推荐业务经验优先。
2. 熟悉高并发推荐服务、模型优化或工程化落地者优先。"""

SCENARIO_2_RESUME = """姓名: 李四
求职意向: 推荐算法工程师
教育背景:
- XX大学 数学与应用数学 本科 2019-2023

工作经历:
2023.06 - 至今 | XX电商平台 | 推荐算法工程师
- 负责首页商品推荐的召回和排序模型迭代开发
- 基于 TensorFlow/PyTorch 构建 DeepFM 双塔排序模型, CTR 提升 8%
- 使用 Spark 处理亿级用户行为数据, 完成特征工程和样本构建
- 设计并落地 A/B 实验框架, 推动推荐策略持续优化
- 与后端协作通过 Redis 缓存热门推荐结果, P99 延迟降低至 50ms 以内

技能清单:
编程语言: Python(熟练)、SQL(熟练)
框架/工具: TensorFlow、PyTorch、Spark、Kafka、Redis
领域知识: 推荐系统、召回模型、排序模型、特征工程、A/B测试、机器学习
其他: Linux、Git、数据分析"""


# ================================================================
# 场景3: 中等匹配 - 后端开发工程师
# ================================================================

SCENARIO_3_JD = """岗位名称: 后端开发工程师
岗位职责:
1. 负责招聘业务和企业服务平台的后端开发, 包括用户、岗位、简历、匹配结果等核心模块。
2. 设计 RESTful API、微服务和数据访问层, 保障系统高并发、可扩展和可维护。
3. 参与岗位能力图谱、搜索推荐、消息队列和缓存体系建设。
任职要求:
1. 本科及以上学历, 3 年以上 Java 或 Python 后端开发经验。
2. 熟练掌握 Java、Spring Boot、MySQL、Redis、Kafka, 熟悉 Linux、Git 和 Docker。
3. 具备系统设计、接口开发、性能优化、分布式系统和微服务实践经验。
4. 有良好的沟通协作、项目管理和文档能力。
加分项:
1. 有招聘业务、人力资源 SaaS、搜索推荐或知识图谱项目经验优先。
2. 熟悉 Kubernetes、CI/CD、DevOps 或云原生技术者优先。"""

SCENARIO_3_RESUME = """姓名: 王五
求职意向: Java后端开发工程师
教育背景:
- XX大学 计算机科学 本科 2019-2023

工作经历:
2023.07 - 至今 | XX互联网公司 | Java后端开发工程师
- 负责 SaaS 平台核心模块的 Spring Boot 微服务开发和接口设计
- 设计 MySQL 数据库表结构, 通过索引优化将查询响应时间降低 60%
- 使用 Redis 做分布式缓存, Kafka 处理订单异步消息
- 参与微服务拆分和服务治理, 编写接口文档和单元测试

技能清单:
编程语言: Java(熟练)、SQL
框架/工具: Spring Boot、MyBatis、MySQL、Redis、Kafka、Docker
领域知识: 微服务、RESTful API、分布式系统、数据库设计、缓存策略
其他: Linux、Git、Maven
待提升: Kubernetes、消息队列深度调优、高并发架构设计"""


# ================================================================
# 场景4: 低匹配 - 大模型JD vs 后端简历
# ================================================================

SCENARIO_4_JD = """岗位名称: 大模型算法工程师
岗位职责:
1. 负责企业知识库问答场景的大语言模型应用建设, 包括 RAG 检索增强生成、Prompt 优化。
2. 设计并优化向量召回、排序模型和问答链路, 提升答案准确率。
任职要求:
1. 本科及以上, 3 年以上 NLP 或大模型相关经验。
2. 熟练掌握 Python、PyTorch、Transformer、BERT 或大语言模型训练与推理流程。
3. 熟悉 LangChain、Milvus、Elasticsearch 等 RAG 工具。
4. 具备 Docker、FastAPI 工程化能力。"""

SCENARIO_4_RESUME = """姓名: 赵六
求职意向: Java后端开发工程师
教育背景:
- XX大学 软件工程 本科 2020-2024

工作经历:
2024.07 - 至今 | XX科技公司 | Java开发工程师
- 参与企业管理系统后端开发, 使用 Spring Boot 提供 RESTful API
- MySQL 数据库设计和 CRUD 操作
- Redis 缓存常用数据, 提升接口响应速度
- Git 版本管理, Linux 服务器基本操作

技能清单:
Java、Spring Boot、MySQL、Redis、Git、Linux、RESTful API
了解: Docker、Maven、MyBatis"""


# ================================================================
# 场景5: 跨领域完全不匹配 - 数据开发JD vs 前端简历
# ================================================================

SCENARIO_5_JD = """岗位名称: 数据开发工程师
岗位职责:
1. 负责金融风控业务的数据仓库建设、ETL 流程开发和数据质量治理。
2. 设计指标体系和主题数据集市, 支撑 BI 报表、风险监控和数据分析需求。
3. 优化 Spark、Hadoop、Flink 任务性能, 提升离线和准实时数据链路稳定性。
任职要求:
1. 本科及以上学历, 3 年以上数据开发、数据仓库或大数据平台经验。
2. 熟练掌握 SQL、Python 或 Scala, 熟悉 Spark、Hadoop、Flink、Airflow。
3. 理解数据建模、ETL、数据质量和调度监控体系。"""

SCENARIO_5_RESUME = """姓名: 孙七
求职意向: 前端开发工程师
教育背景:
- XX大学 数字媒体技术 本科 2021-2025

工作经历:
2025.03 - 至今 | XX互联网公司 | 前端开发工程师
- 使用 Vue3 + TypeScript 开发企业级 Web 应用
- Element Plus 组件库封装和业务页面搭建
- ECharts 数据可视化图表开发
- 与 UI 设计师协作还原设计稿, 保证像素级一致性

技能清单:
JavaScript、TypeScript、Vue3、React、HTML/CSS、Element Plus、ECharts
Webpack、Vite、Git、前端工程化
了解: Node.js、小程序开发"""


# ================================================================
# 场景6: 简历信息不足 - 信息太少难以匹配
# ================================================================

SCENARIO_6_JD = """岗位名称: 大模型算法工程师
岗位职责:
1. 负责企业知识库问答场景的大语言模型应用建设, 包括 RAG 检索增强生成。
2. 设计并优化向量召回、排序模型和问答链路。
任职要求:
1. 本科及以上, 3 年以上 NLP 或大模型相关经验。
2. 熟练掌握 Python、PyTorch、LangChain、Milvus 等 RAG 相关技术。
3. 熟悉 Docker、FastAPI、Linux。"""

SCENARIO_6_RESUME = """姓名: 周八
求职意向: 算法工程师
教育背景:
XX大学 计算机 本科 2022-2026

技能: 会用Python, 了解过机器学习基础"""


# ================================================================
# 快速引用字典 - 方便程序中使用
# ================================================================

TEST_CASES = {
    "scenario_1_high_match": {
        "name": "高度匹配 - 大模型",
        "jd": SCENARIO_1_JD,
        "resume": SCENARIO_1_RESUME,
        "expected_score_range": (80, 100),
    },
    "scenario_2_high_match_rec": {
        "name": "高度匹配 - 推荐",
        "jd": SCENARIO_2_JD,
        "resume": SCENARIO_2_RESUME,
        "expected_score_range": (75, 95),
    },
    "scenario_3_medium_match": {
        "name": "中等匹配 - 后端",
        "jd": SCENARIO_3_JD,
        "resume": SCENARIO_3_RESUME,
        "expected_score_range": (55, 80),
    },
    "scenario_4_low_match": {
        "name": "低匹配 - 大模型JD+后端简历",
        "jd": SCENARIO_4_JD,
        "resume": SCENARIO_4_RESUME,
        "expected_score_range": (20, 45),
    },
    "scenario_5_no_match": {
        "name": "不匹配 - 数据JD+前端简历",
        "jd": SCENARIO_5_JD,
        "resume": SCENARIO_5_RESUME,
        "expected_score_range": (0, 25),
    },
    "scenario_6_insufficient_resume": {
        "name": "简历信息不足",
        "jd": SCENARIO_6_JD,
        "resume": SCENARIO_6_RESUME,
        "expected_score_range": (10, 35),
    },
}


if __name__ == "__main__":
    print("=" * 60)
    print("  测试样例数据 - 共 6 组场景")
    print("=" * 60)
    for key, case in TEST_CASES.items():
        print(f"\n[{key}]")
        print(f"  名称: {case['name']}")
        print(f"  预期分数: {case['expected_score_range'][0]}-{case['expected_score_range'][1]}")
        print(f"  JD长度: {len(case['jd'])} 字符")
        print(f"  简历长度: {len(case['resume'])} 字符")
