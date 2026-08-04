import * as vscode from "vscode";
import * as path from "path";

import { DependencyFile } from "../types/dependency";

import {
    FileDependencyProvider
} from "../providers/dependencyProvider";

export class DependencyService {

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
        const symbols = await this.getSymbols(editor.document);

        const result = new Map<string, DependencyFile>();

        await Promise.all([

            this.collectImports(editor.document, result),

            this.collectDefinitions(editor.document, symbols, result),

            this.collectReferences(editor.document, symbols, result)

        ]);

        this.provider.updateFiles([...result.values()]);
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

        // 우선 Language Provider 사용
        const links =
            await vscode.commands.executeCommand<vscode.DocumentLink[]>(
                "vscode.executeLinkProvider",
                document.uri
            );

        if (links && links.length > 0) {

            for (const link of links) {

                if (!link.target) {
                    continue;
                }

                if (link.target.scheme !== "file") {
                    continue;
                }

                result.set(link.target.fsPath, {
                    path: link.target.fsPath,
                    label: vscode.workspace.asRelativePath(link.target),
                    imported: true,
                    referenced: false
                });
            }

            return;
        }

        // 지원하지 않는 언어라면 Regex 사용
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

        const regex =
            /import\s+(?:[\w*\s{},]*)\s+from\s+['"](.+)['"]|export\s+.*?from\s+['"](.+)['"]/g;

        for (let i = 0; i < document.lineCount; i++) {

            const line = document.lineAt(i).text;

            let match: RegExpExecArray | null;

            while ((match = regex.exec(line)) !== null) {

                const importPath = match[1] || match[2];

                if (!importPath.startsWith(".")) {
                    continue;
                }

                const file = await this.resolveImport(
                    currentDir,
                    importPath
                );

                if (!file) {
                    continue;
                }

                result.set(file, {
                    path: file,
                    label: vscode.workspace.asRelativePath(file),
                    imported: true,
                    referenced: false
                });
            }
        }
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

            const defs =
                await vscode.commands.executeCommand<
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

                const uri =
                    def instanceof vscode.Location
                        ? def.uri
                        : def.targetUri;

                if (uri.fsPath === document.uri.fsPath) {
                    continue;
                }

                result.set(uri.fsPath, {
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

            const refs =
                await vscode.commands.executeCommand<vscode.Location[]>(
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

                result.set(ref.uri.fsPath, {
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

        const symbols =
            await vscode.commands.executeCommand<vscode.DocumentSymbol[]>(
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

                visit(item.children);
            }
        };

        visit(symbols);

        return result;
    }

    /**
     * ======================================================
     * import path resolve
     * ======================================================
     */

    private async resolveImport(
        currentDir: string,
        importPath: string
    ): Promise<string | undefined> {

        const base = path.resolve(currentDir, importPath);

        const candidates = [

            base,

            `${base}.ts`,
            `${base}.tsx`,
            `${base}.js`,
            `${base}.jsx`,

            path.join(base, "index.ts"),
            path.join(base, "index.tsx"),
            path.join(base, "index.js"),
            path.join(base, "index.jsx")

        ];

        for (const candidate of candidates) {

            try {

                await vscode.workspace.fs.stat(
                    vscode.Uri.file(candidate)
                );

                return candidate;

            } catch {
                // ignore
            }
        }

        return undefined;
    }
}