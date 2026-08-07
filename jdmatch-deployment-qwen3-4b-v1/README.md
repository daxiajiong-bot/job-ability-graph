# Qwen3-Embedding-4B 人岗匹配实验结果说明

本目录保存了“JD—简历匹配”实验的运行报告和训练日志。实验使用
`Qwen3-Embedding-4B` 作为最终双塔编码器，通过 LoRA 和对比学习进行领域适配；
`BGE-M3` 与 `BGE-reranker-v2-m3` 只用于冻结基线和离线困难负样本挖掘。

> 重要：本目录当前只包含指标、manifest 和训练日志，不包含服务器上的
> `best_adapter/`、`checkpoints/` 与负样本明细 `train_groups.jsonl`。
> 因此可以审计实验结果，但不能仅凭本目录加载微调后的模型。正式归档时应从服务器
> 一并复制 `best_adapter/`，并建议保留最后一个完整 checkpoint。

## 1. 实验流程

```text
清洗后的真实岗位 JD
        │
        ├─ Qwen-Plus 按 JD 生成 P1、P2、H1 三类合成简历
        │
        ├─ BGE-M3 对跨 JD 简历做稠密召回
        │
        ├─ BGE-reranker-v2-m3 复核困难负样本
        │
        └─ Qwen3-Embedding-4B LoRA 双塔对比学习
                         │
                         └─ 验证集、测试集全库检索评测
```

三个模型的具体作用如下：

| 模型 | 作用 | 是否参与最终评测排序 |
|---|---|---|
| BGE-M3 | 冻结基线、离线粗召回困难负样本 | 仅作为一条冻结基线 |
| BGE-reranker-v2-m3 | 离线教师，复核 BGE-M3 召回候选 | 否 |
| Qwen3-Embedding-4B | 共享权重双塔编码器，进行 LoRA 微调 | 是 |

当前实现并不是线上“BGE 召回后再由 Qwen 重排”的服务。最终评测中，
微调后的 Qwen 直接对评测集合中的全部候选简历进行向量检索。

## 2. 数据规模

运行时数据包含：

| 数据 | 数量 |
|---|---:|
| JD | 8,407 |
| 合成简历 | 25,221 |
| 生成契约 | 8,407 |

数据切分：

| Split | JD | 简历 |
|---|---:|---:|
| train | 6,725 | 20,175 |
| validation | 841 | 2,523 |
| test | 841 | 2,523 |

每个 JD 对应三份合成简历：

- `P1`：正样本，满足岗位核心要求；
- `P2`：第二个正样本，采用不同职业路径或项目场景；
- `H1`：同领域近失配样本，整体相关但缺少一项指定核心能力。

合计有 16,814 份正样本和 8,407 份 H1。数据按照 JD 近重复簇进行
train/validation/test 整簇划分，避免高度相似的 JD 跨集合泄漏。

### 合成数据说明

这些简历不是企业真实求职者简历，而是基于 JD 条件生成的匿名化合成候选人画像。
模型输入文本中不包含 `P1`、`P2`、`H1`、`positive`、`relevance`、
`jd_id` 或 `resume_id` 等标签字段。

全量生成数据的 JSON 可解析、三元组结构、匿名化和标签槽位完整率为 100%；
但更严格的语义契约校验通过 4,044/8,407 组，即 48.10%，另外 4,363 组
存在至少一项严格语义警告。当前训练采用全部结构安全数据，因此实验可能受到一定的
弱监督标签噪声影响。后续应增加 strict-only 消融和人工抽样复核。

## 3. 模型实际输入

模型不会直接读取原始 JSON，而是读取序列化后的自然语言文本。

JD 文本顺序：

```text
岗位名称
学历要求
经验要求
任职要求
岗位职责
```

Qwen 的 JD 侧会在运行时增加检索指令：

```text
Instruct: Given a job description, retrieve candidate resumes that satisfy core skills, experience, and education requirements.
Query:<序列化后的 JD 文本>
```

简历文本顺序：

```text
相关经验
技能
工作经历
项目经历
教育
```

Tokenizer 最大长度为 512 token。Qwen 使用左填充和最后一个有效 token
的隐藏状态进行池化，截取前 1,024 维后做 L2 归一化。JD 与简历相似度为
归一化向量的点积，即余弦相似度。

