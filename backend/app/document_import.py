"""Local, bounded document-to-schema *candidates*. No execution, network or storage.

Office packages are read in memory, never extracted. Only UTF-8 XML without
DTD/entities is accepted. Records are not copied into the generated model.
"""
import base64
import binascii
from io import BytesIO
import posixpath
from pathlib import PurePosixPath
import re
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError
from xml.etree import ElementTree as ET

from pydantic import BaseModel, ConfigDict, Field
import yaml

from .modeling import InvalidModel, NAME, parse_model

MAX_FILE = 2 * 1024 * 1024
MAX_REQUEST = 3 * 1024 * 1024
TYPES = {"string", "integer", "decimal", "float", "double", "boolean", "date", "datetime", "uriorcurie"}
SS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentInput(StrictInput):
    filename: str = Field(min_length=1, max_length=180)
    content_base64: str = Field(min_length=1, max_length=2796204)


class CandidateField(StrictInput):
    name: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    range: str = Field(default="string", max_length=80)
    required: bool = False
    multivalued: bool = False
    description: str = Field(default="", max_length=1000)
    evidence: str = Field(default="", max_length=500)


class CandidateClass(StrictInput):
    name: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    evidence: str = Field(default="", max_length=500)
    fields: list[CandidateField] = Field(default_factory=list, max_length=100)


class DraftInput(StrictInput):
    name: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    namespace: str = Field(min_length=1, max_length=1000)
    classes: list[CandidateClass] = Field(min_length=1, max_length=30)


def generate_draft(payload: DraftInput):
    if not NAME.fullmatch(payload.name):
        raise InvalidModel("模型技术标识只能包含 ASCII 字母、数字和下划线，且不能以数字开头。")
    if not re.fullmatch(r"https?://[^\s<>\"{}|\\^`]+[/#]", payload.namespace):
        raise InvalidModel("命名空间须为 http(s) IRI，并以 / 或 # 结尾；不会联网访问。")
    names = [c.name for c in payload.classes]
    if len(names) != len(set(names)) or any(not NAME.fullmatch(n) or n in TYPES for n in names):
        raise InvalidModel("类技术标识无效、重复或与内置类型冲突。")
    if sum(len(c.fields) for c in payload.classes) > 120:
        raise InvalidModel("导入草稿最多包含 120 个属性，请拆分文档。")
    classes = {}
    for cls in payload.classes:
        fields = {}
        for field in cls.fields:
            if not NAME.fullmatch(field.name) or field.name in fields:
                raise InvalidModel(f"类 {cls.name} 的属性技术标识无效或重复。")
            if field.range not in TYPES | set(names):
                raise InvalidModel(f"属性 {field.name} 引用未知类型，请检查被删除或改名的类。")
            fields[field.name] = {"title": field.title, "range": field.range,
                                  "slot_uri": f"model:{cls.name}/{field.name}",
                                  "required": field.required, "multivalued": field.multivalued}
            description = "\n".join(s for s in (field.description, f"来源：{field.evidence}" if field.evidence else "") if s)
            if description:
                fields[field.name]["description"] = description
        classes[cls.name] = {"title": cls.title, "class_uri": f"model:{cls.name}", "attributes": fields}
        if cls.evidence:
            classes[cls.name]["description"] = f"来源：{cls.evidence}；经用户确认的文档建模草稿。"
    data = {"id": payload.namespace + payload.name, "name": payload.name, "title": payload.title,
            "prefixes": {"model": payload.namespace, "linkml": "https://w3id.org/linkml/"},
            "default_prefix": "model", "default_range": "string", "imports": ["linkml:types"], "classes": classes}
    source = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    report = parse_model(source)[1]
    return {"source": source, "report": report, "saved": False}


def _xml(raw):
    if len(raw) > 4 * 1024 * 1024:
        raise InvalidModel("Office XML 超过 4 MiB，请拆分文档。")
    try:
        text = raw.decode("utf-8-sig")
        if "\x00" in text or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            raise InvalidModel("不允许 XML DTD、实体或非 UTF-8 XML。")
        root = ET.fromstring(text)
        stack = [(root, 0)]
        count = 0
        while stack:
            node, depth = stack.pop()
            count += 1
            if depth > 40 or count > 100000:
                raise InvalidModel("XML 嵌套或节点数超过安全上限。")
            stack.extend((child, depth + 1) for child in node)
        return root
    except (UnicodeError, ET.ParseError) as exc:
        raise InvalidModel("Office XML 无效；请另存为标准 UTF-8 OOXML 文档。") from exc


