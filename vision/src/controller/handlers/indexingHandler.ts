import * as vscode from "vscode";

import { SidebarMessage } from "../../types/sidebarMessage";

import { ProjectMetadataService } from "../../services/indexing/projectMetadataService";
import { ProjectIndexingService } from "../../services/indexing/projectIndexingService";
import { APIService } from "../../services/APIService";

export class IndexingHandler {

    private readonly metadataService = new ProjectMetadataService();
    private readonly indexdataService = new ProjectIndexingService();
    private readonly APIService = new APIService();

    constructor(
        private readonly view: vscode.WebviewView
    ) {}

    public async handle(message: SidebarMessage) {
        
        const metadata = await this.metadataService.getMetadata();
        const indexdata = await this.indexdataService.getProjectIndexingData();
        console.log(indexdata);
        try {
            const response = await this.APIService.post('/v1/documents/ingest-with-metadata', indexdata);
            console.log(response);
        }
        catch{
            console.log('Project Indexing Fail...');
        }

        console.log(metadata);


        this.view.webview.postMessage({
            command: "displayProject",
            data: metadata
        });

    }

}