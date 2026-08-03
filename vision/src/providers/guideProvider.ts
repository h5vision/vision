import * as vscode from 'vscode';
import * as path from 'path';

import { getHtmlContent } from './guideContents';

export class GuideProvider {

    public panel?: vscode.WebviewPanel;

    constructor(
        private readonly context: vscode.ExtensionContext,
        private readonly sendMessage: (
            message: any
        ) => Thenable<boolean> | undefined
    ) {}

    public showGuide(): void {

        if (this.panel) {
            this.panel.reveal(vscode.ViewColumn.One);
            return;
        }

        this.panel = vscode.window.createWebviewPanel(
            'visionGuide',
            'Vision Guide',
            vscode.ViewColumn.One,
            {
                enableScripts: true,
                localResourceRoots: [
                    vscode.Uri.file(path.join(this.context.extensionPath))
                ]
            }
        );

        this.panel.webview.html = getHtmlContent(
            this.context,
            this.panel
        );

        this.registerMessageHandler();

        this.panel.onDidDispose(() => {
            this.panel = undefined;
        });

        this.sendMessage({
            command: "guideStatus",
            data: true
        });
    }

    public toggleGuide(): void {

        if (this.panel) {
            this.panel.dispose();
            this.sendMessage({
                command: "guideStatus",
                data: false
            });
            return;
        }

        this.showGuide();
    }

    private registerMessageHandler() {

        if (!this.panel) {
            return;
        }

        this.panel.webview.onDidReceiveMessage(async (message) => {

            switch (message.command) {

                case "hideGuideBook":
                    await vscode.workspace
                        .getConfiguration("vision")
                        .update(
                            "showGuideBook",
                            false,
                            vscode.ConfigurationTarget.Global
                        );
                    vscode.window.showInformationMessage(
                        "Guidebook 자동표시를 비활성화했습니다."
                    );
                    break;

                case "showGuideBook":
                    await vscode.workspace
                        .getConfiguration("vision")
                        .update(
                            "showGuideBook",
                            true,
                            vscode.ConfigurationTarget.Global
                        );
                    vscode.window.showInformationMessage(
                        "Guidebook 자동표시를 활성화했습니다."
                    );
                    break;
            }

            // Sidebar 등에 메시지 전달
            await this.sendMessage(message);

        });

    }

}