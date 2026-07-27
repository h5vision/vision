import * as vscode from "vscode";
import { WorkspaceService } from "../../services/indexing/workspaceService";
import { GitService } from "../../services/indexing/gitService";
import {SidebarMessage} from "../../types/sidebarMessage";

export class ProjectInfoHandler {

    private readonly workspaceService = new WorkspaceService();
    private readonly gitService = new GitService();

    constructor( 
        private readonly view: vscode.WebviewView
    ) {}

    public async handle(message: SidebarMessage) {
        
        console.log(message.command);
        const workspace:any = this.workspaceService.getWorkspace();
        const git = this.gitService.getGitInfo(workspace.path).enabled;
        const response = {name: workspace.name, path: workspace.path, git: git};

        this.view.webview.postMessage({
            command: "showProjectInfo",
            data: response
        });

    }

}