import * as vscode from "vscode";
import { WorkspaceMetadata } from "../types";

export class WorkspaceService {

    public getWorkspace(): WorkspaceMetadata | null {

        const folders = vscode.workspace.workspaceFolders;

        if (!folders || folders.length === 0) {return null;}

        return {
            name: folders[0].name,
            path: folders[0].uri.fsPath
        };
    }

    public isMultiRoot(): boolean {

        const folders = vscode.workspace.workspaceFolders;

        return !!folders && folders.length > 1;
    }
}