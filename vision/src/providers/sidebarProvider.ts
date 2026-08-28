import * as vscode from "vscode";
import { DependencyGraphManager } from "../services/dependencyGraphManager";
import { getWebviewContent } from "./sidebarContents";
import { SidebarController } from "../controller/sidebarController";
import { GraphProgress } from "../types/dependencyGraph";

export class SidebarProvider implements vscode.WebviewViewProvider {

    public view?: vscode.WebviewView;
    
    private readonly statusDisposable: vscode.Disposable;
    private messageDisposable?: vscode.Disposable;

    constructor( 
        private readonly extensionUri: vscode.Uri,
        private readonly dependencyGraphManager: DependencyGraphManager
    ) {
        this.statusDisposable =
            this.dependencyGraphManager.onStatusChanged(
                progress => {
                    this.sendGraphStatus(progress);
                }
            );
    };

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
        this.messageDisposable =
            webviewView.webview.onDidReceiveMessage(
                async message => {
                    if (message.command === 'getDependencyGraphStatus') {
                        this.sendGraphStatus(this.dependencyGraphManager.getProgress());
                        return;
                    }
                    await controller.handle(message);                    
                }
            );

        this.sendGraphStatus(
            this.dependencyGraphManager.getProgress()
        );
    };

    private sendGraphStatus(
        progress: GraphProgress
    ): void {
        if (!this.view) {return;}
        this.view.webview.postMessage({
            command: 'dependencyGraphStatus',
            data: {...progress}
        });
    }
    
    dispose(): void {
        this.statusDisposable.dispose();
        this.messageDisposable?.dispose();
    }
};
