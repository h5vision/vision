import * as vscode from "vscode";
import { ChatService } from "../services/chatServices";
import { APIService } from "../services/APIService";

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

            stream.progress("Vision가 답변을 생성하고 있습니다...");

            const response = await chatService.sendMessage({
                prompt: request.prompt
            });

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