def _package(raw):
    try:
        package = ZipFile(BytesIO(raw))
        entries = package.infolist()
        names = [e.filename for e in entries]
        if len(entries) > 256 or len(names) != len(set(names)) or sum(e.file_size for e in entries) > 12 * 1024 * 1024:
            raise InvalidModel("Office 包文件数、重复文件名或解压大小超出限制（256 项 / 12 MiB）。")
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in entry.filename or entry.flag_bits & 1:
                raise InvalidModel("Office 包包含不安全路径或加密内容。")
            if entry.file_size > max(1024 * 1024, entry.compress_size * 200):
                raise InvalidModel("Office 压缩比超过安全上限。")
            if "vbaproject" in entry.filename.lower() or "externallinks/" in entry.filename.lower():
                raise InvalidModel("不支持宏或外部工作簿链接，请先移除。")
        content_types = package.read("[Content_Types].xml")
        _xml(content_types)
        if b"macroenabled" in content_types.lower():
            raise InvalidModel("不支持启用宏的 Office 文档。")
        return package
    except (BadZipFile, KeyError, RuntimeError, NotImplementedError) as exc:
        raise InvalidModel("文件不是有效的、未加密的 XLSX / DOCX 文档。") from exc


def _technical(label, fallback, used):
    value = label.strip() if NAME.fullmatch(label.strip()) and label.strip() not in TYPES else fallback
    base = value[:70]
    suffix = 2
    while value in used:
        value = f"{base}_{suffix}"
        suffix += 1
    return value


class Candidates:
    def __init__(self, filename):
        self.filename = filename
        self.classes = []
        self.warnings = ["本地规则提取，不调用外部 AI；候选不等于已确认的业务语义。",
                         "不推断唯一性、必填、基数或枚举；不导入业务记录，不发布数据映射。"]

    def add(self, title, evidence):
        if len(self.classes) >= 30:
            raise InvalidModel("候选类超过 30 个，请拆分文档。")
        cls = {"name": _technical(title, f"Entity{len(self.classes) + 1}", {c["name"] for c in self.classes}),
               "title": title[:200], "evidence": f"{self.filename} · {evidence}"[:500], "fields": []}
        self.classes.append(cls)
        return cls

    def field(self, cls, title, evidence, range="string", description=""):
        if len(cls["fields"]) >= 100 or sum(len(c["fields"]) for c in self.classes) >= 120:
            raise InvalidModel("候选属性超过上限（每类 100 / 总计 120），请拆分文档。")
        cls["fields"].append({"name": _technical(title, f"field{len(cls['fields']) + 1}", {f["name"] for f in cls["fields"]}),
                              "title": title[:200], "range": range, "required": False, "multivalued": False,
                              "evidence": f"{self.filename} · {evidence}"[:500], "description": description[:1000]})

    def table(self, title, rows, location):
        rows = [(number, cells) for number, cells in rows if any(c.strip() for c in cells)]
        if not rows:
            return
        number, header = rows[0]
        normalized = [c.strip().lower() for c in header]
        def column(aliases):
            return next((i for i, cell in enumerate(normalized) if cell in aliases), None)
        entity = column({"实体", "类", "实体名称", "class", "entity"})
        field = column({"字段", "属性", "字段名称", "字段名", "field", "attribute"})
        datatype = column({"类型", "数据类型", "type", "range"})
        description = column({"说明", "描述", "description"})
        if entity is not None and field is not None:
            if len(rows) > 201:
                raise InvalidModel("数据字典超过 200 行，请拆分。")
            groups = {}
            for row_number, cells in rows[1:]:
                def get(i): return cells[i].strip() if i is not None and i < len(cells) else ""
                owner, label = get(entity), get(field)
                if not owner or not label:
                    raise InvalidModel(f"{location} 第 {row_number} 行缺少实体或字段；不支持合并单元格字典。")
                if owner not in groups:
                    groups[owner] = self.add(owner, f"{location} 第 {row_number} 行")
                raw_type = get(datatype).lower()
                aliases = {"字符串": "string", "整数": "integer", "日期": "date", "布尔": "boolean", "小数": "decimal"}
                dtype = aliases.get(raw_type, raw_type)
                if dtype and dtype not in TYPES:
                    self.warnings.append(f"字段 {label[:80]} 的类型 {raw_type[:80]} 未识别，暂用 string；对象关系请人工设置。")
                self.field(groups[owner], label, f"{location} 第 {row_number} 行", dtype if dtype in TYPES else "string", get(description))
        else:
            if any(not h.strip() for h in header) or len(set(normalized)) != len(header):
                raise InvalidModel(f"{location} 表头为空或重复，请整理为单行、非合并表头。")
            cls = self.add(title, f"{location} 第 {number} 行表头")
            for index, label in enumerate(header):
                self.field(cls, label.strip(), f"{location} 第 {number} 行第 {index + 1} 列")
            self.warnings.append(f"{location} 仅使用首个非空行作为表头；数据行已忽略，属性暂用 string。")


