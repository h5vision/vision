import * as vscode from "vscode";
import { waitUntil } from "../utils/wait";
import {
    GitRepositoryInfo,
    GitChangedFile,
    GitCommit
} from "../types/git";

interface GitExtension {
    enabled: boolean;
    getAPI(version: 1): GitAPI;
}

interface GitAPI {
    repositories: Repository[];
}

interface Repository {

    rootUri: vscode.Uri;
    state: RepositoryState;

    log(options?: {
        maxEntries?: number;
        path?: string;
    }): Promise<GitCommit[]>;

    diffWithHEAD(path?: string): Promise<string>;
}

interface RepositoryState {

    HEAD?: Branch;

    workingTreeChanges: readonly Change[];
    indexChanges: readonly Change[];
    mergeChanges: readonly Change[];
}

interface Change {
    uri: vscode.Uri;
    status: number;
}

interface Branch {
    name?: string;
    commit?: string;
    ahead?: number;
    behind?: number;
}

export class GitService implements vscode.Disposable {
    
    private readonly _onDidRepositoryReady =
        new vscode.EventEmitter<void>();

    public readonly onDidRepositoryReady =
        this._onDidRepositoryReady.event;

    private git?: GitAPI;
    private repository?: Repository;
    private initializePromise?: Promise<void>;

    constructor() {}

    public dispose() { this._onDidRepositoryReady.dispose(); }

    public initialize(): Promise<void> {

        if (!this.initializePromise) {
            this.initializePromise = this.doInitialize();
        }

        return this.initializePromise;
    }

    private async doInitialize(): Promise<void> {

        const extension = await waitUntil(() => {

            const ext = vscode.extensions.getExtension<GitExtension>("vscode.git");

            if (!ext?.isActive) {
                return undefined;
            }

            if (!ext.exports.enabled) {
                return undefined;
            }

            return ext;
        });

        if (!extension) {
            console.log("Git extension is not available or not active.");
            return;
        }

        this.git = extension.exports.getAPI(1);

        await this.waitRepositoryReady();
    }

    private async waitRepositoryReady(): Promise<void> {
        if (!this.git) { return; }

        this.repository = await waitUntil(
            () => this.git?.repositories[0]
        );

        if (!this.repository) {
            return;
        }

        this._onDidRepositoryReady.fire();
        
    }

    //---------------------------------------
    // Repository
    //---------------------------------------

    public exists(): boolean {
        return this.repository !== undefined;
    }

    public getRepositoryInfo(): GitRepositoryInfo | undefined {

        const repo = this.repository;

        if (!repo) {
            return undefined;
        }

        const head = repo.state.HEAD;

        return {

            rootPath: repo.rootUri.fsPath,

            branch: head?.name ?? "",

            commit: head?.commit ?? "",

            ahead: head?.ahead ?? 0,

            behind: head?.behind ?? 0,

            workingTreeCount: repo.state.workingTreeChanges.length,

            stagedCount: repo.state.indexChanges.length,

            mergeCount: repo.state.mergeChanges.length
        };
    }

    //---------------------------------------
    // Branch
    //---------------------------------------

    public getCurrentBranch(): string {

        return this.repository?.state.HEAD?.name ?? "";
    }

    //---------------------------------------
    // Commit
    //---------------------------------------

    public getCurrentCommit(): string {

        return this.repository?.state.HEAD?.commit ?? "";
    }

    public async getRecentCommits(
        limit: number = 20
    ): Promise<GitCommit[]> {

        if (!this.repository) {
            return [];
        }

        return this.repository.log({
            maxEntries: limit
        });
    }

    //---------------------------------------
    // Changed Files
    //---------------------------------------

    public getWorkingTreeFiles(): GitChangedFile[] {

        if (!this.repository) {
            return [];
        }

        return this.repository.state.workingTreeChanges.map(change => ({

            path: change.uri.fsPath,

            uri: change.uri,

            status: change.status
        }));
    }

    public getStagedFiles(): GitChangedFile[] {

        if (!this.repository) {
            return [];
        }

        return this.repository.state.indexChanges.map(change => ({

            path: change.uri.fsPath,

            uri: change.uri,

            status: change.status
        }));
    }

    public getMergedFiles(): GitChangedFile[] {

        if (!this.repository) {
            return [];
        }

        return this.repository.state.mergeChanges.map(change => ({

            path: change.uri.fsPath,

            uri: change.uri,

            status: change.status
        }));
    }

    //---------------------------------------
    // Diff
    //---------------------------------------

    public async getDiff(path?: string): Promise<string> {

        if (!this.repository) {
            return "";
        }

        return this.repository.diffWithHEAD(path);
    }

    //---------------------------------------
    // Helper
    //---------------------------------------

    public hasChanges(): boolean {

        const repo = this.repository;

        if (!repo) {
            return false;
        }

        return (
            repo.state.workingTreeChanges.length > 0 ||
            repo.state.indexChanges.length > 0 ||
            repo.state.mergeChanges.length > 0
        );
    }
}