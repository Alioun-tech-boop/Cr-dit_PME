"""Référentiel exhaustif des pièces du périmètre convenu.

Les alias servent à repérer des libellés, jamais à prouver l'authenticité.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    key: str
    aliases: tuple[str, ...]
    kind: str = "text"


def f(key, aliases, kind="text"):
    return Field(key, tuple(aliases.split("|")), kind)


COMMON = (
    f("subject_name", "Nom du titulaire|Nom de l'emprunteur|Nom du salarié|Dénomination sociale|Raison sociale|Nom et prénoms"),
    f("document_date", "Date du document|Date d'établissement|Date d'émission", "date"),
    f("period", "Période concernée|Période|Exercice"),
    f("currency", "Devise|Monnaie", "currency"),
    f("reference", "Référence du document|Référence|Numéro du document"),
)

FAMILIES = {
    "identity": (
        f("identity_number", "Numéro CNIB|N° CNIB|Numéro de passeport|Numéro d'identité"),
        f("birth_date", "Date de naissance", "date"),
        f("expiry_date", "Date d'expiration|Valable jusqu'au", "date"),
        f("address", "Adresse|Domicile"),
    ),
    "legal": (
        f("registration_number", "Numéro RCCM|N° RCCM|RCCM"),
        f("tax_number", "Numéro IFU|N° IFU|IFU"),
        f("legal_form", "Forme juridique"),
        f("representative", "Représentant légal|Gérant|Mandataire"),
        f("capital", "Capital social", "money"),
        f("ownership", "Répartition du capital|Bénéficiaire effectif|Actionnaire"),
        f("scope", "Objet social|Pouvoirs accordés|Activité autorisée"),
        f("expiry_date", "Date d'expiration|Valable jusqu'au", "date"),
    ),
    "location": (
        f("address", "Adresse des locaux|Adresse|Localisation"),
        f("rent", "Loyer mensuel|Montant du loyer", "money"),
        f("owner", "Bailleur|Propriétaire"),
        f("occupancy_right", "Titre d'occupation|Nature du droit"),
    ),
    "request": (
        f("requested_amount", "Montant sollicité|Montant demandé|Montant du crédit", "money"),
        f("purpose", "Objet du financement|Objet du crédit|Besoin financé"),
        f("duration", "Durée du crédit|Durée souhaitée"),
        f("contribution", "Apport personnel|Apport du promoteur", "money"),
        f("project_cost", "Coût total du projet|Budget total", "money"),
    ),
    "income": (
        f("employer", "Employeur|Nom de l'employeur"),
        f("employment_start", "Date d'embauche|Date d'entrée", "date"),
        f("contract_type", "Type de contrat|Nature du contrat"),
        f("contract_end", "Fin du contrat|Date de fin", "date"),
        f("gross_income", "Salaire brut|Rémunération brute", "money"),
        f("net_income", "Net à payer|Salaire net|Pension nette|Revenu net", "money"),
        f("loan_withholding", "Retenue prêt|Retenue sur prêt|Retenue crédit", "money"),
        f("bonuses", "Total primes|Primes et indemnités", "money"),
        f("income_amount", "Montant versé|Montant de la pension|Montant des revenus", "money"),
    ),
    "budget": (
        f("income_amount", "Total revenus|Revenus mensuels|Revenu disponible", "money"),
        f("expenses", "Total dépenses|Total charges|Charges du ménage", "money"),
        f("rent", "Loyer mensuel|Loyer", "money"),
        f("household_size", "Personnes à charge|Taille du ménage"),
        f("existing_instalments", "Échéances existantes|Mensualités en cours", "money"),
    ),
    "statement": (
        f("account_number", "Numéro de compte|N° de compte|IBAN"),
        f("institution", "Banque|Institution|Opérateur"),
        f("opening_balance", "Solde initial|Solde d'ouverture", "money"),
        f("closing_balance", "Solde final|Solde de clôture|Solde disponible", "money"),
        f("total_credits", "Total crédits|Total des crédits|Total encaissements", "money"),
        f("total_debits", "Total débits|Total des débits|Total décaissements", "money"),
        f("blocked_amount", "Montant bloqué|Fonds bloqués", "money"),
    ),
    "debt": (
        f("loan_id", "Identifiant du crédit|Numéro de prêt|Référence du prêt"),
        f("payment_amount", "Montant remboursé|Montant payé|Montant du versement", "money"),
        f("payment_date", "Date du paiement|Date de remboursement", "date"),
        f("disbursement_date", "Date de décaissement", "date"),
        f("lender", "Prêteur|Créancier|Établissement prêteur"),
        f("principal", "Capital emprunté|Capital initial|Montant accordé", "money"),
        f("outstanding", "Capital restant dû|Solde restant dû", "money"),
        f("instalment", "Mensualité|Montant de l'échéance|Échéance mensuelle", "money"),
        f("interest_rate", "Taux nominal annuel|Taux d'intérêt|Taux nominal", "rate"),
        f("fees", "Total frais|Frais du crédit", "money"),
        f("arrears", "Montant des impayés|Arriérés|Montant en retard", "money"),
        f("duration", "Durée du prêt|Durée du crédit"),
        f("restructuring", "Motif de restructuration|Motif du rééchelonnement"),
    ),
    "credit_history": (
        f("borrower_id", "Identifiant emprunteur|Identifiant client"),
        f("application_id", "Identifiant demande|Numéro de demande"),
        f("loan_id", "Identifiant du crédit|Numéro de prêt"),
        f("application_date", "Date de demande", "date"),
        f("payment_amount", "Montant payé|Montant reçu", "money"),
        f("payment_date", "Date du paiement|Date de réception", "date"),
        f("due_date", "Date d'échéance", "date"),
        f("expected_amount", "Montant attendu|Échéance attendue", "money"),
        f("decision_reason", "Motif de décision|Motif du refus"),
        f("outstanding", "Encours total|Capital restant dû", "money"),
        f("arrears", "Total impayés|Montant en retard|Arriérés", "money"),
        f("days_past_due", "Jours de retard|Retard maximal"),
        f("default_date", "Date de défaut", "date"),
        f("decision", "Décision|Statut de la demande"),
        f("recovered_amount", "Montant recouvré|Montant récupéré", "money"),
        f("loss", "Perte finale|Perte constatée", "money"),
    ),
    "financial": (
        f("turnover", "Chiffre d'affaires|Chiffre affaires", "money"),
        f("net_result", "Résultat net|Résultat de l'exercice", "money"),
        f("equity", "Capitaux propres|Fonds propres", "money"),
        f("total_assets", "Total actif|Total de l'actif", "money"),
        f("total_liabilities", "Total passif|Total du passif", "money"),
        f("cash", "Trésorerie disponible|Trésorerie nette|Disponibilités", "money"),
        f("receivables", "Créances clients|Clients et comptes rattachés", "money"),
        f("payables", "Dettes fournisseurs|Fournisseurs et comptes rattachés", "money"),
        f("inventory", "Stocks et en-cours|Total stocks", "money"),
        f("operating_cash_flow", "Flux de trésorerie d'exploitation|Flux opérationnels", "money"),
        f("expenses", "Total charges|Charges d'exploitation", "money"),
    ),
    "ledger": (
        f("total_receipts", "Total recettes|Total ventes|Total encaissements", "money"),
        f("total_expenses", "Total dépenses|Total achats|Total décaissements", "money"),
        f("total_balance", "Solde total|Total général", "money"),
        f("valuation", "Valeur totale|Valeur du stock", "money"),
    ),
    "commercial": (
        f("counterparty", "Client|Fournisseur|Acheteur|Prestataire"),
        f("amount_ex_tax", "Montant HT|Total HT", "money"),
        f("tax_amount", "Total TVA|Montant TVA", "money"),
        f("amount_inc_tax", "Montant TTC|Total TTC|Net à payer", "money"),
        f("due_date", "Date d'échéance|Échéance de paiement", "date"),
        f("payment_terms", "Conditions de paiement|Délai de paiement"),
        f("contract_value", "Montant du marché|Montant du contrat|Budget total", "money"),
    ),
    "tax_social": (
        f("tax_number", "Numéro IFU|IFU"),
        f("social_number", "Numéro CNSS|Matricule CNSS"),
        f("amount_due", "Montant dû|Cotisations dues|Impôt dû", "money"),
        f("amount_paid", "Montant payé|Montant acquitté", "money"),
        f("arrears", "Arriérés|Solde à payer", "money"),
        f("payroll", "Masse salariale", "money"),
        f("tax_status", "Situation fiscale|Situation sociale|Statut fiscal"),
    ),
    "collateral": (
        f("owner", "Propriétaire|Titulaire du droit|Caution"),
        f("asset_identifier", "Titre foncier|Numéro de châssis|Immatriculation|Référence du bien"),
        f("asset_description", "Description du bien|Nature du bien|Désignation du bien"),
        f("valuation", "Valeur estimée|Valeur d'expertise|Montant garanti", "money"),
        f("encumbrances", "Charges et inscriptions|Garanties existantes"),
        f("coverage", "Conditions de couverture|Étendue de la garantie"),
        f("expiry_date", "Date d'expiration|Fin de couverture", "date"),
    ),
    "sector": (
        f("activity", "Activité|Spéculation|Type d'élevage"),
        f("quantity", "Quantité produite|Effectif du cheptel|Quantité vendue"),
        f("surface", "Superficie exploitée|Surface exploitée"),
        f("sales", "Total ventes|Recettes d'exploitation", "money"),
        f("costs", "Coût des intrants|Coût d'entretien|Coût d'alimentation", "money"),
        f("insurance", "Assureur|Numéro de police"),
        f("use_right", "Droit d'usage|Droit d'exploitation"),
    ),
    "verification": (
        f("reviewer", "Agent vérificateur|Nom de l'agent|Auteur du rapport"),
        f("visit_date", "Date de visite|Date de vérification", "date"),
        f("observations", "Observations|Constats|Conclusion"),
        f("activity", "Activité constatée|Activité"),
    ),
    "policy": (
        f("version", "Version du document|Version"),
        f("effective_date", "Date d'effet|Date d'application", "date"),
        f("scope", "Périmètre|Finalité|Objet"),
        f("parties", "Parties signataires|Responsable du traitement"),
        f("retention", "Durée de conservation"),
        f("product", "Produit de crédit|Nom du produit"),
        f("rate", "Taux nominal annuel|Taux nominal", "rate"),
        f("fees", "Frais du crédit|Total frais", "money"),
    ),
}

# id ; libellé ; famille ; destination. Chaque ligne a un profil d'extraction.
ROWS = """
identity_card;CNIB;identity;shared
passport;Passeport;identity;shared
address_proof;Justificatif de domicile;location;shared
credit_application;Demande de crédit;request;shared
income_expense_declaration;Déclaration des revenus charges et dettes;budget;individuals
data_notice;Notice de traitement des données;policy;shared
data_authorization;Autorisation de collecte et de partage;policy;shared
bic_consent;Consentement BIC;policy;shared
bic_report;Rapport de solvabilité;credit_history;shared
rccm;Extrait RCCM;legal;businesses
ifu;Attestation IFU;legal;businesses
articles;Statuts de la société;legal;businesses
ownership;Répartition du capital et bénéficiaires effectifs;legal;businesses
appointment;Acte de nomination;legal;businesses
power_of_attorney;Délégation de pouvoir;legal;shared
borrowing_resolution;Décision autorisant l'emprunt;legal;businesses
commercial_lease;Bail commercial;location;businesses
occupancy_title;Titre d'occupation des locaux;location;businesses
operating_license;Agrément ou autorisation d'exercice;legal;businesses
annual_financials;États financiers annuels;financial;businesses
balance_sheet;Bilan;financial;businesses
income_statement;Compte de résultat;financial;businesses
cash_flow_statement;Tableau des flux de trésorerie;financial;businesses
financial_notes;Notes annexes;financial;businesses
interim_accounts;Situation comptable intermédiaire;financial;businesses
trial_balance;Balance générale;ledger;businesses
general_ledger;Grand livre;ledger;businesses
monthly_activity;Tableau mensuel du chiffre d'affaires et des charges;financial;businesses
bank_statement;Relevé bancaire;statement;shared
mobile_money_statement;Relevé mobile money;statement;shared
cash_book;Livre de caisse;ledger;businesses
receivables;État des créances clients;ledger;businesses
payables;État des dettes fournisseurs;ledger;businesses
inventory;Inventaire des stocks;ledger;businesses
fixed_assets;Liste des immobilisations;ledger;businesses
cash_forecast;Plan de trésorerie prévisionnel;financial;businesses
loan_contract;Contrat de prêt;debt;shared
amortization_schedule;Tableau d'amortissement;debt;shared
loan_balance;Attestation de capital restant dû;debt;shared
payment_receipt;Justificatif de remboursement;debt;shared
finance_lease;Contrat de crédit-bail;debt;businesses
credit_lines;État des lignes de crédit et découverts;debt;businesses
tax_debt_schedule;Échéancier de dette fiscale;tax_social;businesses
social_debt_schedule;Échéancier de dette sociale;tax_social;businesses
informal_debt;Déclaration des prêts informels;debt;shared
shareholder_advance;Avances et comptes courants d'associés;debt;businesses
guarantees_given;État des cautions données;collateral;businesses
restructuring;Accord de rééchelonnement ou restructuration;debt;shared
arrears_notice;Avis d'impayés;debt;shared
business_description;Présentation de l'entreprise;verification;businesses
customer_concentration;Liste des principaux clients;commercial;businesses
supplier_concentration;Liste des principaux fournisseurs;commercial;businesses
sales_invoice;Facture de vente;commercial;businesses
purchase_invoice;Facture d'achat;commercial;businesses
customer_contract;Contrat client;commercial;businesses
purchase_order;Bon de commande;commercial;businesses
awarded_market;Marché obtenu;commercial;businesses
quotation;Devis;commercial;shared
proforma_invoice;Facture pro forma;commercial;shared
project_budget;Budget du projet;request;shared
contribution_proof;Justificatif d'apport;statement;shared
financial_forecast;Prévisions financières et hypothèses;financial;businesses
site_visit;Rapport de visite d'activité;verification;businesses
tax_return;Déclaration fiscale;tax_social;businesses
tax_payment;Justificatif de paiement d'impôt;tax_social;businesses
tax_clearance;Attestation de situation fiscale;tax_social;businesses
social_return;Déclaration de cotisations sociales;tax_social;businesses
social_payment;Justificatif de cotisations sociales;tax_social;businesses
payroll_summary;Synthèse de la masse salariale;tax_social;businesses
sales_journal;Cahier de ventes;ledger;businesses
expense_journal;Cahier des dépenses et achats;ledger;businesses
supplier_receipt;Reçu fournisseur;commercial;businesses
household_business_split;Séparation du budget ménage et activité;budget;shared
interview;Fiche d'entretien structuré;verification;shared
payslip;Bulletin de salaire;income;individuals
employment_certificate;Attestation d'emploi;income;individuals
employment_contract;Contrat de travail;income;individuals
employment_appointment;Acte de nomination professionnelle;income;individuals
bonus_income;Justificatif de primes et revenus complémentaires;income;individuals
household_budget;Budget du ménage;budget;individuals
residential_lease;Bail d'habitation;location;individuals
housing_instalment;Échéancier de crédit logement;debt;individuals
salary_withholdings;Justificatif des retenues sur salaire;income;individuals
pension_statement;Justificatif de pension;income;individuals
self_employment_proof;Justificatif d'activité indépendante;verification;individuals
service_contract;Contrat de prestation;commercial;shared
receipt_proof;Justificatif d'encaissement;commercial;shared
farm_calendar;Calendrier de campagne agricole;sector;businesses
land_use;Justificatif d'usage des terres;sector;businesses
farm_production;Historique de production et ventes agricoles;sector;businesses
input_budget;Budget des intrants;sector;businesses
livestock_inventory;Inventaire du cheptel;sector;businesses
livestock_costs;Coûts d'alimentation et soins du cheptel;sector;businesses
vehicle_registration;Documents d'identification du véhicule;collateral;shared
transport_revenue;Recettes d'exploitation du transport;sector;businesses
maintenance;Justificatifs d'entretien;sector;businesses
insurance;Contrat d'assurance;sector;shared
guarantor_commitment;Engagement de caution personnelle;collateral;shared
guarantor_resources;Ressources et dettes de la caution;budget;shared
property_title;Titre de propriété immobilière;collateral;shared
encumbrance_report;État des droits et inscriptions;collateral;shared
appraisal;Rapport d'expertise de garantie;collateral;shared
equipment_ownership;Preuve de propriété d'équipement;collateral;businesses
stock_pledge;Dossier de garantie sur stock;collateral;businesses
receivable_assignment;Cession ou nantissement de créance;collateral;businesses
blocked_savings;Attestation d'épargne bloquée;statement;shared
guarantee_letter;Lettre de garantie d'un organisme;collateral;shared
partner_application;Formulaire de demande du partenaire;request;partner
partner_checklist;Liste de pièces du partenaire;policy;partner
credit_product;Fiche produit de crédit;policy;partner
eligibility_rules;Critères d'éligibilité;policy;partner
scoring_grid;Grille de notation;policy;partner
analysis_report;Rapport d'analyse de crédit;verification;partner
exception_policy;Règles de gestion des exceptions;policy;partner
verification_policy;Procédure de vérification et validation;policy;partner
default_definition;Définition des retards et défauts;policy;partner
historical_applications;Historique des demandes de crédit;credit_history;training
historical_decisions;Historique des décisions de crédit;credit_history;training
historical_disbursements;Historique des crédits décaissés;debt;training
historical_schedules;Historique des échéanciers;debt;training
historical_payments;Historique des paiements réels;credit_history;training
historical_arrears;Historique des retards;credit_history;training
historical_restructurings;Historique des restructurations;debt;training
historical_defaults_recoveries;Historique des défauts pertes et recouvrements;credit_history;training
data_dictionary;Dictionnaire des données;policy;internal
document_reference;Référentiel des pièces;policy;internal
indicator_manual;Manuel des indicateurs;policy;internal
missing_data_policy;Politique des données manquantes;policy;internal
model_validation;Protocole d'entraînement et validation;policy;internal
access_retention_policy;Politique d'accès et conservation;policy;internal
partner_agreement;Convention partenaire;policy;internal
correction_procedure;Procédure de correction et contestation;policy;internal
"""


def catalog():
    result = {}
    for row in ROWS.strip().splitlines():
        key, title, family, target = row.split(";")
        fields = list(COMMON + FAMILIES[family])
        result[key] = {"id": key, "title": title, "family": family,
                       "target": target, "fields": fields}
    return result


CATALOG = catalog()


def public_catalog():
    return [{**{k: v for k, v in p.items() if k != "fields"},
             "fields": [{"key": f.key, "aliases": list(f.aliases), "kind": f.kind}
                        for f in p["fields"]],
             "support": "text_tables_forms_ocr_candidates",
             "authenticity_verification": False}
            for p in CATALOG.values()]
