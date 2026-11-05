"""Contrat d'adaptation. Aucun accès à une URL fournie dans une requête utilisateur."""

from typing import Protocol
from pydantic import Field
from credit.shared.contracts import Contract
from credit.partners.signing import digest, canonical


class Delivery(Contract):
    tracking_id: str
    idempotency_key: str
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    recipient_institution_id: str
    file_hashes: list[str]


class Acknowledgment(Contract):
    external_id: str = Field(min_length=1, max_length=200)
    technical_accepted: bool
    business_received: bool = False
    simulated: bool = False


class Connector(Protocol):
    def deliver(
        self, request: Delivery, *, attempt: int, configuration: dict
    ) -> Acknowledgment: ...


class PortalConnector:
    def deliver(self, request, *, attempt, configuration):
        return Acknowledgment(external_id="portal:" + request.tracking_id, technical_accepted=True)


class DemonstrationConnector:
    def deliver(self, request, *, attempt, configuration):
        if not configuration["demonstration"]:
            raise ValueError("demo_only")
        if attempt <= configuration.get("demo_failures", 0):
            raise TimeoutError("synthetic_timeout")
        # Identifiant stable même après une réponse perdue. Aucun appel réseau.
        return Acknowledgment(
            external_id="DEMO-" + digest(canonical(request.model_dump(mode="json")))[:24],
            technical_accepted=True,
            business_received=False,
            simulated=True,
        )


CONNECTORS = {"portal": PortalConnector(), "api_demo": DemonstrationConnector()}
