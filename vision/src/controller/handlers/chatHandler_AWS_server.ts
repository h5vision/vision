import * as vscode from "vscode";
import * as path from "path";
import { APIService } from "../../services/APIService";
import * as session from "../../utils/session";
import { ChatStreamEventName } from "../../types/chat";
import { HistoryService } from "../../services/historyService";
import { ChatService } from "../../services/chatServices_SSE";
import { WorkspaceService } from "../../services/workspaceService";
import { DependencyGraphProvider } from "../../providers/dependencyGraphProvider";

export class ChatHandler {

    constructor (
        private readonly historyServcie: HistoryService,
        private readonly dependencyGraphProvider?: DependencyGraphProvider,
    ) {}

    private readonly workspaceService = new WorkspaceService();
    private readonly workspace = this.workspaceService.getWorkspace();

    public handle: vscode.ChatRequestHandler = async (
        request : vscode.ChatRequest,
        context : vscode.ChatContext,
        stream : vscode.ChatResponseStream,
        token : vscode.CancellationToken
    ) => {
        const backendService = new APIService();
        const chatService = new ChatService(backendService);
        const controller = new AbortController();
        const cancellation = token.onCancellationRequested(() => {
            controller.abort();
        });
        const isStream = vscode.workspace.getConfiguration("vision").get<boolean>("streaming", false);
        const model_id = vscode.workspace.getConfiguration("vision").get<string>("modelId");

        let finalAnswer = "";
        let collectedDelta = "";
        let lastEvent = "";
        const dummyLabels: Record<ChatStreamEventName, string> = {
            meta: "RAG 검색 완료",
            stage: `${model_id?.split(':')[0]} 답변 생성 중`,
            delta: "답변 전송 중",
            done: `ollama의 ${model_id?.split(':')[0]}에 의해 생성된 답변`,
            error: "답변 실패"
        };

        const project_id = vscode.workspace.getConfiguration("vision").get<string>("projectId") || this.workspace?.name || 'none';

        // get all the previous participant messages
        const previousMessages = context.history.filter(
            h => h instanceof vscode.ChatResponseTurn
        );
        let session_id = session.getSessionId();
        
        if (!previousMessages) {
            session_id = session.resetSessionId();
        } 
        
        // // 추후 snapshot 기능을 위해 commitId를 가져옵니다. 
        // const commitId = vscode.workspace.getConfiguration("vision").get<string>("commitId");

        let rag = true;
        if (request.command === 'no-rag') {
            rag = false;
        }

        const payload = {
            project_id: project_id,
            message: request.prompt,
            rag: rag, 
            stream: true,
            model_id: model_id
        };
        this.historyServcie.save(
            project_id,
            session_id,
            'user',
            request.prompt
        );
        let response: any;
        console.log("Payload:", payload);

        try {
            await chatService.sendMessage(
                payload,
                (event: ChatStreamEventName, data) => {
                    if (event !== lastEvent) {
                        if (rag || event !== "meta") {
                            stream.progress(dummyLabels[event]);
                        }
                        lastEvent = event;
                    }
                    if (event === "meta") {
                        console.log("[meta]", data);
                        return;
                    }
                    if (event === "stage") {
                        console.log("[stage]", data);
                        return;
                    }
                    if (event === "delta") {
                        collectedDelta += data.text ?? '';
                        if (isStream) {stream.markdown(data.text ?? '');}
                        return;
                    }
                    if (event === "done") {
                        finalAnswer = data.answer ?? collectedDelta;
                        if (!isStream) {stream.markdown(finalAnswer);}
                        response = data;
                        return;
                    }
                    if (event === "error") {
                        throw new Error(
                            data.error ??
                            "답변 생성에 실패했습니다."
                        );
                    }
                },
                controller.signal
            );
        
            console.log(response);
            const highlightedPaths: string[] = [];
            for (const source of response.reference_files) {
                const sourceUri = this.getWorkspaceFileUri(source.path);

                if (!sourceUri) {
                    stream.markdown(`\n- \`${source.path}\``);
                    continue;
                }

                const relativePath = this.getWorkspaceRelativePath(sourceUri);
                if (relativePath) {
                    highlightedPaths.push(relativePath);
                }

                const lineStart = Number(source.line);
                const openArguments =
                    Number.isInteger(lineStart) && lineStart > 0
                        ? [
                            sourceUri,
                            {
                                selection: new vscode.Range(
                                    lineStart - 1,
                                    0,
                                    lineStart - 1,
                                    0
                                )
                            }
                        ]
                        : [sourceUri];
                stream.button({
                    command: "vscode.open",
                    title: `${path.basename(source.path)} ${source.line_start ? `:${source.line_start}-${source.lines[1]}` : ''}`,
                    arguments: openArguments
                });
            }
            if (highlightedPaths.length) {
                this.dependencyGraphProvider?.highlightSources(highlightedPaths);
            }
            this.historyServcie.save(project_id, session_id, 'assistant', response.answer);
        }
        catch (err) {
            if (token.isCancellationRequested) {
                stream.progress("요청 취소됨");
                return;
            }
            stream.markdown("❌ " + err?.toString());
        } finally {
            cancellation.dispose();
        }
    };

    private getWorkspaceFileUri(sourcePath: string): vscode.Uri | undefined {
        if (!this.workspace) {
            return undefined;
        }
        const filePath = path.isAbsolute(sourcePath)
            ? path.normalize(sourcePath)
            : path.resolve(this.workspace.path, sourcePath);
        const isInWorkspace = this.workspace ? (() => {
            const relativePath = path.relative(this.workspace.path, filePath);
            return relativePath === "" ||
                (!relativePath.startsWith(`..${path.sep}`) &&
                    relativePath !== ".." &&
                    !path.isAbsolute(relativePath));
        })() : false;

        return isInWorkspace ? vscode.Uri.file(filePath) : undefined;
    }

    // 그래프 노드의 path(워크스페이스 상대 posix 경로)와 매칭시키기 위한 변환
    private getWorkspaceRelativePath(fileUri: vscode.Uri): string | undefined {
        if (!this.workspace) {
            return undefined;
        }

        const relativePath = path.relative(this.workspace.path, fileUri.fsPath);
        return relativePath.split(path.sep).join('/');
    }

}
