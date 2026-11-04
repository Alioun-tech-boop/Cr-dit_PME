-- À exécuter APRÈS migrations par le propriétaire du schéma, sur une base dédiée.
-- psql "$MIGRATION_DATABASE_URL" -v app_role=credit_runtime -f ops/runtime_grants.sql
-- Créer le rôle LOGIN séparément avec un secret géré ; ce fichier ne stocke aucun mot de passe.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"app_role";
GRANT SELECT, INSERT, UPDATE ON cases, submissions, print_editions TO :"app_role";
GRANT SELECT, INSERT ON analyses, assessments, documents, document_sources,
  document_runs, structured_inputs, document_reviews, document_events,
  print_events, print_publications, security_events TO :"app_role";
GRANT SELECT ON alembic_version TO :"app_role";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app_role";
