# JD Parser Manual Review Report

## JD_SAMPLE_001

### 原始 JD
```text
岗位名称：NLP算法工程师
工作地点：南京
岗位职责：
1. 负责信息抽取模型研发
2. 参与RAG系统建设
任职要求：
1. 熟练使用Python和PyTorch
2. 具备2年以上自然语言处理相关经验
加分项：
有知识图谱经验者优先
```

### cleaned_text
```text
岗位名称：NLP算法工程师
工作地点：南京
岗位职责：
1. 负责信息抽取模型研发
2. 参与RAG系统建设
任职要求：
1. 熟练使用Python和PyTorch
2. 具备2年以上自然语言处理相关经验
加分项：
有知识图谱经验者优先
```

### Profile
```json
{
  "schema_version": "jd_profile_v1",
  "document_id": "JD_SAMPLE_001",
  "document_type": "job",
  "title": "NLP算法工程师",
  "responsibilities": [
    "负责信息抽取模型研发",
    "参与RAG系统建设"
  ],
  "requirements": [
    "熟练使用Python和PyTorch",
    "具备2年以上自然语言处理相关经验"
  ],
  "preferred": [
    "有知识图谱经验者优先"
  ],
  "skills": [
    {
      "name": "信息抽取",
      "level": "mentioned",
      "evidence": "负责信息抽取模型研发"
    },
    {
      "name": "RAG",
      "level": "mentioned",
      "evidence": "参与RAG系统建设"
    },
    {
      "name": "Python",
      "level": "required",
      "evidence": "熟练使用Python和PyTorch"
    },
    {
      "name": "PyTorch",
      "level": "required",
      "evidence": "熟练使用Python和PyTorch"
    },
    {
      "name": "自然语言处理",
      "level": "required",
      "evidence": "具备2年以上自然语言处理相关经验"
    },
    {
      "name": "知识图谱",
      "level": "preferred",
      "evidence": "有知识图谱经验者优先"
    }
  ],
  "constraints": {
    "education": {
      "value": null,
      "evidence": null
    },
    "experience_years": {
      "value": 2,
      "evidence": "2. 具备2年以上自然语言处理相关经验"
    },
    "location": {
      "value": "南京",
      "evidence": "工作地点：南京"
    }
  },
  "raw_text": "岗位名称：NLP算法工程师\n工作地点：南京\n岗位职责：\n1. 负责信息抽取模型研发\n2. 参与RAG系统建设\n任职要求：\n1. 熟练使用Python和PyTorch\n2. 具备2年以上自然语言处理相关经验\n加分项：\n有知识图谱经验者优先"
}
```

### validation 状态
valid

### serialized_text
```text
[岗位名称]
NLP算法工程师

[岗位职责]
负责信息抽取模型研发；
参与RAG系统建设

[任职要求]
熟练使用Python和PyTorch；
具备2年以上自然语言处理相关经验

[必需技能]
Python；PyTorch；自然语言处理

[相关技能]
信息抽取；RAG

[优先技能]
知识图谱

[经验要求]
2年以上

[工作地点]
南京
```

## JD_SAMPLE_002

### 原始 JD
```text
岗位名称：AI应用开发工程师
岗位职责：
负责大模型应用开发
参与Agent工作流设计
推动模型部署落地
```

### cleaned_text
```text
岗位名称：AI应用开发工程师
岗位职责：
负责大模型应用开发
参与Agent工作流设计
推动模型部署落地
```

### Profile
```json
{
  "schema_version": "jd_profile_v1",
  "document_id": "JD_SAMPLE_002",
  "document_type": "job",
  "title": "AI应用开发工程师",
  "responsibilities": [
    "负责大模型应用开发",
    "参与Agent工作流设计",
    "推动模型部署落地"
  ],
  "requirements": [],
  "preferred": [],
  "skills": [
    {
      "name": "大模型",
      "level": "mentioned",
      "evidence": "负责大模型应用开发"
    },
    {
      "name": "Agent",
      "level": "mentioned",
      "evidence": "参与Agent工作流设计"
    },
    {
      "name": "模型部署",
      "level": "mentioned",
      "evidence": "推动模型部署落地"
    }
  ],
  "constraints": {
    "education": {
      "value": null,
      "evidence": null
    },
    "experience_years": {
      "value": null,
      "evidence": null
    },
    "location": {
      "value": null,
      "evidence": null
    }
  },
  "raw_text": "岗位名称：AI应用开发工程师\n岗位职责：\n负责大模型应用开发\n参与Agent工作流设计\n推动模型部署落地"
}
```

