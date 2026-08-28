import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs/promises';

import {
    DependencyGraph,
    DependencyGraphEdge,
    DependencyGraphNode
} from '../types/dependencyGraph';

import {
    extractImportPaths,
    resolveLanguageId,
    buildImportResolutionCandidates
} from './dependencyImportPatterns';

export class DependencyGraphService {

    private readonly graphFileName =
        '.vscode/dependency-graph.json';
    
    private async yieldToEventLoop(): Promise<void> {
        await new Promise<void>(
                resolve => setTimeout(resolve, 0)
            );
    }

    /**
     * 프로젝트 전체 Graph 최초 생성
     */
    public async build(
        gitCommit: string,
        onProgress: (
            phase : 'building [Node]' | 'building [Edge]',
            current: number,
            total: number
        ) => void
    ): Promise<DependencyGraph> {

        const workspace =
            vscode.workspace.workspaceFolders?.[0];

        if (!workspace) {
            throw new Error('Workspace is not opened.');
        }

        const root = workspace.uri.fsPath;

        const files = await this.findSourceFiles();

        const nodes: DependencyGraphNode[] = [];

        for (let i = 0; i < files.length; i++) {

            const file = files[i];

            const node = await this.createNode(
                    root,
                    file
                );

            nodes.push(node);

            onProgress?.(
                'building [Node]',
                i + 1,
                files.length
            );

            if (i % 20 === 0) {
                await this.yieldToEventLoop();
            }
        }

        const edges = await this.buildEdges(root, files, (status, current, total) => onProgress?.(status, current, total));

        return {
            version: 1,
            gitCommit,
            generatedAt: new Date().toISOString(),
            nodes,
            edges: this.removeDuplicateEdges(edges)
        };
    }

    /**
     * 변경된 파일만 다시 분석
     */
    public async updateFiles(
        graph: DependencyGraph,
        changedFiles: string[],
        gitCommit: string,
        onProgress: (
            phase: 'building [Node]' | 'building [Edge]',
            current: number,
            total: number
        ) => void
    ): Promise<DependencyGraph> {

        const workspace =
            vscode.workspace.workspaceFolders?.[0];

        if (!workspace) {
            throw new Error('Workspace is not opened.');
        }

        const root = workspace.uri.fsPath;

        for (let i = 0; i < changedFiles.length; i++) {

            const file = changedFiles[i];
            onProgress?.(
                'building [Node]',
                i + 1,
                changedFiles.length
            );

            const absolutePath = path.isAbsolute(file)
                ? file
                : path.join(root, file);

            /*
             * 삭제된 파일 처리
             */
            const exists =
                await this.fileExists(absolutePath);

            const relativePath =
                this.toRelativePath(
                    root,
                    absolutePath
                );

            if (!exists) {

                this.removeNode(
                    graph,
                    relativePath
                );

                this.removeEdgesForNode(
                    graph,
                    relativePath
                );

                continue;
            }

            /*
             * source file이 아니면 무시
             */
            if (!this.isSourceFile(absolutePath)) {
                continue;
            }

            /*
             * Node 갱신
             */
            const node =
                await this.createNode(
                    root,
                    absolutePath
                );

            this.upsertNode(
                graph,
                node
            );

            /*
             * 해당 파일에서 나가는
             * 기존 dependency 제거
             */
            this.removeOutgoingEdges(
                graph,
                relativePath
            );

            /*
             * 변경된 파일 다시 분석
             */
            const edges =
                await this.buildEdgesForFile(
                    root,
                    absolutePath
                );

            graph.edges.push(...edges);
        }

        graph.gitCommit = gitCommit;
        graph.generatedAt =
            new Date().toISOString();

        graph.edges =
            this.removeDuplicateEdges(
                graph.edges
            );

        return graph;
    }

    /**
     * 저장
     */
    public async save(
        graph: DependencyGraph
    ): Promise<void> {

        const workspace =
            vscode.workspace.workspaceFolders?.[0];

        if (!workspace) {
            throw new Error('Workspace is not opened.');
        }

        const file =
            path.join(
                workspace.uri.fsPath,
                this.graphFileName
            );

        await fs.mkdir(
            path.dirname(file),
            { recursive: true }
        );

        await fs.writeFile(
            file,
            JSON.stringify(
                graph,
                null,
                2
            ),
            'utf-8'
        );
    }

    /**
     * 로드
     */
    public async load():
        Promise<DependencyGraph | undefined> {

        const workspace =
            vscode.workspace.workspaceFolders?.[0];

        if (!workspace) {
            return undefined;
        }

        const file =
            path.join(
                workspace.uri.fsPath,
                this.graphFileName
            );

        try {

            const content =
                await fs.readFile(
                    file,
                    'utf-8'
                );

            return JSON.parse(content);

        } catch {

            return undefined;
        }
    }

    // =====================================================
    // Build
    // =====================================================

    private async buildEdges(
        root: string,
        files: string[], 
        onProgress: (
            phase: 'building [Edge]',
            current: number, 
            total: number
        ) => void
    ): Promise<DependencyGraphEdge[]> {

        const edges: DependencyGraphEdge[] = [];

        for (let i = 0; i < files.length; i++) {

            const file = files[i];
            onProgress(
                'building [Edge]',
                i,
                files.length
            );

            const fileEdges =
                await this.buildEdgesForFile(
                    root,
                    file
                );

            edges.push(...fileEdges);

            if (i % 10 === 0) {
                await this.yieldToEventLoop();
            }
        }

        return edges;
    }

