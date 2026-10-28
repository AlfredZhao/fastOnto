"""Bounded LinkML authoring profile; no remote imports, generated code, or writes."""
import hashlib
import re

import yaml
from linkml_runtime.linkml_model.meta import SchemaDefinition
from linkml_runtime.utils.schemaview import SchemaView

NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,79}$")
TOP = {"id", "name", "title", "description", "prefixes", "default_prefix",
       "default_range", "imports", "classes", "slots", "enums"}
CLASS = {"title", "description", "class_uri", "is_a", "slots", "attributes", "slot_usage"}
SLOT = {"title", "description", "slot_uri", "range", "required", "multivalued", "identifier"}


class InvalidModel(ValueError):
    pass


class UniqueLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise InvalidModel("YAML 键必须是字符串。")
            if key in result:
                raise InvalidModel(f"YAML 键重复：{key}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _keys(value, allowed, path):
    if not isinstance(value, dict):
        raise InvalidModel(f"{path} 必须是对象。")
    unknown = set(value) - allowed
    if unknown:
        raise InvalidModel(f"{path} 当前不支持字段：{', '.join(sorted(unknown))}")


def _named(values, path):
    if not isinstance(values, dict) or len(values) > 100:
        raise InvalidModel(f"{path} 必须是最多 100 项的对象。")
    for name, definition in values.items():
        if not NAME.fullmatch(name):
            raise InvalidModel(f"{path} 标识须为 ASCII 字母、数字或下划线：{name}")
        if not isinstance(definition, dict):
            raise InvalidModel(f"{path}.{name} 必须是对象。")


def parse_model(source: str):
    if len(source.encode("utf-8")) > 65536:
        raise InvalidModel("模型不能超过 64 KiB。")
    try:
        depth = 0
        count = 0
        for event in yaml.parse(source):
            count += 1
            if isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None):
                raise InvalidModel("首版不支持 YAML 锚点或别名。")
            if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
                depth += 1
            elif isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
                depth -= 1
            if depth > 20 or count > 6000:
                raise InvalidModel("模型嵌套或节点数量超出上限。")
        data = yaml.load(source, Loader=UniqueLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"（第 {mark.line + 1} 行）" if mark else ""
        raise InvalidModel(f"YAML 语法错误{where}。") from exc
    _keys(data, TOP, "schema")
    for field in ("id", "name", "default_prefix"):
        if not isinstance(data.get(field), str) or not data[field]:
            raise InvalidModel(f"缺少字符串字段 {field}。")
    if not NAME.fullmatch(data["name"]):
        raise InvalidModel("模型 name 必须是稳定的 ASCII 技术标识。")
    if "title" in data and (not isinstance(data["title"], str) or len(data["title"]) > 500):
        raise InvalidModel("模型 title 必须是最多 500 字符的字符串。")
    if data.get("imports", []) not in ([], ["linkml:types"]):
        raise InvalidModel("只允许内置 linkml:types；禁止远程与本地文件导入。")
    prefixes = data.get("prefixes", {})
    if not isinstance(prefixes, dict) or any(not isinstance(v, str) for v in prefixes.values()):
        raise InvalidModel("prefixes 必须是字符串映射。")
    if prefixes.get("linkml", "https://w3id.org/linkml/") != "https://w3id.org/linkml/":
        raise InvalidModel("不允许重定向内置 linkml 命名空间。")
    if data["default_prefix"] not in prefixes:
        raise InvalidModel("default_prefix 必须在 prefixes 中定义。")
    classes = data.get("classes", {})
    slots = data.get("slots", {})
    enums = data.get("enums", {})
    for values, path in ((classes, "classes"), (slots, "slots"), (enums, "enums")):
        _named(values, path)
    if not classes:
        raise InvalidModel("至少需要定义一个类。")
    all_slots = list(slots.items())
    for name, value in classes.items():
        _keys(value, CLASS, f"classes.{name}")
        parent = value.get("is_a")
        if parent is not None and (not isinstance(parent, str) or parent not in classes):
            raise InvalidModel(f"类 {name} 的父类不存在。")
        selected = value.get("slots", [])
        if not isinstance(selected, list) or any(not isinstance(s, str) or s not in slots for s in selected):
            raise InvalidModel(f"类 {name} 引用了未定义的全局属性。")
        for field in ("attributes", "slot_usage"):
            local = value.get(field, {})
            _named(local, f"classes.{name}.{field}")
            all_slots.extend(local.items())
    for name in classes:
        seen = set()
        applicable_slots = set()
        current = name
        while current:
            if current in seen:
                raise InvalidModel(f"类 {name} 存在继承环。")
            seen.add(current)
            applicable_slots.update(classes[current].get("slots", []))
            applicable_slots.update(classes[current].get("attributes", {}))
            current = classes[current].get("is_a")
        unknown_usage = set(classes[name].get("slot_usage", {})) - applicable_slots
        if unknown_usage:
            raise InvalidModel(f"类 {name} 的 slot_usage 引用了不适用的属性：{', '.join(sorted(unknown_usage))}")
    if len(all_slots) > 500:
        raise InvalidModel("属性定义总数不能超过 500。")
    for name, value in all_slots:
        _keys(value, SLOT, f"slot.{name}")
        for flag in ("required", "multivalued", "identifier"):
            if flag in value and not isinstance(value[flag], bool):
                raise InvalidModel(f"{name}.{flag} 必须是布尔值。")
    for name, value in enums.items():
        _keys(value, {"title", "description", "permissible_values"}, f"enum.{name}")
        permissible = value.get("permissible_values", {})
        if not isinstance(permissible, dict) or len(permissible) > 100:
            raise InvalidModel(f"枚举 {name} 取值必须是最多 100 项的对象。")
        for entry in permissible.values():
            if entry is not None:
                _keys(entry, {"description", "meaning"}, f"enum.{name}.value")
    try:
        schema = SchemaDefinition(**data)
        view = SchemaView(schema)
        ranges = set(classes) | set(enums) | set(view.all_types())
        default_range = data.get("default_range", "string")
        if default_range not in ranges:
            raise InvalidModel(f"默认类型不存在：{default_range}")
        for name, value in all_slots:
            if value.get("range", default_range) not in ranges:
                raise InvalidModel(f"属性 {name} 引用未知类型：{value.get('range')}")
        result = []
        relationships = []
        for name, cls in view.all_classes().items():
            induced = view.class_induced_slots(name)
            fields = []
            for slot in induced:
                fields.append({"name": str(slot.name), "title": slot.title or str(slot.name),
                               "range": str(slot.range or default_range), "required": bool(slot.required),
                               "multivalued": bool(slot.multivalued), "identifier": bool(slot.identifier)})
                if slot.range in classes:
                    relationships.append({"source": str(name), "target": str(slot.range),
                                          "label": slot.title or str(slot.name), "kind": "reference"})
            if cls.is_a:
                relationships.append({"source": str(name), "target": str(cls.is_a),
                                      "label": "继承", "kind": "inheritance"})
            result.append({"name": str(name), "title": cls.title or str(name),
                           "description": cls.description or "", "uri": view.get_uri(cls, expand=True),
                           "slots": fields})
    except InvalidModel:
        raise
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise InvalidModel(f"LinkML 模型解析失败：{str(exc)[:250]}") from exc
    return schema, {"valid": True, "name": str(schema.name), "title": schema.title or str(schema.name),
                    "sha256": hashlib.sha256(source.encode()).hexdigest(), "classes": result,
                    "relationships": relationships, "enum_count": len(enums),
                    "warnings": ["当前校验覆盖受支持的模型结构与引用，不代表业务实例已通过约束校验。"]}