### validation 状态
valid

### serialized_text
```text
[岗位名称]
AI应用开发工程师

[岗位职责]
负责大模型应用开发；
参与Agent工作流设计；
推动模型部署落地

[相关技能]
大模型；Agent；模型部署
```

## JD_SAMPLE_003

### 原始 JD
```text
岗位名称：计算机视觉算法工程师
任职要求：
硕士及以上学历
熟悉OpenCV和PyTorch
具备3年以上计算机视觉项目经验
```

### cleaned_text
```text
岗位名称：计算机视觉算法工程师
任职要求：
硕士及以上学历
熟悉OpenCV和PyTorch
具备3年以上计算机视觉项目经验
```

### Profile
```json
{
  "schema_version": "jd_profile_v1",
  "document_id": "JD_SAMPLE_003",
  "document_type": "job",
  "title": "计算机视觉算法工程师",
  "responsibilities": [],
  "requirements": [
    "硕士及以上学历",
    "熟悉OpenCV和PyTorch",
    "具备3年以上计算机视觉项目经验"
  ],
  "preferred": [],
  "skills": [
    {
      "name": "OpenCV",
      "level": "required",
      "evidence": "熟悉OpenCV和PyTorch"
    },
    {
      "name": "PyTorch",
      "level": "required",
      "evidence": "熟悉OpenCV和PyTorch"
    },
    {
      "name": "计算机视觉",
      "level": "required",
      "evidence": "具备3年以上计算机视觉项目经验"
    }
  ],
  "constraints": {
    "education": {
      "value": "硕士及以上",
      "evidence": "硕士及以上学历"
    },
    "experience_years": {
      "value": 3,
      "evidence": "具备3年以上计算机视觉项目经验"
    },
    "location": {
      "value": null,
      "evidence": null
    }
  },
  "raw_text": "岗位名称：计算机视觉算法工程师\n任职要求：\n硕士及以上学历\n熟悉OpenCV和PyTorch\n具备3年以上计算机视觉项目经验"
}
```

### validation 状态
valid

### serialized_text
```text
[岗位名称]
计算机视觉算法工程师

[任职要求]
硕士及以上学历；
熟悉OpenCV和PyTorch；
具备3年以上计算机视觉项目经验

[必需技能]
OpenCV；PyTorch；计算机视觉

[学历要求]
硕士及以上

[经验要求]
3年以上
```

## JD_SAMPLE_004

### 原始 JD
```text
岗位名称：Machine Learning Engineer
Location：上海
Responsibilities:
Build ML pipeline with Python and TensorFlow
Requirements:
Familiar with Docker, Kubernetes and Git
```

### cleaned_text
```text
岗位名称：Machine Learning Engineer
Location：上海
Responsibilities:
Build ML pipeline with Python and TensorFlow
Requirements:
Familiar with Docker, Kubernetes and Git
```

### Profile
```json
{
  "schema_version": "jd_profile_v1",
  "document_id": "JD_SAMPLE_004",
  "document_type": "job",
  "title": "Machine Learning Engineer",
  "responsibilities": [
    "Build ML pipeline with Python and TensorFlow"
  ],
  "requirements": [
    "Familiar with Docker, Kubernetes and Git"
  ],
  "preferred": [],
  "skills": [
    {
      "name": "Python",
      "level": "mentioned",
      "evidence": "Build ML pipeline with Python and TensorFlow"
    },
    {
      "name": "TensorFlow",
      "level": "mentioned",
      "evidence": "Build ML pipeline with Python and TensorFlow"
    },
    {
      "name": "Docker",
      "level": "required",
      "evidence": "Familiar with Docker, Kubernetes and Git"
    },
    {
      "name": "Kubernetes",
      "level": "required",
      "evidence": "Familiar with Docker, Kubernetes and Git"
    },
    {
      "name": "Git",
      "level": "required",
      "evidence": "Familiar with Docker, Kubernetes and Git"
    }
  ],
  "constraints": {
    "education": {
      "value": null,
      "evidence": null
    },
    "experience_years": {
      "value": null,
      "evidence": null
    },
    "location": {
      "value": "上海",
      "evidence": "Location：上海"
    }
  },
  "raw_text": "岗位名称：Machine Learning Engineer\nLocation：上海\nResponsibilities:\nBuild ML pipeline with Python and TensorFlow\nRequirements:\nFamiliar with Docker, Kubernetes and Git"
}
```

