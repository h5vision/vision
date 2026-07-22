import * as vscode from "vscode";

import { SidebarMessage } from "../../types/sidebarMessage";
// import { databaseService } from "../../services/historyService";

export class HistoryHandler {

    constructor(
        private readonly view: vscode.WebviewView
    ) {}

    public async handle(message: SidebarMessage) {

        console.log(message.command);

    }

}