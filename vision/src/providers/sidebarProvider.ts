import * as vscode from "vscode";

import { BackendService } from "../services/APIService";
import { getWebviewContent } from "./sidebarContents";

export class SidebarProvider implements vscode.WebviewViewProvider {

    private view?: vscode.WebviewView;

    private backend = new BackendService(
        "http://localhost:8888"
    );

    constructor(
        private readonly extensionUri: vscode.Uri
    ) {}

    resolveWebviewView(
        webviewView: vscode.WebviewView
    ) {

        this.view = webviewView;

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

        webviewView.webview.onDidReceiveMessage(
            async (message) => {

                switch (message.command) {

                    case "checkBackend":

                        await this.checkBackend();

                        break;

                }

            }
        );

        // 처음 열렸을 때 자동 확인
        this.checkBackend();

    }

    /**
     * JS에게 메시지 전달
     */
    private sendMessage(
        command: string,
        data: any
    ) {

        this.view?.webview.postMessage({

            command,

            data

        });

    }

    /**
     * 백엔드 상태 확인
     */
    private async checkBackend() {

        const result = await this.backend.checkHealth();

        this.sendMessage("backendStatus", result);

    }

};