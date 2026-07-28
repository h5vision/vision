import * as vscode from "vscode";

import { getWebviewContent } from "./sidebarContents";
import { SidebarController } from "../controller/sidebarController";

export class SidebarProvider implements vscode.WebviewViewProvider {

    public view?: vscode.WebviewView;

    constructor( private readonly extensionUri: vscode.Uri ) {};

    resolveWebviewView( webviewView: vscode.WebviewView ) {

        this.view = webviewView;
        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this.extensionUri]
        };

        webviewView.webview.html =
            getWebviewContent(
                webviewView.webview,
                this.extensionUri
            );

         // Controller 생성
        const controller = new SidebarController(webviewView);

        // 메시지 연결
        webviewView.webview.onDidReceiveMessage(
            async message => {
                await controller.handle(message);
            }
        );
    };
};
