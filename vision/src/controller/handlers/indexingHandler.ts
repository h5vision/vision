import * as vscode from "vscode";

import { SidebarMessage } from "../../types/sidebarMessage";

import { ProjectMetadataService } from "../../services/indexing/projectMetadataService";

export class IndexingHandler {

    private readonly metadataService = new ProjectMetadataService();

    constructor(
        private readonly view: vscode.WebviewView
    ) {}

    public async handle(message: SidebarMessage) {
        
        const metadata = await this.metadataService.getMetadata();

        console.log(metadata);

        this.view.webview.postMessage({
            command: "displayProject",
            data: metadata
        });

    }

}