def _xlsx(package, result):
    workbook = _xml(package.read("xl/workbook.xml"))
    rels = _xml(package.read("xl/_rels/workbook.xml.rels"))
    targets = {r.get("Id"): r.get("Target", "") for r in rels if r.get("TargetMode") != "External"}
    shared = []
    if "xl/sharedStrings.xml" in package.namelist():
        shared = ["".join(item.itertext()) for item in _xml(package.read("xl/sharedStrings.xml")).findall(f"{SS}si")]
    sheets = workbook.findall(f"{SS}sheets/{SS}sheet")
    if len(sheets) > 30:
        raise InvalidModel("工作表超过 30 个，请拆分。")
    for sheet in sheets:
        if sheet.get("state", "visible") != "visible":
            result.warnings.append(f"已跳过隐藏工作表：{sheet.get('name', '')[:100]}")
            continue
        target = targets.get(sheet.get(f"{REL}id"), "")
        path = posixpath.normpath(target.lstrip("/") if target.startswith("/") else "xl/" + target)
        if not path.startswith("xl/worksheets/") or not path.endswith(".xml"):
            raise InvalidModel("工作表引用无效或不支持该工作表类型。")
        root = _xml(package.read(path))
        rows = []
        for number, row in enumerate(root.findall(f"{SS}sheetData/{SS}row"), 1):
            cells = {}
            for cell in row.findall(f"{SS}c"):
                address = cell.get("r", "")
                match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]*)", address)
                if not match:
                    raise InvalidModel("工作表单元格坐标无效。")
                index = 0
                for letter in match[1]: index = index * 26 + ord(letter) - 64
                if index > 120:
                    raise InvalidModel("工作表列数超过 120，请先裁剪。")
                value = cell.findtext(f"{SS}v", "")
                if cell.find(f"{SS}f") is not None:
                    value = ""  # Never evaluate formulas, including cached results.
                elif cell.get("t") == "s":
                    if not value.isdigit() or int(value) >= len(shared):
                        raise InvalidModel("共享字符串引用无效。")
                    value = shared[int(value)]
                elif cell.get("t") == "inlineStr":
                    value = "".join(t.text or "" for t in cell.iter(f"{SS}t"))
                cells[index] = value.strip()
            if cells:
                rows.append((row.get("r", str(number)), [cells.get(i, "") for i in range(1, max(cells) + 1)]))
        if root.find(f"{SS}mergeCells") is not None:
            result.warnings.append(f"工作表 {sheet.get('name', '')[:100]} 含合并单元格，请核对候选；不补全合并值。")
        result.table(sheet.get("name", "工作表"), rows, f"工作表 {sheet.get('name', '')[:100]}")
    result.warnings.append("公式及其缓存值不参与提取；隐藏工作表已跳过；不读取外部链接。")


