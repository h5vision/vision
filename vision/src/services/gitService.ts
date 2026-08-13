import * as vscode from "vscode";
import { waitUntil } from "../utils/wait";
import {GitAPI, GitChangedFile, GitCommit, GitExtension, GitRepositoryInfo, Repository} from "../types/git";

export class GitService implements vscode.Disposable {
    
    private readonly _onDidRepositoryReady =
        new vscode.EventEmitter<void>();

    public readonly onDidRepositoryReady =
        this._onDidRepositoryReady.event;

    private readonly _onDidCommit =
        new vscode.EventEmitter<{ commit: string; previousCommit: string }>();

    public readonly onDidCommit =
        this._onDidCommit.event;

    private git?: GitAPI;
    private repository?: Repository;
    private initializePromise?: Promise<void>;
    private lastCommit?: string;
    private stateChangeListener?: vscode.Disposable;

    constructor() {}

    public dispose() {
        this._onDidRepositoryReady.dispose();
        this._onDidCommit.dispose();
        this.stateChangeListener?.dispose();
    }

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
            vscode.window.showErrorMessage("Git extension is not available or not active.");
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
        
        const head = await waitUntil(
            () => this.git?.repositories[0]?.state.HEAD,
        );

        if (!this.repository || !head) {
            return;
        }

        this.lastCommit = head.commit;

        this.stateChangeListener = this.repository.state.onDidChange(
            () => this.checkForNewCommit()
        );

        this._onDidRepositoryReady.fire();
        
    }

    // HEAD의 commit hash 변경을 감지하여 새 커밋 발생 여부를 판단합니다.
    private checkForNewCommit(): void {

        const currentCommit = this.repository?.state.HEAD?.commit;
        const previousCommit = this.lastCommit;

        if (!currentCommit || currentCommit === previousCommit) {
            return;
        }

        this.lastCommit = currentCommit;

        if (previousCommit) {
            this._onDidCommit.fire({ commit: currentCommit, previousCommit });
        }
    }

    //---------------------------------------
    // Repository
    //---------------------------------------

    public exists(): boolean {
        return this.repository !== undefined;
    }

    public async getRepositoryInfo(): Promise<GitRepositoryInfo | undefined> {

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

    public async getCommitDiff(
        commit: string,
        parentCommit?: string
    ): Promise<string> {

        if (!this.repository) {
            return "";
        }

        const parent = parentCommit ?? `${commit}^`;

        const changes = await this.repository.diffBetween(parent, commit);

        const diffs = await Promise.all(
            changes.map(change =>
                this.repository!.diffBetween(parent, commit, change.uri.fsPath)
            )
        );
        console.log("Commit diff generated:", diffs.join("\n"));

        return diffs.join("\n");
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