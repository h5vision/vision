import * as vscode from "vscode";
import * as fs from "fs";
import { getNonce } from "../utils/nonce";

export function getWebviewContent(
    webview: vscode.Webview,
    extensionUri: vscode.Uri
): string {

    const htmlPath = vscode.Uri.joinPath(extensionUri, "webview", "sidebar.html");
    let html = fs.readFileSync(htmlPath.fsPath, "utf-8");

    const nonce = getNonce();

    const styleUri =
        webview.asWebviewUri(
            vscode.Uri.joinPath(extensionUri, "webview", "style.css")
        );

    const codiconUri = 
        webview.asWebviewUri(
            vscode.Uri.joinPath(extensionUri, "media", "codicon", "codicon.css")
        );

    const scriptUri =
        webview.asWebviewUri(
            vscode.Uri.joinPath(extensionUri, "webview", "script.js")
        );

    html = html
        .replaceAll("{{cspSource}}", webview.cspSource)
        .replaceAll("{{nonce}}", nonce)
        .replace("{{styleUri}}", styleUri.toString())
        .replace("{{codiconUri}}", codiconUri.toString())
        .replace("{{scriptUri}}", scriptUri.toString());
    
    return html;
};