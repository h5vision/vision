import * as vscode from 'vscode';
import { DependencyFile } from '../types/dependency';

export class FileDependencyProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<vscode.TreeItem | undefined | void> = new vscode.EventEmitter<vscode.TreeItem | undefined | void>();
    readonly onDidChangeTreeData: vscode.Event<vscode.TreeItem | undefined | void> = this._onDidChangeTreeData.event;

    private files: DependencyFile[] = [];

    public updateFiles(newFiles: DependencyFile[]) {
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
            
            if (file.imported) {
                item.description = '[imported]';
                item.iconPath = new vscode.ThemeIcon('circle-filled', new vscode.ThemeColor('charts.red'));
            } else if (file.referenced) {
                item.description = '[referenced]';
                item.iconPath = new vscode.ThemeIcon('circle-filled', new vscode.ThemeColor('charts.blue'));
            } else {
                item.description = '';
                item.iconPath = new vscode.ThemeIcon('star-filled', new vscode.ThemeColor('charts.yellow'));
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