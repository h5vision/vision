import * as vscode from "vscode";
import { ChatService } from "../services/chatServices";
import { APIService } from "../services/APIService";
import { getSessionId } from "../utils/session";
import { HistoryService } from "../services/historyService";

export class ChatHandler {

    constructor (
        private readonly historyServcie: HistoryService
    ) {}

    public handle: vscode.ChatRequestHandler = async (
        request,
        context,
        stream,
        token
    ) => {
        const backendService = new APIService();
        const chatService = new ChatService(backendService);
        const previousMessages = context.history.filter(h => h instanceof vscode.ChatRequestTurn);
        
        const modelList = {default:"backendai-default", nvidia:"nvidia-default", groq:"groq-default"};

        try {
            stream.progress("VisionAI가 답변을 생성하고 있습니다...");
            const session_id = getSessionId();

            const message = {
                project_id: "FastAPI",
                message: request.prompt,
                session_id: session_id,
                history: [],
                model_id: modelList.nvidia
            };
            // const history = {
            //     project_id: 'FastAPI',
            //     session_id: session_id,
            //     content: request.prompt,
            //     role: 'user'
            // };
            console.log(message);
            this.historyServcie.save('FastAPI', session_id, 'user', request.prompt);            
            const response = await chatService.sendMessage(message);
            console.log(response);

            stream.markdown(response.answer);
            this.historyServcie.save('FastAPI', session_id, 'assistant', response.answer);

        }
        catch (err) {

            stream.markdown("❌ Backend 연결에 실패했습니다.");

            console.error(err);

        }

    };

}