### validation 状态
valid

### serialized_text
```text
[岗位名称]
Machine Learning Engineer

[岗位职责]
Build ML pipeline with Python and TensorFlow

[任职要求]
Familiar with Docker, Kubernetes and Git

[必需技能]
Docker；Kubernetes；Git

[相关技能]
Python；TensorFlow

[工作地点]
上海
```

## JD_SAMPLE_005

### 原始 JD
```text
岗位名称：推荐算法工程师
任职要求：熟练掌握Python、Spark、Flink、Kafka，具备推荐系统经验
```

### cleaned_text
```text
岗位名称：推荐算法工程师
任职要求：熟练掌握Python、Spark、Flink、Kafka，具备推荐系统经验
```

### Profile
```json
{
  "schema_version": "jd_profile_v1",
  "document_id": "JD_SAMPLE_005",
  "document_type": "job",
  "title": "推荐算法工程师",
  "responsibilities": [],
  "requirements": [
    "熟练掌握Python、Spark、Flink、Kafka，具备推荐系统经验"
  ],
  "preferred": [],
  "skills": [
    {
      "name": "Python",
      "level": "required",
      "evidence": "熟练掌握Python、Spark、Flink、Kafka，具备推荐系统经验"
    },
    {
      "name": "Spark",
      "level": "required",
      "evidence": "熟练掌握Python、Spark、Flink、Kafka，具备推荐系统经验"
    },
    {
      "name": "Flink",
      "level": "required",
      "evidence": "熟练掌握Python、Spark、Flink、Kafka，具备推荐系统经验"
    },
    {
      "name": "Kafka",
      "level": "required",
      "evidence": "熟练掌握Python、Spark、Flink、Kafka，具备推荐系统经验"
    },
    {
      "name": "推荐系统",
      "level": "required",
      "evidence": "熟练掌握Python、Spark、Flink、Kafka，具备推荐系统经验"
    }
  ],
  "constraints": {
    "education": {
      "value": null,
      "evidence": null
    },
    "experience_years": {
      "value": null,
      "evidence": null
    },
    "location": {
      "value": null,
      "evidence": null
    }
  },
  "raw_text": "岗位名称：推荐算法工程师\n任职要求：熟练掌握Python、Spark、Flink、Kafka，具备推荐系统经验"
}
```

### validation 状态
valid

### serialized_text
```text
[岗位名称]
推荐算法工程师

[任职要求]
熟练掌握Python、Spark、Flink、Kafka，具备推荐系统经验

[必需技能]
Python；Spark；Flink；Kafka；推荐系统
```

## JD_SAMPLE_006

### 原始 JD
```text
岗位名称：知识图谱算法工程师
岗位职责：负责知识图谱构建和信息抽取
任职要求：熟悉Python
优先条件：有RAG或大模型经验者优先
```

### cleaned_text
```text
岗位名称：知识图谱算法工程师
岗位职责：负责知识图谱构建和信息抽取
任职要求：熟悉Python
优先条件：有RAG或大模型经验者优先
```

### Profile
```json
{
  "schema_version": "jd_profile_v1",
  "document_id": "JD_SAMPLE_006",
  "document_type": "job",
  "title": "知识图谱算法工程师",
  "responsibilities": [
    "负责知识图谱构建和信息抽取"
  ],
  "requirements": [
    "熟悉Python"
  ],
  "preferred": [
    "有RAG或大模型经验者优先"
  ],
  "skills": [
    {
      "name": "知识图谱",
      "level": "mentioned",
      "evidence": "负责知识图谱构建和信息抽取"
    },
    {
      "name": "信息抽取",
      "level": "mentioned",
      "evidence": "负责知识图谱构建和信息抽取"
    },
    {
      "name": "Python",
      "level": "required",
      "evidence": "熟悉Python"
    },
    {
      "name": "RAG",
      "level": "preferred",
      "evidence": "有RAG或大模型经验者优先"
    },
    {
      "name": "大模型",
      "level": "preferred",
      "evidence": "有RAG或大模型经验者优先"
    }
  ],
  "constraints": {
    "education": {
      "value": null,
      "evidence": null
    },
    "experience_years": {
      "value": null,
      "evidence": null
    },
    "location": {
      "value": null,
      "evidence": null
    }
  },
  "raw_text": "岗位名称：知识图谱算法工程师\n岗位职责：负责知识图谱构建和信息抽取\n任职要求：熟悉Python\n优先条件：有RAG或大模型经验者优先"
}
```

