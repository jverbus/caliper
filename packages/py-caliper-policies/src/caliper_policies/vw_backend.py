from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VWScoredArm:
    arm_id: str
    score: float
    probability: float


class VWPolicyBackend:
    """Scaffold backend for VW CB ADF policy-family integration.

    This backend intentionally avoids a hard runtime dependency on the `vw` binary.
    It provides:
    - deterministic CB-ADF example shaping,
    - deterministic per-arm scaffold scoring,
    - normalized action probabilities for assignment + replay logging.

    A later chunk can swap the scoring implementation for real VW model inference
    while preserving the same backend contract.
    """

    def score_arms(
        self,
        *,
        job_id: str,
        unit_id: str,
        idempotency_key: str,
        arm_ids: list[str],
        context: dict[str, Any],
        params: dict[str, Any],
    ) -> list[VWScoredArm]:
        if not arm_ids:
            return []

        shared_features = self._shared_features(context)
        arm_features = self._arm_features(context)
        prior_scores = self._prior_scores(params=params, arm_ids=arm_ids)
        temperature = self._temperature(params=params)

        raw_scores: dict[str, float] = {}
        for arm_id in arm_ids:
            example = self._cb_adf_example(
                shared_features=shared_features,
                arm_features=arm_features.get(arm_id, {}),
                arm_id=arm_id,
            )
            scaffold = self._deterministic_scaffold_score(
                job_id=job_id,
                unit_id=unit_id,
                idempotency_key=idempotency_key,
                arm_id=arm_id,
                example=example,
            )
            raw_scores[arm_id] = prior_scores[arm_id] + scaffold

        probabilities = self._softmax(raw_scores=raw_scores, temperature=temperature)
        return [
            VWScoredArm(
                arm_id=arm_id,
                score=raw_scores[arm_id],
                probability=probabilities[arm_id],
            )
            for arm_id in arm_ids
        ]

    def _shared_features(self, context: dict[str, Any]) -> dict[str, float]:
        features = context.get("shared_features")
        if not isinstance(features, dict):
            return {}

        parsed: dict[str, float] = {}
        for key, value in features.items():
            try:
                parsed[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        return parsed

    def _arm_features(self, context: dict[str, Any]) -> dict[str, dict[str, float]]:
        features = context.get("arm_features")
        if not isinstance(features, dict):
            return {}

        parsed: dict[str, dict[str, float]] = {}
        for arm_id, arm_dict in features.items():
            if not isinstance(arm_dict, dict):
                continue
            bucket: dict[str, float] = {}
            for key, value in arm_dict.items():
                try:
                    bucket[str(key)] = float(value)
                except (TypeError, ValueError):
                    continue
            parsed[str(arm_id)] = bucket
        return parsed

    def _prior_scores(self, *, params: dict[str, Any], arm_ids: list[str]) -> dict[str, float]:
        priors_raw = params.get("arm_priors")
        if not isinstance(priors_raw, dict):
            return {arm_id: 0.0 for arm_id in arm_ids}

        priors: dict[str, float] = {}
        for arm_id in arm_ids:
            try:
                priors[arm_id] = float(priors_raw.get(arm_id, 0.0))
            except (TypeError, ValueError):
                priors[arm_id] = 0.0
        return priors

    def _temperature(self, *, params: dict[str, Any]) -> float:
        raw = params.get("temperature", 1.0)
        try:
            parsed = float(raw)
        except (TypeError, ValueError):
            parsed = 1.0
        return max(parsed, 1e-6)

    def _cb_adf_example(
        self,
        *,
        shared_features: dict[str, float],
        arm_features: dict[str, float],
        arm_id: str,
    ) -> str:
        shared = " ".join(f"{key}:{value:.6f}" for key, value in sorted(shared_features.items()))
        action = " ".join(f"{key}:{value:.6f}" for key, value in sorted(arm_features.items()))
        return f"shared |s {shared}\naction {arm_id} |a {action}"

    def _deterministic_scaffold_score(
        self,
        *,
        job_id: str,
        unit_id: str,
        idempotency_key: str,
        arm_id: str,
        example: str,
    ) -> float:
        material = f"{job_id}:{unit_id}:{idempotency_key}:{arm_id}:{example}"
        digest = hashlib.sha256(material.encode()).digest()
        value = int.from_bytes(digest[:8], byteorder="big", signed=False)
        return value / float(1 << 64)

    def _softmax(self, *, raw_scores: dict[str, float], temperature: float) -> dict[str, float]:
        max_score = max(raw_scores.values())
        exp_scores = {
            arm_id: math.exp((score - max_score) / temperature)
            for arm_id, score in raw_scores.items()
        }
        total = sum(exp_scores.values())
        if total <= 0:
            equal = 1.0 / len(raw_scores)
            return {arm_id: equal for arm_id in raw_scores}
        return {arm_id: value / total for arm_id, value in exp_scores.items()}
