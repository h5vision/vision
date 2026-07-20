import * as vscode from "vscode";

export class ContextCollector {

    static getCurrentFile(): string | undefined {

        return vscode.window.activeTextEditor
            ?.document.uri.fsPath;

    }

    static getSelectedText(): string {

        return vscode.window.activeTextEditor
            ?.document.getText(
                vscode.window.activeTextEditor.selection
            ) ?? "";

    }

}