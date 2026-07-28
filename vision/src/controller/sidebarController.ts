import * as vscode from "vscode";

import { SidebarMessage, SidebarCommand } from "../types/sidebarMessage";

import { APIHandler } from "./handlers/APIHandler";
import { HistoryHandler } from "./handlers/historyHandler";
import { IndexingHandler } from "./handlers/indexingHandler";
import { ProjectInfoHandler } from "./handlers/projectInfoHandler";

export class SidebarController {

    private readonly APIHandler: APIHandler;
    private readonly historyHandler: HistoryHandler;
    private readonly indexingHandler: IndexingHandler;
    private readonly projectInfoHandler: ProjectInfoHandler;

    constructor(
        private readonly view: vscode.WebviewView
    ) {
        this.APIHandler = new APIHandler(view);
        this.historyHandler = new HistoryHandler(view);
        this.indexingHandler = new IndexingHandler(view);
        this.projectInfoHandler = new ProjectInfoHandler(view);
    }

    public async handle(message: SidebarMessage) {

        switch (message.command) {

            case SidebarCommand.CheckBackend:
                return this.APIHandler.handle(message);

            case SidebarCommand.InitialProjectIndexing:
                return this.indexingHandler.handle(message);

            case SidebarCommand.LoadHistory:
                return this.historyHandler.handle(message);

            case SidebarCommand.GetProjectInfo:
                return this.projectInfoHandler.handle(message);

            case SidebarCommand.UpdateEndpoint:
                await vscode.workspace.getConfiguration()
                    .update(
                        "vision.endpoint",
                        message.data,
                        vscode.ConfigurationTarget.Workspace
                    );

                vscode.window.showInformationMessage(
                    "Endpoint가 변경되었습니다."
                );
                return this.APIHandler.handle(message);

        }
    }
}