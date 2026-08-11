import * as vscode from "vscode";
import * as path from "path";

import { DependencyFile } from "../types/dependency";
import { FileDependencyProvider } from "../providers/dependencyProvider";
import { buildImportResolutionCandidates, extractImportPaths, resolveLanguageId, shouldPreferSymbolBasedStrategy } from "./dependencyImportPatterns";

interface DependencyCacheEntry {
    version: number;
    files: DependencyFile[];
}

export class DependencyService {

    private readonly dependencyCache = new Map<string, DependencyCacheEntry>();

    constructor(
        private readonly provider: FileDependencyProvider
    ) {}

    /**
     * Explorer 갱신
     */
    public async refresh(): Promise<void> {
        const editor = vscode.window.activeTextEditor;

        if (!editor) {
            this.provider.updateFiles([]);
            return;
        }

        const document = editor.document;
        const cacheKey = document.uri.toString();
        const cached = this.dependencyCache.get(cacheKey);

        if (cached && cached.version === document.version) {
            this.provider.updateFiles(cached.files);
            return;
        }

        this.provider.setLoading();

        const symbols = await this.getSymbols(document);
        const result = new Map<string, DependencyFile>();
        const languageId = resolveLanguageId(document.languageId, document.fileName);
        const shouldUseSymbolStrategy = shouldPreferSymbolBasedStrategy(languageId, document.fileName);

        if (shouldUseSymbolStrategy) {
            await Promise.all([
                this.collectDefinitions(document, symbols, result),
                this.collectReferences(document, symbols, result),
                this.collectImports(document, result)
            ]);
        } else {
            await Promise.all([
                this.collectImports(document, result),
                this.collectDefinitions(document, symbols, result),
                this.collectReferences(document, symbols, result)
            ]);
        }

        const dependencies = [...result.values()];
        this.dependencyCache.set(cacheKey, {
            version: document.version,
            files: dependencies
        });

        this.provider.updateFiles(dependencies);
    }

    /**
     * ======================================================
     * Import
     * ======================================================
     */
    private async collectImports(
        document: vscode.TextDocument,
        result: Map<string, DependencyFile>
    ): Promise<void> {
        const links = await vscode.commands.executeCommand<vscode.DocumentLink[]>(
            "vscode.executeLinkProvider",
            document.uri
        );

        if (links) {
            for (const link of links) {
                if (!link.target || link.target.scheme !== "file") {
                    continue;
                }

                this.mergeDependency(result, link.target.fsPath, {
                    path: link.target.fsPath,
                    label: vscode.workspace.asRelativePath(link.target),
                    imported: true,
                    referenced: false
                });
            }

        }

        await this.collectImportsByRegex(document, result);
    }

    /**
     * Regex Fallback
     */
    private async collectImportsByRegex(
        document: vscode.TextDocument,
        result: Map<string, DependencyFile>
    ) {
        const currentDir = path.dirname(document.uri.fsPath);
        const source = document.getText();
        const languageId = resolveLanguageId(document.languageId, document.fileName);
        const importPaths = extractImportPaths(source, languageId);
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

        for (const importPath of importPaths) {
            if (!this.shouldResolveImport(importPath, languageId)) {
                continue;
            }

            const resolved = await this.resolveImport(currentDir, importPath, languageId, workspaceRoot, document.fileName);
            if (!resolved) {
                continue;
            }

            this.mergeDependency(result, resolved, {
                path: resolved,
                label: vscode.workspace.asRelativePath(resolved),
                imported: true,
                referenced: false
            });
        }
    }

    private shouldResolveImport(importPath: string, languageId: string): boolean {
        const normalized = (languageId || '').toLowerCase();

        if (normalized.startsWith('python')) {
            return Boolean(importPath) && !importPath.startsWith('http://') && !importPath.startsWith('https://');
        }

        if (normalized === 'cpp' || normalized === 'c' || normalized === 'objective-c' || normalized === 'objective-cpp') {
            return importPath.startsWith('.') || importPath.startsWith('/') || importPath.includes('/') || importPath.includes('\\');
        }

        return importPath.startsWith('.');
    }

