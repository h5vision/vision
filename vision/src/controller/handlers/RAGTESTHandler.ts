import * as vscode from "vscode";
import { SidebarMessage } from "../../types/sidebarMessage";
import { RAGTESTPromptBuilder } from "../../chat/promptBuilder";
import { waitUntil } from "../../utils/wait";

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

}