def _docx(package, result):
    root = _xml(package.read("word/document.xml"))
    body = root.find(f"{W}body")
    if body is None:
        raise InvalidModel("Word 文档缺少正文。")
    headings = []
    for index, node in enumerate(body, 1):
        if node.tag == f"{W}tbl":
            rows = [(i, ["".join(t.text or "" for t in cell.iter(f"{W}t")) for cell in row.findall(f"{W}tc")])
                    for i, row in enumerate(node.findall(f"{W}tr"), 1)]
            result.table(f"表格{index}", rows, f"正文块 {index} 表格")
        elif node.tag == f"{W}p":
            text = "".join(t.text or "" for t in node.iter(f"{W}t")).strip()
            style = node.find(f"{W}pPr/{W}pStyle")
            if text and style is not None and re.fullmatch(r"(?:Heading|标题)[1-6]", style.get(f"{W}val", ""), re.I):
                headings.append((text, f"正文块 {index} 标题"))
    if not result.classes:
        for title, location in headings: result.add(title, location)
    result.warnings.append("Word 只提取正文表格；无表格候选时使用 Heading1–6/标题1–6。正文、图片、页眉、文本框及附件不做语义推断。")


def _text(raw, result, markdown):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise InvalidModel("文本/YAML 必须为 UTF-8 编码。") from exc
    if "\x00" in text:
        raise InvalidModel("文本含二进制空字符。")
    if not text.strip():
        raise InvalidModel("文档为空。")
    headings, table = [], []
    table_valid = False
    fenced = False
    def flush():
        nonlocal table_valid
        if table and table_valid:
            result.table(f"表格{len(result.classes) + 1}", table, f"Markdown 第 {table[0][0]} 行起")
        table.clear()
        table_valid = False
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if markdown and re.match(r"^(`{3,}|~{3,})", stripped):
            fenced = not fenced
            flush()
            continue
        if fenced:
            continue
        if markdown and "|" in stripped:
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                if len(table) == 1 and len(cells) == len(table[0][1]): table_valid = True
            else:
                table.append((number, cells))
        else:
            flush()
            match = re.match(r"^#{1,6}\s+(.+)$", stripped) if markdown else None
            if match: headings.append((match[1], f"第 {number} 行标题"))
    flush()
    if not result.classes:
        for title, location in headings: result.add(title, location)
    result.warnings.append("Markdown 只识别简单管道表格/ATX 标题，忽略代码块；自然语言正文不自动推断关系或规则。")


def inspect_document(payload: DocumentInput):
    filename = payload.filename
    if "/" in filename or "\\" in filename or any(ord(c) < 32 for c in filename):
        raise InvalidModel("文件名不能包含路径或控制字符。")
    extension = PurePosixPath(filename).suffix.lower()
    if extension not in {".xlsx", ".docx", ".md", ".txt", ".yaml", ".yml"}:
        raise InvalidModel("仅支持 .xlsx、.docx、.md、.txt、.yaml/.yml；旧版 .xls/.doc 请先转换。")
    try:
        raw = base64.b64decode(payload.content_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise InvalidModel("文件编码无效。") from exc
    if not raw or len(raw) > MAX_FILE:
        raise InvalidModel("文件为空或超过 2 MiB。")
    if extension in {".yaml", ".yml"}:
        try:
            source = raw.decode("utf-8-sig")
        except UnicodeError as exc:
            raise InvalidModel("YAML 必须为 UTF-8 编码。") from exc
        report = parse_model(source)[1]
        return {"kind": "yaml", "source": source, "report": report, "saved": False}
    result = Candidates(filename)
    try:
        if extension in {".xlsx", ".docx"}:
            with _package(raw) as package:
                (_xlsx if extension == ".xlsx" else _docx)(package, result)
        else:
            _text(raw, result, extension == ".md")
    except (BadZipFile, KeyError, RuntimeError, NotImplementedError, ValueError, OverflowError, ZlibError) as exc:
        if isinstance(exc, InvalidModel): raise
        raise InvalidModel("Office 文档损坏或结构不受支持，请另存为标准 XLSX / DOCX。") from exc
    if not result.classes:
        result.warnings.append("未发现可识别的表格或标题。请手动添加类和属性，或整理为数据字典；不会根据文件名猜测本体。")
    return {"kind": "document", "filename": filename, "classes": result.classes,
            "warnings": list(dict.fromkeys(result.warnings)), "saved": False}
