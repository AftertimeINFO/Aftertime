from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import settings


@dataclass(frozen=True)
class SyncRecord:
    external_id: str
    name: str
    kind: str
    level: str
    symbol: str | None
    attributes: dict[str, Any]
    evidence: dict[str, Any]


class ChebiAdapter:
    base_url = "https://www.ebi.ac.uk/chebi/backend/api/public/compound"

    def fetch(self, parameters: dict[str, Any]) -> list[SyncRecord]:
        ids = parameters.get("external_ids") or [parameters.get("external_id", "16134")]
        records: list[SyncRecord] = []
        with httpx.Client(timeout=settings.sync_http_timeout_seconds) as client:
            for external_id in ids:
                response = client.get(f"{self.base_url}/{external_id}/")
                response.raise_for_status()
                payload = response.json()
                name = payload.get("name") or payload.get("asciiName") or f"ChEBI:{external_id}"
                formula = (
                    payload.get("formula")
                    or payload.get("chemicalFormula")
                    or payload.get("defaultStructure", {}).get("formula")
                )
                records.append(
                    SyncRecord(
                        external_id=str(external_id),
                        name=name,
                        kind="substance",
                        level="molecular",
                        symbol=formula,
                        attributes={"chebi": payload},
                        evidence={
                            "source_url": str(response.url),
                            "retrieved_at": datetime.now(UTC).isoformat(),
                        },
                    )
                )
        return records


class WorldBankAdapter:
    base_url = "https://api.worldbank.org/v2"

    def fetch(self, parameters: dict[str, Any]) -> list[SyncRecord]:
        country = parameters.get("country", "UA")
        indicator = parameters.get("indicator", "AG.CON.FERT.ZS")
        url = f"{self.base_url}/country/{country}/indicator/{indicator}"
        with httpx.Client(timeout=settings.sync_http_timeout_seconds) as client:
            response = client.get(url, params={"format": "json", "per_page": 100})
            response.raise_for_status()
            payload = response.json()
        values = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
        latest = next((item for item in values if item.get("value") is not None), None)
        if not latest:
            return []
        return [
            SyncRecord(
                external_id=f"{country}:{indicator}:{latest['date']}",
                name=latest["indicator"]["value"],
                kind="indicator",
                level="institutional",
                symbol=indicator,
                attributes={
                    "country": country,
                    "year": latest["date"],
                    "value": latest["value"],
                    "unit": "% of fertilizer production",
                },
                evidence={
                    "source_url": str(response.url),
                    "retrieved_at": datetime.now(UTC).isoformat(),
                },
            )
        ]


ADAPTERS = {"chebi": ChebiAdapter, "worldbank": WorldBankAdapter}
