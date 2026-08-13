from __future__ import annotations

from pathlib import Path

from .io_utils import write_json
from .schemas import (
    EmergingRole,
    Evidence,
    ExternalDocument,
    JobSkillUpdate,
    KGLinkDelta,
    RunManifest,
    SourceManifest,
    TrendFeature,
)


PUBLIC_SCHEMAS = {
    "source_manifest_v1": SourceManifest,
    "external_document_v1": ExternalDocument,
    "evidence_v1": Evidence,
    "trend_feature_v1": TrendFeature,
    "emerging_role_v1": EmergingRole,
    "job_skill_update_v1": JobSkillUpdate,
    "trend_kg_delta_v1": KGLinkDelta,
    "jobtrend_run_manifest_v1": RunManifest,
}


def export_json_schemas(output_dir: str | Path) -> list[Path]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for name, model in PUBLIC_SCHEMAS.items():
        path = target / f"{name}.schema.json"
        write_json(path, model.model_json_schema())
        outputs.append(path)
    return outputs
