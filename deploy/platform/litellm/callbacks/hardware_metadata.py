"""Stamp every LiteLLM request with hardware_id + backend_type metadata.

Sourced from `model_info` in config.yaml. Without this hook, those keys
never reach Langfuse: `langfuse_default_tags` only resolves cache_hit /
cache_key natively (see
litellm/integrations/langfuse/langfuse.py::add_default_langfuse_tags),
so custom strings are silently dropped. The W6 NPU utilisation report
needs to aggregate by hardware, so we inject directly via a pre-call hook.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from litellm.integrations.custom_logger import CustomLogger

CONFIG_PATH = os.environ.get("LITELLM_CONFIG_PATH", "/app/config.yaml")


def _load_model_info(path: str | os.PathLike[str] = CONFIG_PATH) -> dict[str, dict[str, str]]:
    cfg = yaml.safe_load(Path(path).read_text()) or {}
    out: dict[str, dict[str, str]] = {}
    for entry in cfg.get("model_list") or []:
        name = entry.get("model_name")
        info = entry.get("model_info") or {}
        if not name:
            continue
        stamp: dict[str, str] = {}
        if info.get("hardware_id"):
            stamp["hardware_id"] = str(info["hardware_id"])
        if info.get("backend_type"):
            stamp["backend_type"] = str(info["backend_type"])
        if stamp:
            out[name] = stamp
    return out


_MODEL_INFO = _load_model_info()


class HardwareMetadataLogger(CustomLogger):
    """Inject `hardware_id` / `backend_type` into request metadata + tags."""

    async def async_pre_call_hook(
        self,
        user_api_key_dict: Any,
        cache: Any,
        data: dict[str, Any],
        call_type: str,
    ) -> dict[str, Any]:
        stamp = _MODEL_INFO.get(data.get("model") or "")
        if not stamp:
            return data
        meta = data.setdefault("metadata", {})
        if not isinstance(meta, dict):
            return data
        # Tags are the queryable surface in Langfuse — primary path for
        # "aggregate by hardware" reports (W6).
        tags = meta.setdefault("tags", [])
        if isinstance(tags, list):
            for k, v in stamp.items():
                tag = f"{k}:{v}"
                if tag not in tags:
                    tags.append(tag)
        # `trace_metadata` is the only metadata key LiteLLM forwards to
        # Langfuse's trace.metadata (other flat keys are dropped).
        trace_meta = meta.setdefault("trace_metadata", {})
        if isinstance(trace_meta, dict):
            for k, v in stamp.items():
                trace_meta.setdefault(k, v)
        return data


proxy_handler_instance = HardwareMetadataLogger()
