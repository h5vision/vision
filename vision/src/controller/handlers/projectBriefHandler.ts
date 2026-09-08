import * as vscode from "vscode";
import { SidebarMessage } from "../../types/sidebarMessage";
import { BriefPromptBuilder } from "../../utils/promptBuilder";
import { APIService } from "../../services/APIService";
import { WorkspaceService } from "../../services/workspaceService";
import { GitService } from "../../services/gitService";

export class ProjectBriefHandler {

    private readonly APIService = new APIService();
    private readonly workspaceService = new WorkspaceService();
    private readonly gitService = new GitService();

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
        const workspace = this.workspaceService.getWorkspace();
        if (!workspace) {
            vscode.window.showErrorMessage("열려 있는 워크스페이스가 없습니다.");
            return;
        }
        let projectId = vscode.workspace.getConfiguration("vision").get<string>("projectId");
        const briefName = message.data === "locale" ? `brief.md` : `brief-${projectId}.md`;
        

        if ((await vscode.workspace.fs.readDirectory(vscode.Uri.file(workspace.path))).some(([name]) => name === briefName)) {
            const briefUri = vscode.Uri.joinPath(vscode.Uri.file(workspace.path), briefName);
            await vscode.commands.executeCommand("markdown.showPreview", briefUri);
            return;
        }

        try {
            
            const response = await this.APIService.get(
                `/briefing?project_id=${projectId}`
            );
            const brief = (response as briefing).briefing;

            if (!(response as briefing).ok) {
                const reason = (response as briefing).reason;
                switch (reason) {
                    case "not_generated":
                        throw new Error("브리핑이 생성되지 않았습니다.");
                    case "model_not_loaded":
                        throw new Error("AWS ollama 모델이 로드되지 않았습니다.");
                    case "no_material":
                        throw new Error("브리핑에 필요한 자료가 없습니다.");
                    default:
                        throw new Error("브리핑이 존재하지 않습니다.");
                }
            }
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
        const projectName = vscode.workspace.getConfiguration("vision").get<string>("projectId");
        try {
            const response:any = await this.APIService.get(
                `/briefing?project_id=${projectName}`
            );
            return response.ok && response.briefing !== "";
        } catch (error) {
            throw new Error("브리핑 확인 중 오류가 발생했습니다.");
        }
    }
}

interface briefing {
    ok: boolean;
    project_id: string;
    indexed_id: string;
    briefing: string;
    reason?: string;
}