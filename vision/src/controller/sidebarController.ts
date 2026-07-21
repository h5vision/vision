import * as vscode from "vscode";

import { SidebarMessage, SidebarCommand } from "../types/sidebarMessage";

import { APIHandler } from "./handlers/APIhandler";
import { HistoryHandler } from "./handlers/historyHandler";
import { IndexingHandler } from "./handlers/indexingHandler";

export class SidebarController {

    private readonly APIHandler: APIHandler;
    private readonly historyHandler: HistoryHandler;
    private readonly indexingHandler: IndexingHandler;

    constructor(
        private readonly view: vscode.WebviewView
    ) {
        this.APIHandler = new APIHandler(view);
        this.historyHandler = new HistoryHandler(view);
        this.indexingHandler = new IndexingHandler(view);
    }

    public async handle(message: SidebarMessage) {

        switch (message.command) {

            case SidebarCommand.CheckBackend:
                return this.APIHandler.handle(message);

            case SidebarCommand.InitialProjectIndexing:
                return this.indexingHandler.handle(message);

            case SidebarCommand.LoadHistory:
                return this.historyHandler.handle(message);
        }
    }
}