import * as vscode from "vscode";
import * as fs from "fs";
import { ChatService } from "../services/chatServices";
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
        const chatService = new ChatService(backendService);

        const controller = new AbortController();
        const cancellation = token.onCancellationRequested(() => {
            controller.abort();
        });

        const project_id = vscode.workspace.name || 'none';
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
        const modelList = {default:"backendai-default", nvidia:"nvidia-default", groq:"groq-default"};

        try {
            stream.progress("VisionAI가 답변을 생성하고 있습니다...");

            const message = {
                project_id: "h5vision/fast-api",
                session_id: session_id,
                message: messages,
                context: '',
                history: []
            };

            console.log(message);
            this.historyServcie.save(project_id, session_id, 'user', request.prompt);            
            const response = await chatService.sendMessage(message);
            
            // response 객체 확인용
            // const dbPath = path.join(vscode.workspace.workspaceFolders?.[0].uri.fsPath || '', 'response.json');
            // fs.writeFileSync(dbPath, JSON.stringify(response, null, 2));

            for await (const fragment of response.answer) {
                stream.markdown(fragment);
            }
            console.log(response.source);
            this.historyServcie.save('FastAPI', session_id, 'assistant', response.answer);

        }
        catch (err) {
            if (token.isCancellationRequested) {
                stream.progress("요청 취소됨");
                return;
            }
            stream.markdown("❌ Backend 연결에 실패했습니다.");
            console.error(err);
        } finally {
            cancellation.dispose();
        }

    };

}