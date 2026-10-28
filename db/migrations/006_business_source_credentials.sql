-- Encrypted external Oracle source credentials. Master keys never enter this database.
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
  select count(*) into n from FO_SCHEMA_MIGRATIONS where version_no=5;
  if n<>1 then raise_application_error(-20002,'Apply migrations 001 through 005 first'); end if;
  ensure_table('FO_BUSINESS_SOURCES', q'~create table FO_BUSINESS_SOURCES(
    source_id varchar2(36) primary key, domain_id varchar2(36) not null references FO_DOMAINS(domain_id),
    code varchar2(80 char) not null, title varchar2(200 char) not null,
    owner_schema varchar2(128 char) not null, credentials_ciphertext clob not null,
    credential_key_version varchar2(40 char) not null, readonly number(1) default 1 not null check(readonly=1),
    enabled number(1) default 1 not null check(enabled in (0,1)),
    created_at timestamp with time zone default systimestamp not null,
    updated_at timestamp with time zone default systimestamp not null,
    constraint FO_BUSINESS_SOURCES_UQ unique(domain_id,code))~');
  ensure_table('FO_SOURCE_OBJECTS', q'~create table FO_SOURCE_OBJECTS(
    object_id varchar2(36) primary key, source_id varchar2(36) not null references FO_BUSINESS_SOURCES(source_id),
    object_name varchar2(128 char) not null, object_type varchar2(10 char) not null check(object_type in ('TABLE','VIEW')),
    columns_json clob not null, schema_fingerprint varchar2(64) not null, enabled number(1) default 1 not null check(enabled in (0,1)),
    created_at timestamp with time zone default systimestamp not null, updated_at timestamp with time zone default systimestamp not null,
    constraint FO_SOURCE_OBJECTS_UQ unique(source_id,object_name))~');
  insert into FO_SCHEMA_MIGRATIONS(version_no,description)
    select 6,'Encrypted external Oracle source credentials and approved source object metadata' from dual
    where not exists(select 1 from FO_SCHEMA_MIGRATIONS where version_no=6);
  commit;
end;
/