## 4. 模型与 LoRA 配置

当前双塔是共享参数的 Siamese Bi-Encoder，不是两个相互独立的 4B 模型。
JD 和简历共用同一个 `Qwen3-Embedding-4B`，仅 JD 侧增加查询指令。

| 配置 | 值 |
|---|---|
| 基础模型 | Qwen3-Embedding-4B |
| 精度 | BF16 |
| 最大长度 | 512 token |
| 输出维度 | 1,024 |
| LoRA rank | 16 |
| LoRA alpha | 32 |
| LoRA dropout | 0.05 |
| LoRA目标层 | q_proj、k_proj、v_proj、o_proj |
| Gradient Checkpointing | 开启 |
| 量化 | 无 |
| Attention实现 | PyTorch SDPA |

参数规模：

| 参数 | 数量 |
|---|---:|
| 总参数 | 4,033,570,816 |
| 可训练 LoRA 参数 | 11,796,480 |
| 可训练比例 | 0.292457% |

LoRA 将原权重更新表示为：

```text
W' = W + (alpha / rank) * B * A
```

本实验中 `alpha/rank = 2`，基础模型权重冻结，只训练低秩适配参数。

## 5. 负样本挖掘

训练集共有 6,725 个 JD，BGE-M3 的候选池使用训练集 P1/P2，共 13,450
份简历。每个 JD 的挖掘过程为：

1. BGE-M3 召回稠密相似度 Top 200；
2. 排除本 JD 简历和同一近重复簇简历；
3. 结合学历、工作年限和关键能力缺口进行规则过滤；
4. 取前 24 个候选交给 BGE reranker 复核；
5. 优先保留同岗位族、与正样本相似但存在明确能力缺口的候选；
6. 为每个 JD 建立最多 12 份困难负样本池；
7. 从跨岗位族低相似候选中建立简单负样本池。

负样本池结果：

| 指标 | 结果 |
|---|---:|
| 平均困难池大小 | 11.168 |
| 至少有 2 个困难负样本的 JD | 6,610（98.29%） |
| 至少有 6 个困难负样本的 JD | 6,308（93.80%） |
| 挖掘耗时 | 4,734.501 秒（约 1 小时 19 分） |

困难负样本的主要缺口统计：

| 原因 | 次数 |
|---|---:|
| 缺少关键能力 | 35,019 |
| 工作经验不足 | 31,882 |
| 学历不足 | 20,895 |

## 6. 训练 Batch

一个完整逻辑 batch 包含 16 个 JD。每个 JD 理想情况下包含：

```text
2 个正样本 P1/P2
1 个近失配样本 H1
2 个跨 JD 困难负样本
1 个跨岗位族简单负样本
```

因此完整 batch 为 16 个 JD、96 份简历，共 112 段文本。实际日志中平均
每步有 15.97 个 JD 和 95.44 份简历；少数 JD 的困难池不足 2 条，因此
个别 batch 少于 96 份简历。

除显式负样本外，其他 JD 的非 H1 文档会成为 batch 内负样本。完整 batch
中，每个 JD 面对 2 个正样本和约 78 个潜在负候选。疑似也适合该 JD 的
跨 JD 简历通过全局 mask 排除，减少假负样本污染。

## 7. 训练目标

设归一化后的 JD 向量为 `q_i`，简历向量为 `d_j`，相似度为：

```text
s(i,j) = q_i · d_j
```

总损失由三部分组成：

```text
L = L_InfoNCE + 0.5 * L_H1 + 1.0 * L_hard
```

### 多正样本 InfoNCE

每个 JD 的 P1、P2 共同进入分子：

```text
L_InfoNCE(i) = -log(
    sum(exp(s(i,p) / temperature), p in {P1,P2})
    /
    sum(exp(s(i,d) / temperature), d in valid documents)
)
```

`temperature = 0.05`。H1 不进入 InfoNCE 分母，而是单独使用 margin loss。

### H1 Margin Loss

```text
positive_score = mean(s(i,P1), s(i,P2))
L_H1 = ReLU(0.05 - positive_score + s(i,H1))
```

要求正样本平均得分至少比 H1 高 0.05。

