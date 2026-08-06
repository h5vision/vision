import * as vscode from "vscode";

import { SidebarMessage, SidebarCommand } from "../types/sidebarMessage";

import { APIHandler } from "./handlers/checkHealthHandler";
import { HistoryHandler } from "./handlers/historyHandler";
import { IndexingHandler } from "./handlers/indexingHandler";
import { ProjectInfoHandler } from "./handlers/projectInfoHandler";
import { ProjectListHandler } from "./handlers/projectListHandler";
import { ProjectBriefHandler } from "./handlers/projectBriefHandler";
import { RAGTESTHandler } from "./handlers/RAGTESTHandler";

export class SidebarController {

    private readonly APIHandler: APIHandler;
    private readonly historyHandler: HistoryHandler;
    private readonly indexingHandler: IndexingHandler;
    private readonly projectInfoHandler: ProjectInfoHandler;
    private readonly projectListHandler: ProjectListHandler;
    private readonly projectBriefHandler: ProjectBriefHandler;
    private readonly ragtestHandler: RAGTESTHandler;

    constructor(
        private readonly view: vscode.WebviewView
    ) {
        this.APIHandler = new APIHandler(view);
        this.historyHandler = new HistoryHandler(view);
        this.indexingHandler = new IndexingHandler(view);
        this.projectInfoHandler = new ProjectInfoHandler(view);
        this.projectListHandler = new ProjectListHandler(view);
        this.projectBriefHandler = new ProjectBriefHandler(view);
        this.ragtestHandler = new RAGTESTHandler(view);
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

            case SidebarCommand.GetProjectGitInfo:
                return this.projectInfoHandler.handleGitInfo(message);

            case SidebarCommand.GetProjectList: 
                return this.projectListHandler.handle(message);

            case SidebarCommand.GenerateProjectBrief:
                return this.projectBriefHandler.handle(message);

            case SidebarCommand.GenerateRAGTEST:
                return this.ragtestHandler.handle(message);

            case SidebarCommand.UpdateEndpoint:
                await vscode.workspace.getConfiguration('vision')
                    .update(
                        "endpoint",
                        message.data,
                        vscode.ConfigurationTarget.Workspace
                    );
                vscode.window.showInformationMessage(
                    "Endpoint가 변경되었습니다."
                );
                return this.APIHandler.handle(message);

            
            case SidebarCommand.GetGuideStatus:
                const guideStatus = vscode.workspace.getConfiguration('vision').get('showGuideBook', false);
                this.view.webview.postMessage({
                    command: "guideStatus",
                    data: guideStatus
                });
                return;
            
            case SidebarCommand.ToggleGuide:
                vscode.commands.executeCommand('vision.toggleGuide');
                return;
        }
    }
}