### validation 状态
valid

### serialized_text
```text
[岗位名称]
知识图谱算法工程师

[岗位职责]
负责知识图谱构建和信息抽取

[任职要求]
熟悉Python

[必需技能]
Python

[相关技能]
知识图谱；信息抽取

[优先技能]
RAG；大模型
```

## JD_SAMPLE_007

### 原始 JD
```text
岗位名称：数据挖掘工程师
工作地点：杭州
岗位职责：负责用户行为数据分析和模型训练
任职要求：熟练使用SQL和Python
```

### cleaned_text
```text
岗位名称：数据挖掘工程师
工作地点：杭州
岗位职责：负责用户行为数据分析和模型训练
任职要求：熟练使用SQL和Python
```

### Profile
```json
{
  "schema_version": "jd_profile_v1",
  "document_id": "JD_SAMPLE_007",
  "document_type": "job",
  "title": "数据挖掘工程师",
  "responsibilities": [
    "负责用户行为数据分析和模型训练"
  ],
  "requirements": [
    "熟练使用SQL和Python"
  ],
  "preferred": [],
  "skills": [
    {
      "name": "数据分析",
      "level": "mentioned",
      "evidence": "负责用户行为数据分析和模型训练"
    },
    {
      "name": "模型训练",
      "level": "mentioned",
      "evidence": "负责用户行为数据分析和模型训练"
    },
    {
      "name": "SQL",
      "level": "required",
      "evidence": "熟练使用SQL和Python"
    },
    {
      "name": "Python",
      "level": "required",
      "evidence": "熟练使用SQL和Python"
    }
  ],
  "constraints": {
    "education": {
      "value": null,
      "evidence": null
    },
    "experience_years": {
      "value": null,
      "evidence": null
    },
    "location": {
      "value": "杭州",
      "evidence": "工作地点：杭州"
    }
  },
  "raw_text": "岗位名称：数据挖掘工程师\n工作地点：杭州\n岗位职责：负责用户行为数据分析和模型训练\n任职要求：熟练使用SQL和Python"
}
```

### validation 状态
valid

### serialized_text
```text
[岗位名称]
数据挖掘工程师

[岗位职责]
负责用户行为数据分析和模型训练

[任职要求]
熟练使用SQL和Python

[必需技能]
SQL；Python

[相关技能]
数据分析；模型训练

[工作地点]
杭州
```

## JD_SAMPLE_008

### 原始 JD
```text
岗位名称：模型部署工程师
工作地点：深圳
岗位职责：负责模型推理服务优化
任职要求：熟悉Linux、Docker、TensorRT
```

### cleaned_text
```text
岗位名称：模型部署工程师
工作地点：深圳
岗位职责：负责模型推理服务优化
任职要求：熟悉Linux、Docker、TensorRT
```

### Profile
```json
{
  "schema_version": "jd_profile_v1",
  "document_id": "JD_SAMPLE_008",
  "document_type": "job",
  "title": "模型部署工程师",
  "responsibilities": [
    "负责模型推理服务优化"
  ],
  "requirements": [
    "熟悉Linux、Docker、TensorRT"
  ],
  "preferred": [],
  "skills": [
    {
      "name": "模型推理",
      "level": "mentioned",
      "evidence": "负责模型推理服务优化"
    },
    {
      "name": "Linux",
      "level": "required",
      "evidence": "熟悉Linux、Docker、TensorRT"
    },
    {
      "name": "Docker",
      "level": "required",
      "evidence": "熟悉Linux、Docker、TensorRT"
    },
    {
      "name": "TensorRT",
      "level": "required",
      "evidence": "熟悉Linux、Docker、TensorRT"
    }
  ],
  "constraints": {
    "education": {
      "value": null,
      "evidence": null
    },
    "experience_years": {
      "value": null,
      "evidence": null
    },
    "location": {
      "value": "深圳",
      "evidence": "工作地点：深圳"
    }
  },
  "raw_text": "岗位名称：模型部署工程师\n工作地点：深圳\n岗位职责：负责模型推理服务优化\n任职要求：熟悉Linux、Docker、TensorRT"
}
```

### validation 状态
valid

### serialized_text
```text
[岗位名称]
模型部署工程师

[岗位职责]
负责模型推理服务优化

[任职要求]
熟悉Linux、Docker、TensorRT

[必需技能]
Linux；Docker；TensorRT

[相关技能]
模型推理

[工作地点]
深圳
```

## JD_SAMPLE_009

