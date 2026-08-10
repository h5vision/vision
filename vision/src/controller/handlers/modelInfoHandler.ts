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

        const response = await this.APIService.get("/models");

        let modelsInfo: {model_id: string, model_name: string}[] = [];

        if ((response as responseModel).models) {
            modelsInfo = (response as responseModel).models.map((model) => {
                return {
                    model_id: model.model_id,
                    model_name: model.display_name
                };
            });
        }

        this.view.webview.postMessage({
            command: "showModelsInfo",
            data: {models: modelsInfo, current_model_id: current_model_id}
        });
    }
}

interface responseModel {
    schema_version: string;
    default_model_id: string;
    checked_at: string;
    models: {
        model_id: string;
        model_name: string;
        display_name: string;
        provider: string;
        location: string;
        deployment_type: string;
        endpoint: string;
        enabled: boolean;
        available: boolean;
        is_default: boolean;
        streaming: boolean;
    }[];
}