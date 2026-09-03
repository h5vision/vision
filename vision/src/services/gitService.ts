import * as vscode from "vscode";
import * as path from "path";
import { waitUntil } from "../utils/wait";
import {GitAPI, GitChangedFile, GitCommit, GitCommitFile, GitCommitPayload, GitExtension, GitRepositoryInfo, Repository} from "../types/git";

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
        }, 30000, 1000);

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

            mergeCount: repo.state.mergeChanges.length,

            remote: this.getGitHubRemoteUrl(repo.state.remotes)
        };
    }

    //---------------------------------------
    // GitHub Remote URL
    //---------------------------------------

    private getGitHubRemoteUrl(remotes: readonly { fetchUrl?: string; pushUrl?: string }[]): string {
        for (const remote of remotes) {
            for (const remoteUrl of [remote.fetchUrl, remote.pushUrl]) {
                if (!remoteUrl) {
                    continue;
                }

                const githubUrl = this.toGitHubUrl(remoteUrl);

                if (githubUrl) {
                    return githubUrl;
                }
            }
        }

        return "";
    }

    private toGitHubUrl(remoteUrl: string): string | undefined {
        const normalizedUrl = remoteUrl.replace(/\.git$/, "");
        const sshMatch = normalizedUrl.match(/^(?:ssh:\/\/)?git@github\.com[:/]([^/]+\/.+)$/i);

        if (sshMatch) {
            return `https://github.com/${sshMatch[1]}`;
        }

        try {
            const url = new URL(normalizedUrl);

            return url.hostname.toLowerCase() === "github.com"
                ? `https://github.com${url.pathname}`
                : undefined;
        } catch {
            return undefined;
        }
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
    ): Promise<GitCommitPayload> {

        if (!this.repository) {
            throw new Error("Git repository is not available.");
        }

        const parent = parentCommit ?? `${commit}^`;

        const changes = await this.repository.diffBetween(parent, commit);
        const files: GitCommitFile[] = [];
        const deletedPaths: string[] = [];
        const renames: GitCommitPayload["renames"] = [];

        await Promise.all(changes.map(async change => {
            const filePath = this.toRepositoryPath(change.uri);
            const isDeleted = this.isDeletedStatus(change.status);

            if (isDeleted) {
                deletedPaths.push(filePath);
                return;
            }

            if (change.renameUri) {
                renames.push({
                    old_path: this.toRepositoryPath(change.originalUri),
                    new_path: this.toRepositoryPath(change.renameUri)
                });
            }

            const contents = await this.repository!.buffer(commit, filePath);

            files.push({
                status: this.toFileStatus(change.status),
                path: filePath,
                content: Buffer.from(contents).toString("utf-8"),
                encoding: "utf-8"
            });
        }));

        return {
            project_id: await this.getProjectId(),
            base_revision: parent,
            target_revision: commit,
            files,
            deleted_paths: deletedPaths,
            renames
        };
    }

    private toRepositoryPath(uri: vscode.Uri): string {
        return path.relative(this.repository!.rootUri.fsPath, uri.fsPath)
            .replace(/\\/g, "/");
    }

    private isDeletedStatus(status: number): boolean {
        // Git API Status: INDEX_DELETED, DELETED, DELETED_BY_US,
        // DELETED_BY_THEM, BOTH_DELETED
        return [2, 6, 14, 15, 17].includes(status);
    }

    private toFileStatus(status: number): GitCommitFile["status"] {
        // Git API Status: INDEX_ADDED, UNTRACKED, ADDED_BY_US,
        // ADDED_BY_THEM, BOTH_ADDED
        return [1, 7, 12, 13, 16].includes(status) ? "added" : "modified";
    }

    private async getProjectId(): Promise<string> {
        let remoteUrl: string;

        try {
            remoteUrl = await this.repository!.getConfig("remote.origin.url");
        } catch {
            return path.basename(this.repository!.rootUri.fsPath);
        }

        const normalizedUrl = remoteUrl.replace(/\.git$/, "");
        const sshMatch = normalizedUrl.match(/^[^@]+@[^:]+:(.+)$/);

        if (sshMatch) {
            return sshMatch[1];
        }

        try {
            const remotePath = new URL(normalizedUrl).pathname.replace(/^\//, "");
            return remotePath || path.basename(this.repository!.rootUri.fsPath);
        } catch {
            return path.basename(this.repository!.rootUri.fsPath);
        }
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