### 跨 JD 困难负样本 Margin Loss

```text
L_hard = ReLU(0.10 - positive_score + s(i,hard_negative))
```

跨 JD 困难负样本同时参与 InfoNCE 分母和 margin loss。简单负样本与
batch 内负样本只参与 InfoNCE。

## 8. GradCache 与显存

逻辑 batch 虽然包含约 112 段文本，但 GradCache 每次只处理 2 段文本：

1. 无梯度地分块计算并缓存所有 Embedding；
2. 在完整 Embedding batch 上计算全局损失和 Embedding 梯度；
3. 按原随机状态重放每个文本微批，将缓存梯度传播到 LoRA 参数。

这样同时保留了大 batch 的 batch 内负样本与全局 mask，又大幅降低显存。

预检结果：

| 指标 | 结果 |
|---|---:|
| GPU | NVIDIA GeForce RTX 3090 |
| 可见 GPU 数 | 1 |
| CUDA_VISIBLE_DEVICES | 0 |
| BF16 | 支持 |
| 文本微批 | 2 |
| 峰值 allocated 显存 | 8.0861 GiB |
| 峰值 reserved 显存 | 8.3418 GiB |
| OOM 回退 | 0 次 |

服务器未安装或未成功导入 FlashAttention 2，因此实际使用 SDPA。

## 9. 训练过程

| 超参数 | 值 |
|---|---:|
| Epoch | 3 |
| JD batch size | 16 |
| 每轮步数 | 421 |
| 总步数 | 1,263 |
| 优化器 | AdamW |
| 学习率 | 2e-5 |
| Weight decay | 0.01 |
| Warmup | 5% |
| 最大梯度范数 | 1.0 |
| 随机种子 | 20260730 |

逐轮平均损失：

| Epoch | 总损失 | InfoNCE | H1 margin | Hard margin |
|---:|---:|---:|---:|---:|
| 1 | 0.06463 | 0.06088 | 0.00293 | 0.00228 |
| 2 | 0.01027 | 0.00924 | 0.00117 | 0.00044 |
| 3 | 0.00874 | 0.00797 | 0.00088 | 0.00033 |

训练稳定性：

- 完成 1,263 个连续训练步；
- 无 NaN、Inf 或零梯度异常；
- 无 CUDA OOM；
- GradCache 全程保持文本微批 2；
- 平均每步 35.82 秒；
- 训练耗时 45,274.765 秒，约 12 小时 35 分钟。

日志中的 `gradient_norm` 是裁剪前范数；优化前会按配置裁剪到最大 1.0。

## 10. 指标定义

验证集和测试集分别包含 841 个 JD、2,523 份简历。每个 JD 只有源 JD
生成的 P1/P2 被标为已知相关。

- `Recall@K`：两个已知正样本中有多少进入 Top K；
- `MRR`：第一个正样本排名的倒数；
- `NDCG@10`：两个正样本在 Top 10 中的排序质量；
- `mean_known_positive_rank`：两个正样本的平均排名；
- `pairwise_p_over_h1_accuracy`：P1/P2 分别高于 H1 的比例；
- `strict_both_positives_over_h1`：P1、P2 同时高于 H1 的 JD 比例。

由于每个 JD 有两个正样本，`Recall@1` 的理论最大值为 0.5，而不是 1.0。

## 11. 最终测试集结果

测试候选池为全部 2,523 份测试简历。

| 模型 | MRR | NDCG@10 | R@1 | R@2 | R@5 | R@10 | 正样本平均排名 |
|---|---:|---:|---:|---:|---:|---:|---:|
| BGE-M3 冻结 | 0.6661 | 0.6042 | 0.2776 | 0.4560 | 0.6130 | 0.7081 | 28.96 |
| Qwen3-4B 冻结 | 0.9423 | 0.8948 | 0.4554 | 0.7782 | 0.9067 | 0.9405 | 6.38 |
| Qwen3-4B LoRA | **0.9861** | **0.9578** | **0.4875** | **0.8918** | **0.9649** | **0.9792** | **3.14** |

LoRA 相对冻结 Qwen：

- Recall@2 提升 11.36 个百分点；
- Recall@5 提升 5.83 个百分点；
- Recall@10 提升 3.86 个百分点；
- NDCG@10 提升 6.30 个百分点；
- 正样本平均排名从 6.38 改善到 3.14。

