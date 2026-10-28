-- Run while connected as FASTONTO. DDL auto-commits; never run as SH or SYS.
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
  ensure_table('FO_SCHEMA_MIGRATIONS', q'~create table FO_SCHEMA_MIGRATIONS(
    version_no number primary key, description varchar2(500 char) not null,
    applied_at timestamp with time zone default systimestamp not null)~');
  ensure_table('FO_MODELS', q'~create table FO_MODELS(
    model_id varchar2(36) primary key, title varchar2(500 char) not null,
    revision number(10) not null check(revision>0), source_yaml clob not null,
    source_sha256 varchar2(64) not null,
    created_at timestamp with time zone default systimestamp not null,
    updated_at timestamp with time zone default systimestamp not null)~');
  ensure_table('FO_MODEL_VERSIONS', q'~create table FO_MODEL_VERSIONS(
    model_id varchar2(36) not null references FO_MODELS(model_id),
    revision number(10) not null, source_yaml clob not null, source_sha256 varchar2(64) not null,
    created_at timestamp with time zone default systimestamp not null,
    constraint FO_MODEL_VERSIONS_PK primary key(model_id,revision))~');
  select count(*) into n from user_tab_columns where
    (table_name='FO_MODELS' and column_name in ('MODEL_ID','TITLE','REVISION','SOURCE_YAML','SOURCE_SHA256','CREATED_AT','UPDATED_AT')) or
    (table_name='FO_MODEL_VERSIONS' and column_name in ('MODEL_ID','REVISION','SOURCE_YAML','SOURCE_SHA256','CREATED_AT'));
  if n<>12 then raise_application_error(-20002,'Metadata table structure mismatch; inspect manually'); end if;
  execute immediate q'~insert into FO_SCHEMA_MIGRATIONS(version_no,description)
    select 1,'Platform model metadata and immutable revision records' from dual
    where not exists(select 1 from FO_SCHEMA_MIGRATIONS where version_no=1)~';
  commit;
end;
/
