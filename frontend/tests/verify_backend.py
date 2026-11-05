import json
import sys
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from credit.individuals.contracts import IndividualCase
from credit.businesses.contracts import BusinessCase
from credit.assessment.engines import IndividualAnalysisEngine,BusinessAnalysisEngine
from credit.shared.contracts import Scenario
from pydantic import ValidationError
checks=[]
def check(name,condition):
 assert condition,name
 checks.append(name)
payloads=json.loads((ROOT / 'tests/output/form-payloads.json').read_text())
for item in payloads:
 core=item['core'];contract=IndividualCase if core=='individuals' else BusinessCase
 case=contract.model_validate(item['data'])
 check(core+' : export de formulaire validé par Pydantic',case.currency=='XOF')
 engine=IndividualAnalysisEngine() if core=='individuals' else BusinessAnalysisEngine()
 report=engine.analyze(case,mode='real')
 check(core+' : calcul sans grille ni modèle',report.scoring['combined_score'] is None and report.scoring['probability_of_default'] is None)
 check(core+' : aucune validation d’identité forgée',case.analysis_details.identity.subject_linked is None)
 wrong=deepcopy(item['data']);wrong['requested_loan']['principal']['value']='0'
 try:contract.model_validate(wrong)
 except ValidationError:check(core+' : capital incompatible refusé',True)
 else:raise AssertionError('capital incompatible accepté')
for core,name,contract,engine,expected in [('individuals','individual_control',IndividualCase,IndividualAnalysisEngine,'70000.00'),('businesses','business_seasonal',BusinessCase,BusinessAnalysisEngine,'-213000.00')]:
 case=contract.model_validate_json((ROOT / ('tests/fixtures/'+name+'.json')).read_text());before=case.model_dump_json()
 report=engine().analyze(case,mode='real');stress=engine().analyze(case,mode='real',scenario=Scenario(name='Hypothèse illustrative : revenus ou encaissements −20 %',revenue_drop='0.20'))
 key='margin_after_credit' if core=='individuals' else 'margin_after_debt'
 check(core+' : résultat financier de référence',report.financial_calculations['periods'][0][key]==expected)
 check(core+' : calcul sans mutation de la source',case.model_dump_json()==before)
 check(core+' : nombre exact de sections',len(report.sections)==(7 if core=='individuals' else 9))
 check(core+' : stress diminue la marge',Decimal(stress.financial_calculations['periods'][0][key])<Decimal(expected))
 check(core+' : résultat consulté identique au moteur',json.loads((ROOT / ('tests/fixtures/'+core+'-report.json')).read_text())==report.model_dump(mode='json'))
 check(core+' : scénario consulté identique au moteur',json.loads((ROOT / ('tests/fixtures/'+core+'-stress.json')).read_text())['financial_calculations']==stress.model_dump(mode='json')['financial_calculations'])
(ROOT / 'tests/output/verification-python.json').write_text(json.dumps({'count':len(checks),'checks':checks},ensure_ascii=False,indent=2))
print(str(len(checks))+' vérifications Python réussies : contrats réels, invariants, moteurs et rapports affichés.')
