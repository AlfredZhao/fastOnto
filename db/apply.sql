-- Run manually from the repository root: sql -S /nolog @db/apply.sql
whenever sqlerror exit failure rollback
connect -name test_fastonto
@@migrations/001_platform.sql
@@migrations/002_virtual_rdf.sql
@@migrations/003_auth.sql
@@migrations/004_semantic_governance.sql
@@migrations/005_default_domain_scope.sql
@@migrations/006_business_source_credentials.sql
@@migrations/007_multi_source_semantics.sql
exit
