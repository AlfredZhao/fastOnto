-- Hide the future multi-tenant workspace layer behind one internal default scope.
-- No SH objects, data, privileges, or RDF mappings are changed.
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
  select count(*) into n from FO_SCHEMA_MIGRATIONS where version_no=4;
  if n<>1 then raise_application_error(-20002,'Apply migration 004_semantic_governance.sql first'); end if;
  insert into FO_WORKSPACES(workspace_id,code,title,description,lifecycle)
    select '00000000-0000-0000-0000-000000000005','platform_default','平台内部默认范围',
           '当前单管理员部署的内部业务域容器；不在 UI 暴露。','ACTIVE'
    from dual where not exists(select 1 from FO_WORKSPACES where workspace_id='00000000-0000-0000-0000-000000000005');
  insert into FO_SCHEMA_MIGRATIONS(version_no,description)
    select 5,'Internal default workspace; business domains are the only user-facing top-level scope' from dual
    where not exists(select 1 from FO_SCHEMA_MIGRATIONS where version_no=5);
  commit;
end;
/
