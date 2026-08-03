import * as vscode from "vscode";
import { WorkspaceService } from "../../services/workspaceService";
import { SidebarMessage } from "../../types/sidebarMessage";
import { GitService } from "../../services/gitService";

export class ProjectInfoHandler {

    private readonly workspaceService = new WorkspaceService();
    private readonly gitService = new GitService();

    constructor( 
        private readonly view: vscode.WebviewView
    ) {}

    public async handle(message: SidebarMessage) {
    
        console.log(message.command);
        const workspace:any = this.workspaceService.getWorkspace();
        const response = {name: workspace.name, path: workspace.path};
        console.log(response);

        this.view.webview.postMessage({
            command: "showProjectInfo",
            data: response
        });
    };

    public async handleGitInfo(message: SidebarMessage) {
        console.log(message.command);
        this.gitService.onDidRepositoryReady(() => {
            const git = this.gitService.exists();
            const response = {git: git, repository: this.gitService.getRepositoryInfo()};
            console.log(response);

            this.view.webview.postMessage({
                command: "showProjectGitInfo",
                data: response
            });
        });
        await this.gitService.initialize();
    }
}