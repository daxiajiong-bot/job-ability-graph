from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import torch
import torch.nn.functional as F
from torch import nn

from jd_resume_pipeline.config import load_config
from jd_resume_pipeline.gradcache import direct_step, gradcache_step
from jd_resume_pipeline.runtime_data import load_runtime_data


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _ToyEncoder:
    def __init__(self, weights: torch.Tensor) -> None:
        self.device = torch.device("cpu")
        self.model = nn.Linear(4, 3, bias=False)
        with torch.no_grad():
            self.model.weight.copy_(weights)

    def encode_texts(
        self, texts: list[str], is_query: bool
    ) -> torch.Tensor:
        rows = []
        for text in texts:
            row = torch.zeros(4)
            row[int(text)] = 1.0
            if is_query:
                row += 0.05
            rows.append(row)
        return F.normalize(self.model(torch.stack(rows)), dim=-1)


def _toy_loss(
    queries: torch.Tensor, documents: torch.Tensor
) -> tuple[torch.Tensor, dict[str, float]]:
    loss = F.cross_entropy(
        queries @ documents.T / 0.1,
        torch.arange(queries.shape[0]),
    )
    return loss, {"loss": float(loss.detach())}


class ServerBundleTests(unittest.TestCase):
    def test_runtime_data_and_checksums(self) -> None:
        data_dir = ROOT / "data/runtime"
        data = load_runtime_data(data_dir)
        self.assertEqual(len(data["jds"]), 8407)
        self.assertEqual(len(data["resumes"]), 25221)
        self.assertEqual(len(data["contracts"]), 8407)
        manifest = json.loads(
            (data_dir / "manifest.json").read_text(encoding="utf-8")
        )
        for name, expected in manifest["files"].items():
            self.assertEqual(_sha256(data_dir / name), expected["sha256"])

    def test_server_configs_pin_gpu_zero_and_expected_batch(self) -> None:
        for name, quantization in (
            ("qwen3_4b_rtx3090_24gb.yaml", "none"),
            ("qwen3_4b_rtx3090_24gb_qlora.yaml", "nf4"),
        ):
            config = load_config(ROOT / "configs" / name)
            self.assertEqual(
                config["hardware"]["required_cuda_visible_devices"], "0"
            )
            self.assertEqual(
                config["hardware"]["expected_gpu_name"],
                "NVIDIA GeForce RTX 3090",
            )
            self.assertEqual(
                config["training"]["global_jd_batch_size"], 16
            )
            self.assertEqual(
                config["training"]["gradcache_microbatch_texts"], 2
            )
            self.assertEqual(config["training"]["quantization"], quantization)

    def test_gradcache_gradient_matches_direct_batch(self) -> None:
        torch.manual_seed(20260730)
        weights = torch.randn(3, 4)
        direct = _ToyEncoder(weights)
        cached = _ToyEncoder(weights)
        direct.model.zero_grad(set_to_none=True)
        direct_loss, _ = direct_step(
            direct, ["0", "1"], ["0", "1", "2"], _toy_loss
        )
        cached.model.zero_grad(set_to_none=True)
        cached_loss, _ = gradcache_step(
            cached,
            ["0", "1"],
            ["0", "1", "2"],
            _toy_loss,
            microbatch_size=1,
        )
        self.assertAlmostEqual(
            float(direct_loss), float(cached_loss), places=6
        )
        self.assertTrue(
            torch.allclose(
                direct.model.weight.grad,
                cached.model.weight.grad,
                atol=1e-6,
                rtol=1e-5,
            )
        )


if __name__ == "__main__":
    unittest.main()
