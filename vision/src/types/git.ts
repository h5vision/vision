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
    remote: string;
}

export interface GitChangedFile {
    path: string;
    uri: vscode.Uri;
    status: number;
}

export interface GitCommitFile {
    status: "added" | "modified";
    path: string;
    content: string;
    encoding: "utf-8";
}

export interface GitCommitRename {
    old_path: string;
    new_path: string;
}

export interface GitCommitPayload {
    project_id: string;
    base_revision: string;
    target_revision: string;
    files: GitCommitFile[];
    deleted_paths: string[];
    renames: GitCommitRename[];
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

    diffBetween(ref1: string, ref2: string): Promise<Change[]>;
    diffBetween(ref1: string, ref2: string, path: string): Promise<string>;

    getConfig(key: string): Promise<string>;
    buffer(ref: string, path: string): Promise<Uint8Array>;
}

export interface RepositoryState {

    HEAD?: Branch;
    remotes: readonly Remote[];

    workingTreeChanges: readonly Change[];
    indexChanges: readonly Change[];
    mergeChanges: readonly Change[];

    onDidChange: vscode.Event<void>;
}

export interface Remote {
    fetchUrl?: string;
    pushUrl?: string;
}

export interface Change {
    uri: vscode.Uri;
    originalUri: vscode.Uri;
    renameUri?: vscode.Uri;
    status: number;
}

export interface Branch {
    name?: string;
    commit?: string;
    ahead?: number;
    behind?: number;
}
