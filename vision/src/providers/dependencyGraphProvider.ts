import * as vscode from 'vscode';

import { DependencyGraphManager } from '../services/dependencyGraphManager';
import { getNonce } from '../utils/nonce';

export class DependencyGraphProvider {

    private panel: vscode.WebviewPanel | undefined;

    constructor(
        private readonly context: vscode.ExtensionContext,
        private readonly manager: DependencyGraphManager
    ) {}

    public show(): void {

        if (this.panel) {
            this.panel.reveal(vscode.ViewColumn.One);
            return;
        }

        const panel =
            vscode.window.createWebviewPanel(
                'dependencyGraph',
                'Dependency Graph',
                vscode.ViewColumn.One,
                {
                    enableScripts: true,
                    localResourceRoots: [
                        vscode.Uri.joinPath(
                            this.context.extensionUri,
                            'webview_graph',
                            'dist'
                        )
                    ]
                }
            );

        this.panel = panel;

        panel.onDidDispose(() => {
            this.panel = undefined;
        });

        panel.webview.html =
            this.getHtml(panel.webview);

        const graph = this.manager.getGraph();

        panel.webview.onDidReceiveMessage(async (message) => {
            if (message.type === 'ready') {
                if (graph) {
                    this.sendGraph(panel, graph);
                }
            }
        });
    }

    // 챗 응답의 근거 문서 경로를 그래프 웹뷰로 전달해 노드를 강조 표시
    public highlightSources(paths: string[]): void {
        this.panel?.webview.postMessage({
            type: 'highlightSources',
            paths
        });
    }

    private async sendGraph(panel: vscode.WebviewPanel, graph: any): Promise<void> {
        if (graph) {
            panel.webview.postMessage({
                type: 'graphData',
                data: graph
            });
        }
    }

    private getHtml(
        webview: vscode.Webview
    ): string {

        const scriptUri =
            webview.asWebviewUri(
                vscode.Uri.joinPath(
                    this.context.extensionUri,
                    'webview_graph',
                    'dist',
                    'assets',
                    'index-CGJ8Ok-C.js'
                )
            );

        const styleUri =
            webview.asWebviewUri(
                vscode.Uri.joinPath(
                    this.context.extensionUri,
                    'webview_graph',
                    'dist',
                    'assets',
                    'index-DgIqE3F2.css'
                )
            );

        const nonce = getNonce();

        return `
            <!DOCTYPE html>

            <html>
            <head>
                <meta
                    charset="UTF-8"
                />

                <meta name="viewport" content="width=device-width, initial-scale=1.0" />

                <meta
                    http-equiv="Content-Security-Policy"
                    content="
                        default-src 'none';
                        style-src ${webview.cspSource} 'unsafe-inline';
                        script-src ${webview.cspSource} 'nonce-${nonce}';
                    "
                />

                <title>
                    webview_graph
                </title>

                <link
                    rel="stylesheet"
                    href="${styleUri}"
                />
            </head>

            <body>

                <div id="root"></div>

                <script
                    type="module" 
                    nonce="${nonce}"
                    src="${scriptUri}"
                ></script>

            </body>
            </html>
        `;
    }
}