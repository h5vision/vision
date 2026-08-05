import * as vscode from "vscode";

import { SidebarMessage } from "../../types/sidebarMessage";

export class ProjectListHandler {

    constructor(
        private readonly view: vscode.WebviewView
    ) {}

    public async handle(message: SidebarMessage) {

        console.log(message.command);
        
        // 💡 프로젝트 이름과 아코디언은 유지하되, 커밋 배열만 비워두어 "커밋 내역 없음"이 표시되도록 설정
        // 추후 실제 커밋 데이터(예: ['1', '2', '3'])가 들어오면 자동으로 번호와 함께 렌더링됩니다.
        const sampleProjects = [
            {
                id: 'fastapi',
                name: 'FastAPI',
                commits: [] 
            },
            {
                id: 'flask',
                name: 'Flask',
                commits: [] 
            }
        ];

        this.view.webview.postMessage({
            command: 'showProjectList',
            data: sampleProjects
        });

    }

}