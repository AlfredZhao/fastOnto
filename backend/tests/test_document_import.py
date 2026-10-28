import base64
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape

import pytest
import yaml

from app.document_import import (DocumentInput, DraftInput, MAX_FILE, MAX_REQUEST,
                                 inspect_document, generate_draft, _xml)
from app.modeling import InvalidModel


def upload(filename, content):
    raw = content.encode() if isinstance(content, str) else content
    return DocumentInput(filename=filename, content_base64=base64.b64encode(raw).decode())


def package(parts):
    buffer = BytesIO()
    with ZipFile(buffer, 'w', compression=ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<Types/>')
        for name, data in parts.items(): archive.writestr(name, data)
    return buffer.getvalue()


def xlsx(rows, extra=None):
    body = ''.join(f'<row r="{ri}">' + ''.join(
        f'<c r="{chr(65 + ci)}{ri}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
        for ci, value in enumerate(row)) + '</row>' for ri, row in enumerate(rows, 1))
    parts = {
        'xl/workbook.xml': '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="标准" sheetId="1" r:id="rId1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
        'xl/worksheets/sheet1.xml': f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{body}</sheetData></worksheet>',
    }
    parts.update(extra or {})
    return package(parts)


def draft(classes):
    return DraftInput(name='standards', title='标准与机构', namespace='https://example.org/demo/', classes=classes)


def test_xlsx_headers_not_business_records():
    result = inspect_document(upload('标准.xlsx', xlsx([['标准编号', '发布机构'], ['PRIVATE-ROW', '私人机构']])))
    assert len(result['classes']) == 1
    fields = result['classes'][0]['fields']
    assert [f['title'] for f in fields] == ['标准编号', '发布机构']
    assert all(f['range'] == 'string' and not f['required'] for f in fields)
    assert '第 1 行第 2 列' in fields[1]['evidence']
    generated = generate_draft(draft(result['classes']))
    assert 'PRIVATE-ROW' not in str(result) + generated['source']
    assert '私人机构' not in generated['source']
    assert generated['report']['valid']


def test_dictionary_typed_fields_and_evidence():
    result = inspect_document(upload('字典.xlsx', xlsx([
        ['实体', '字段', '类型', '说明'], ['Standard', 'issuedDate', '日期', '发布日期'],
        ['Organization', 'name', 'string', '机构名称'], ['Standard', 'issuedBy', 'Organization', '发布机构'],
    ])))
    assert [c['name'] for c in result['classes']] == ['Standard', 'Organization']
    standard = result['classes'][0]
    assert standard['fields'][0]['range'] == 'date'
    assert standard['fields'][1]['range'] == 'string'
    assert any('未识别' in w for w in result['warnings'])
    standard['fields'][1]['range'] = 'Organization'
    model = generate_draft(draft(result['classes']))
    assert model['report']['relationships'][0]['target'] == 'Organization'
    assert '来源：字典.xlsx' in model['source']


def test_markdown_tables_and_code_fences():
    result = inspect_document(upload('字典.md', '''# 不当作额外实体
| 实体 | 字段 | 类型 |
| --- | --- | --- |
| Product | price | decimal |

```yaml
# 不提取代码
```
'''))
    assert len(result['classes']) == 1
    assert result['classes'][0]['fields'][0]['range'] == 'decimal'


def test_markdown_headings_and_plain_text_empty_candidates():
    result = inspect_document(upload('术语.md', '# 标准\n正文\n## 发布机构\n正文'))
    assert [c['title'] for c in result['classes']] == ['标准', '发布机构']
    assert all(c['fields'] == [] for c in result['classes'])
    result = inspect_document(upload('说明.txt', '标准由机构发布；这不是一个自动推断的对象关系。'))
    assert result['classes'] == []
    assert any('未发现' in w for w in result['warnings'])


def test_docx_table_no_record_copy():
    result = inspect_document(upload('标准.docx', package({'word/document.xml': '''
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
<w:tbl><w:tr><w:tc><w:p><w:r><w:t>编号</w:t></w:r></w:p></w:tc></w:tr>
<w:tr><w:tc><w:p><w:r><w:t>SECRET-ROW</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
</w:body></w:document>'''})))
    assert result['classes'][0]['fields'][0]['title'] == '编号'
    assert 'SECRET-ROW' not in str(result)


def test_docx_heading():
    result = inspect_document(upload('术语.docx', package({'word/document.xml': '''
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>标准</w:t></w:r></w:p>
</w:body></w:document>'''})))
    assert result['classes'][0]['title'] == '标准'


def test_yaml_import_roundtrip(source):
    result = inspect_document(upload('模型.yaml', source))
    assert result['kind'] == 'yaml' and result['source'] == source and result['saved'] is False


@pytest.mark.parametrize('filename,content', [
    ('old.xls', b'bad'), ('old.doc', b'bad'), ('bad.docm', b'bad'), ('bad.xlsx', b'notzip'),
    ('bad.md', b'\xff'), ('bad.txt', b'\x00'), ('empty.md', '  '), ('../file.md', '# title'),
    ('x\\y.md', '# title'), ('bad.yaml', 'classes: ['), ('bad.yaml', b'\xff'),
])
def test_invalid_files(filename, content):
    with pytest.raises(InvalidModel): inspect_document(upload(filename, content))


def test_invalid_base64_and_oversize():
    with pytest.raises(InvalidModel):
        inspect_document(DocumentInput(filename='x.md', content_base64='?'))
    with pytest.raises(InvalidModel, match='2 MiB'):
        inspect_document(upload('x.txt', b'a' * (MAX_FILE + 1)))


@pytest.mark.parametrize('raw', [b'<!DOCTYPE x><x/>', b'<!DOCTYPE x [<!ENTITY e "boom">]><x>&e;</x>', '<x/>'.encode('utf-16'), b'<x>'])
def test_xml_no_entities_or_non_utf8(raw):
    with pytest.raises(InvalidModel): _xml(raw)


@pytest.mark.parametrize('extra', [{'../unsafe': 'x'}, {'xl/vbaProject.bin': 'x'}, {'xl/externalLinks/externalLink1.xml': '<x/>'}, {'large.xml': 'a' * (4 * 1024 * 1024)}])
def test_unsafe_packages(extra):
    with pytest.raises(InvalidModel): inspect_document(upload('unsafe.xlsx', xlsx([['id']], extra)))


def test_duplicate_header_rejected():
    with pytest.raises(InvalidModel, match='表头'):
        inspect_document(upload('bad.xlsx', xlsx([['name', 'name']])))


def test_duplicate_and_broken_candidate_references():
    cls = {'name': 'Standard', 'title': '标准', 'fields': []}
    with pytest.raises(InvalidModel, match='重复'): generate_draft(draft([cls, cls]))
    cls['fields'] = [{'name': 'issuedBy', 'title': '发布机构', 'range': 'Missing'}]
    with pytest.raises(InvalidModel, match='未知类型'): generate_draft(draft([cls]))
    cls['fields'] = [{'name': 'title', 'title': '名称'}, {'name': 'title', 'title': '名称'}]
    with pytest.raises(InvalidModel, match='重复'): generate_draft(draft([cls]))


def test_distinct_property_iris_for_same_field_name():
    result = generate_draft(draft([{'name': n, 'title': n, 'fields': [{'name': 'title', 'title': '名称'}]} for n in ['A', 'B']]))
    schema = yaml.safe_load(result['source'])
    assert schema['classes']['A']['attributes']['title']['slot_uri'] != schema['classes']['B']['attributes']['title']['slot_uri']


def test_import_and_draft_api_never_persist(client, monkeypatch):
    from app import repository
    monkeypatch.setattr(repository, 'save_model', lambda *args: pytest.fail('unexpected persistence'))
    response = client.post('/api/models/import', json=upload('术语.md', '# Standard').model_dump())
    assert response.status_code == 200
    response = client.post('/api/models/draft', json=draft(response.json()['classes']).model_dump())
    assert response.status_code == 200 and response.json()['saved'] is False


@pytest.mark.parametrize('name', ['blank', 'sales', 'standards'])
def test_template_allowlist(client, name):
    from app.modeling import parse_model
    response = client.get('/api/models/template', params={'name': name})
    assert response.status_code == 200
    assert parse_model(response.json()['source'])[1]['valid']
    assert client.get('/api/models/template?name=../../.env').status_code == 422


def test_import_route_size_and_origin(client):
    assert client.post('/api/models/import', content='a' * (MAX_REQUEST + 1)).status_code == 413
    assert client.post('/api/models/import', json=upload('x.md', '# X').model_dump(), headers={'Origin': 'https://evil.invalid'}).status_code == 403
    assert client.post('/api/models/import', json=upload('large.txt', 'x' * 140000).model_dump()).status_code == 200
    assert client.post('/api/models/draft', content='a' * 131073).status_code == 413


def test_markdown_pipe_in_prose_is_not_a_table():
    result = inspect_document(upload('prose.md', '这不是表格 | 只是句子\n另一行'))
    assert result['classes'] == []


def test_formulas_never_use_cached_values():
    xml = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="str"><f>HYPERLINK("https://evil.invalid")</f><v>cached header</v></c></row></sheetData></worksheet>'
    result = inspect_document(upload('formula.xlsx', xlsx([['ignored']], {'xl/worksheets/sheet1.xml': xml})))
    assert result['classes'] == []
    assert 'cached header' not in str(result)


def test_hidden_sheet_and_shared_strings():
    sheet = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData></worksheet>'
    shared = '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>编号</t></si></sst>'
    result = inspect_document(upload('shared.xlsx', xlsx([['ignored']], {'xl/worksheets/sheet1.xml': sheet, 'xl/sharedStrings.xml': shared})))
    assert result['classes'][0]['fields'][0]['title'] == '编号'
    workbook = '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="私密" state="hidden" r:id="rId1"/></sheets></workbook>'
    result = inspect_document(upload('hidden.xlsx', xlsx([['hidden header']], {'xl/workbook.xml': workbook})))
    assert result['classes'] == []
    assert any('跳过隐藏' in w for w in result['warnings'])


def test_deep_xml_and_duplicate_package_names():
    with pytest.raises(InvalidModel, match='嵌套'):
        _xml(('<x>' * 42 + '</x>' * 42).encode())
    buffer = BytesIO()
    with ZipFile(buffer, 'w') as archive:
        archive.writestr('[Content_Types].xml', '<Types/>')
        with pytest.warns(UserWarning): archive.writestr('[Content_Types].xml', '<Types/>')
    with pytest.raises(InvalidModel, match='重复'):
        inspect_document(upload('duplicate.xlsx', buffer.getvalue()))


def test_candidate_count_rejected_without_silent_truncation():
    with pytest.raises(InvalidModel, match='30'):
        inspect_document(upload('many.md', '\n'.join(f'# Entity{i}' for i in range(31))))


@pytest.mark.parametrize('format', ['jsonschema', 'owl', 'shacl'])
def test_generated_candidate_exports(client, format):
    from rdflib import Graph
    result = inspect_document(upload('dictionary.md', '| 实体 | 字段 | 类型 |\n| --- | --- | --- |\n| Standard | issuedBy | string |\n| Organization | name | string |'))
    result['classes'][0]['fields'][0]['range'] = 'Organization'
    source = generate_draft(draft(result['classes']))['source']
    response = client.post(f'/api/models/export/{format}', json={'source': source})
    assert response.status_code == 200
    if format != 'jsonschema': assert len(Graph().parse(data=response.json()['content'], format='turtle')) > 0


def test_shipped_dictionary_example():
    from app.config import ROOT
    result = inspect_document(upload('example.md', (ROOT / 'models/document-dictionary-example.md').read_text()))
    assert [c['name'] for c in result['classes']] == ['Standard', 'Organization']
    assert sum(len(c['fields']) for c in result['classes']) == 4
