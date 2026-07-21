import * as vscode from "vscode";

import { SidebarMessage } from "../../types/sidebarMessage";
import { APIService } from "../../services/APIService";

export class APIHandler {

    private readonly APIService = new APIService();

    constructor( 
        private readonly view: vscode.WebviewView
    ) {}

    public async handle(message: SidebarMessage) {
        console.log('checkBackend');

        // CheckBackend 기능 추가
        const response = await this.APIService.checkHealth();
        console.log(response);

        this.view.webview.postMessage({
            command: "backendStatus",
            data: response
        });

    }

}