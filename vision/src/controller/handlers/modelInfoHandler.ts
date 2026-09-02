import * as vscode from "vscode";

import { SidebarMessage } from "../../types/sidebarMessage";
import { APIService } from "../../services/APIService";

export class ModelInfoHandler {

    private readonly APIService = new APIService();

    constructor( 
        private readonly view: vscode.WebviewView
    ) {}

    public async handle(message: SidebarMessage) {
        
        console.log(message.command);

        const current_model_id = vscode.workspace.getConfiguration("vision").get<string>("modelId");

        try {
            const response:any = await this.APIService.get("/v1/models", 2500);

            if (response.models) {
                this.view.webview.postMessage({
                    command: "showModelsInfo",
                    data: {models: response.models, current_model_id: current_model_id}
                });
            }
        } catch (error) {
            console.log("Failed to load models info:", error);
        }

        
    }
}
