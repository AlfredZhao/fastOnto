-- Only schema-private network and metadata; ordinary views, NOT materialized copies.
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
  select count(*) into n from FO_SCHEMA_MIGRATIONS where version_no=1;
  if n<>1 then raise_application_error(-20002,'Apply 001_platform.sql first'); end if;
  select count(*) into n from user_tables where table_name='FO_NET#RDF_PARAMETER';
  if n=0 then
    SEM_APIS.CREATE_RDF_NETWORK(tablespace_name=>'USERS', network_owner=>'FASTONTO', network_name=>'FO_NET');
  end if;
end;
/

create or replace view FO_CUSTOMERS_SOURCE as
select CUST_ID, CUST_FIRST_NAME || ' ' || CUST_LAST_NAME as CUSTOMER_LABEL, COUNTRY_ID
from SH.CUSTOMERS;

create or replace view FO_PRODUCTS_SOURCE as
select PROD_ID, PROD_NAME, PROD_CATEGORY, PROD_LIST_PRICE from SH.PRODUCTS;

declare
  n number;
  mapping clob := q'~
@prefix rr: <http://www.w3.org/ns/r2rml#> .
@prefix fo: <https://fastonto.example/vocab/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
<https://fastonto.example/mapping/customer>
  rr:logicalTable [ rr:tableName "FO_CUSTOMERS_SOURCE" ];
  rr:subjectMap [ rr:template "https://fastonto.example/entity/customer/{CUST_ID}"; rr:class fo:Customer ];
  rr:predicateObjectMap [ rr:predicate fo:label; rr:objectMap [ rr:column "CUSTOMER_LABEL" ] ];
  rr:predicateObjectMap [ rr:predicate fo:country; rr:objectMap [ rr:template "https://fastonto.example/entity/country/{COUNTRY_ID}"; rr:termType rr:IRI ] ].
<https://fastonto.example/mapping/product>
  rr:logicalTable [ rr:tableName "FO_PRODUCTS_SOURCE" ];
  rr:subjectMap [ rr:template "https://fastonto.example/entity/product/{PROD_ID}"; rr:class fo:Product ];
  rr:predicateObjectMap [ rr:predicate fo:label; rr:objectMap [ rr:column "PROD_NAME" ] ];
  rr:predicateObjectMap [ rr:predicate fo:category; rr:objectMap [ rr:column "PROD_CATEGORY" ] ];
  rr:predicateObjectMap [ rr:predicate fo:listPrice; rr:objectMap [ rr:column "PROD_LIST_PRICE"; rr:datatype xsd:decimal ] ].
~';
begin
  -- Physical graph catalogs differ by network; use the network-owned catalog.
  execute immediate 'select count(*) from "FO_NET#SEM_MODEL$" where MODEL_NAME=:name' into n using 'FO_SH_V1';
  if n=0 then
    SEM_APIS.CREATE_RDFVIEW_GRAPH(rdf_graph_name=>'FO_SH_V1', tables=>NULL,
      r2rml_string=>mapping, r2rml_string_fmt=>'TURTLE',
      network_owner=>'FASTONTO', network_name=>'FO_NET');
  end if;
  insert into FO_SCHEMA_MIGRATIONS(version_no,description)
    select 2,'Schema-private network and virtual customer/product R2RML mapping v1' from dual
    where not exists(select 1 from FO_SCHEMA_MIGRATIONS where version_no=2);
  commit;
end;
/
