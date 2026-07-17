import * as vscode from "vscode";
import { getWebviewContent } from "./sidebar";

export class SidebarProvider implements vscode.WebviewViewProvider {

    public static readonly viewType = "VisionAssistant.sidebar";

    constructor(
        private readonly extensionUri: vscode.Uri
    ){}

    resolveWebviewView(
        webviewView: vscode.WebviewView
    ){

        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [
                this.extensionUri
            ]
        };

        webviewView.webview.html =
            getWebviewContent(
                webviewView.webview,
                this.extensionUri
            );
    }
}