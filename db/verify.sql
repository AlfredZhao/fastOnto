-- Read-only verification. No source edits are used to simulate a live update.
whenever sqlerror exit failure rollback
connect -name test_fastonto
@@verification/001_virtual_rdf.sql
exit rollback
