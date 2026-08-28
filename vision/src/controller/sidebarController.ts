import * as vscode from "vscode";

import { SidebarMessage, SidebarCommand } from "../types/sidebarMessage";

import { APIHandler } from "./handlers/checkHealthHandler";
import { HistoryHandler } from "./handlers/historyHandler";
import { IndexingHandler } from "./handlers/indexingHandler";
import { ModelInfoHandler } from "./handlers/modelInfoHandler";
import { ProjectInfoHandler } from "./handlers/projectInfoHandler";
import { ProjectListHandler } from "./handlers/projectListHandler";
import { ProjectBriefHandler } from "./handlers/projectBriefHandler";
import { RAGTESTHandler } from "./handlers/RAGTESTHandler";
import { GitService } from "../services/gitService";

export class SidebarController {

    private readonly APIHandler: APIHandler;
    private readonly historyHandler: HistoryHandler;
    private readonly indexingHandler: IndexingHandler;
    private readonly modelInfoHandler: ModelInfoHandler;
    private readonly projectInfoHandler: ProjectInfoHandler;
    private readonly projectListHandler: ProjectListHandler;
    private readonly projectBriefHandler: ProjectBriefHandler;
    private readonly ragtestHandler: RAGTESTHandler;
    private readonly gitService = new GitService();

    constructor(
        private readonly view: vscode.WebviewView
    ) {
        this.APIHandler = new APIHandler(view);
        this.historyHandler = new HistoryHandler(view);
        this.indexingHandler = new IndexingHandler(view);
        this.modelInfoHandler = new ModelInfoHandler(view);
        this.projectInfoHandler = new ProjectInfoHandler(view, this.gitService);
        this.projectListHandler = new ProjectListHandler(view, this.gitService);
        this.projectBriefHandler = new ProjectBriefHandler();
        this.ragtestHandler = new RAGTESTHandler(view);
    }

    public async handle(message: SidebarMessage) {

        switch (message.command) {

            case SidebarCommand.CheckBackend:
                return this.APIHandler.handle(message);

            case SidebarCommand.GetModelsInfo:
                return this.modelInfoHandler.handle(message);

            case SidebarCommand.InitialProjectIndexing:
                return this.indexingHandler.handle(message);

            case SidebarCommand.OpenDBExternal:
                return this.historyHandler.handle(message);

            case SidebarCommand.GetProjectInfo:
                return this.projectInfoHandler.handle(message);

            case SidebarCommand.GetProjectGitInfo:
                return this.projectInfoHandler.handleGitInfo(message);

            case SidebarCommand.GetProjectList: 
                return this.projectListHandler.handle(message);

            case SidebarCommand.GetProjectBrief:
                return this.projectBriefHandler.handle(message);

            case SidebarCommand.GenerateBriefByCopilot:
                return this.projectBriefHandler.CopilotGenBrief(message);

            case SidebarCommand.GenerateRAGTEST:
                return this.ragtestHandler.handle(message);

            case SidebarCommand.RemoveRAGTEST:
                return this.ragtestHandler.removeRAGTEST(message);


            case SidebarCommand.UpdateEndpoint:
                await vscode.workspace.getConfiguration('vision')
                    .update(
                        "endpoint",
                        message.data,
                        vscode.ConfigurationTarget.Global
                    );
                vscode.window.showInformationMessage(
                    "Endpoint가 변경되었습니다."
                );
                return this.APIHandler.handle(message);


            case SidebarCommand.UpdateModelId:
                await vscode.workspace.getConfiguration('vision')
                    .update(
                        "modelId",
                        message.data,
                        vscode.ConfigurationTarget.Global
                    );
                vscode.window.showInformationMessage(
                    "Model ID가 변경되었습니다."
                );
                this.view.webview.postMessage({
                    command: "modelIdUpdated",
                    data: message.data
                });
                return ;


            case SidebarCommand.UpdateCommitId:
                await vscode.workspace.getConfiguration('vision')
                    .update(
                        "projectId",
                        message.data.project_id,
                        vscode.ConfigurationTarget.Global
                    );
                await vscode.workspace.getConfiguration('vision')
                    .update(
                        "commitId",
                        message.data.commit,
                        vscode.ConfigurationTarget.Global
                    );
                this.view.webview.postMessage({
                    command: "commitIdUpdated",
                    data: message.data
                });
                return;
            
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
