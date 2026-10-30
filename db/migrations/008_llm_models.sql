-- HTTPS-only LLM provider configuration. API keys remain AES-256-GCM ciphertext in FASTONTO.
whenever sqlerror exit failure rollback
set define off
set serveroutput on
declare
  n number;
begin
  if sys_context('USERENV','SESSION_USER') <> 'FASTONTO'
     or sys_context('USERENV','CURRENT_SCHEMA') <> 'FASTONTO'
     or sys_context('USERENV','CON_NAME') <> 'ORCLPDB1' then
    raise_application_error(-20001,'Expected FASTONTO in ORCLPDB1');
  end if;
  select count(*) into n from FO_SCHEMA_MIGRATIONS where version_no=7;
  if n<>1 then raise_application_error(-20002,'Apply migrations 001 through 007 first'); end if;
  select count(*) into n from user_tables where table_name='FO_LLM_MODELS';
  if n=0 then
    execute immediate q'~create table FO_LLM_MODELS(
      llm_id varchar2(36) primary key, code varchar2(80 char) not null unique,
      title varchar2(200 char) not null, base_url varchar2(1000 char) not null,
      model_name varchar2(200 char) not null, api_key_ciphertext clob not null,
      credential_key_version varchar2(40 char) not null, enabled number(1) default 1 not null check(enabled in (0,1)),
      is_default number(1) default 0 not null check(is_default in (0,1)),
      created_at timestamp with time zone default systimestamp not null,
      updated_at timestamp with time zone default systimestamp not null)~';
  end if;
  insert into FO_SCHEMA_MIGRATIONS(version_no,description)
    select 8,'Encrypted HTTPS LLM provider configurations and default selection' from dual
    where not exists(select 1 from FO_SCHEMA_MIGRATIONS where version_no=8);
  commit;
end;
/
