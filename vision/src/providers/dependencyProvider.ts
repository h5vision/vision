import * as vscode from 'vscode';

export class FileDependencyProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<vscode.TreeItem | undefined | void> = new vscode.EventEmitter<vscode.TreeItem | undefined | void>();
    readonly onDidChangeTreeData: vscode.Event<vscode.TreeItem | undefined | void> = this._onDidChangeTreeData.event;

    private files: { path: string; label: string; type: 'red' | 'blue' }[] = [];

    public updateFiles(newFiles: { path: string; label: string; type: 'red' | 'blue' }[]) {
        this.files = newFiles;
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: vscode.TreeItem): Thenable<vscode.TreeItem[]> {
        if (element) {
            return Promise.resolve([]);
        }

        const items = this.files.map(file => {
            const item = new vscode.TreeItem(file.label, vscode.TreeItemCollapsibleState.None);
            
            if (file.type === 'red') {
                item.description = '[연관]';
                item.iconPath = new vscode.ThemeIcon('circle-filled', new vscode.ThemeColor('errorForeground'));
            } else {
                item.description = '[sLLM 출처]';
                item.iconPath = new vscode.ThemeIcon('circle-filled', new vscode.ThemeColor('charts.blue'));
            }

            item.command = {
                command: 'vscode.open',
                title: 'Open File',
                arguments: [vscode.Uri.file(file.path)]
            };

            return item;
        });

        return Promise.resolve(items);
    }
}