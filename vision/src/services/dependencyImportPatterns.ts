import * as path from "path";

export function extractImportPaths(source: string, languageId: string): string[] {
    const normalizedLanguage = normalizeLanguageId(languageId);

    if (normalizedLanguage === 'python') {
        return extractPythonImportPaths(source);
    }

    const patterns = getImportPatterns(normalizedLanguage);
    const results: string[] = [];

    for (const pattern of patterns) {
        const regex = new RegExp(pattern, 'g');
        let match: RegExpExecArray | null;

        while ((match = regex.exec(source)) !== null) {
            const importPath = match[1] || match[2] || match[3] || match[4];
            if (!importPath) {
                continue;
            }

            if (normalizedLanguage === 'go' && pattern.includes('import\\s*\\(')) {
                const nestedPaths = extractQuotedPaths(importPath);
                for (const nestedPath of nestedPaths) {
                    if (nestedPath) {
                        results.push(nestedPath);
                    }
                }
                continue;
            }

            results.push(importPath);
        }
    }
    
    return Array.from(new Set(results));
}

function extractQuotedPaths(text: string): string[] {
    const matches = text.matchAll(/"([^"]+)"/g);
    return Array.from(matches, (m) => m[1]);
}

function extractPythonImportPaths(source: string): string[] {
    const results = new Set<string>();
    const logicalLines = source.replace(/\\\r?\n/g, ' ');

    // `from package import module` is ambiguous: module may be a symbol or a
    // submodule. Keep the complete path and let resolution fall back from the
    // most specific path (package/module.py) to the containing package.
    const statements = /^\s*(?:from\s+([.\w]+)\s+import\s+(.+?)|import\s+(.+?))\s*(?:#.*)?$/gm;
    let match: RegExpExecArray | null;
    while ((match = statements.exec(logicalLines)) !== null) {
        const base = match[1];
        const importedNames = match[2];
        const directNames = match[3];

        for (const nameWithAlias of (importedNames || directNames).replace(/[()]/g, '').split(',')) {
            const name = nameWithAlias.trim().split(/\s+as\s+/i)[0].trim();
            if (base && name === '*') {
                results.add(base);
            } else if (/^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$/.test(name)) {
                results.add(base ? joinPythonImportPath(base, name) : name);
            }
        }
    }

    return Array.from(results);
}

function joinPythonImportPath(base: string, name: string): string {
    return base === '.' ? `.${name}` : `${base}.${name}`;
}

export function shouldPreferSymbolBasedStrategy(languageId: string, fileName?: string): boolean {
    const normalized = normalizeLanguageId(languageId, fileName);
    return ['typescript', 'javascript', 'python', 'java'].includes(normalized);
}

export function resolveLanguageId(languageId: string, fileName?: string): string {
    return normalizeLanguageId(languageId, fileName);
}

export function buildImportResolutionCandidates(
    currentDir: string,
    importPath: string,
    languageId: string,
    workspaceRoot?: string,
    fileName?: string
): string[] {
    const normalizedLanguage = normalizeLanguageId(languageId, fileName);

    if (normalizedLanguage === 'python') {
        return buildPythonImportResolutionCandidates(currentDir, importPath, workspaceRoot);
    }

    const base = path.resolve(currentDir, importPath);
    return [
        base,
        `${base}.ts`,
        `${base}.tsx`,
        `${base}.js`,
        `${base}.jsx`,
        path.join(base, 'index.ts'),
        path.join(base, 'index.tsx'),
        path.join(base, 'index.js'),
        path.join(base, 'index.jsx')
    ];
}

function buildPythonImportResolutionCandidates(
    currentDir: string,
    importPath: string,
    workspaceRoot?: string
): string[] {
    const candidates = new Set<string>();
    const relativeDepth = (importPath.match(/^\.+/)?.[0] || '').length;
    const trimmedImportPath = importPath.replace(/^\.+/, '');
    const segments = trimmedImportPath.split('.').filter(Boolean);

    const baseDirs: string[] = [];
    baseDirs.push(currentDir);

    if (workspaceRoot) {
        baseDirs.push(workspaceRoot);
    }

    for (const baseDir of baseDirs) {
        let resolvedBaseDir = baseDir;
        for (let i = 1; i < relativeDepth; i++) {
            resolvedBaseDir = path.dirname(resolvedBaseDir);
        }

        if (segments.length === 0) {
            candidates.add(resolvedBaseDir);
            candidates.add(path.join(resolvedBaseDir, '__init__.py'));
            continue;
        }

        // Check the full module name first, then progressively fall back to
        // parent modules. This handles both `from pkg import module` and
        // `from pkg.module import Symbol` without treating Symbol as a file.
        for (let depth = segments.length; depth >= 1; depth--) {
            const nestedSegments = segments.slice(0, depth);
            const nestedModulePath = path.resolve(resolvedBaseDir, ...nestedSegments);
            candidates.add(nestedModulePath);
            candidates.add(path.join(nestedModulePath, '__init__.py'));
            candidates.add(`${nestedModulePath}.py`);
        }
    }

    return Array.from(candidates);
}

function normalizeLanguageId(languageId: string, fileName?: string): string {
    const normalized = (languageId || '').toLowerCase();
    const resolvedFileName = (fileName || '').toLowerCase();

    if (resolvedFileName.endsWith('.py')) {
        return 'python';
    }

    if (normalized.startsWith('typescript')) {
        return 'typescript';
    }

    if (normalized.startsWith('javascript')) {
        return 'javascript';
    }

    if (normalized.startsWith('python')) {
        return 'python';
    }

    if (normalized === 'cpp' || normalized === 'c' || normalized === 'objective-c' || normalized === 'objective-cpp') {
        return 'cpp';
    }

    if (normalized.startsWith('java')) {
        return 'java';
    }

    if (normalized.startsWith('rust') || normalized === 'rs') {
        return 'rust';
    }

    if (normalized.startsWith('go') || normalized === 'golang') {
        return 'go';
    }

    return normalized;
}

function getImportPatterns(languageId: string): string[] {
    switch (languageId) {
        case 'typescript':
        case 'javascript':
            return [
                "import\\s+(?:type\\s+)?(?:[\\w*\\s{},]+)\\s+from\\s+['\"]([^'\"]+)['\"]",
                "import\\s*\\(\\s*['\"]([^'\"]+)['\"]\\s*\\)",
                "require\\s*\\(\\s*['\"]([^'\"]+)['\"]\\s*\\)",
                "export\\s+(?:[^'\"]*?)from\\s+['\"]([^'\"]+)['\"]"
            ];
        case 'cpp':
            return [
                "^\\s*#include\\s+\\\"([^\\\"]+)\\\"", "^\\s*#include\\s+<([^>]+)>"
            ];
        case 'java':
            return [
                "^\\s*import\\s+(?:static\\s+)?([A-Za-z0-9_.\\*]+)\\s*;"
            ];
        case 'rust':
            return [
                "^\\s*(?:pub\\s+)?use\\s+([A-Za-z0-9_:./]+)",
                "^\\s*mod\\s+([A-Za-z0-9_./-]+)\\s*;"
            ];
        case 'go':
            return [
                '^\\s*import\\s+"([^"]+)"',
                '^\\s*import\\s+\\((?:[\\s\\S]*?)\\)'
            ];
        default:
            return [];
    }
}
