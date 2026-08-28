import * as vscode from "vscode";
import { WorkspaceService } from "../../services/workspaceService";
import { SidebarMessage } from "../../types/sidebarMessage";
import { GitService } from "../../services/gitService";

export class ProjectInfoHandler {

    private readonly workspaceService = new WorkspaceService();

    constructor( 
        private readonly view: vscode.WebviewView,
        private readonly gitService: GitService = new GitService()
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
        console.log(message.command);
        await this.gitService.initialize();
        const repo = await this.gitService.getRepositoryInfo();
        const response = {git: this.gitService.exists(), repository: repo};
        this.view.webview.postMessage({
            command: "showProjectGitInfo",
            data: response
        });
        await vscode.workspace.getConfiguration('vision').update(
                "projectId",
                repo?.rootPath.split('\\').pop(),
                vscode.ConfigurationTarget.Global
            );
        await vscode.workspace.getConfiguration('vision').update(
                "commitId",
                repo?.commit,
                vscode.ConfigurationTarget.Global
            );
        console.log("Git info sent to webview:", response);
        
        
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
