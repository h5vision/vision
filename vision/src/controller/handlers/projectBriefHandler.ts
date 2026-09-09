import * as vscode from "vscode";
import { SidebarMessage } from "../../types/sidebarMessage";
import { BriefPromptBuilder } from "../../utils/promptBuilder";
import { APIService } from "../../services/APIService";
import { WorkspaceService } from "../../services/workspaceService";
import { GitService } from "../../services/gitService";

export class ProjectBriefHandler {

    private readonly APIService = new APIService();
    private readonly workspaceService = new WorkspaceService();

    constructor(
        private readonly gitService: GitService = new GitService()
    ) {}
    public async CopilotGenBrief(message: SidebarMessage) {
        console.log(message.command);
        const query = BriefPromptBuilder.build();
        await vscode.commands.executeCommand("workbench.action.chat.open", {
            path: "",
            query,
            isPartialQuery: false
        });
        vscode.window.showInformationMessage(
            "프로젝트 브리핑 요청을 Copilot 채팅으로 전송했습니다."
        );
    }

    public async handle(message: SidebarMessage) {
        console.log(message.command);
        this.gitService.initialize();
        const workspace = this.workspaceService.getWorkspace();
        if (!workspace) {
            vscode.window.showErrorMessage("열려 있는 워크스페이스가 없습니다.");
            return;
        }
        const projectId = vscode.workspace.getConfiguration("vision").get<string>("projectId");
        const branch = vscode.workspace.getConfiguration("vision").get<string>("branch", 'None');
        const commitId = vscode.workspace.getConfiguration("vision").get<string>("commitId", 'None');
        const briefName = `Vision_brief-${commitId.slice(0,7)}.md`;

        if ((await vscode.workspace.fs.readDirectory(vscode.Uri.file(workspace.path))).some(([name]) => name === briefName)) {
            const briefUri = vscode.Uri.joinPath(vscode.Uri.file(workspace.path), briefName);
            await vscode.commands.executeCommand("markdown.showPreview", briefUri);
            return;
        }

        try {
            const response:any = await this.APIService.get(
                `/briefing?project_id=${projectId}@${branch}`
            );
            if (!response.ok) {
                const reason = response.reason;
                switch (reason) {
                    case "not_generated":
                        throw new Error("브리핑이 생성되지 않았습니다.");
                    case "model_not_loaded":
                        throw new Error("AWS ollama 모델이 로드되지 않았습니다.");
                    case "no_material":
                        throw new Error("브리핑에 필요한 자료가 없습니다.");
                }
            }
            const brief = response.briefing;
            const outputUri = vscode.Uri.joinPath(
                vscode.Uri.file(workspace.path),
                briefName
            );
            await vscode.workspace.fs.writeFile(
                outputUri,
                Buffer.from(brief, "utf8")
            );
            await vscode.commands.executeCommand("markdown.showPreview", outputUri);
        } catch (error) {
            const detail = error instanceof Error ? error.message : String(error);
            vscode.window.showErrorMessage(`프로젝트 브리핑 저장에 실패했습니다: ${detail}`);
        }
    }

    public async isBriefReady(): Promise<Boolean | undefined> {
        const projectId = vscode.workspace.getConfiguration("vision").get<string>("projectId", "");
        const branch = vscode.workspace.getConfiguration("vision").get<string>("branch", 'None');
        try {
            const response:any = await this.APIService.get(
                `/index/status?project_id=${projectId}@${branch}`
            );
            switch (response.briefing) {
                case 'failed':
                    const error = response.briefing_error;
                    vscode.window.showInformationMessage(`브리핑이 생성되지 않았습니다: ${error}`);
                    const response2:any = await this.APIService.get(
                        `/briefing?project_id=${projectId}@${branch}`
                    );
                    if (response2.ok) {
                        vscode.window.showInformationMessage('이전 브리핑이 존재합니다.');
                        return true;
                    }
                    return false;
                case 'ready':
                    return true;
                default:
                    return undefined;
            }
        } catch (error) {
            return undefined;
        }
    }
}