### 原始 JD
```text
岗位名称：嵌入式算法工程师
岗位要求：本科及以上学历，3-5年控制算法经验，熟悉Matlab/Simulink
```

### cleaned_text
```text
岗位名称：嵌入式算法工程师
岗位要求：本科及以上学历，3-5年控制算法经验，熟悉Matlab/Simulink
```

### Profile
```json
{
  "schema_version": "jd_profile_v1",
  "document_id": "JD_SAMPLE_009",
  "document_type": "job",
  "title": "嵌入式算法工程师",
  "responsibilities": [],
  "requirements": [
    "本科及以上学历，3-5年控制算法经验，熟悉Matlab/Simulink"
  ],
  "preferred": [],
  "skills": [
    {
      "name": "控制算法",
      "level": "required",
      "evidence": "本科及以上学历，3-5年控制算法经验，熟悉Matlab/Simulink"
    },
    {
      "name": "Matlab",
      "level": "required",
      "evidence": "本科及以上学历，3-5年控制算法经验，熟悉Matlab/Simulink"
    },
    {
      "name": "Simulink",
      "level": "required",
      "evidence": "本科及以上学历，3-5年控制算法经验，熟悉Matlab/Simulink"
    }
  ],
  "constraints": {
    "education": {
      "value": "本科及以上",
      "evidence": "岗位要求：本科及以上学历，3-5年控制算法经验，熟悉Matlab/Simulink"
    },
    "experience_years": {
      "value": 3,
      "evidence": "岗位要求：本科及以上学历，3-5年控制算法经验，熟悉Matlab/Simulink"
    },
    "location": {
      "value": null,
      "evidence": null
    }
  },
  "raw_text": "岗位名称：嵌入式算法工程师\n岗位要求：本科及以上学历，3-5年控制算法经验，熟悉Matlab/Simulink"
}
```

### validation 状态
valid

### serialized_text
```text
[岗位名称]
嵌入式算法工程师

[任职要求]
本科及以上学历，3-5年控制算法经验，熟悉Matlab/Simulink

[必需技能]
控制算法；Matlab；Simulink

[学历要求]
本科及以上

[经验要求]
3年以上
```

## JD_SAMPLE_010

### 原始 JD
```text
首页
岗位名称：AI工程师

岗位职责：负责AI系统设计
岗位职责：负责AI系统设计
立即申请
任职要求：熟悉Python和Linux
```

### cleaned_text
```text
岗位名称：AI工程师

岗位职责：负责AI系统设计
任职要求：熟悉Python和Linux
```

### Profile
```json
{
  "schema_version": "jd_profile_v1",
  "document_id": "JD_SAMPLE_010",
  "document_type": "job",
  "title": "AI工程师",
  "responsibilities": [
    "负责AI系统设计"
  ],
  "requirements": [
    "熟悉Python和Linux"
  ],
  "preferred": [],
  "skills": [
    {
      "name": "系统设计",
      "level": "mentioned",
      "evidence": "负责AI系统设计"
    },
    {
      "name": "Python",
      "level": "required",
      "evidence": "熟悉Python和Linux"
    },
    {
      "name": "Linux",
      "level": "required",
      "evidence": "熟悉Python和Linux"
    }
  ],
  "constraints": {
    "education": {
      "value": null,
      "evidence": null
    },
    "experience_years": {
      "value": null,
      "evidence": null
    },
    "location": {
      "value": null,
      "evidence": null
    }
  },
  "raw_text": "首页\n岗位名称：AI工程师\n\n岗位职责：负责AI系统设计\n岗位职责：负责AI系统设计\n立即申请\n任职要求：熟悉Python和Linux"
}
```

### validation 状态
valid

### serialized_text
```text
[岗位名称]
AI工程师

[岗位职责]
负责AI系统设计

[任职要求]
熟悉Python和Linux

[必需技能]
Python；Linux

[相关技能]
系统设计
```

## JD_SAMPLE_011

### 原始 JD
```text
岗位名称：语音算法工程师
公司介绍：我们是一家快速发展的公司
福利待遇：五险一金、年终奖
岗位职责：负责ASR和TTS算法开发
任职要求：硕士以上学历，熟悉深度学习
```

### cleaned_text
```text
岗位名称：语音算法工程师
公司介绍：我们是一家快速发展的公司
福利待遇：五险一金、年终奖
岗位职责：负责ASR和TTS算法开发
任职要求：硕士以上学历，熟悉深度学习
```

