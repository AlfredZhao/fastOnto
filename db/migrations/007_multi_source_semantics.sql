-- Multi-source mapping metadata and declarative cross-source entity alignment only.
-- It never copies business rows, creates database links, or executes cross-source queries.
whenever sqlerror exit failure rollback
set define off
set serveroutput on
declare
  n number;
  procedure ensure_column(p_table varchar2,p_column varchar2,p_ddl varchar2) is
    found number;
  begin
    select count(*) into found from user_tab_columns where table_name=p_table and column_name=p_column;
    if found=0 then execute immediate p_ddl; end if;
  end;
  procedure ensure_table(p_name varchar2,p_ddl varchar2) is
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
  select count(*) into n from FO_SCHEMA_MIGRATIONS where version_no=6;
  if n<>1 then raise_application_error(-20002,'Apply migrations 001 through 006 first'); end if;

  ensure_column('FO_MAPPING_ASSETS','SOURCE_ID',
    'alter table FO_MAPPING_ASSETS add (source_id varchar2(36) references FO_BUSINESS_SOURCES(source_id))');
  ensure_column('FO_MAPPING_ASSETS','SOURCE_OBJECT_NAME',
    'alter table FO_MAPPING_ASSETS add (source_object_name varchar2(128 char))');
  ensure_table('FO_ENTITY_LINK_ASSETS', q'~create table FO_ENTITY_LINK_ASSETS(
    link_id varchar2(36) primary key, ontology_id varchar2(36) not null references FO_ONTOLOGIES(ontology_id),
    code varchar2(80 char) not null, title varchar2(200 char) not null,
    left_mapping_id varchar2(36) not null references FO_MAPPING_ASSETS(mapping_id),
    right_mapping_id varchar2(36) not null references FO_MAPPING_ASSETS(mapping_id),
    definition_json clob not null, lifecycle varchar2(20 char) default 'DRAFT' not null check(lifecycle in ('DRAFT','RETIRED')),
    created_at timestamp with time zone default systimestamp not null,
    updated_at timestamp with time zone default systimestamp not null,
    constraint FO_ENTITY_LINK_ASSETS_UQ unique(ontology_id,code),
    constraint FO_ENTITY_LINK_ASSETS_DIFFERENT_CK check(left_mapping_id <> right_mapping_id))~');
  insert into FO_SCHEMA_MIGRATIONS(version_no,description)
    select 7,'Business-source mapping bindings and declarative cross-source entity alignment drafts' from dual
    where not exists(select 1 from FO_SCHEMA_MIGRATIONS where version_no=7);
  commit;
end;
/
