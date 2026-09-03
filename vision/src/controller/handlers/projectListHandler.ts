import * as vscode from "vscode";
import { SidebarMessage } from "../../types/sidebarMessage";
import { GitService } from "../../services/gitService";
import { WorkspaceService } from "../../services/workspaceService";
import { APIService } from "../../services/APIService";

export class ProjectListHandler {

    private readonly workspaceService = new WorkspaceService();
    constructor(
        private readonly view: vscode.WebviewView,
        private readonly gitService: GitService = new GitService()
    ) {}

    public async handle(message: SidebarMessage) {
        
        console.log(message.command);
        const apiService = new APIService();
        const indexedProjects: any = await apiService.get('/projects?view=repos');
        const indexedProjectsList = (await indexedProjects.repos).map((project:any) => ({
            id: project.index_id,
            location: "DB",
            name: project.name,
            commits: project.commits.length > 0 
                ? project.commits.map((c:any) => [c, '']) 
                : [[project.indexed_commit, '']]
        }));
        console.log(indexedProjectsList);
        
        const workspace:any = this.workspaceService.getWorkspace();
        const response = {name: workspace.name, path: workspace.path};
        await this.gitService.initialize();
        if (this.gitService.exists()) {
            const gitCommits = (await this.gitService.getRecentCommits()).map(m=>
                [m.hash, m.message]);
            const localPrj = {
                id: response.name, 
                location: "Local",
                name: response.name, 
                commits: gitCommits,
            };
            const matchingProject = indexedProjectsList.find(
                (project: any) => project.name === localPrj.name
            );
            const otherProjects = indexedProjectsList
                .filter((project: any) => project !== matchingProject)
                .sort((a: any, b: any) => a.name.localeCompare(b.name));
            
            this.view.webview.postMessage({
                command: 'showProjectList',
                data: matchingProject
                    ? [localPrj, matchingProject, ...otherProjects]
                    : [localPrj, ...otherProjects]
            });
        } else {
            this.view.webview.postMessage({
                command: 'showProjectList',
                data: [...indexedProjectsList]
            });
        }
    }
}
