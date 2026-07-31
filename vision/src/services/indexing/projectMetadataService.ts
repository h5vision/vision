import * as vscode from "vscode";

import { ProjectMetadata } from "../../types";

import { WorkspaceService } from "../workspaceService";
import { ConfigFileService } from "./configFileService";
import { GitService } from "../gitService";
import { LanguageService } from "./languageService";
import { DirectoryTreeService } from "./directoryTreeService";

export class ProjectMetadataService {

    private readonly workspaceService = new WorkspaceService();
    private readonly configService = new ConfigFileService();
    private readonly gitService = new GitService();
    private readonly languageService = new LanguageService();
    private readonly directoryTreeService = new DirectoryTreeService();

    public async getMetadata(): Promise<ProjectMetadata | null> {

        const workspace = this.workspaceService.getWorkspace();

        if (!workspace) {return null;}

        return {

            workspace,

            vscodeVersion: vscode.version,

            isMultiRoot: this.workspaceService.isMultiRoot(),

            configFiles: this.configService.getConfigFiles(workspace.path),

            git: {enabled: this.gitService.exists()},

            language: this.languageService.getLanguage(workspace.path), 

            dirTree: await this.directoryTreeService.getDirectoryTree(workspace.path)

        };
    }

}