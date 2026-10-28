-- Application users only; no Oracle DB users or SH objects are changed.
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
  if sys_context('USERENV','SESSION_USER')<>'FASTONTO'
     or sys_context('USERENV','CURRENT_SCHEMA')<>'FASTONTO'
     or sys_context('USERENV','CON_NAME')<>'ORCLPDB1' then
    raise_application_error(-20001,'Expected FASTONTO in ORCLPDB1');
  end if;
  select count(*) into n from FO_SCHEMA_MIGRATIONS where version_no=1;
  if n<>1 then raise_application_error(-20002,'Apply platform migration first'); end if;
  ensure_table('FO_USERS', q'~create table FO_USERS(
    user_id varchar2(36) primary key,
    username varchar2(64 char) not null unique,
    password_hash varchar2(512) not null,
    enabled number(1) default 1 not null check(enabled in (0,1)),
    must_change_password number(1) default 1 not null check(must_change_password in (0,1)),
    credential_version number(10) default 1 not null,
    failed_attempts number(5) default 0 not null,
    locked_until timestamp with time zone,
    password_changed_at timestamp with time zone,
    created_at timestamp with time zone default systimestamp not null)~');
  ensure_table('FO_AUTH_SESSIONS', q'~create table FO_AUTH_SESSIONS(
    token_hash varchar2(64) primary key,
    user_id varchar2(36) not null references FO_USERS(user_id),
    csrf_token varchar2(64) not null,
    credential_version number(10) not null,
    created_at timestamp with time zone default systimestamp not null,
    last_seen_at timestamp with time zone default systimestamp not null,
    expires_at timestamp with time zone not null)~');
  select count(*) into n from user_indexes where index_name='FO_AUTH_SESSIONS_USER_IX';
  if n=0 then execute immediate 'create index FO_AUTH_SESSIONS_USER_IX on FO_AUTH_SESSIONS(user_id)'; end if;
  select count(*) into n from user_indexes where index_name='FO_AUTH_SESSIONS_EXP_IX';
  if n=0 then execute immediate 'create index FO_AUTH_SESSIONS_EXP_IX on FO_AUTH_SESSIONS(expires_at)'; end if;
  insert into FO_SCHEMA_MIGRATIONS(version_no,description)
    select 3,'Argon2id application users and revocable hashed-token sessions' from dual
    where not exists(select 1 from FO_SCHEMA_MIGRATIONS where version_no=3);
  commit;
end;
/