    /**
     * ======================================================
     * Definition
     * ======================================================
     */
    private async collectDefinitions(
        document: vscode.TextDocument,
        symbols: vscode.DocumentSymbol[],
        result: Map<string, DependencyFile>
    ) {
        for (const symbol of symbols) {
            const defs = await vscode.commands.executeCommand<
                vscode.Location[] | vscode.LocationLink[]
            >(
                "vscode.executeDefinitionProvider",
                document.uri,
                symbol.selectionRange.start
            );

            if (!defs) {
                continue;
            }

            for (const def of defs) {
                const uri = def instanceof vscode.Location ? def.uri : def.targetUri;
                if (uri.fsPath === document.uri.fsPath) {
                    continue;
                }

                this.mergeDependency(result, uri.fsPath, {
                    path: uri.fsPath,
                    label: vscode.workspace.asRelativePath(uri),
                    imported: true,
                    referenced: false
                });
            }
        }
    }

    /**
     * ======================================================
     * Reference
     * ======================================================
     */
    private async collectReferences(
        document: vscode.TextDocument,
        symbols: vscode.DocumentSymbol[],
        result: Map<string, DependencyFile>
    ) {
        for (const symbol of symbols) {
            const refs = await vscode.commands.executeCommand<vscode.Location[]>(
                "vscode.executeReferenceProvider",
                document.uri,
                symbol.selectionRange.start
            );

            if (!refs) {
                continue;
            }

            for (const ref of refs) {
                if (ref.uri.fsPath === document.uri.fsPath) {
                    continue;
                }

                this.mergeDependency(result, ref.uri.fsPath, {
                    path: ref.uri.fsPath,
                    label: vscode.workspace.asRelativePath(ref.uri),
                    imported: false,
                    referenced: true
                });
            }
        }
    }

    /**
     * ======================================================
     * Symbol 수집
     * ======================================================
     */
    private async getSymbols(
        document: vscode.TextDocument
    ): Promise<vscode.DocumentSymbol[]> {
        const symbols = await vscode.commands.executeCommand<vscode.DocumentSymbol[]>(
            "vscode.executeDocumentSymbolProvider",
            document.uri
        );

        if (!symbols) {
            return [];
        }

        const result: vscode.DocumentSymbol[] = [];
        const visit = (items: vscode.DocumentSymbol[]) => {
            for (const item of items) {
                switch (item.kind) {
                    case vscode.SymbolKind.Class:
                    case vscode.SymbolKind.Interface:
                    case vscode.SymbolKind.Function:
                    case vscode.SymbolKind.Method:
                    case vscode.SymbolKind.Constructor:
                        result.push(item);
                        break;
                }

                if (item.children.length > 0) {
                    visit(item.children);
                }
            }
        };

        visit(symbols);
        return result;
    }

    private mergeDependency(
        result: Map<string, DependencyFile>,
        key: string,
        incoming: DependencyFile
    ) {
        const existing = result.get(key);
        if (!existing) {
            result.set(key, incoming);
            return;
        }

        existing.imported = existing.imported || incoming.imported;
        existing.referenced = existing.referenced || incoming.referenced;
        existing.llmSource = existing.llmSource || incoming.llmSource;
        existing.gitRelated = existing.gitRelated || incoming.gitRelated;
    }

    /**
     * ======================================================
     * import path resolve
     * ======================================================
     */
    private async resolveImport(
        currentDir: string,
        importPath: string,
        languageId: string,
        workspaceRoot?: string,
        fileName?: string
    ): Promise<string | undefined> {
        const candidates = buildImportResolutionCandidates(currentDir, importPath, languageId, workspaceRoot, fileName);

        for (const candidate of candidates) {
            try {
                await vscode.workspace.fs.stat(vscode.Uri.file(candidate));
                return candidate;
            } catch {
                // ignore
            }
        }

        return undefined;
    }
}
