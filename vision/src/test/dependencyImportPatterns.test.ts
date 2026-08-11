import * as assert from 'assert';
import * as path from 'path';
import { buildImportResolutionCandidates, extractImportPaths, shouldPreferSymbolBasedStrategy } from '../services/dependencyImportPatterns';

suite('Dependency import pattern parsing', () => {
    test('extracts TypeScript-style imports', () => {
        const text = [
            "import foo from './foo';",
            "const bar = require('./bar');",
            "export { baz } from './baz';"
        ].join('\n');

        assert.deepStrictEqual(extractImportPaths(text, 'typescript'), ['./foo', './bar', './baz']);
    });

    test('extracts Python relative imports', () => {
        const text = [
            "from .module import A",
            "from ..helpers import B"
        ].join('\n');

        assert.deepStrictEqual(extractImportPaths(text, 'python'), ['.module.A', '..helpers.B']);
    });

    test('extracts C/C++ relative includes', () => {
        const text = [
            '#include "src/foo.h"',
            '#include <vector>'
        ].join('\n');

        assert.deepStrictEqual(extractImportPaths(text, 'cpp'), ['src/foo.h']);
    });

    test('extracts Java imports', () => {
        const text = [
            'import com.example.foo.Bar;',
            'import static com.example.foo.Baz.*;'
        ].join('\n');

        assert.deepStrictEqual(extractImportPaths(text, 'java'), ['com.example.foo.Bar', 'com.example.foo.Baz.*']);
    });

    test('extracts Rust imports', () => {
        const text = [
            'use crate::foo::Bar;',
            'use super::baz;'
        ].join('\n');

        assert.deepStrictEqual(extractImportPaths(text, 'rust'), ['crate::foo::Bar', 'super::baz']);
    });

    test('extracts Go imports', () => {
        const text = [
            'import "fmt"',
            'import (',
            '  "example.com/pkg/bar"',
            ')'
        ].join('\n');

        assert.deepStrictEqual(extractImportPaths(text, 'go'), ['fmt', 'example.com/pkg/bar']);
    });

    test('prefers symbol-based strategy for JavaScript, Python, and Java', () => {
        assert.strictEqual(shouldPreferSymbolBasedStrategy('typescript'), true);
        assert.strictEqual(shouldPreferSymbolBasedStrategy('javascript'), true);
        assert.strictEqual(shouldPreferSymbolBasedStrategy('python'), true);
        assert.strictEqual(shouldPreferSymbolBasedStrategy('java'), true);
        assert.strictEqual(shouldPreferSymbolBasedStrategy('cpp'), false);
    });

    test('extracts Python package-module imports', () => {
        const text = [
            'from fastapi_cli.config import FastAPIConfig',
            'from fastapi_cli import config'
        ].join('\n');

        assert.deepStrictEqual(extractImportPaths(text, 'python'), ['fastapi_cli.config.FastAPIConfig', 'fastapi_cli.config']);
    });

    test('extracts Python direct, aliased, and multi-import statements', () => {
        const text = [
            'import app.models, app.services as services',
            'from . import sibling',
            'from package import feature as renamed'
        ].join('\n');

        assert.deepStrictEqual(extractImportPaths(text, 'python'), [
            'app.models', 'app.services', '.sibling', 'package.feature'
        ]);
    });

    test('builds Python import candidates for relative and package imports', () => {
        const candidates = buildImportResolutionCandidates('/workspace/pkg', '.module', 'python', '/workspace');
        assert.ok(candidates.includes(path.resolve('/workspace/pkg', 'module.py')));

        const packageCandidates = buildImportResolutionCandidates('/workspace/pkg', 'pkg.module', 'python', '/workspace');
        assert.ok(packageCandidates.includes(path.resolve('/workspace/pkg', 'module.py')));

        const nestedCandidates = buildImportResolutionCandidates('/workspace', 'pkg.subpkg.module', 'python', '/workspace');
        assert.ok(nestedCandidates.includes(path.resolve('/workspace/pkg/subpkg', '__init__.py')));
        assert.ok(nestedCandidates.includes(path.resolve('/workspace/pkg/subpkg', 'module.py')));

        const fromImportCandidates = buildImportResolutionCandidates('/workspace/pkg', '.sibling', 'python', '/workspace');
        assert.ok(fromImportCandidates.includes(path.resolve('/workspace/pkg', 'sibling.py')));
    });
});
