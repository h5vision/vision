import * as vscode from "vscode";

import { SidebarMessage } from "../../types/sidebarMessage";
import { APIService } from "../../services/APIService";

export class APIHandler {

    private readonly APIService = new APIService();

    constructor( 
        private readonly view: vscode.WebviewView
    ) {}

    public async handle(message: SidebarMessage) {
        
        console.log(message.command);

        // CheckBackend 기능 추가
        const response = await this.APIService.checkHealth();

        this.view.webview.postMessage({
            command: "backendStatus",
            data: response
        });

    }

}