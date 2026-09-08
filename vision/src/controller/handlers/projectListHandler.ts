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
        await this.gitService.initialize();
        console.log(message.command);
        const apiService = new APIService();
        const indexedProjects: any = await apiService.get('/projects?view=repos');
        console.log(indexedProjects);
        const indexedProjectsList = (await indexedProjects.repos).map((project:any) => ({
            id: project.index_id,
            location: "DB",
            name: project.name,
            commits: project.commits.length > 0 
                ? project.commits.map((c:any) => [c, '']) 
                : [[project.indexed_commit, '']]
        }));
        
        const workspace:any = this.workspaceService.getWorkspace();
        const response = {name: workspace.name, path: workspace.path};
        
        if (this.gitService.exists()) {
            const branch = this.gitService.getCurrentBranch();
            const gitCommits = (await this.gitService.getRecentCommits()).map(m=>
                [m.hash, m.message]);
            const localPrj = {
                id: response.name,
                branch: branch,
                location: "Local",
                name: response.name, 
                commits: gitCommits,
                need_indexing: true
            };
            const matchingProject = indexedProjectsList.find(
                (project: any) => project.id === localPrj.name + '@' + branch
            );
            if (matchingProject) {
                localPrj.need_indexing = false;
                const latestCommit = matchingProject.commits[0];
                const latestLocalCommit = localPrj.commits[0];
                if (latestCommit[0] !== latestLocalCommit[0]) {
                    matchingProject.need_update = true;
                }
            }
            const otherProjects = indexedProjectsList
                .filter((project: any) => project !== matchingProject)
                .sort((a: any, b: any) => a.name.localeCompare(b.name));
            
            this.view.webview.postMessage({
                command: 'showProjectList',
                data: matchingProject
                    ? [localPrj, matchingProject, ...otherProjects]
                    : [localPrj, ...otherProjects]
            });
            console.log(localPrj, matchingProject, otherProjects);
        } else {
            this.view.webview.postMessage({
                command: 'showProjectList',
                data: [...indexedProjectsList]
            });
        }
    }
}
