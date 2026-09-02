import * as vscode from "vscode";
import { SidebarMessage } from "../../types/sidebarMessage";
import { BriefPromptBuilder } from "../../utils/promptBuilder";
import { APIService } from "../../services/APIService";
import { WorkspaceService } from "../../services/workspaceService";

export class ProjectBriefHandler {

    private readonly APIService = new APIService();
    private readonly workspaceService = new WorkspaceService();

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
        let projectId = vscode.workspace.getConfiguration("vision").get<string>("projectId") || vscode.workspace.name;
        if (message.data === "locale") {
            projectId = vscode.workspace.name;
        }
        const briefName = message.data === "locale" ? "brief.md" : `brief-${projectId}.md`;

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
                throw new Error("브리핑 응답에 Markdown 내용이 없습니다.");
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
}

interface briefing {
    ok: boolean;
    project_id: string;
    indexed_id: string;
    briefing: string;
}