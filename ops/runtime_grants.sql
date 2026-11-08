-- À exécuter APRÈS migrations par le propriétaire du schéma, sur une base dédiée.
-- psql "$MIGRATION_DATABASE_URL" -v app_role=credit_runtime -f ops/runtime_grants.sql
-- Créer le rôle LOGIN séparément avec un secret géré ; ce fichier ne stocke aucun mot de passe.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"app_role";

-- Dossiers et documents : mise à jour contrôlée par l'application.
GRANT SELECT, INSERT, UPDATE ON cases, submissions, print_editions TO :"app_role";
GRANT SELECT, INSERT ON analyses, assessments, documents, document_sources,
  document_runs, structured_inputs, document_reviews, document_events,
  print_events, print_publications, security_events TO :"app_role";

-- Parcours web et comptes.
GRANT SELECT, INSERT, UPDATE ON web_users, web_sessions, journey_drafts,
  web_registrations, institution_accounts TO :"app_role";
GRANT DELETE ON web_sessions TO :"app_role";

-- Partenaires, transmissions et décisions bancaires.
GRANT SELECT, INSERT, UPDATE ON case_grants, institution_workflow_policies,
  bank_partners, internal_reviews, partner_packet_files, internal_attestations,
  bank_transmissions, partner_outbox, partner_events, bank_attachments,
  bank_decision_records, client_inbox_messages TO :"app_role";

-- Niveaux 1 à 3 : analyses décisionnelles, garanties, sinistres, capacité.
GRANT SELECT, INSERT, UPDATE ON decision_analyses, guarantees, guarantee_events,
  guarantee_claims, claim_events, institution_capacity, institution_limits
  TO :"app_role";

GRANT SELECT ON alembic_version TO :"app_role";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app_role";
