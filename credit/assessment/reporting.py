"""Restitution déterministe à partir de faits structurés ; aucun LLM calculateur."""


def minimum_margin(financial):
    values = [p.margin_after_debt for p in financial.periods]
    return min(values) if values and all(v is not None for v in values) else None


def financial_risk(financial, timing):
    findings = financial.financial_findings
    deficit = bool(findings.deficit_periods)
    illiquid = bool(findings.negative_balance_periods) or (
        timing["minimum_balance"] is not None and timing["minimum_balance"] < 0
    )
    return {
        "status": "payment_pressure"
        if deficit or illiquid
        else "incomplete"
        if financial.status == "incomplete"
        else "no_deficit_in_supplied_flows",
        "period_deficits": [d.isoformat() for d in findings.deficit_periods],
        "negative_balance_periods": [d.isoformat() for d in findings.negative_balance_periods],
        "minimum_margin": minimum_margin(financial),
        "minimum_balance": findings.minimum_balance,
        "minimum_balance_date": findings.minimum_balance_date.isoformat()
        if findings.minimum_balance_date
        else None,
        "dated_cashflow_analysis": timing,
        "notice": "Constats conditionnels aux données fournies ; aucune probabilité de défaut ni décision d’accord.",
    }


def compare_financial(before, after):
    old, new = minimum_margin(before), minimum_margin(after)
    return {
        "minimum_margin_before": old,
        "minimum_margin_after": new,
        "minimum_margin_change": None if old is None or new is None else new - old,
        "minimum_balance_before": before.financial_findings.minimum_balance,
        "minimum_balance_after": after.financial_findings.minimum_balance,
        "periods": [
            {
                "period": row.period.isoformat(),
                "margin_before": next(
                    (p.margin_after_debt for p in before.periods if p.period == row.period), None
                ),
                "margin_after": row.margin_after_debt,
                "balance_after": row.closing_reserve_or_cash,
            }
            for row in after.periods
        ],
        "notice": "Effets comptables du scénario ; pas une réduction causale démontrée de la PD.",
    }


def summary(core, risk, missing, review, scoring):
    label = "particulier" if core == "individuals" else "entreprise"
    text = f"Analyse {label} : "
    if risk["status"] == "payment_pressure":
        text += "des déficits ou tensions de liquidité sont identifiés ; revue approfondie requise."
    elif risk["status"] == "incomplete":
        text += "la capacité financière ne peut pas être complètement évaluée."
    else:
        text += "aucun déficit dans les flux fournis, sous les hypothèses déclarées."
    if missing:
        text += f" {len(missing)} informations ou vérifications restent demandées."
    if scoring["criteria_score"] is not None:
        text += f" Score de solvabilité par critères : {scoring['criteria_score']}/100 ({scoring['criteria_validation_status']})."
    else:
        text += (
            " Score par critères indisponible ; les données et indicateurs restent consultables."
        )
    if scoring["combined_score"] is None:
        text += " Combinaison 70/30 indisponible."
    text += " Aucune décision de prêt ni authenticité documentaire n’est déduite."
    return text


def render_french(report):
    lines = [
        "# Rapport Crédix",
        report.summary,
        "",
        f"État opérationnel : {report.operating_state}",
        f"Version : {report.engine_version}",
        f"Politique : {report.versions.get('policy', 'indisponible')}",
        "",
        "## Risque financier",
        str(report.financial_risk["status"]),
        "Indice de risque = 100 − score de solvabilité ; ce n’est pas une probabilité de défaut.",
        f"Modèle : {report.scoring['model_status']}",
    ]
    for section in report.sections:
        lines += ["", f"## {section.title} — {section.status}", section.explanation]
        for indicator in section.indicators:
            value = "indisponible" if indicator.value is None else str(indicator.value)
            lines.append(
                f"- {indicator.id} : {value} {indicator.unit}. Formule : {indicator.formula}."
            )
        for message in section.alerts:
            lines.append("- Alerte : " + message)
        for message in section.missing_information:
            lines.append("- À compléter : " + message)
        for datum in section.data_used:
            if datum.sources:
                refs = ", ".join(
                    s["id"] + (f" page {s['page']}" if s.get("page") else "") for s in datum.sources
                )
                lines.append(f"- Source {datum.path} : {refs}.")
    lines += ["", "## Suggestions"]
    for item in report.suggestions:
        lines += [
            f"- [{item.priority}] {item.action} Destinataire : {item.recipient}.",
            "  Limites : " + " ; ".join(item.costs_and_limits),
        ]
    lines += ["", "## Décision du prêteur", "Non fournie. Ce rapport n’est pas un accord bancaire."]
    return "\n".join(lines) + "\n"
