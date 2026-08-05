import * as vscode from 'vscode';
import { DependencyFile } from '../types/dependency';

type DependencyGroupId = 'imported' | 'referenced' | 'both' | 'unknown';

interface DependencyGroup {
    id: DependencyGroupId;
    label: string;
    count: number;
}

export class FileDependencyProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<vscode.TreeItem | undefined | void> = new vscode.EventEmitter<vscode.TreeItem | undefined | void>();
    readonly onDidChangeTreeData: vscode.Event<vscode.TreeItem | undefined | void> = this._onDidChangeTreeData.event;

    private files: DependencyFile[] = [];
    private statusMessage = 'Ready';

    public updateFiles(newFiles: DependencyFile[]) {
        this.files = newFiles;
        this._onDidChangeTreeData.fire();
    }

    public updateStatus(status: string) {
        this.statusMessage = status;
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: vscode.TreeItem): Thenable<vscode.TreeItem[]> {
        if (!element) {
            if (!this.files.length) {
                return Promise.resolve([this.createPlaceholderItem()]);
            }

            const groups = this.buildGroups();
            return Promise.resolve(groups.map(group => this.createGroupItem(group)));
        }

        if (element.contextValue === 'dependencyGroup') {
            const groupId = element.id as DependencyGroupId;
            const children = this.files
                .filter(file => this.getGroupId(file) === groupId)
                .map(file => this.createFileItem(file));
            return Promise.resolve(children);
        }

        return Promise.resolve([]);
    }

    private buildGroups(): DependencyGroup[] {
        const counts: Record<DependencyGroupId, number> = {
            imported: 0,
            referenced: 0,
            both: 0,
            unknown: 0
        };

        for (const file of this.files) {
            counts[this.getGroupId(file)] += 1;
        }

        return Object.entries(counts)
            .filter(([, count]) => count > 0)
            .map(([id, count]) => ({
                id: id as DependencyGroupId,
                label: this.getGroupLabel(id as DependencyGroupId),
                count
            }));
    }

    private createGroupItem(group: DependencyGroup): vscode.TreeItem {
        const item = new vscode.TreeItem(
            `${group.label} (${group.count})`,
            vscode.TreeItemCollapsibleState.Collapsed
        );
        item.id = group.id;
        item.contextValue = 'dependencyGroup';
        item.description = `${group.count} items`;
        item.tooltip = `Show ${group.count} ${group.label.toLowerCase()} dependencies`;
        item.iconPath = new vscode.ThemeIcon('folder');
        return item;
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
            title: 'Open File',
            arguments: [vscode.Uri.file(file.path)]
        };

        const groupId = this.getGroupId(file);
        item.description = this.getGroupDescription(groupId);
        item.tooltip = this.buildTooltip(file, groupId);
        item.iconPath = this.getIconForGroup(groupId);

        return item;
    }

    private createPlaceholderItem(): vscode.TreeItem {
        const item = new vscode.TreeItem('의존성 파일이 없습니다.', vscode.TreeItemCollapsibleState.None);
        item.tooltip = '현재 활성화된 파일에 추출 가능한 의존성이 없습니다.';
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

    private getGroupLabel(groupId: DependencyGroupId): string {
        switch (groupId) {
            case 'imported':
                return 'Imported Files';
            case 'referenced':
                return 'Referenced By Current File';
            case 'both':
                return 'Imported and Referenced';
            case 'unknown':
                return 'Unknown Dependency Type';
        }
    }

    private getGroupDescription(groupId: DependencyGroupId): string {
        switch (groupId) {
            case 'imported':
                return '[imported]';
            case 'referenced':
                return '[referenced]';
            case 'both':
                return '[imported/referenced]';
            case 'unknown':
                return '[unknown]';
        }
    }

    private buildTooltip(file: DependencyFile, groupId: DependencyGroupId): string {
        const details = [`Type: ${this.getGroupDescription(groupId)}`];

        if (file.llmSource) {
            details.push('LLM Source');
        }
        if (file.gitRelated) {
            details.push('Git Related');
        }

        return `${vscode.workspace.asRelativePath(file.path)}\n${details.join(' · ')}`;
    }

    private getIconForGroup(groupId: DependencyGroupId): vscode.ThemeIcon {
        switch (groupId) {
            case 'imported':
                return new vscode.ThemeIcon('circle-filled', new vscode.ThemeColor('charts.red'));
            case 'referenced':
                return new vscode.ThemeIcon('circle-filled', new vscode.ThemeColor('charts.blue'));
            case 'both':
                return new vscode.ThemeIcon('circle-filled', new vscode.ThemeColor('charts.purple'));
            case 'unknown':
                return new vscode.ThemeIcon('question');
        }
    }
}