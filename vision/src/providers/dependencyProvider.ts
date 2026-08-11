import * as vscode from 'vscode';
import { DependencyFile } from '../types/dependency';

type DependencyGroupId = 'imported' | 'referenced' | 'both' | 'unknown';

export class FileDependencyProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<vscode.TreeItem | undefined | void> = new vscode.EventEmitter<vscode.TreeItem | undefined | void>();
    readonly onDidChangeTreeData: vscode.Event<vscode.TreeItem | undefined | void> = this._onDidChangeTreeData.event;

    private files: DependencyFile[] = [];
    private isLoading = false;

    public setLoading() {
        this.files = [];
        this.isLoading = true;
        this._onDidChangeTreeData.fire();
    }

    public updateFiles(newFiles: DependencyFile[]) {
        this.files = newFiles;
        this.isLoading = false;
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: vscode.TreeItem): Thenable<vscode.TreeItem[]> {
        if (element) {
            return Promise.resolve([]);
        }

        if (this.isLoading) {
            return Promise.resolve([this.createLoadingItem()]);
        }

        if (!this.files.length) {
            return Promise.resolve([this.createPlaceholderItem()]);
        }

        return Promise.resolve(this.files.map(file => this.createFileItem(file)));
    }

    private createFileItem(file: DependencyFile): vscode.TreeItem {
        const item = new vscode.TreeItem(
            file.label,
            vscode.TreeItemCollapsibleState.None
        );

        item.resourceUri = vscode.Uri.file(file.path);
        item.contextValue = 'dependencyFile';
        item.command = {
            command: 'vscode.open',
            title: '파일 열기',
            arguments: [vscode.Uri.file(file.path)]
        };

        const groupId = this.getGroupId(file);
        item.description = this.getGroupDescription(groupId);
        item.tooltip = this.buildTooltip(file, groupId);
        item.iconPath = this.getIconForGroup(groupId);

        return item;
    }

    private createLoadingItem(): vscode.TreeItem {
        const item = new vscode.TreeItem('의존성 파일을 찾는 중입니다...', vscode.TreeItemCollapsibleState.None);
        item.tooltip = '현재 활성 파일의 import와 참조 관계를 분석하고 있습니다.';
        item.iconPath = new vscode.ThemeIcon('sync~spin');
        item.contextValue = 'dependencyLoading';
        return item;
    }

    private createPlaceholderItem(): vscode.TreeItem {
        const item = new vscode.TreeItem('의존성 파일이 없습니다.', vscode.TreeItemCollapsibleState.None);
        item.tooltip = '현재 활성 파일에서 확인된 의존성 파일이 없습니다.';
        item.iconPath = new vscode.ThemeIcon('info');
        item.contextValue = 'dependencyPlaceholder';
        return item;
    }

    private getGroupId(file: DependencyFile): DependencyGroupId {
        if (file.imported && file.referenced) {
            return 'both';
        }

        if (file.imported) {
            return 'imported';
        }

        if (file.referenced) {
            return 'referenced';
        }

        return 'unknown';
    }

    private getGroupDescription(groupId: DependencyGroupId): string {
        switch (groupId) {
            case 'imported':
                return 'imported';
            case 'referenced':
                return 'referenced';
            case 'both':
                return 'imported/referenced';
            case 'unknown':
                return 'unknown';
        }
    }

    private buildTooltip(file: DependencyFile, groupId: DependencyGroupId): string {
        return `${vscode.workspace.asRelativePath(file.path)}\n유형: ${this.getGroupDescription(groupId)}`;
    }

    private getIconForGroup(groupId: DependencyGroupId): vscode.ThemeIcon {
        switch (groupId) {
            case 'imported':
                return new vscode.ThemeIcon('fold-down', new vscode.ThemeColor('charts.red'));
            case 'referenced':
                return new vscode.ThemeIcon('fold-up', new vscode.ThemeColor('charts.blue'));
            case 'both':
                return new vscode.ThemeIcon('fold', new vscode.ThemeColor('charts.purple'));
            case 'unknown':
                return new vscode.ThemeIcon('question');
        }
    }
}
