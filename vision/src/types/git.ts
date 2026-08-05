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

export interface GitExtension {
    enabled: boolean;
    getAPI(version: 1): GitAPI;
}

export interface GitAPI {
    repositories: Repository[];
}

export interface Repository {

    rootUri: vscode.Uri;
    state: RepositoryState;

    log(options?: {
        maxEntries?: number;
        path?: string;
    }): Promise<GitCommit[]>;

    diffWithHEAD(path?: string): Promise<string>;
}

export interface RepositoryState {

    HEAD?: Branch;

    workingTreeChanges: readonly Change[];
    indexChanges: readonly Change[];
    mergeChanges: readonly Change[];
}

export interface Change {
    uri: vscode.Uri;
    status: number;
}

export interface Branch {
    name?: string;
    commit?: string;
    ahead?: number;
    behind?: number;
}
