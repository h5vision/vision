import * as vscode from "vscode";
import { SidebarMessage } from "../../types/sidebarMessage";
import { BriefPromptBuilder } from "../../chat/promptBuilder";

export class ProjectBriefHandler {

    constructor(
        private readonly view: vscode.WebviewView

    ) {}

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

}