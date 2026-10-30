import { Download, Layers3 } from 'lucide-react';
import { download } from '../api';

export default function ApplicationBlueprint({ontology, mappings, entityLinks, assets}: {ontology: {id: string; code: string; title: string; model_id?: string | null; model_revision?: number | null}; mappings: number; entityLinks: number; assets: number}) {
  function exportBlueprint() {
    const content = JSON.stringify({
      version: 1,
      kind: 'FASTONTO_APPLICATION_BLUEPRINT',
      ontology: {id: ontology.id, code: ontology.code, title: ontology.title, model_revision: ontology.model_revision},
      semantic_assets: {mapping_drafts: mappings, identity_link_drafts: entityLinks, rule_metric_action_drafts: assets},
      query_boundary: 'Only reviewed fixed query templates may run; this blueprint does not grant arbitrary SQL or SPARQL.',
      traceability: 'Use the linked LinkML model revision and governance asset IDs as the implementation baseline.',
    }, null, 2);
    download(content, `${ontology.code}-application-blueprint.json`, 'application/json;charset=utf-8');
  }
  return <section className="application-blueprint"><div><strong><Layers3 size={14}/>应用构建蓝图</strong><p>以当前 LinkML 版本、映射草稿和规则/指标/操作草稿生成可交接的应用设计基线。</p></div><button type="button" onClick={exportBlueprint}><Download size={14}/>下载蓝图</button><small>蓝图用于追溯和方案交接，不会发布映射、执行查询或自动生成生产应用。</small></section>;
}
