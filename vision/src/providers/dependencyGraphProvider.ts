import * as vscode from 'vscode';

import { DependencyGraphManager } from '../services/dependencyGraphManager';
import { getNonce } from '../utils/nonce';

export class DependencyGraphProvider {

    constructor(
        private readonly context: vscode.ExtensionContext,
        private readonly manager: DependencyGraphManager
    ) {}

    public show(): void {

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
                            'webview',
                            'dependencyGraph',
                            'dist'
                        )
                    ]
                }
            );

        panel.webview.html =
            this.getHtml(panel.webview);

        const graph =
            this.manager.getGraph();

        if (graph) {

            panel.webview.postMessage({
                type: 'graph',
                graph
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
                    'webview',
                    'dependencyGraph',
                    'dist',
                    'assets',
                    'index.js'
                )
            );

        const styleUri =
            webview.asWebviewUri(
                vscode.Uri.joinPath(
                    this.context.extensionUri,
                    'webview',
                    'dependencyGraph',
                    'dist',
                    'assets',
                    'index.css'
                )
            );

        const nonce =
            getNonce();

        return `
            <!DOCTYPE html>

            <html>
            <head>
                <meta
                    charset="UTF-8"
                />

                <meta
                    http-equiv="Content-Security-Policy"
                    content="
                        default-src 'none';
                        style-src ${webview.cspSource};
                        script-src 'nonce-${nonce}';
                    "
                />

                <link
                    rel="stylesheet"
                    href="${styleUri}"
                />
            </head>

            <body>

                <div id="root"></div>

                <script
                    nonce="${nonce}"
                    src="${scriptUri}"
                ></script>

            </body>
            </html>
        `;
    }
}