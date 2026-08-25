import * as vscode from "vscode";
import { SidebarMessage } from "../../types/sidebarMessage";
import { RAGTESTPromptBuilder } from "../../chat/promptBuilder";
import { APIService } from "../../services/APIService";
import { GitService } from "../../services/gitService";

export class RAGTESTHandler {

    constructor(
        private readonly view: vscode.WebviewView
    ) {}

    public async handle(message: SidebarMessage) {
        console.log(message.command);
        const i = Number(message.data);
        const query = RAGTESTPromptBuilder.build(i);
        await vscode.commands.executeCommand("workbench.action.chat.open", {
            path: "",
            query,
            isPartialQuery: false
        });
    

        vscode.window.showInformationMessage(
            "RAG_TEST 생성 요청을 Copilot 채팅으로 전송했습니다."
        );
    }

    public async removeRAGTEST(message: SidebarMessage) {
        console.log(message.command);
        const apiService = new APIService();
        const gitService = new GitService();
        await gitService.initialize();
        const currentCommit = gitService.getCurrentCommit();
        const payload = {
            "project_id": vscode.workspace.name || 'none',
            "base_revision": currentCommit,
            "target_revision": vscode.workspace.getConfiguration("vision").get<string>("commitId", currentCommit),
            "files": [],
            "deleted_paths": ["RAG_TEST.md", "RAG_TEST.json"],
            "renames": []
        };
        console.log("removeRAGTEST payload:", payload);
        const response:any = await apiService.post("/index/update/files", payload);
        if (response && response.ok) {
            vscode.window.showInformationMessage(
                "RAG_TEST 제거 요청을 백엔드로 전송했습니다."
            );
        } else if (response.ok === false) {
            vscode.window.showErrorMessage(
                "RAG_TEST 제거에 실패했습니다. 백엔드 서버에서 오류가 발생했습니다."
            );
        }
        const response2:any = await apiService.get(`/index/status?project_id=${vscode.workspace.name || 'none'}`);
        console.log(response2);
    }

}