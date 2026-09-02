import * as vscode from "vscode";

import { SidebarMessage, SidebarCommand } from "../types/sidebarMessage";

import { APIHandler } from "./handlers/checkHealthHandler";
import { ModelInfoHandler } from "./handlers/modelInfoHandler";
import { ProjectInfoHandler } from "./handlers/projectInfoHandler";
import { ProjectListHandler } from "./handlers/projectListHandler";
import { ProjectBriefHandler } from "./handlers/projectBriefHandler";
import { GitService } from "../services/gitService";

export class SidebarController {

    private readonly APIHandler: APIHandler;
    private readonly modelInfoHandler: ModelInfoHandler;
    private readonly projectInfoHandler: ProjectInfoHandler;
    private readonly projectListHandler: ProjectListHandler;
    private readonly projectBriefHandler: ProjectBriefHandler;
    private readonly gitService = new GitService();

    constructor(
        private readonly view: vscode.WebviewView
    ) {
        this.APIHandler = new APIHandler(view);
        this.modelInfoHandler = new ModelInfoHandler(view);
        this.projectInfoHandler = new ProjectInfoHandler(view, this.gitService);
        this.projectListHandler = new ProjectListHandler(view, this.gitService);
        this.projectBriefHandler = new ProjectBriefHandler();
    }

    public async handle(message: SidebarMessage) {

        switch (message.command) {

            case SidebarCommand.CheckBackend:
                return this.APIHandler.handle(message);

            case SidebarCommand.GetModelsInfo:
                return this.modelInfoHandler.handle(message);

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
            
            case SidebarCommand.SetStreaming:
                await vscode.workspace.getConfiguration('vision')
                    .update(
                        "streaming",
                        message.data,
                        vscode.ConfigurationTarget.Global
                    );
                vscode.window.showInformationMessage(
                    `Streaming 설정이 ${message.data ? "활성화" : "비활성화"}되었습니다.`
                );
                return;
            
            case SidebarCommand.GetStreamingStatus:
                const streamingStatus = vscode.workspace.getConfiguration('vision')
                    .get('streaming', false);
                this.view.webview.postMessage({
                    command: "streamingStatus",
                    data: streamingStatus
                });
                return;
            
            case SidebarCommand.GetGuideStatus:
                const guideStatus = vscode.workspace.getConfiguration('vision').get('showGuideBook', false);
                this.view.webview.postMessage({
                    command: "guideStatus",
                    data: guideStatus
                });
                return;
            

            case SidebarCommand.OpenDBExternal:
                await vscode.commands.executeCommand('vision.openDBExternal');
                return;

            case SidebarCommand.ToggleGuide:
                vscode.commands.executeCommand('vision.toggleGuide');
                return;
            
            case SidebarCommand.ShowDependencyGraph:
                vscode.commands.executeCommand('vision.showDependencyGraph');
                return;
            
            case SidebarCommand.InitializeDependencyGraph:
                vscode.commands.executeCommand('vision.initializeDependencyGraph');
                return;
        }
    }
}
