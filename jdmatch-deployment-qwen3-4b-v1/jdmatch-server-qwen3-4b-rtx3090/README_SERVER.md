# JD–简历匹配：RTX 3090 单卡服务器运行说明

本包用于在一张 24GB RTX 3090 上完成冻结基线、困难负样本挖掘、
Qwen3-Embedding-4B LoRA/GradCache 训练和评测。配置强制要求
`CUDA_VISIBLE_DEVICES=0` 且 PyTorch 只能看到一张
`NVIDIA GeForce RTX 3090`，从而避开物理 GPU 7 上的已有任务。

包内包含 8407 条 JD、25221 份简历、8407 条负样本采样契约、源码、
wheel、测试和配置，不包含模型权重。

## 1. 校验和解压

```bash
sha256sum -c jdmatch-server-qwen3-4b-rtx3090.tar.gz.sha256
tar -xzf jdmatch-server-qwen3-4b-rtx3090.tar.gz
cd jdmatch-server-qwen3-4b-rtx3090
```

## 2. 使用已有 Conda 环境安装

```bash
conda activate /data/wangxianjiong/conda_envs/jdmatch
python -m pip install --upgrade pip

python -m pip install torch==2.8.0 \
  --index-url https://download.pytorch.org/whl/cu126

python -m pip install \
  wheels/jd_resume_match-0.1.0-py3-none-any.whl
```

服务器驱动显示 CUDA 13.1 不影响使用 PyTorch wheel 自带的 CUDA 12.6
runtime；NVIDIA 驱动向下兼容这一 runtime。

可选安装 FlashAttention 2：

```bash
python -m pip install packaging ninja
python -m pip install flash-attn --no-build-isolation
```

如果安装或导入失败，程序自动改用 PyTorch SDPA。若 BF16 LoRA
预检 OOM，备用 NF4 配置还需要：

```bash
python -m pip install bitsandbytes
```

## 3. 离线结构测试

该测试不下载或加载模型：

```bash
python -m unittest tests.test_server_bundle -v
```

它会验证数据条数与 SHA-256、两套 GPU 配置以及 GradCache 梯度等价性。

## 4. 验证 GPU 0

```bash
CUDA_VISIBLE_DEVICES=0 python - <<'PY'
import torch

print("torch:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
print("cuda runtime:", torch.version.cuda)
print("visible devices:", torch.cuda.device_count())
print("gpu:", torch.cuda.get_device_name(0))
print("bf16:", torch.cuda.is_bf16_supported())
PY
```

预期 `visible devices` 为 `1`，GPU 名称为
`NVIDIA GeForce RTX 3090`。

## 5. 下载并锁定模型版本

```bash
CUDA_VISIBLE_DEVICES=0 jdmatch download-models \
  --config configs/qwen3_4b_rtx3090_24gb.yaml
```

模型仍保存在 Hugging Face cache，不写入本项目目录。命令会将每个模型
实际下载的 commit hash 写入：

```text
runs/qwen3_embedding_4b_rtx3090/model_downloads.json
```

后续阶段读取这个精确 snapshot，运行 manifest 同时记录模型、数据、
配置、依赖和源码哈希。

## 6. 必须先做单步预检

```bash
CUDA_VISIBLE_DEVICES=0 jdmatch preflight \
  --config configs/qwen3_4b_rtx3090_24gb.yaml
```

预检会检查：

- `CUDA_VISIBLE_DEVICES` 必须严格等于 `0`；
- PyTorch 只能看到一张 RTX 3090；
- BF16、FlashAttention/SDPA 和三份数据可用；
- Qwen3-4B LoRA + GradCache 能完成一次真实反向更新；
- 峰值 reserved 显存不超过 21.5 GiB。

GradCache 默认文本微批为 2。如果 CUDA 报 OOM，预检和正式训练会自动
用微批 1 重试，并在输出与日志中记录
`gradcache_oom_fallback`。如果微批 1 仍 OOM，使用第 10 节的 NF4 配置。

## 7. 分阶段正式运行

```bash
CUDA_VISIBLE_DEVICES=0 jdmatch baseline \
  --config configs/qwen3_4b_rtx3090_24gb.yaml

CUDA_VISIBLE_DEVICES=0 jdmatch mine-negatives \
  --config configs/qwen3_4b_rtx3090_24gb.yaml

CUDA_VISIBLE_DEVICES=0 jdmatch train \
  --config configs/qwen3_4b_rtx3090_24gb.yaml

CUDA_VISIBLE_DEVICES=0 jdmatch evaluate \
  --config configs/qwen3_4b_rtx3090_24gb.yaml
```

每个 JD 的训练组固定包含 P1、P2、H1，并优先从同岗位族困难负样本池
取 2 份，再取 1 份跨岗位族简单负样本。H1 只进入 margin loss，不进入
InfoNCE 分母；疑似假负例通过全局 mask 排除。

## 8. 一条命令运行

`run-all` 会执行预检、基线、负样本挖掘、训练和评测。模型下载建议先
单独完成，以便锁定 commit。

```bash
CUDA_VISIBLE_DEVICES=0 jdmatch run-all \
  --config configs/qwen3_4b_rtx3090_24gb.yaml
```

后台运行：

```bash
CUDA_VISIBLE_DEVICES=0 nohup jdmatch run-all \
  --config configs/qwen3_4b_rtx3090_24gb.yaml \
  > server_run.log 2>&1 &
```

监控：

```bash
tail -f server_run.log
```

另开终端：

```bash
watch -n 5 nvidia-smi -i 0
```

## 9. 中断恢复

```bash
CUDA_VISIBLE_DEVICES=0 jdmatch train \
  --config configs/qwen3_4b_rtx3090_24gb.yaml \
  --resume auto
```

`auto` 会选择 `checkpoints/step-*` 中编号最大的完整 checkpoint，同时
恢复 adapter、优化器、scheduler、epoch 和下一个 batch 位置。

## 10. BF16 单步确实失败时使用 NF4

只有 BF16 LoRA 在文本微批 1 下仍无法通过单步预检时，才使用：

```bash
CUDA_VISIBLE_DEVICES=0 jdmatch preflight \
  --config configs/qwen3_4b_rtx3090_24gb_qlora.yaml

CUDA_VISIBLE_DEVICES=0 jdmatch run-all \
  --config configs/qwen3_4b_rtx3090_24gb_qlora.yaml
```

NF4 使用独立运行目录，不会覆盖 BF16 结果。

## 11. 输出

主配置结果位于：

```text
runs/qwen3_embedding_4b_rtx3090/
├── baselines/
├── negative_mining/
├── checkpoints/
├── best_adapter/
├── evaluation/
├── model_downloads.json
├── preflight.json
└── run_manifest.json
```

预估单卡总耗时约 30–45 小时，其中负样本挖掘约 10–16 小时，
三轮训练约 15–24 小时。实际速度取决于 FlashAttention 是否可用、
文本达到 512 token 的比例和磁盘/Hugging Face cache 性能。
