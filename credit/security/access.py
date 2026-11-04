"""Matrice de permissions côté serveur ; toujours après l’autorisation de l’objet."""

from fastapi import HTTPException

STAFF = {"analyst", "institution_manager", "administrator"}


def role(actor):
    return actor.role or ("analyst" if actor.reviewer else "applicant")


def require_staff(actor):
    if role(actor) not in STAFF:
        raise HTTPException(403, "Habilitation d’analyse requise")


def enforce(request, actor):
    route = getattr(request.scope.get("route"), "path", "")
    internal = (
        ("/assessments" in route and "/print-publication" not in route)
        or "/analyses" in route
        or "/scenarios" in route
        or "/documents" in route
        or route.endswith("/events")
        or ("/runs/" in route and "/pages/" not in route)
        or ("/submissions/" in route and route.endswith("/process"))
    )
    if internal:
        require_staff(actor)


def client_fields(case, actor, creating=False, previous=None):
    """Un JSON de saisie ne constitue pas une validation documentaire serveur."""
    if role(actor) == "applicant" and case.record_details.internal_observations:
        raise HTTPException(403, "Observations internes réservées aux analystes")
    if role(actor) == "applicant":
        identity = case.analysis_details.identity.model_dump(mode="json")
        if any(v is not None and v != [] for v in identity.values()) and identity != (
            previous or {}
        ).get("analysis_details", {}).get("identity"):
            raise HTTPException(403, "Contrôles d’identité réservés aux analystes")
        verified = case.analysis_details.funding.verified_contribution
        if verified is not None and verified.model_dump(mode="json") != (previous or {}).get(
            "analysis_details", {}
        ).get("funding", {}).get("verified_contribution"):
            raise HTTPException(403, "Apport contrôlé réservé aux analystes")
    for proof in case.evidence:
        if (
            proof.status == "verified"
            or proof.review_id
            or proof.run_id
            or proof.submission_id
            or proof.source_locations
        ):
            raise HTTPException(
                422, "Utiliser la revue serveur et le rattachement explicite des sources validées"
            )
    if creating and role(actor) == "applicant" and case.data_classification == "synthetic":
        raise HTTPException(403, "Classification de démonstration réservée aux analystes")


def public_payload(payload, actor):
    if role(actor) in STAFF:
        return payload
    # Exclusion réelle avant sérialisation, pas un masque de présentation.
    from copy import deepcopy

    data = deepcopy(payload)
    data.get("record_details", {}).pop("internal_observations", None)
    data.get("analysis_details", {}).pop("identity", None)
    return data
