import * as vscode from "vscode";
import { FileDependencyProvider } from "../providers/dependencyProvider";

export interface DependencyFile {
    path: string;
    label: string;
    type: "red" | "blue";
}

export class DependencyService {

    constructor(
        private readonly provider: FileDependencyProvider
    ) {}

    /**
     * 현재 활성 Editor 기준으로 Dependency Tree를 갱신
     */
    public async refresh(): Promise<void> {

        const editor = vscode.window.activeTextEditor;

        if (!editor) {
            this.provider.updateFiles([]);
            return;
        }

        const files = await this.collectDependencies(editor.document);

        this.provider.updateFiles(files);
    }

    /**
     * Document 전체의 Dependency 수집
     */
    private async collectDependencies(
        document: vscode.TextDocument
    ): Promise<DependencyFile[]> {

        const dependencies = new Map<string, DependencyFile>();

        const symbols =
            await vscode.commands.executeCommand<vscode.DocumentSymbol[]>(
                "vscode.executeDocumentSymbolProvider",
                document.uri
            );

        if (!symbols) {
            return [];
        }

        await this.visitSymbols(
            document.uri,
            symbols,
            dependencies
        );

        return [...dependencies.values()];
    }

    /**
     * Symbol Tree 순회
     */
    private async visitSymbols(
        uri: vscode.Uri,
        symbols: vscode.DocumentSymbol[],
        result: Map<string, DependencyFile>
    ): Promise<void> {

        for (const symbol of symbols) {

            // 필요한 Symbol만 분석
            switch (symbol.kind) {

                case vscode.SymbolKind.Class:
                case vscode.SymbolKind.Interface:
                case vscode.SymbolKind.Function:
                case vscode.SymbolKind.Method:
                case vscode.SymbolKind.Constructor:

                    await Promise.all([
                        this.collectDefinition(uri, symbol.selectionRange.start, result),
                        this.collectReference(uri, symbol.selectionRange.start, result)
                    ]);

                    break;
            }

            if (symbol.children.length > 0) {
                await this.visitSymbols(
                    uri,
                    symbol.children,
                    result
                );
            }
        }
    }

    /**
     * Definition 검색
     */
    private async collectDefinition(
        uri: vscode.Uri,
        position: vscode.Position,
        result: Map<string, DependencyFile>
    ): Promise<void> {

        const defs =
            await vscode.commands.executeCommand<
                vscode.Location[] | vscode.LocationLink[]
            >(
                "vscode.executeDefinitionProvider",
                uri,
                position
            );

        if (!defs) {
            return;
        }

        for (const def of defs) {

            const targetUri =
                def instanceof vscode.Location
                    ? def.uri
                    : def.targetUri;

            if (targetUri.fsPath === uri.fsPath) {
                continue;
            }

            result.set(targetUri.fsPath, {
                path: targetUri.fsPath,
                label: vscode.workspace.asRelativePath(targetUri),
                type: "red"
            });
        }
    }

    /**
     * Reference 검색
     */
    private async collectReference(
        uri: vscode.Uri,
        position: vscode.Position,
        result: Map<string, DependencyFile>
    ): Promise<void> {

        const refs =
            await vscode.commands.executeCommand<vscode.Location[]>(
                "vscode.executeReferenceProvider",
                uri,
                position
            );

        if (!refs) {
            return;
        }

        for (const ref of refs) {

            if (ref.uri.fsPath === uri.fsPath) {
                continue;
            }

            result.set(ref.uri.fsPath, {
                path: ref.uri.fsPath,
                label: vscode.workspace.asRelativePath(ref.uri),
                type: "red"
            });
        }
    }
}