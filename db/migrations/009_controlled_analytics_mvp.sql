-- Controlled analytics MVP metadata. Runtime SQL remains in reviewed application templates, never in this table.
whenever sqlerror exit failure rollback
set define off
set serveroutput on
declare
  n number;
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
  select count(*) into n from FO_SCHEMA_MIGRATIONS where version_no=8;
  if n<>1 then raise_application_error(-20002,'Apply migrations 001 through 008 first'); end if;
  ensure_table('FO_ANALYTIC_SCENARIOS', q'~create table FO_ANALYTIC_SCENARIOS(
      scenario_id varchar2(36) primary key, ontology_id varchar2(36) not null references FO_ONTOLOGIES(ontology_id),
      code varchar2(80 char) not null, title varchar2(200 char) not null, description varchar2(1000 char),
      definition_json clob not null, lifecycle varchar2(20 char) default 'DRAFT' not null check(lifecycle in ('DRAFT','PUBLISHED','RETIRED')),
      created_at timestamp with time zone default systimestamp not null, updated_at timestamp with time zone default systimestamp not null,
      constraint FO_ANALYTIC_SCENARIOS_UQ unique(ontology_id,code))~');
  insert into FO_SCHEMA_MIGRATIONS(version_no,description)
    select 9,'Controlled SH analytics scenario metadata; reviewed fixed runtime templates only' from dual
    where not exists(select 1 from FO_SCHEMA_MIGRATIONS where version_no=9);
  commit;
end;
/
