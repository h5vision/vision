import * as vscode from "vscode";

import { SidebarMessage } from "../../types/sidebarMessage";

export class HistoryHandler {

    constructor(

        private readonly view: vscode.WebviewView

    ) {}

    public async handle(message: SidebarMessage) {

        console.log("History Handler");

    }

}