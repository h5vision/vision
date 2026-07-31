import * as vscode from "vscode";
import { WorkspaceService } from "../../services/workspaceService";
import { GitService } from "../../services/gitService";
import {SidebarMessage} from "../../types/sidebarMessage";

export class ProjectInfoHandler {

    private readonly workspaceService = new WorkspaceService();
    private readonly gitService = new GitService();

    constructor( 
        private readonly view: vscode.WebviewView
    ) {}

    public async handle(message: SidebarMessage) {
        await this.gitService.initialize();
        this.gitService.onDidRepositoryReady(()=>{
            console.log(this.gitService.getRepositoryInfo());
            console.log(message.command);
            const workspace:any = this.workspaceService.getWorkspace();
            const git = this.gitService.exists();
            const response = {name: workspace.name, path: workspace.path, git: git};
            console.log(response);

            this.view.webview.postMessage({
                command: "showProjectInfo",
                data: response
            });
        });
    }
}