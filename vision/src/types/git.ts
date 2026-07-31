import * as vscode from "vscode";

export interface GitRepositoryInfo {
    rootPath: string;
    branch: string;
    commit: string;
    ahead: number;
    behind: number;
    workingTreeCount: number;
    stagedCount: number;
    mergeCount: number;
}

export interface GitChangedFile {
    path: string;
    uri: vscode.Uri;
    status: number;
}

export interface GitCommit {

    hash: string;
    message: string;
    authorName: string;
    authorEmail?: string;
    authorDate: Date;
}