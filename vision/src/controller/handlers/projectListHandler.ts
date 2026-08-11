import * as vscode from "vscode";

import { SidebarMessage } from "../../types/sidebarMessage";
import { GitService } from "../../services/gitService";
import { WorkspaceService } from "../../services/workspaceService";

export class ProjectListHandler {

    private readonly gitService = new GitService();
    private readonly workspaceService = new WorkspaceService();
    constructor(
        private readonly view: vscode.WebviewView
    ) {}

    public async handle(message: SidebarMessage) {

        // 💡 프로젝트 이름과 아코디언은 유지하되, 커밋 배열만 비워두어 "커밋 내역 없음"이 표시되도록 설정
        // 추후 실제 커밋 데이터(예: ['1', '2', '3'])가 들어오면 자동으로 번호와 함께 렌더링됩니다.
        const sampleProjects = [
            {
                id:1,
                location: "DB",
                name: 'FastAPI',
                commits: [['','']]
            },
            {
                id:2,
                location: "DB",
                name: 'Flask',
                commits: [['','']] 
            }
        ];

        console.log(message.command);
        const workspace:any = this.workspaceService.getWorkspace();
        const response = {name: workspace.name, path: workspace.path};
        await this.gitService.initialize();
        console.log("GitService initialized. Repository exists:", this.gitService.exists());
        if (this.gitService.exists()) {
            const gitCommits = (await this.gitService.getRecentCommits()).map(m=>
                [m.hash, m.message]);
            sampleProjects.push({
                id:0, 
                location: "Local",
                name: response.name, 
                commits: gitCommits,
            });
            console.log(sampleProjects);
        }

        this.view.webview.postMessage({
            command: 'showProjectList',
            data: sampleProjects
        });

    }

}