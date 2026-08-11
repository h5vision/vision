import * as vscode from "vscode";

import { SidebarMessage } from "../../types/sidebarMessage";

export class HistoryHandler {

    constructor(
        private readonly view: vscode.WebviewView
    ) {}

    public async handle(message: SidebarMessage) {
        console.log(message.command);
        vscode.window.showInformationMessage(
            "DB 열기 요청을 수신했습니다. 외부에서 DB를 열도록 시도합니다."
        );
        await vscode.commands.executeCommand('vision.openDBExternal');
    }

}