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

        this.view.webview.postMessage({
            command: "showProjectInfo",
            data: response
        });
    };

    public async handleGitInfo(message: SidebarMessage) {
        this.gitService.dispose();
        console.log(message.command);
        await this.gitService.initialize();
        const response = {git: this.gitService.exists(), repository: this.gitService.getRepositoryInfo()};
        this.view.webview.postMessage({
            command: "showProjectGitInfo",
            data: response
        });
        this.gitService.onDidRepositoryReady(() => {
            const updatedResponse = {git: this.gitService.exists(), repository: this.gitService.getRepositoryInfo()};
            console.log("Repository is ready. Updated response:", updatedResponse);
            this.view.webview.postMessage({
                command: "showProjectGitInfo",
                data: updatedResponse
            });
        });
    }
}