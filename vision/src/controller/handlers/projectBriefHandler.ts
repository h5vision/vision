import * as vscode from "vscode";
import { SidebarMessage } from "../../types/sidebarMessage";
import { BriefPromptBuilder } from "../../chat/promptBuilder";
import { APIService } from "../../services/APIService";
import { WorkspaceService } from "../../services/workspaceService";

export class ProjectBriefHandler {

    private readonly APIService = new APIService();
    private readonly workspaceService = new WorkspaceService();

    public async handle(message: SidebarMessage) {
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

    public async GetBrief(message: SidebarMessage) {
        console.log(message.command);
        const workspace = this.workspaceService.getWorkspace();
        if (!workspace) {
            vscode.window.showErrorMessage("열려 있는 워크스페이스가 없습니다.");
            return;
        }


        if ((await vscode.workspace.fs.readDirectory(vscode.Uri.file(workspace.path))).some(([name]) => name === 'brief.md')) {
            vscode.window.showInformationMessage("프로젝트 브리핑 파일이 이미 존재합니다. brief.md 파일을 엽니다.");
            await vscode.window.showTextDocument(
                vscode.Uri.joinPath(vscode.Uri.file(workspace.path), "brief.md"), 
                { preview: true }
            );
            return;
        }

        try {
            const response = await this.APIService.get(
                `/briefing?project_id=${encodeURIComponent(workspace.name)}`
            );
            const brief = (response as { briefing?: unknown }).briefing;

            if (typeof brief !== "string") {
                throw new Error("브리핑 응답에 Markdown 내용이 없습니다.");
            }

            const outputUri = vscode.Uri.joinPath(
                vscode.Uri.file(workspace.path),
                "brief.md"
            );
            await vscode.workspace.fs.writeFile(
                outputUri,
                Buffer.from(brief, "utf8")
            );

            const document = await vscode.workspace.openTextDocument(outputUri);
            await vscode.window.showTextDocument(document, { preview: true });
        } catch (error) {
            const detail = error instanceof Error ? error.message : String(error);
            vscode.window.showErrorMessage(`프로젝트 브리핑 저장에 실패했습니다: ${detail}`);
        }
    }
}