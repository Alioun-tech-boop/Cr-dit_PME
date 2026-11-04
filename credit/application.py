from copy import deepcopy

from credit.businesses.contracts import BusinessCase
from credit.businesses.engine import analyze as analyze_business
from credit.config import ENGINE_CONFIGURATION, ENGINE_VERSION
from credit.individuals.contracts import IndividualCase
from credit.individuals.engine import analyze as analyze_individual
from credit.persistence import AnalysisRecord

CONTRACTS = {"individuals": IndividualCase, "businesses": BusinessCase}
ENGINES = {"individuals": analyze_individual, "businesses": analyze_business}


def run_analysis(session, record, scenario=None):
    snapshot = deepcopy(record.payload)
    case = CONTRACTS[record.kind].model_validate(snapshot)
    result = ENGINES[record.kind](case, scenario)
    analysis = AnalysisRecord(
        case_id=record.id,
        kind=record.kind,
        input_snapshot=snapshot,
        result=result.model_dump(mode="json"),
        scenario=scenario.model_dump(mode="json") if scenario else {},
        engine_version=ENGINE_VERSION,
        configuration=deepcopy(ENGINE_CONFIGURATION),
        evidence_snapshot=deepcopy(snapshot["evidence"]),
    )
    session.add(analysis)
    session.commit()
    return analysis