    private async buildEdgesForFile(
        root: string,
        file: string, 
    ): Promise<DependencyGraphEdge[]> {

        const document =
            await vscode.workspace.openTextDocument(
                vscode.Uri.file(file)
            );

        const language =
            resolveLanguageId(
                document.languageId,
                document.fileName
            );

        const imports =
            extractImportPaths(
                document.getText(),
                language
            );

        const sourceId =
            this.toRelativePath(
                root,
                file
            );

        const edges: DependencyGraphEdge[] = [];

        for (const importPath of imports) {

            if (
                !this.shouldResolveImport(
                    importPath,
                    language
                )
            ) {
                continue;
            }

            const target =
                await this.resolveImport(
                    file,
                    importPath,
                    language,
                    root,
                    document.fileName
                );

            if (!target) {
                continue;
            }

            const targetId =
                this.toRelativePath(
                    root,
                    target
                );

            edges.push({
                id:
                    `${sourceId}->${targetId}:import`,

                source: sourceId,
                target: targetId,

                type: 'import'
            });
        }

        return edges;
    }

    // =====================================================
    // Node
    // =====================================================

    private async createNode(
        root: string,
        file: string
    ): Promise<DependencyGraphNode> {

        const document =
            await vscode.workspace.openTextDocument(
                vscode.Uri.file(file)
            );

        const relativePath =
            this.toRelativePath(
                root,
                file
            );

        const language =
            resolveLanguageId(
                document.languageId,
                document.fileName
            );

        return {
            id: relativePath,
            path: relativePath,
            label: path.basename(file),
            language
        };
    }

    private upsertNode(
        graph: DependencyGraph,
        node: DependencyGraphNode
    ): void {

        const index =
            graph.nodes.findIndex(
                item => item.id === node.id
            );

        if (index === -1) {
            graph.nodes.push(node);
            return;
        }

        graph.nodes[index] = node;
    }

    private removeNode(
        graph: DependencyGraph,
        nodeId: string
    ): void {

        graph.nodes =
            graph.nodes.filter(
                node => node.id !== nodeId
            );
    }

    // =====================================================
    // Edge
    // =====================================================

    private removeOutgoingEdges(
        graph: DependencyGraph,
        source: string
    ): void {

        graph.edges =
            graph.edges.filter(
                edge => edge.source !== source
            );
    }

    private removeEdgesForNode(
        graph: DependencyGraph,
        nodeId: string
    ): void {

        graph.edges =
            graph.edges.filter(
                edge =>
                    edge.source !== nodeId &&
                    edge.target !== nodeId
            );
    }

    private removeDuplicateEdges(
        edges: DependencyGraphEdge[]
    ): DependencyGraphEdge[] {

        const map =
            new Map<string, DependencyGraphEdge>();

        for (const edge of edges) {
            map.set(edge.id, edge);
        }

        return [...map.values()];
    }

    // =====================================================
    // Import
    // =====================================================

    private async resolveImport(
        sourceFile: string,
        importPath: string,
        language: string,
        workspaceRoot: string,
        fileName: string
    ): Promise<string | undefined> {

        const currentDir =
            path.dirname(sourceFile);

        const candidates =
            buildImportResolutionCandidates(
                currentDir,
                importPath,
                language,
                workspaceRoot,
                fileName
            );

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

    private shouldResolveImport(
        importPath: string,
        language: string
    ): boolean {

        const normalized =
            language.toLowerCase();

        if (normalized.startsWith('python')) {
            return (
                Boolean(importPath) &&
                !importPath.startsWith('http://') &&
                !importPath.startsWith('https://')
            );
        }

        if (
            normalized === 'cpp' ||
            normalized === 'c' ||
            normalized === 'objective-c' ||
            normalized === 'objective-cpp'
        ) {
            return (
                importPath.startsWith('.') ||
                importPath.startsWith('/') ||
                importPath.includes('/') ||
                importPath.includes('\\')
            );
        }

        return importPath.startsWith('.');
    }

    // =====================================================
    // Files
    // =====================================================

    private async findSourceFiles():
        Promise<string[]> {

        const files =
            await vscode.workspace.findFiles(
                '**/*',
                '**/{node_modules,.git,.vscode,out,dist,build}/**'
            );

        return files
            .map(uri => uri.fsPath)
            .filter(file =>
                this.isSourceFile(file)
            );
    }

    private isSourceFile(
        file: string
    ): boolean {

        const extensions = [
            '.ts',
            '.tsx',
            '.js',
            '.jsx',
            '.py',
            '.java',
            '.c',
            '.cpp',
            '.h',
            '.hpp',
            '.rs',
            '.go'
        ];

        return extensions.some(
            ext =>
                file
                    .toLowerCase()
                    .endsWith(ext)
        );
    }

    private async fileExists(
        file: string
    ): Promise<boolean> {

        try {

            await vscode.workspace.fs.stat(
                vscode.Uri.file(file)
            );

            return true;

        } catch {

            return false;
        }
    }

    private toRelativePath(
        root: string,
        file: string
    ): string {

        return path
            .relative(root, file)
            .replace(/\\/g, '/');
    }
}