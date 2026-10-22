"""Holds the champion model in memory and reloads it on 'model.promoted' events."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import socket
import threading
from pathlib import Path
from typing import Any

import pandas as pd
from telco_ml.champion import Champion, load_champion
from telco_ml.modeling import risk_band, top_factors

from .config import Settings

log = logging.getLogger(__name__)


class ModelService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._champion: Champion | None = None
        self._lock = threading.Lock()

    @property
    def champion(self) -> Champion | None:
        return self._champion

    def reload(self) -> Champion | None:
        champ = load_champion(self.settings.ml_model_name, self.settings.mlflow_tracking_uri, Path(self.settings.ml_model_dir))
        with self._lock:
            self._champion = champ
        if champ:
            log.info("champion loaded", extra={"version": champ.version, "algorithm": champ.algorithm, "from": champ.source})
        else:
            log.warning("no champion model available yet")
        return champ

    def predict(self, profile: dict[str, Any]) -> dict[str, Any]:
        champ = self._champion
        if champ is None:
            raise LookupError("no champion model is available yet")
        X = pd.DataFrame([{f: profile.get(f) for f in champ.features}])
        for c in champ.numeric:
            X[c] = pd.to_numeric(X[c], errors="coerce").astype(float)
        p = float(champ.pipeline.predict_proba(X)[:, 1][0])
        return {
            "churn_probability": round(p, 5),
            "predicted_label": int(p >= champ.threshold),
            "risk_band": risk_band(p, self.settings.ml_high_risk_threshold, self.settings.ml_medium_risk_threshold),
            "threshold": champ.threshold,
            "top_factors": top_factors(champ.pipeline, X, champ.reference["baseline"])[0],
            "model": {"name": self.settings.ml_model_name, "version": champ.version, "algorithm": champ.algorithm},
        }

    async def keep_loaded(self, stop: asyncio.Event, retry_seconds: float = 300) -> None:
        """Load the champion now and keep retrying while none is available."""
        while not stop.is_set():
            try:
                if await asyncio.to_thread(self.reload) is not None:
                    return
            except Exception:  # noqa: BLE001 - keep serving OLAP/KPIs without a model
                log.exception("champion load failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=retry_seconds)

    async def listen_for_promotions(self, stop: asyncio.Event) -> None:
        if not self.settings.kafka_bootstrap_servers:
            return
        from aiokafka import AIOKafkaConsumer

        consumer = AIOKafkaConsumer(
            "dw.events.v1",
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            group_id=f"analytics-api-{socket.gethostname()}",
            auto_offset_reset="latest",
            enable_auto_commit=True,
        )
        try:
            while not stop.is_set():
                try:
                    await consumer.start()
                    break
                except Exception as exc:  # noqa: BLE001
                    log.warning("kafka unavailable for model events (%s); retrying", exc)
                    await asyncio.sleep(10)
            while not stop.is_set():
                batch = await consumer.getmany(timeout_ms=1000)
                for messages in batch.values():
                    for m in messages:
                        try:
                            event = json.loads(m.value)
                        except (TypeError, ValueError):
                            continue
                        if event.get("event_type") == "model.promoted":
                            log.info("model.promoted received; reloading champion")
                            await asyncio.to_thread(self.reload)
        finally:
            await consumer.stop()
