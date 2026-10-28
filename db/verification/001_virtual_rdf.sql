whenever sqlerror exit failure rollback
set define off
set serveroutput on
set transaction read only;

declare
  source_count number; rdf_count number;
  mismatch_count number;
  graph_kind varchar2(20);
begin
  if sys_context('USERENV','SESSION_USER') <> 'FASTONTO' then
    raise_application_error(-20001,'Expected FASTONTO');
  end if;
  select count(*) into source_count from SH.CUSTOMERS;
  select count(*) into rdf_count from table(SEM_MATCH(
    'SELECT ?s WHERE { ?s a <https://fastonto.example/vocab/Customer> }',
    SEM_MODELS('FO_SH_V1'), null,null,null,null,null,null,null,'FASTONTO','FO_NET'));
  if source_count<>rdf_count then raise_application_error(-20010,'Customer counts differ'); end if;
  dbms_output.put_line('CUSTOMERS SQL=RDF: ' || source_count);
  select count(*) into source_count from SH.PRODUCTS;
  select count(*) into rdf_count from table(SEM_MATCH(
    'SELECT ?s WHERE { ?s a <https://fastonto.example/vocab/Product> }',
    SEM_MODELS('FO_SH_V1'), null,null,null,null,null,null,null,'FASTONTO','FO_NET'));
  if source_count<>rdf_count then raise_application_error(-20011,'Product counts differ'); end if;
  dbms_output.put_line('PRODUCTS SQL=RDF: ' || source_count);
  select count(*) into mismatch_count from (
    select 'https://fastonto.example/entity/product/' || to_char(prod_id,'FM9999999999990') uri,
      prod_name label from SH.PRODUCTS
    minus
    select product,label from table(SEM_MATCH(
      'SELECT ?product ?label WHERE { ?product a <https://fastonto.example/vocab/Product>; <https://fastonto.example/vocab/label> ?label }',
      SEM_MODELS('FO_SH_V1'),null,null,null,null,null,null,null,'FASTONTO','FO_NET'))
  );
  if mismatch_count<>0 then raise_application_error(-20012,'Product URI/label mapping differs'); end if;
  dbms_output.put_line('PRODUCT URI/LABEL mismatches: 0');
  select model_type into graph_kind from "FO_NET#SEM_MODEL$" where model_name='FO_SH_V1';
  if graph_kind<>'D' then raise_application_error(-20013,'Expected virtual RDF view graph'); end if;
  select count(*) into mismatch_count from "FO_NET#RDF_LINK$" l
    join "FO_NET#RDF_VALUE$" s on s.value_id=l.start_node_id
    where s.value_name like 'https://fastonto.example/entity/%';
  if mismatch_count<>0 then raise_application_error(-20014,'Unexpected materialized business subjects'); end if;
  select count(*) into mismatch_count from "FO_NET#RDF_LINK$" l
    join "FO_NET#RDF_VALUE$" p on p.value_id=l.p_value_id
    where p.value_name like 'https://fastonto.example/vocab/%';
  if mismatch_count<>0 then raise_application_error(-20015,'Unexpected materialized business predicates'); end if;
  select count(*) into rdf_count from "FO_NET#RDF_LINK$";
  dbms_output.put_line('PHYSICAL MAPPING METADATA TRIPLES: ' || rdf_count || '; business subjects/predicates: 0');
end;
/

select product, label, label$rdfterm from table(SEM_MATCH(
  'SELECT ?product ?label WHERE { ?product a <https://fastonto.example/vocab/Product>; <https://fastonto.example/vocab/label> ?label } LIMIT 5',
  SEM_MODELS('FO_SH_V1'), null,null,null,null,'PLUS_RDFT=T',null,null,'FASTONTO','FO_NET'));

rollback;
