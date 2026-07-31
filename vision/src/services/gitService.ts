import * as vscode from "vscode";
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

export class GitService {
    
    private readonly _onDidRepositoryReady =
        new vscode.EventEmitter<void>();

    public readonly onDidRepositoryReady =
        this._onDidRepositoryReady.event;

    private git?: GitAPI;
    private repository?: Repository;


    constructor() {}

    public initialize():void {
        this.initializeAsync();
    }

    private async initializeAsync(): Promise<void> {

        const extension =
            vscode.extensions.getExtension<GitExtension>("vscode.git");
        

        if (!extension || !extension.isActive) {
            this.git = undefined;
            return;
        }

        this.git = extension.exports.getAPI(1);
        await this.waitRepositoryReady();
    }

    private async waitRepositoryReady(): Promise<void> {

        if (!this.git) {return;}

        // 최대 5초 대기
        for (let i = 0; i < 50; i++) {

            if (this.git.repositories.length > 0) {

                this.repository = this.git.repositories[0];

                this._onDidRepositoryReady.fire();

                return;
            }

            await new Promise(resolve => setTimeout(resolve, 100));
        }
    }

    /**
     * Workspace의 첫 번째 Repository
     */
    private get repo(): Repository | undefined {
        return this.repository;
    }

    //---------------------------------------
    // Repository
    //---------------------------------------

    public exists(): boolean {
        console.log(this.getRepositoryInfo());
        return this.repo !== undefined;
    }

    public getRepositoryInfo(): GitRepositoryInfo | undefined {

        const repo = this.repo;

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

        return this.repo?.state.HEAD?.name ?? "";
    }

    //---------------------------------------
    // Commit
    //---------------------------------------

    public getCurrentCommit(): string {

        return this.repo?.state.HEAD?.commit ?? "";
    }

    public async getRecentCommits(
        limit: number = 20
    ): Promise<GitCommit[]> {

        if (!this.repo) {
            return [];
        }

        return this.repo.log({
            maxEntries: limit
        });
    }

    //---------------------------------------
    // Changed Files
    //---------------------------------------

    public getWorkingTreeFiles(): GitChangedFile[] {

        if (!this.repo) {
            return [];
        }

        return this.repo.state.workingTreeChanges.map(change => ({

            path: change.uri.fsPath,

            uri: change.uri,

            status: change.status
        }));
    }

    public getStagedFiles(): GitChangedFile[] {

        if (!this.repo) {
            return [];
        }

        return this.repo.state.indexChanges.map(change => ({

            path: change.uri.fsPath,

            uri: change.uri,

            status: change.status
        }));
    }

    public getMergedFiles(): GitChangedFile[] {

        if (!this.repo) {
            return [];
        }

        return this.repo.state.mergeChanges.map(change => ({

            path: change.uri.fsPath,

            uri: change.uri,

            status: change.status
        }));
    }

    //---------------------------------------
    // Diff
    //---------------------------------------

    public async getDiff(path?: string): Promise<string> {

        if (!this.repo) {
            return "";
        }

        return this.repo.diffWithHEAD(path);
    }

    //---------------------------------------
    // Helper
    //---------------------------------------

    public hasChanges(): boolean {

        const repo = this.repo;

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