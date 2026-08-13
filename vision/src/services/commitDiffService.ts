import * as vscode from "vscode";
import { GitService } from "./gitService";
import { APIService } from "./APIService";

// 커밋이 발생하면 해당 커밋의 diff를 backend 서버로 전송합니다.
export class CommitDiffService implements vscode.Disposable {

    private readonly apiService = new APIService();
    private listener?: vscode.Disposable;

    constructor(
        private readonly gitService: GitService
    ) {}

    public start(): void {

        this.listener = this.gitService.onDidCommit(
            event => void this.handleCommit(event.commit, event.previousCommit)
        );
    }

    private async handleCommit(
        commit: string,
        previousCommit: string
    ): Promise<void> {

        try {
            const payload = await this.gitService.getCommitDiff(commit, previousCommit);
            console.log("Commit diff payload:", payload);

            await this.apiService.post("/workspace-overlays", payload);
        } catch (error) {
            console.log("Failed to send commit diff to backend:", error);
        }
    }

    public dispose(): void {
        this.listener?.dispose();
    }
}
