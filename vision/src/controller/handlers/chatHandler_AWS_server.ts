import * as vscode from "vscode";
import * as path from "path";
import { APIService } from "../../services/APIService";
import * as session from "../../utils/session";
import { ChatStreamEventName, ChatStreamData, SourceDocument, ReferenceDocument } from "../../types/chat";
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
        if (request.command === 'ragonly') {
            vscode.commands.executeCommand('vision.showDependencyGraph');
        }

        let finalAnswer = "";
        let collectedDelta = "";
        let lastEvent = "";
        const eventLabels: Record<ChatStreamEventName, string> = {
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
        const highlightedPaths: string[] = [];

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
                (event: ChatStreamEventName, data : ChatStreamData) => {
                    if (event !== lastEvent) {
                        if (rag || event !== "meta") {
                            stream.progress(eventLabels[event]);
                        }
                        lastEvent = event;
                    }
                    if (event === "meta") {
                        console.log("[meta]", data);
                        if (request.command === "ragonly") {
                            if (!data.references || data.references.length === 0) {
                                stream.markdown("참조 파일이 없습니다.");
                            } else {
                                const referenceFiles : Array<ReferenceDocument> = data.references;
                                this.referenceFilesHandle(referenceFiles, highlightedPaths, stream);
                            }
                            controller.abort("RAG only mode");
                        }
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
                        this.referenceFilesHandle(response.references, highlightedPaths, stream);
                        return;
                    }
                    if (event === "error") {
                        throw new Error(
                            data.message ??
                            "답변 생성에 실패했습니다."
                        );
                    }
                },
                controller.signal
            );
        
            console.log(response);
            
            this.historyServcie.save(project_id, session_id, 'assistant', response.answer);
        }
        catch (err) {
            if (token.isCancellationRequested) {
                stream.progress("요청 취소됨");
                return;
            }
            stream.markdown("  " + err?.toString());
        } finally {
            cancellation.dispose();
        }
    };

    private referenceFilesHandle (
        references: Array<ReferenceDocument>,
        highlightedPaths: string[],
        stream: any
    ): void {
        if (references.length > 0) {
            stream.markdown("Reference Files:\n");
        } else {return;}
        
        for (const source of references) {
            const sourceUri = this.getWorkspaceFileUri(source.path);

            if (!sourceUri) {
                console.log(`\n- \`${source.path}\``);
                continue;
            }

            const relativePath = this.getWorkspaceRelativePath(sourceUri);
            if (relativePath) {
                highlightedPaths.push(relativePath);
            }

            const lineStart = source.line_start;
            const lineEnd = source.line_end;
            const anchorTarget =
                Number.isInteger(lineStart) && lineStart > 0
                    ? new vscode.Location(
                        sourceUri,
                        new vscode.Range(lineStart - 1, 0, lineStart - 1, 0)
                    )
                    : sourceUri;
            stream.anchor(
                anchorTarget,
                `[${source.n}] ${path.basename(source.path)}:${lineStart === lineEnd ? lineStart : lineStart + '-' + lineEnd}`
            );
        }
        if (highlightedPaths.length) {
            this.dependencyGraphProvider?.highlightSources(highlightedPaths);
        }
    }

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
        if (!this.workspace) {return undefined;}
        const relativePath = path.relative(this.workspace.path, fileUri.fsPath);
        return relativePath.split(path.sep).join('/');
    }

}