### Profile
```json
{
  "schema_version": "jd_profile_v1",
  "document_id": "JD_SAMPLE_011",
  "document_type": "job",
  "title": "语音算法工程师",
  "responsibilities": [
    "负责ASR和TTS算法开发"
  ],
  "requirements": [
    "硕士以上学历，熟悉深度学习"
  ],
  "preferred": [],
  "skills": [
    {
      "name": "ASR",
      "level": "mentioned",
      "evidence": "负责ASR和TTS算法开发"
    },
    {
      "name": "TTS",
      "level": "mentioned",
      "evidence": "负责ASR和TTS算法开发"
    },
    {
      "name": "算法开发",
      "level": "mentioned",
      "evidence": "负责ASR和TTS算法开发"
    },
    {
      "name": "深度学习",
      "level": "required",
      "evidence": "硕士以上学历，熟悉深度学习"
    }
  ],
  "constraints": {
    "education": {
      "value": "硕士以上",
      "evidence": "任职要求：硕士以上学历，熟悉深度学习"
    },
    "experience_years": {
      "value": null,
      "evidence": null
    },
    "location": {
      "value": null,
      "evidence": null
    }
  },
  "raw_text": "岗位名称：语音算法工程师\n公司介绍：我们是一家快速发展的公司\n福利待遇：五险一金、年终奖\n岗位职责：负责ASR和TTS算法开发\n任职要求：硕士以上学历，熟悉深度学习"
}
```

### validation 状态
valid

### serialized_text
```text
[岗位名称]
语音算法工程师

[岗位职责]
负责ASR和TTS算法开发

[任职要求]
硕士以上学历，熟悉深度学习

[必需技能]
深度学习

[相关技能]
ASR；TTS；算法开发

[学历要求]
硕士以上
```

## JD_SAMPLE_012

### 原始 JD
```text
岗位名称：多模态大模型工程师
岗位职责：
负责多模态大模型训练
参与Transformer模型优化
任职要求：
熟悉CUDA、PyTorch和模型微调
优先：有LoRA经验者优先
```

### cleaned_text
```text
岗位名称：多模态大模型工程师
岗位职责：
负责多模态大模型训练
参与Transformer模型优化
任职要求：
熟悉CUDA、PyTorch和模型微调
优先：有LoRA经验者优先
```

### Profile
```json
{
  "schema_version": "jd_profile_v1",
  "document_id": "JD_SAMPLE_012",
  "document_type": "job",
  "title": "多模态大模型工程师",
  "responsibilities": [
    "负责多模态大模型训练",
    "参与Transformer模型优化"
  ],
  "requirements": [
    "熟悉CUDA、PyTorch和模型微调"
  ],
  "preferred": [
    "有LoRA经验者优先"
  ],
  "skills": [
    {
      "name": "多模态",
      "level": "mentioned",
      "evidence": "负责多模态大模型训练"
    },
    {
      "name": "大模型",
      "level": "mentioned",
      "evidence": "负责多模态大模型训练"
    },
    {
      "name": "Transformer",
      "level": "mentioned",
      "evidence": "参与Transformer模型优化"
    },
    {
      "name": "CUDA",
      "level": "required",
      "evidence": "熟悉CUDA、PyTorch和模型微调"
    },
    {
      "name": "PyTorch",
      "level": "required",
      "evidence": "熟悉CUDA、PyTorch和模型微调"
    },
    {
      "name": "模型微调",
      "level": "required",
      "evidence": "熟悉CUDA、PyTorch和模型微调"
    },
    {
      "name": "LoRA",
      "level": "preferred",
      "evidence": "有LoRA经验者优先"
    }
  ],
  "constraints": {
    "education": {
      "value": null,
      "evidence": null
    },
    "experience_years": {
      "value": null,
      "evidence": null
    },
    "location": {
      "value": null,
      "evidence": null
    }
  },
  "raw_text": "岗位名称：多模态大模型工程师\n岗位职责：\n负责多模态大模型训练\n参与Transformer模型优化\n任职要求：\n熟悉CUDA、PyTorch和模型微调\n优先：有LoRA经验者优先"
}
```

### validation 状态
valid

### serialized_text
```text
[岗位名称]
多模态大模型工程师

[岗位职责]
负责多模态大模型训练；
参与Transformer模型优化

[任职要求]
熟悉CUDA、PyTorch和模型微调

[必需技能]
CUDA；PyTorch；模型微调

[相关技能]
多模态；大模型；Transformer

[优先技能]
LoRA
```