H1 组内诊断：

| 模型 | P/H1 Pairwise | 两个正样本同时高于 H1 |
|---|---:|---:|
| BGE-M3 冻结 | 78.36% | 67.30% |
| Qwen3-4B 冻结 | 93.76% | 88.70% |
| Qwen3-4B LoRA | **97.32%** | **94.65%** |

LoRA 模型的验证集/测试集对比：

| Split | Recall@10 | NDCG@10 |
|---|---:|---:|
| validation | 0.9828 | 0.9625 |
| test | 0.9792 | 0.9578 |

当前配置只计算到 Recall@10 和 NDCG@10，没有计算 Recall@20 或
NDCG@20，不应根据现有文件推测具体数值。

## 12. 结果边界

这些结果说明：

> 在当前 JD 条件生成的合成候选人基准上，LoRA 微调显著提升了
> Qwen3-Embedding-4B 的正样本召回、排序质量以及近失配能力区分效果。

这些结果不能直接解释为真实招聘场景中的 97.92% 匹配准确率，原因包括：

1. 简历由源 JD 条件生成，存在生成器风格和同源偏差；
2. 其他 JD 的简历可能也适合当前岗位，但没有跨 JD 人工相关性标签；
3. 全量生成数据中存在严格语义契约警告，可能引入弱监督噪声；
4. 尚未使用真实匿名简历或人工作标注外部测试集；
5. Recall/NDCG 是检索排序指标，不等同于二分类“匹配准确率”。

建议将本结果称为“合成受控人岗检索基准结果”，并补充 strict-only 消融、
人工抽样复核和独立人审测试集。

## 13. 文件说明

```text
qwen3_embedding_4b_rtx3090/
├── README.md                         # 本说明
├── preflight.json                    # GPU、依赖、显存和单步训练预检
├── run_manifest.json                 # 完整运行配置、数据哈希与各阶段汇总
├── train_log.jsonl                   # 1,263 步逐步训练日志
├── baselines/
│   └── metrics.json                  # BGE-M3 与冻结 Qwen 基线
├── negative_mining/
│   └── manifest.json                 # 困难负样本池统计
└── evaluation/
    └── metrics.json                  # LoRA 模型最终评测
```

`run_manifest.json` 中的模型和输出路径是服务器绝对路径，复制到其他机器后
路径不会自动有效。该 manifest 记录了代码、配置和数据哈希，但模型来自手工下载的
本地目录，未记录 Hugging Face/ModelScope 的精确 commit revision。

## 14. 常用审计命令

在本目录执行：

```bash
# 查看 GPU 和显存预检
jq . preflight.json

# 查看负样本挖掘统计
jq . negative_mining/manifest.json

# 查看冻结基线
jq . baselines/metrics.json

# 查看 LoRA 最终指标
jq . evaluation/metrics.json

# 查看完整运行信息
jq . run_manifest.json

# 查看训练首尾步骤
head -n 1 train_log.jsonl | jq .
tail -n 1 train_log.jsonl | jq .

# 按 epoch 计算平均损失
jq -s '
  group_by(.epoch)
  | map({
      epoch: .[0].epoch,
      steps: length,
      mean_loss: (map(.loss) | add / length),
      mean_info_nce: (map(.info_nce) | add / length),
      mean_h1: (map(.h1_margin_loss) | add / length),
      mean_hard: (map(.hard_margin_loss) | add / length)
    })
' train_log.jsonl
```

## 15. 环境信息

本次服务器运行环境：

| 环境 | 版本 |
|---|---|
| GPU | NVIDIA GeForce RTX 3090 24GB |
| Python | 3.11.15 |
| PyTorch | 2.12.1+cu126 |
| CUDA Runtime | 12.6 |
| Transformers | 4.57.6 |
| Sentence Transformers | 5.6.1 |
| PEFT | 0.20.0 |
| Accelerate | 1.14.0 |
| FlashAttention | 未安装/未使用 |

本实验固定使用逻辑 GPU 0，运行时 `CUDA_VISIBLE_DEVICES=0`，PyTorch
只检测到一张 RTX 3090。
