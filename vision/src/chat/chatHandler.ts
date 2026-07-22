import * as vscode from "vscode";
import { ChatService } from "../services/chatServices";
import { APIService } from "../services/APIService";
import { DatabaseService } from "../services/historyService";
import { getSessionId } from "../utils/session";

export class ChatHandler {

    public static async handle(

        request: vscode.ChatRequest,

        context: vscode.ChatContext,

        stream: vscode.ChatResponseStream,

        token: vscode.CancellationToken

    ) {
        const backendService = new APIService();
        const chatService = new ChatService(backendService);

        try {

            stream.progress("VisionAI가 답변을 생성하고 있습니다...");

            const message = {
                project_id: "FastAPI",
                message: request.prompt,
                session_id: getSessionId(),
                top_k: 3,
                history: []
            };
            
            console.log(message);
            const response = await chatService.sendMessage(message);
            console.log(response);

            stream.markdown(response.answer);

        }
        catch (err) {

            stream.markdown(
                "❌ Backend 연결에 실패했습니다."
            );

            console.error(err);

        }

    }

}