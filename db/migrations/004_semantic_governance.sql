-- Governance metadata only.  It never creates, alters, or writes SH objects.
-- Oracle DDL auto-commits; inspect any partial failure before re-running.
whenever sqlerror exit failure rollback
set define off
set serveroutput on

declare
  n number;
  procedure ensure_table(p_name varchar2, p_ddl varchar2) is
    found number;
  begin
    select count(*) into found from user_tables where table_name=p_name;
    if found=0 then execute immediate p_ddl; end if;
  end;
begin
  if sys_context('USERENV','SESSION_USER') <> 'FASTONTO'
     or sys_context('USERENV','CURRENT_SCHEMA') <> 'FASTONTO'
     or sys_context('USERENV','CON_NAME') <> 'ORCLPDB1' then
    raise_application_error(-20001,'Expected FASTONTO in ORCLPDB1');
  end if;
  select count(*) into n from FO_SCHEMA_MIGRATIONS where version_no=3;
  if n<>1 then raise_application_error(-20002,'Apply migrations 001 through 003 first'); end if;

  ensure_table('FO_WORKSPACES', q'~create table FO_WORKSPACES(
    workspace_id varchar2(36) primary key, code varchar2(80 char) not null unique,
    title varchar2(200 char) not null, description varchar2(1000 char),
    lifecycle varchar2(20 char) default 'ACTIVE' not null check(lifecycle in ('ACTIVE','ARCHIVED')),
    created_at timestamp with time zone default systimestamp not null,
    updated_at timestamp with time zone default systimestamp not null)~');
  ensure_table('FO_DOMAINS', q'~create table FO_DOMAINS(
    domain_id varchar2(36) primary key, workspace_id varchar2(36) not null references FO_WORKSPACES(workspace_id),
    code varchar2(80 char) not null, title varchar2(200 char) not null, description varchar2(1000 char),
    lifecycle varchar2(20 char) default 'ACTIVE' not null check(lifecycle in ('ACTIVE','ARCHIVED')),
    created_at timestamp with time zone default systimestamp not null,
    updated_at timestamp with time zone default systimestamp not null,
    constraint FO_DOMAINS_UQ unique(workspace_id,code))~');
  ensure_table('FO_ONTOLOGIES', q'~create table FO_ONTOLOGIES(
    ontology_id varchar2(36) primary key, workspace_id varchar2(36) not null references FO_WORKSPACES(workspace_id),
    domain_id varchar2(36) not null references FO_DOMAINS(domain_id),
    code varchar2(80 char) not null, title varchar2(200 char) not null, description varchar2(1000 char),
    lifecycle varchar2(20 char) default 'DRAFT' not null check(lifecycle in ('DRAFT','PUBLISHED','DEPRECATED')),
    model_id varchar2(36), model_revision number(10),
    created_at timestamp with time zone default systimestamp not null,
    updated_at timestamp with time zone default systimestamp not null,
    constraint FO_ONTOLOGIES_UQ unique(domain_id,code),
    constraint FO_ONTOLOGIES_MODEL_CK check((model_id is null and model_revision is null) or (model_id is not null and model_revision > 0)))~');
  ensure_table('FO_MAPPING_ASSETS', q'~create table FO_MAPPING_ASSETS(
    mapping_id varchar2(36) primary key, ontology_id varchar2(36) not null references FO_ONTOLOGIES(ontology_id),
    code varchar2(80 char) not null, title varchar2(200 char) not null,
    source_code varchar2(80 char) not null, mapping_kind varchar2(30 char) not null check(mapping_kind in ('R2RML_DRAFT','VIEW_R2RML_DRAFT')),
    definition_json clob not null, lifecycle varchar2(20 char) default 'DRAFT' not null check(lifecycle in ('DRAFT','RETIRED')),
    created_at timestamp with time zone default systimestamp not null,
    updated_at timestamp with time zone default systimestamp not null,
    constraint FO_MAPPING_ASSETS_UQ unique(ontology_id,code))~');
  ensure_table('FO_SEMANTIC_ASSETS', q'~create table FO_SEMANTIC_ASSETS(
    asset_id varchar2(36) primary key, ontology_id varchar2(36) not null references FO_ONTOLOGIES(ontology_id),
    asset_kind varchar2(20 char) not null check(asset_kind in ('RULE','METRIC','ACTION')),
    code varchar2(80 char) not null, title varchar2(200 char) not null, description varchar2(1000 char),
    definition_json clob not null, lifecycle varchar2(20 char) default 'DRAFT' not null check(lifecycle in ('DRAFT','PUBLISHED','RETIRED')),
    created_at timestamp with time zone default systimestamp not null,
    updated_at timestamp with time zone default systimestamp not null,
    constraint FO_SEMANTIC_ASSETS_UQ unique(ontology_id,asset_kind,code))~');
  execute immediate q'~insert into FO_SCHEMA_MIGRATIONS(version_no,description)
    select 4,'Workspace, domain, ontology, mapping draft, rule, metric, and action governance metadata' from dual
    where not exists(select 1 from FO_SCHEMA_MIGRATIONS where version_no=4)~';
  commit;
end;
/
