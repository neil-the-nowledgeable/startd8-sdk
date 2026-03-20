"""Tests for Node.js/TypeScript regex-based element extractor (REQ-PLI-NODE-106)."""

from startd8.languages.nodejs_parser import NodeElement, parse_nodejs_source


class TestFunctionDeclaration:
    def test_simple_function(self):
        result = parse_nodejs_source("function greet(name) {\n  return name;\n}")
        assert len(result) == 1
        assert result[0].kind == "function"
        assert result[0].name == "greet"
        assert result[0].is_async is False
        assert result[0].is_exported is False

    def test_async_function(self):
        result = parse_nodejs_source("async function fetchData(url) {\n  return await fetch(url);\n}")
        assert len(result) == 1
        assert result[0].kind == "function"
        assert result[0].name == "fetchData"
        assert result[0].is_async is True

    def test_exported_function(self):
        result = parse_nodejs_source("export function processItems(items) {\n}")
        assert len(result) == 1
        assert result[0].is_exported is True
        assert result[0].name == "processItems"

    def test_exported_async_function(self):
        result = parse_nodejs_source("export async function loadConfig() {\n}")
        assert len(result) == 1
        assert result[0].is_exported is True
        assert result[0].is_async is True
        assert result[0].name == "loadConfig"


class TestClassExtraction:
    def test_simple_class(self):
        result = parse_nodejs_source("class MyService {\n}")
        assert len(result) == 1
        assert result[0].kind == "class"
        assert result[0].name == "MyService"
        assert result[0].extends is None

    def test_class_with_extends(self):
        result = parse_nodejs_source("class HttpService extends BaseService {\n}")
        assert len(result) == 1
        assert result[0].kind == "class"
        assert result[0].name == "HttpService"
        assert result[0].extends == "BaseService"

    def test_exported_class(self):
        result = parse_nodejs_source("export class Router {\n}")
        assert len(result) == 1
        assert result[0].is_exported is True

    def test_export_default_class(self):
        result = parse_nodejs_source("export default class App {\n}")
        assert len(result) == 1
        assert result[0].name == "App"


class TestArrowFunction:
    def test_arrow_function(self):
        result = parse_nodejs_source("const add = (a, b) => a + b;")
        assert len(result) == 1
        assert result[0].kind == "const_function"
        assert result[0].name == "add"

    def test_async_arrow_function(self):
        result = parse_nodejs_source("const fetchUser = async (id) => {\n  return await db.get(id);\n};")
        assert len(result) == 1
        assert result[0].is_async is True
        assert result[0].name == "fetchUser"

    def test_exported_arrow_function(self):
        result = parse_nodejs_source("export const handler = (req, res) => {\n};")
        assert len(result) == 1
        assert result[0].is_exported is True


class TestFunctionExpression:
    def test_function_expression(self):
        result = parse_nodejs_source("const multiply = function(a, b) {\n  return a * b;\n};")
        assert len(result) == 1
        assert result[0].kind == "const_function"
        assert result[0].name == "multiply"

    def test_async_function_expression(self):
        result = parse_nodejs_source("const run = async function() {\n};")
        assert len(result) == 1
        assert result[0].is_async is True


class TestTypeScriptInterface:
    def test_interface(self):
        result = parse_nodejs_source("interface UserProps {\n  name: string;\n}")
        assert len(result) == 1
        assert result[0].kind == "interface"
        assert result[0].name == "UserProps"

    def test_exported_interface(self):
        result = parse_nodejs_source("export interface Config {\n  port: number;\n}")
        assert len(result) == 1
        assert result[0].is_exported is True


class TestTypeScriptTypeAlias:
    def test_type_alias(self):
        result = parse_nodejs_source("type ID = string | number;")
        assert len(result) == 1
        assert result[0].kind == "type_alias"
        assert result[0].name == "ID"

    def test_exported_type_alias(self):
        result = parse_nodejs_source("export type Handler = (req: Request) => Response;")
        assert len(result) == 1
        assert result[0].is_exported is True


class TestClassMethodDetection:
    def test_methods_inside_class(self):
        source = """\
class MyService {
  getData() {
    return this.data;
  }

  async fetchRemote() {
    return await fetch(this.url);
  }
}
"""
        result = parse_nodejs_source(source)
        classes = [e for e in result if e.kind == "class"]
        methods = [e for e in result if e.kind == "method"]
        assert len(classes) == 1
        assert len(methods) == 2
        assert methods[0].name == "getData"
        assert methods[0].parent_class == "MyService"
        assert methods[1].name == "fetchRemote"
        assert methods[1].is_async is True
        assert methods[1].parent_class == "MyService"

    def test_reserved_words_not_methods(self):
        source = """\
class MyClass {
  if (condition) {
    return true;
  }
}
"""
        result = parse_nodejs_source(source)
        methods = [e for e in result if e.kind == "method"]
        assert len(methods) == 0


class TestEdgeCases:
    def test_empty_source(self):
        result = parse_nodejs_source("")
        assert result == []

    def test_syntax_error_tolerance(self):
        source = """\
function validFunc() {
  // fine
}

const broken = {;

class StillParsed {
}
"""
        result = parse_nodejs_source(source)
        names = [e.name for e in result]
        assert "validFunc" in names
        assert "StillParsed" in names

    def test_line_numbers(self):
        source = """\
function first() {}

function second() {}
"""
        result = parse_nodejs_source(source)
        assert result[0].line == 1
        assert result[1].line == 3

    def test_multiple_element_types(self):
        source = """\
export function createApp() {}
export class AppRouter extends Router {}
export const middleware = (req, res) => {};
export interface AppConfig {}
export type AppMode = 'dev' | 'prod';
"""
        result = parse_nodejs_source(source)
        kinds = {e.kind for e in result}
        assert "function" in kinds
        assert "class" in kinds
        assert "const_function" in kinds
        assert "interface" in kinds
        assert "type_alias" in kinds
        assert all(e.is_exported for e in result)
