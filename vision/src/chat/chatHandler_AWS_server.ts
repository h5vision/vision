import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";
import { APIService } from "../services/APIService";
import * as session from "../utils/session";
import { PromptBuilder } from "./promptBuilder";
import { HistoryService } from "../services/historyService";

export class ChatHandler {

    constructor (
        private readonly historyServcie: HistoryService
    ) {}

    public handle: vscode.ChatRequestHandler = async (
        request : vscode.ChatRequest,
        context : vscode.ChatContext,
        stream : vscode.ChatResponseStream,
        token : vscode.CancellationToken
    ) => {
        const backendService = new APIService();

        const controller = new AbortController();
        const cancellation = token.onCancellationRequested(() => {
            controller.abort();
        });

        const project_id = vscode.workspace.getConfiguration("vision").get<string>("projectId") || vscode.workspace.name || 'none';
        let messages = PromptBuilder.build(request.prompt);

        // get all the previous participant messages
        const previousMessages = context.history.filter(
            h => h instanceof vscode.ChatResponseTurn
        );
        let session_id = session.getSessionId();
        
        if (!previousMessages) {
            session_id = session.resetSessionId();
        } 

        // add the previous messages to the messages 
        let responseHistory = [''];
        previousMessages.forEach(m => {
            let fullMessage = '';
            m.response.forEach(r => {
                const mdPart = r as vscode.ChatResponseMarkdownPart;
                if (mdPart.value.value !== 'NO_EVIDENCE') {fullMessage += mdPart.value.value;}
            });
            responseHistory.push(fullMessage);
        });
        messages += responseHistory.join('\n');

        // 에디터 화면에 열려 있는 파일의 텍스트 전체를 가져옵니다. 
        const editor = vscode.window.activeTextEditor;
        let file = '';
        if (editor) {
            file = fs.readFileSync(editor.document.uri.fsPath).toString();
            messages += file;
        }
        
        // 'vision:이 코드 설명해줘' 를 바탕으로 선택한 코드를 가져옵니다. 
        // 가져온 코드를 vscode Search기능으로 검색하고, 검색 결과를 searchFiles로 반환합니다. 
        const match = request.prompt.match(/```\n([\s\S]*?)\n```/);

        let searchFilesStr = '';
        if (!!match) {
            const searchFiles = await vscode.commands.executeCommand<vscode.SymbolInformation[]>(
                "vscode.executeWorkspaceSymbolProvider",
                match[1]
            );
            searchFilesStr = searchFiles.map(f => {return f.name;}).join('\t');
        } else {
            searchFilesStr = '';
        }
        messages += searchFilesStr;
        
        // 백엔드에서 어떤 모델을 사용해 질문할지를 결정합니다. 
        const modelId = vscode.workspace.getConfiguration("vision").get<string>("modelId");
        const commitId = vscode.workspace.getConfiguration("vision").get<string>("commitId");

        let rag = true;
        if (request.command === 'no-rag') {
            rag = false;
        }

        try {
            stream.progress("VisionAI가 답변을 생성하고 있습니다...");

            const message = {
                project_id: project_id,
                query: request.prompt,
                rag: rag
            };

            console.log(message);
            this.historyServcie.save(project_id, session_id, 'user', request.prompt);
            const response:any = await backendService.post("/v1/chat", message);
            if (response.error) {
                throw new Error(response.error.split(';')[0]);
            }

            console.log(response);
            
            stream.markdown(response.answer);

            for (let n = 1; n < response.reference_files.length+1; n++) {
                const source = response.reference_files[n-1];
                const sourceUri = this.getWorkspaceFileUri(source.path);

                if (!sourceUri) {
                    stream.markdown(`\n- \`${source.path}\``);
                    continue;
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
                    title: `${path.basename(source.path || '')}${source.line_start ? `:${source.line_start}-${source.lines[1]}` : ''}`,
                    arguments: openArguments
                });
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
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders?.length) {
            return undefined;
        }

        const filePath = path.isAbsolute(sourcePath)
            ? path.normalize(sourcePath)
            : path.resolve(workspaceFolders[0].uri.fsPath, sourcePath);
        const isInWorkspace = workspaceFolders.some(folder => {
            const relativePath = path.relative(folder.uri.fsPath, filePath);
            return relativePath === "" ||
                (!relativePath.startsWith(`..${path.sep}`) &&
                    relativePath !== ".." &&
                    !path.isAbsolute(relativePath));
        });

        return isInWorkspace ? vscode.Uri.file(filePath) : undefined;
    }

}
