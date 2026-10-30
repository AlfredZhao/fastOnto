-- Per-dimension presentation rules for controlled analytics. Metadata only; never alters SH.
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
  select count(*) into n from FO_SCHEMA_MIGRATIONS where version_no=9;
  if n<>1 then raise_application_error(-20002,'Apply migrations 001 through 009 first'); end if;
  ensure_table('FO_ANALYTIC_PRESENTATIONS', q'~create table FO_ANALYTIC_PRESENTATIONS(
    dimension_code varchar2(80 char) primary key, definition_json clob not null,
    created_at timestamp with time zone default systimestamp not null,
    updated_at timestamp with time zone default systimestamp not null)~');
  insert into FO_SCHEMA_MIGRATIONS(version_no,description)
    select 10,'Controlled analytic dimension presentation rules' from dual
    where not exists(select 1 from FO_SCHEMA_MIGRATIONS where version_no=10);
  commit;
end;
/
